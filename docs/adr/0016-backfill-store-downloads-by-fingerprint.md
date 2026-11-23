# 0016: Backfill — Attach Store Downloads by Fingerprint, Swap In When Better

The homelab library predates stored originals (ADR-0014), so Undo Import
can't work for those albums. The originals still exist: the iTunes and
Amazon purchases can be downloaded again. **Backfill** matches downloads
in the inbox to library tracks and attaches them, without re-importing.

Re-importing was rejected: every album becomes a duplicate to "Replace",
which deletes the album and loses its `navidrome_library`, manual edits,
art choice and added date; a re-match to another release changes the
track's Navidrome ID along with its path, which drops play history
(spike: `.scratch/navidrome-safe-lifecycle/issues/01`).

## Decision

Per inbox audio file (`backfill.py`), never using titles or tags (store
tags differ from MusicBrainz tags, down to curly vs straight apostrophes):

1. **Identical audio** (same audio-region SHA-256 as a library track):
   save the download as the track's original. The library file is not
   touched.
2. **Same recording** (no identical match; a library track within 3 s
   whose Chromaprint fingerprint agrees ≥ 0.85 over the first two
   minutes): compare quality (lossless > lossy, then bit depth/sample
   rate, or bitrate with a ±10% "equal" band).
   - Download better **or equal**: **swap in**. The library's tags are
     written onto a copy of the download, the old file's embedded art is
     copied over, and it replaces the library file (same folder and name;
     the extension follows the format). The old file is copied to
     `<config>/webimport-replaced/<time>/` first and never deleted by
     webimport. Equal swaps too: then the library holds exactly the
     purchase and Undo Import rebuilds it byte for byte (otherwise each
     original would have to be stored whole, ~600 MB on the homelab).
   - Download worse: leave both; the download stays in the inbox.
3. **No match**: stays in the inbox for a normal import.

A library track is claimed by one download (identical first, then
quality, then similarity); the others are marked duplicates. A track
that already has a saved original is left alone. When all the audio under
a folder went to one album, the folder's other files go with it (as on
import); mixed folders keep theirs. Used downloads are deleted and their
folders pruned.

The Inbox tab runs it as a background job: **Check inbox against
library** (scan, with progress), then **Attach to library…** per folder or
**Attach all**, each showing every track's decision first. Applying
re-checks the folder under the Apply Lock. Audio checksums and
fingerprints are cached by path, size and mtime
(`<config>/webimport/backfill-cache.sqlite`); the first scan reads the
whole library once.

## Consequences

- Navidrome keeps history on a swap: the track's tags (hence its
  persistent ID) don't change, and the path changes at most in its
  extension, i.e. a path-only change (spike result).
- Loudness values (ReplayGain, iTunes Sound Check) come from the new file
  and are stored in the DB; the old `acoustid_fingerprint` is dropped.
  `acoustid_id` stays (same recording).
- Measured on the homelab inbox (768 files): 515 identical, ~70 equal
  quality (iTunes AAC 256 re-encodes), ~48 better (library OGG 112 →
  Amazon MP3 ~256), ~130 new. Same-recording pairs scored ≥ 0.90,
  different recordings far below.
- Without `fpcalc`, only identical audio matches.

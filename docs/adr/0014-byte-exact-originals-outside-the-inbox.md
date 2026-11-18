# 0014: Byte-Exact Originals Kept Outside the Inbox

When a review opens (before beets writes anything), webimport keeps each
inbox file's non-audio bytes — tags, embedded art, padding, container
structure — in `<library dir>/webimport-originals/<sha256>/`, and records
the original's SHA-256 on the item (`original_file`). beets only rewrites
tag areas, never audio, so the original is rebuilt exactly by putting those
bytes back around the imported file's audio (Ogg: original page numbers
restored and page checksums recomputed). A rebuild is used only if its
SHA-256 matches the original. Formats without a splitter are kept whole.
After each import, webimport checks the rebuild works; if not and the inbox
original still exists, it keeps that file whole instead.

This made the inbox copy redundant; ADR-0015 switches to `move: yes`.

## Consequences

- Verified byte-identical on real iTunes M4A and Amazon MP3 files after
  import with new tags and new embedded art, and in tests for MP3 (ID3v2.3
  + v1), M4A (index before and after the audio), FLAC, Ogg Vorbis, Opus.
- Storage is the non-audio part only: ~90 KB for an Amazon MP3, ~575 KB
  for an iTunes M4A (its index and purchase data), versus a full copy.
- The store holds private purchase tags (Apple ID) as the original file
  did; they're never shown in the UI.
- Originals from reviews that never imported are pruned at server start.

## Undo import from the library (step two)

The library album modal's **Undo import** (`restore.py`) puts every file
back at its original inbox path, byte-identical, with its original mtime
and permissions, then removes the album (`remove(delete=True)` by ID), the
inbox marker, and the stored originals. It is all-or-nothing: a dry run
lists anything that blocks an exact restore (no stored original, a
different file already at the destination, a destination outside the
inbox), and every file is rebuilt and SHA-256-checked into a temp file
before anything is moved or removed. A destination already holding the
identical file (copy mode) is left alone, so it works before and after the
switch to `move: yes`.

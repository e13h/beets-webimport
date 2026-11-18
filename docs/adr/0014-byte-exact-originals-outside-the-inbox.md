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

This is step one toward `move: yes` (no inbox staging, undo restores from
the library): it makes the inbox copy redundant. ADR-0001 and ADR-0012
still hold until undo-by-restore exists and move mode is switched on.

## Consequences

- Verified byte-identical on real iTunes M4A and Amazon MP3 files after
  import with new tags and new embedded art, and in tests for MP3 (ID3v2.3
  + v1), M4A (index before and after the audio), FLAC, Ogg Vorbis, Opus.
- Storage is the non-audio part only: ~90 KB for an Amazon MP3, ~575 KB
  for an iTunes M4A (its index and purchase data), versus a full copy.
- The store holds private purchase tags (Apple ID) as the original file
  did; they're never shown in the UI.
- Originals from reviews that never imported are pruned at server start.

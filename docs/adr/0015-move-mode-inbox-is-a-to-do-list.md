# 0015: Move Mode — the Inbox Is a To-Do List

beets runs with `move: yes`. An import moves the album's audio into the
library; webimport keeps what's needed to put the folder back exactly
(ADR-0014: each file's non-audio bytes; the folder's other files whole),
then removes the folder's other files and prunes it. The inbox only holds
what's still to import. **Undo Import** on the library album puts every
file back byte-identical and removes the album. There is no Approve tab,
no Confirm Import, no Grace Period, and imports no longer write the
`.webimport_imported` marker.

While an import runs, each audio file has a safety copy in
`<inbox>/.webimport-safety/`: a hard link (free; beets' move across the
container's separate `/downloads` and `/music` mounts is copy-then-delete,
leaving the linked inode untouched), or a real copy when a probe link into
the library succeeds (same mount: beets renames and rewrites in place).
It's deleted once the import is checked; if the post-import check can't
rebuild a file, the safety copy is stored whole instead. At startup,
leftovers from finished imports are deleted; one whose original is gone
and isn't in the library (interrupted import) is moved to
`<inbox>/_recovered/`.

Supersedes ADR-0001 (copy mode), ADR-0012 (Approve tab lifecycle) and the
marker-writing part of ADR-0010.

## Consequences

- No second copy of the library sits in the inbox: storage is the
  non-audio bytes only (ADR-0014).
- Folders imported in copy mode keep their marker and files: at startup
  their originals are saved from those files, and the Inbox shows them as
  Imported with **Remove inbox copy**, which removes the folder only after
  checking every file can be rebuilt exactly.
- On the homelab the inbox and library are separate bind mounts of one
  disk, so each move is a copy then delete (one file at a time, original
  deleted only after the copy is in place). Not instant, but no slower
  than copy mode was.
- Singleton imports have no album to undo; Undo Import covers albums.
- Dev: imports move the repo's `.inbox/` files, so `scripts/dev-reset.sh`
  recreates `.inbox` from a saved initial state (`.inbox-pristine/`)
  rather than relying on Undo Import.

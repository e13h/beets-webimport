# 0011: Two-Phase Metadata Edits (metadata first, move on confirmation)

Navidrome tracks files by stable path while remapping its own PIDs after a
metadata-only change; an operation that changes metadata *and* renames files
in one atomic step (the old Move-on-Field-Change rule: `store()` + `move()`
in one op) loses that remap, breaking playlists and play counts. Therefore
**every** library operation that changes a file's computed path — field
edits, bulk edits, and Library-tab reimport applies — is two-phase: phase 1
writes metadata only, keeping files at their old paths; phase 2 (the move)
runs only after explicit user confirmation that Navidrome has picked up the
metadata change (manual per-album/bulk confirm for MVP; Navidrome API
integration is backlog). If the edit does not change the computed path, no
phasing occurs. Import-tab applies are trivially single-phase: those files
never existed in Navidrome.

## Consequences

- **Pending Move** state is detected, not persisted: an item's actual
  `path` vs. its computed template path mismatch means "move owed."
  Detected at startup and on demand, so ADR-0004 (no persistence across
  restart) still holds.
- Pending moves are advisory, not locks: any later move-producing operation
  supersedes a pending one; undo (which deletes the library item) blows it
  away. Confirm/cancel are the only other resolutions.
- Supersedes the Move-on-Field-Change rule in CONTEXT.md; the
  `set_album_fields`/`set_item_fields` store+move implementation in
  `library.py` must be split.
- **Prerequisite**: a spike must verify the Navidrome remap premise
  (currently docs-based, untested). If falsified, this ADR is unnecessary
  and single-phase edits should be restored.
- Rejected: automatic delayed move (config option later, maybe), and
  Navidrome-API-verified confirmation (real integration, backlog).

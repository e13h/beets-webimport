# 03 — Two-phase metadata edits (Pending Move)

Status: needs-triage
Type: task
Blocked by: 01

Implement ADR-0011. If the spike falsifies the Navidrome premise, resolve
this ticket as wontfix and restore single-phase behavior.

Scope:
- Split `store()` + `move()` in `set_album_fields`/`set_item_fields`
  (`beetsplug/webimport/library.py`): phase 1 writes metadata only; the
  move is withheld into a Pending Move state when the computed path
  differs from the actual path.
- Same phasing for Library-tab reimport applies (ADR-0005 path) — write
  metadata, defer move.
- No phasing when computed path is unchanged; Import-tab applies stay
  single-phase.
- Pending Move detection: actual `path` vs computed template path
  mismatch, computed on demand and at startup (no persisted state).
- Supersede rule: any later move-producing operation replaces a pending
  move; deleting the item (undo) clears it.
- API + UI: badge on affected albums in Library tab, inline confirm/cancel,
  bulk "confirm all". Confirm runs the actual move.

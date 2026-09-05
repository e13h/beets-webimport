# 04 — Approve tab & inbox-original lifecycle

Status: needs-triage
Type: task
Blocked by: 02

Implement ADR-0012.

Scope:
- Rename Undo tab → **Approve**; contents = all inbox folders bearing
  `.webimport_imported`, displayed as "imported N days ago" from
  `imported_at`. Remove them from the Import tab listing (marker presence
  = Approve-only).
- Actions per folder: **Undo import** (remove marked `album_id` from
  library with delete, remove marker → folder returns to Import tab) and
  **Confirm import and delete inbox files** (rmtree inbox originals +
  marker).
- Remove the reimport button from this tab entirely; redo flow is
  undo → Import tab. Update ADR-0010-era UI assumptions in playbooks.
- Grace Period: destructive auto-delete of inbox originals at expiry,
  default **30 days**, config option to disable (manual confirm only).
  Applies to Staging Bins too (same lifecycle). Expiry action = the
  Confirm action.
- Grace-period expiry currently only prunes records (`grace.py`); extend
  `_prune_expired` to delete originals + marker.
- Under `move: yes`: hide Approve tab and undo affordances (import-only
  GUI); no move-mode support otherwise.

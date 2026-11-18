# 03 — Two-phase metadata edits (Pending Move)

Status: resolved
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

## Comments

2026-11-17: implemented with a change of approach agreed with the user:
confirmation is **automatic**. webimport watches Navidrome's
`getScanStatus` instead of waiting for a manual confirm, and only moves
that follow a *tag write* are phased (see the ADR-0011 rewrite, and spike
01 for the evidence).

- `navidrome.py`: Subsonic client (token auth, `getScanStatus`,
  best-effort `startScan`).
- `pendingmove.py`: `Mover`. It moves at once when nothing was written,
  otherwise it holds the move until a scan that started after the write
  has finished. Background poll every 2s. Startup discovery lists
  mismatches but never auto-moves them.
- `library.py`: field edits now **write tags** when a real tag field
  changes (previously only `store()` + `move()`; the web UI only edits
  `navidrome_library`, so this affected API callers only), then go through
  the Mover.
- `reimport.py` / `session.py`: the reimport session holds files
  (`hold_files`: private config overlay with move/copy off), then hands the
  albums, found again by path, to the Mover.
- API: `GET /api/library/pending_moves`,
  `POST /api/library/pending_moves/<kind>/<id>/move`. Albums carry a
  `pending_move` flag/detail.
- UI: "Waiting for Navidrome" tile badge (auto-refreshes), album-detail
  banner with "Move now" (with a warning), save toasts that say when files
  will move.
- Config: `webimport.navidrome.{url,user,password,scan_request_after}`,
  with the password from `WEBIMPORT_NAVIDROME_PASSWORD`.
- Tests: `tests/test_pendingmove.py` (including "a scan already running at
  the write doesn't count", which was checked against a deliberately
  broken version of the rule) and `tests/test_navidrome_client.py`.
- End to end, real plugin + Navidrome 0.64.2 + the Mulan m4a purchase
  (`repro/e2e_webimport.py on|off`): reimporting from the 2020 digital
  release to the 1998 CD release lost history on **8/8** rows with the
  integration off and **0/8** with it on (playlist 8/8). The group move
  `unassigned`→`kids` lost 0/8, and the rows moved into the `kids` library.
- Dev caveat: Docker Desktop on macOS drops some file events into the
  container (renames inside an existing folder), so Navidrome's watcher
  missed them. The e2e script starts the scan itself after 15s. Not
  expected on a Linux host.

Follow-ups: 05 (group roots pruned away), 06 (edits outside webimport).
Homelab rollout: add `webimport.navidrome.url/user` to the beets config
(selfhosted repo + `.config/homelab.yaml`) and
`WEBIMPORT_NAVIDROME_PASSWORD` to the beets container's environment.

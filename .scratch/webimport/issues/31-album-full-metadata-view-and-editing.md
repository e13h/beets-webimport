# 31: Full album metadata view and editing

**What to build:** Expand the album detail view beyond `albumartist`, `album`, and `navidrome_library` to display and allow editing of full album metadata (year, genre, original_year, label, catalog number, MBID, album type) and flexible custom fields, per User Stories 35, 36, and 38.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Album detail modal displays all standard album metadata fields (year, original_year, genre, label, catalognum, mb_albumid, albumtype) returned in `fields` from `GET /api/library/albums/<album_id>`.
- [ ] Supports editing standard metadata fields and saving changes via `POST /api/library/albums/<album_id>/fields`.
- [ ] Supports adding and editing arbitrary extensible custom fields (flexible attributes) on the album.
- [ ] Automatically triggers file relocation if any edited field affects the path template (Move-on-Field-Change, per Story 40).
- [ ] Re-renders album details or refreshes the library view upon successful save.

## Comments

**2026-11-17 — viewing half done.** The read-only metadata explorer
(see 30) now displays every album field, flexible attributes included,
and marks fields where tracks differ ("varies") or where file tags differ
from the DB. Remaining scope: **editing**, built into the explorer's
field rows. Path-affecting edits must follow ADR-0011 (Two-Phase Edit,
navidrome-safe-lifecycle ticket 03), which supersedes the
Move-on-Field-Change criterion above.


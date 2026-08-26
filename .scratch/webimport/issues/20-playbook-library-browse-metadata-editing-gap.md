# 20: Playbook — measure Library Browse & Metadata Editing coverage gap

**What to build:** Create Playbook 20 covering the Library Browse and
Metadata Editing user stories (Stories 32–42) end-to-end: search by
artist/album, album view with track list, track view, metadata edit
per-track and whole-album, bulk-edit, Move-on-Field-Change verification,
type-aware inputs, and extensible custom fields.

Measure the coverage gap between the current implementation and the
PRD's expectations for this domain, logging any missing functionality as
new child tickets.

**Blocked by:** 01 (playbook conventions)

**Status:** done

- [x] Playbook created under `docs/playbooks/20-library-browse-metadata-editing-gap.md` following the conventions documented in #01.
- [x] Exercises search by artist and album with ~800-album scale in mind.
- [x] Exercises album view showing full album metadata + track list.
- [x] Exercises track view showing full metadata for an individual track.
- [x] Exercises per-track metadata edit and whole-album metadata edit.
- [x] Exercises bulk-edit across multiple selected albums.
- [x] Verifies Move-on-Field-Change on edits that change computed paths.
- [x] Assesses and logs coverage gaps for type-aware inputs (date picker, chips) and extensible custom fields as new issues.

## Gap report

Walkthrough of Stories 32–42 from `.scratch/webimport/spec.md`:

- **Story 32 (Browse & text search):** **Pass**. Verified via `loadLibrary()` and `#lib-search` debounce. Search syntax is passed directly to `lib.albums(q)`. Empty states are handled cleanly with query interpolation (ticket #29).
- **Story 33 (Art thumbnails resized/cached 200x200):** **Partial**. Cover art is served directly from `album.artpath` via `GET /api/library/albums/<id>/art`, but server-side thumbnail resizing/caching is not yet implemented. Logged in **#17**.
- **Story 34 (Embedded art fallback when `artpath` is null):** **Missing**. `GET /api/library/albums/<id>/art` immediately 404s if `album.artpath` is null without extracting embedded art. Logged in **#17**.
- **Story 35 (Full album metadata view + track list, and track view):** **Partial**. The album modal displays `albumartist`, `album`, and track listing, but omits full album fields (year, genre, label, MBID). Track rows in the track list lack click handlers to view individual track metadata (`GET /api/library/items/<id>` is present on the backend but unused in the UI). Logged in **#30** (track detail modal) and **#31** (full album metadata view).
- **Story 36 (Edit metadata per-track and whole-album):** **Partial**. Album modal only permits editing `navidrome_library`. Per-track metadata editing UI is completely absent despite `POST /api/library/items/<id>/fields` backend availability. Logged in **#31** (album fields) and **#32** (per-track editing UI).
- **Story 37 (Type-aware inputs):** **Missing**. All inputs are currently plain un-typed text fields. Date pickers, multi-value chip inputs (e.g. for `genres`/`mood`), and type-specific controls are missing. Logged in **#33**.
- **Story 38 (Extensible custom fields):** **Partial**. Backend flexible attributes support arbitrary fields, but the UI has no controls to add or edit arbitrary custom attributes on albums or tracks. Logged in **#31** and **#32**.
- **Story 39 (Bulk edit across multiple albums):** **Partial**. Album multi-selection checkboxes and bulk action bar exist, but bulk edit only prompts for `navidrome_library` via `promptSetLibrary`. Arbitrary field selection for bulk updates is not available in the UI. Logged in **#34**.
- **Story 40 (Move-on-Field-Change):** **Pass**. Backend `set_album_fields()` and `set_item_fields()` evaluate `_paths_would_change()` and trigger `obj.move()`, automatically relocating files on disk according to beets path templates.
- **Story 41 (`%aunique{}` disambiguation on Move-on-Field-Change):** **Pass**. Beets natively handles same-named album disambiguation during `move()`.
- **Story 42 (Single-user concurrency model):** **Pass**. Single-user operation confirmed per ADR-0006.

### Follow-up Tickets Created

- **#30:** Track detail modal & full track metadata view (Story 35)
- **#31:** Full album metadata view and editing (Stories 35, 36, 38)
- **#32:** Per-track metadata editing UI (Story 36)
- **#33:** Type-aware metadata inputs (date picker, multi-value chip inputs) (Story 37)
- **#34:** Bulk edit arbitrary fields across selected albums (Story 39)

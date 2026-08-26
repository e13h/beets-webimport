# 32: Per-track metadata editing UI

**What to build:** Provide a UI for editing individual track metadata fields (title, artist, track, disc, custom fields) from the Track Detail view, calling `POST /api/library/items/<item_id>/fields` and supporting Move-on-Field-Change, per User Story 36.

**Blocked by:** 30 (track detail modal)

**Status:** ready-for-agent

- [ ] Track detail modal provides editable form inputs for track metadata (title, artist, artist_sort, track, disc, custom attributes).
- [ ] Submits edited fields to `POST /api/library/items/<item_id>/fields` with `move: true`.
- [ ] Automatically triggers file relocation if an edited field (such as title or track number) alters the track's destination path per configured path templates (Story 40).
- [ ] Provides save feedback and updates parent album track list and details upon saving.

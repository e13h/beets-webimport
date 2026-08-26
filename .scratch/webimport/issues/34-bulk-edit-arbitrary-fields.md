# 34: Bulk edit arbitrary fields across selected albums

**What to build:** Expand the library bulk-edit bar (`#bulk-bar`) to allow selecting arbitrary target fields (such as `genre`, `year`, `label`, or custom flexible attributes) rather than exclusively hardcoding `navidrome_library` prompt input, per User Story 39.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `#bulk-bar` includes a field selector dropdown populated with common standard fields (`navidrome_library`, `genre`, `year`, `label`, etc.) and an option for custom field entry.
- [ ] Provides an input for entering the new field value corresponding to the selected field.
- [ ] Submits `{ album_ids: [...], field: "<field>", value: "<value>", move: true }` to `POST /api/library/albums/bulk_fields`.
- [ ] Triggers Move-on-Field-Change across all updated albums if the edited field affects path templates (Story 40).
- [ ] Displays toast feedback summarizing the count of updated albums and refreshes the album grid.

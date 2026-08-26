# 21: Playbook — measure Custom Tags (Tag Vocabulary) coverage gap

**What to build:** A Playwright playbook (per the convention from ticket
01) that walks through every user story in `.scratch/webimport/spec.md`'s
"Custom tags (Navidrome integration)" section (stories 43–46) against the
real running server and disposable library. Ticket 11 already covers
`tags.py`'s backend write-down logic at the pytest layer, but no
playbook exercises the actual drag-and-drop (or touch-equivalent) UI flow
described in these stories. This ticket's deliverable is the playbook
itself (kept as ongoing regression coverage) plus a written gap report.
For every story found not implemented, or implemented but not matching
the spec, file a new follow-up ticket (standard local ticket template,
numbered sequentially after the highest existing ticket, `Blocked by:
None` unless a genuine dependency exists) — do not fix anything in this
ticket, only measure and file.

**Blocked by:** 01

**Status:** ready-for-agent

- [x] Playbook exercises, against the real UI: the GUI-managed Tag Vocabulary (starting with `mood`, multi-valued) maintained ahead of use (story 43); applying a tag to an individual track and to a whole album via drag-and-drop or its touch equivalent (44); confirming an album-level tag write actually lands on every track file, not just the album (45, cross-check against ticket 11's pytest coverage of the same requirement at the data layer).
- [x] Story 46 (new tag *value* works immediately vs. new tag *name* needing a `navidrome.toml` edit + rescan) is recorded as a manual, expected, out-of-plugin-control step per the spec — verify only that the plugin doesn't block or mis-handle applying a brand-new tag value; no ticket needed for the `navidrome.toml`/rescan step itself.
- [x] Each story is recorded in the playbook or an accompanying gap report as one of: **pass**, **partial** (note how it diverges), or **missing**.
- [x] Every **partial** or **missing** story produces its own follow-up ticket, filed under `.scratch/webimport/issues/`, written from the user's perspective, citing the spec's user-story number it closes.
- [x] This ticket's file is updated with a "## Gap report" section listing each story's outcome and the follow-up ticket number filed for it (if any).
- [x] The playbook is retained under the location/convention from ticket 01 as standing regression coverage for this area, not a throwaway script.

## Gap report

| User Story | Summary | Status | Follow-up Ticket | Details |
|---|---|---|---|---|
| **43** | Reusable, GUI-managed Tag Vocabulary maintained ahead of use | **Partial** | **#36** | Values can be appended to pre-configured fields like `mood`, but the UI lacks controls to create new tag fields or delete existing vocabulary values/fields. |
| **44** | Apply tag to track or album via drag-and-drop or touch equivalent | **Partial** | **#35** | HTML5 drag-and-drop is unbuilt. Fallback touch equivalent relies on typing raw database IDs into `window.prompt()`. |
| **45** | Album-level tag writes down to all track files (`beet write`) | **Pass** | — | Fully implemented in `tags.apply_tag_to_album` via `item.try_write()`, covered by pytest in `tests/test_tags.py`. |
| **46** | New tag value works immediately; new tag name requires `navidrome.toml` edit | **Pass** | — | Dynamic tag values apply immediately. Navidrome configuration and rescan boundary is documented as an expected manual step outside plugin control. |

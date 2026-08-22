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

- [ ] Playbook exercises, against the real UI: the GUI-managed Tag Vocabulary (starting with `mood`, multi-valued) maintained ahead of use (story 43); applying a tag to an individual track and to a whole album via drag-and-drop or its touch equivalent (44); confirming an album-level tag write actually lands on every track file, not just the album (45, cross-check against ticket 11's pytest coverage of the same requirement at the data layer).
- [ ] Story 46 (new tag *value* works immediately vs. new tag *name* needing a `navidrome.toml` edit + rescan) is recorded as a manual, expected, out-of-plugin-control step per the spec — verify only that the plugin doesn't block or mis-handle applying a brand-new tag value; no ticket needed for the `navidrome.toml`/rescan step itself.
- [ ] Each story is recorded in the playbook or an accompanying gap report as one of: **pass**, **partial** (note how it diverges), or **missing**.
- [ ] Every **partial** or **missing** story produces its own follow-up ticket, filed under `.scratch/webimport/issues/`, written from the user's perspective, citing the spec's user-story number it closes.
- [ ] This ticket's file is updated with a "## Gap report" section listing each story's outcome and the follow-up ticket number filed for it (if any).
- [ ] The playbook is retained under the location/convention from ticket 01 as standing regression coverage for this area, not a throwaway script.

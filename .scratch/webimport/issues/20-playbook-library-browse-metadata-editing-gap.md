# 20: Playbook — measure Library Browse & Metadata Editing coverage gap

**What to build:** A Playwright playbook (per the convention from ticket
01) that walks through every user story in `.scratch/webimport/spec.md`'s
"Library browse & metadata editing" section (stories 32–42) against the
real running server and disposable library, since none of these stories
currently have playbook or pytest coverage. This ticket's deliverable is
two things: the playbook itself (kept as ongoing regression coverage), and
a written gap report. For every story found not implemented, or
implemented but not matching the spec, file a new follow-up ticket
(using the standard local ticket template, numbered sequentially after
the highest existing ticket, `Blocked by: None` unless a genuine
dependency exists) describing exactly what's missing or wrong — do not
fix anything in this ticket, only measure and file.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Playbook exercises, against the real UI: artist/album browse with text search (story 32); art thumbnails sourced from `artpath` with embedded-art fallback when null (33, 34); album view (metadata + track list) and track view (35); per-track and per-album metadata editing including custom fields (36); type-aware inputs (date picker, multi-value chip input) vs. plain-text fallback (37); registering a new custom field name without a code change (38); multi-select bulk edit across several albums (39); Move-on-Field-Change triggering on a path-affecting edit (40); `%aunique{}` handling an ordinary same-named-album collision (41).
- [ ] Each story is recorded in the playbook or an accompanying gap report as one of: **pass** (matches spec), **partial** (implemented but diverges — note how), or **missing** (not implemented at all).
- [ ] Story 42 (no concurrency/conflict handling needed) is recorded as accepted-as-is, not a gap — no ticket needed for it regardless of outcome.
- [ ] Every **partial** or **missing** story produces its own follow-up ticket, filed under `.scratch/webimport/issues/`, written from the user's perspective per the ticket template, citing the spec's user-story number it closes.
- [ ] This ticket's file is updated with a "## Gap report" section listing each story's outcome and the follow-up ticket number filed for it (if any).
- [ ] The playbook is retained under the location/convention from ticket 01 as standing regression coverage for this area, not a throwaway script.

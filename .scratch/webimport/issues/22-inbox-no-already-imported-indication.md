# 22: Inbox shows no indication a folder was already imported, allowing silent duplicate albums

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity:
Critical. Reporter-suggested category: bug.

## What was observed

`/api/inbox` (`beetsplug/webimport/server.py`, `api_inbox_list`) lists
every subdirectory of `inbox_dir` with no cross-reference to library or
Grace Period/undo state. Because this repo runs `copy: yes` (source files
legitimately remain in the inbox after a successful import — see
`CONTEXT.md`'s Grace Period entry), an already-imported folder still shows
an active "Start import" button with nothing distinguishing it from a
never-imported one.

Re-clicking "Start import" on an already-imported folder re-runs full
review from scratch. In testing, choosing "Use as-is" on the second pass
produced a **second, differently-tagged album** ("Lea Salonga – Mulan...")
alongside the first, correctly MusicBrainz-resolved one
("Jerry Goldsmith, Matthew Wilder & David Zippel – Mulan"), because
`duplicate_action: ask` / `get_duplicate_action` keys off albumartist and
the raw file tags didn't match the already-resolved album in the library
closely enough to trigger the duplicate-decision prompt at all.

## Why it matters

This is a real, silent data-integrity gap, not just a cosmetic one: a
second click can leave two albums in the library representing the same
physical files, with no prompt or warning at any point. It also
potentially touches the **Placement Conflict** concept already in
`CONTEXT.md` (the umbrella for "two things want the same library slot") —
worth deciding during triage/grilling whether re-importing an
already-imported folder should route through that same decision shape, or
needs its own resolution.

## Evidence

- `.playwright-mcp/05-after-select-apply.png` — the "Start import" button
  still active on the just-imported folder, immediately after the first
  successful apply.
- `.playwright-mcp/page-2026-08-21T04-46-18-047Z.yml` (lines 12-19) — both
  the correct album and the duplicate "Lea Salonga" album present as
  separate library entries. No PNG was captured at this exact moment; this
  YAML snapshot is the primary evidence.

## Reproduction

1. Reset the disposable library (see `docs/agents/dev-environment.md`),
   start the server, import the Mulan test album fully (start import →
   force target MBID `a5483fb3-634b-4254-a966-de33cefd1f17` via search-by-ID
   → select → apply).
2. Return to the Inbox tab. The same folder is still listed with an active
   "Start import" button.
3. Click "Start import" again, click "Review", click "Use as-is" (skip the
   MBID override this time).
4. Check the Library tab: two albums now exist for the same underlying
   files.

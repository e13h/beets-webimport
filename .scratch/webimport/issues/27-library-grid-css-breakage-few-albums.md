# 27: Library grid tile CSS breaks visually while art is loading/missing, especially with few albums

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: Medium.
Reporter-suggested category: bug.

## What was observed

In `static/style.css`, the `.grid`/`.album-tile` rules use
`grid-template-columns: repeat(auto-fill, minmax(140px, 1fr))`, which lets
a single tile stretch to fill the row when there are only 1-2 albums.
Combined with `aspect-ratio: 1` on the `<img>`, a tile whose art hasn't
loaded yet (or is missing) blows up to near-full-viewport height, because
the `onerror` handler only sets `visibility: hidden` — which still reserves
the full aspect-ratio box rather than collapsing it.

This is specifically a broken/loading-state bug, not a steady-state grid
layout problem: once art finishes loading, the same tile renders correctly
sized (see the "after" evidence below).

## Evidence

- `.playwright-mcp/06-library-after-import.png` — the oversized, near-empty
  tile while art had not yet loaded.
- `.playwright-mcp/console-2026-08-21T04-30-01-152Z.log` — matching 404 on
  `/api/library/albums/1/art` for that broken image request.
- `.playwright-mcp/console-2026-08-21T04-40-14-184Z.log` — a second
  occurrence of the same failure mode, album id 2 (the duplicate album from
  finding #22).
- `.playwright-mcp/08-library-fullpage.png` — the same tile, correctly
  sized, once art finished loading — confirms the bug is scoped to the
  loading/error state, not the grid layout generally.

**Not part of this finding:** `.playwright-mcp/console-2026-08-21T04-22-38-816Z.log`
(a 500 on `/api/library/albums?q=`) is a stale-DB-connection artifact from
wiping `.config/library.db` out from under a running server during this
session (an artifact of the testing setup, not a product bug) — don't
triage it as one.

## Reproduction

1. Import a single album into an otherwise-empty or near-empty library.
2. View the Library tab immediately, before art has finished
   loading/embedding.
3. Observe the oversized tile; compare against a reload once art has
   loaded, which renders correctly.

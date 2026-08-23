# 28: Modals have no visible close button and no Escape key handler

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: Low.
Reporter-suggested category: bug.

## What was observed

Modals (`openModal()` in `static/app.js`) dismiss on backdrop-click, but
have no visible × button and no `Escape` key handler.

## Evidence

- `.playwright-mcp/09-album-detail.png` — the album detail modal, with no
  close affordance other than clicking the backdrop.

## Reproduction

1. Open any modal (e.g. an album detail view).
2. Note there is no × button; pressing `Escape` does not close it.

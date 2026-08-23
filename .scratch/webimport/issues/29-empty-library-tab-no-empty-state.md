# 29: Empty Library tab has no empty state (unlike Undo tab)

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: Low.
Reporter-suggested category: enhancement.

## What was observed

An empty Library tab shows nothing but the heading and search box — no
message. The Undo tab, by contrast, already has a proper empty state
("Nothing pending undo."). The Library tab should match that pattern.

## Evidence

- `.playwright-mcp/page-2026-08-21T04-30-09-874Z.yml` — empty Library tab,
  just heading and search box, no content/message.
- `.playwright-mcp/page-2026-08-21T04-30-19-783Z.yml` and
  `.playwright-mcp/07-undo-tab.png` — the Undo tab's existing "Nothing
  pending undo." empty state, for comparison.

## Reproduction

1. View the Library tab with an empty (freshly reset) disposable library.
2. Compare against the Undo tab's empty state under the same conditions.

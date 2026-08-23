# 25: "Awaiting candidate review" has no in-progress indicator during lookup

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: Medium.
Reporter-suggested category: bug.

## What was observed

After clicking "Start import," the resulting "Awaiting candidate review"
state has no spinner or other animation while the MusicBrainz/chroma
lookup is in progress. It reads as frozen rather than actively working.

## Why it matters

Minor on its own, but compounds with finding #23 (no apply feedback) to
make the whole review flow feel unresponsive/uncertain about what state
it's in.

## Evidence

- `.playwright-mcp/01-after-start-import.png` — the static "Awaiting
  candidate review" state, immediately after clicking "Start import."

## Reproduction

1. Click "Start import" on any inbox folder.
2. Observe the "Awaiting candidate review" state while the lookup runs —
   no visual indication of progress.

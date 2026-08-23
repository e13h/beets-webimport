# 26: No double-submit protection — same inbox path listed under both Inbox and Pending Review at once

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: Medium.
Reporter-suggested category: bug.

## What was observed

After clicking "Start import" on a folder, that same folder appears
simultaneously under both the "Inbox" section (with its own enabled
"Start import" button) and the "Pending review" section. Nothing prevents
clicking "Start import" a second time on the same folder while its first
review is still in flight.

## Why it matters

A second "Start import" for the same folder likely creates a second,
independent Import Task (see `CONTEXT.md`'s Import Task/Import Session
entries) for files already mid-review — worth confirming during triage
whether this can itself lead to a duplicate-album outcome similar to
finding #22, or a confusing pair of review queues for the same files.

## Evidence

- `.playwright-mcp/01-after-start-import.png` — the Mulan folder visible
  under both "Inbox" (enabled "Start import" button) and "Pending review"
  simultaneously.

## Reproduction

1. Click "Start import" on any inbox folder.
2. Without waiting for review to complete, check both the "Inbox" and
   "Pending review" sections — the same folder/path appears in both, and
   the Inbox's "Start import" button for it remains clickable.

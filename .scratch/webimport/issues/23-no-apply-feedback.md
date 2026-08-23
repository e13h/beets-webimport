# 23: No success/failure feedback when applying a review decision

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: High.
Reporter-suggested category: bug.

## What was observed

Submitting a review decision (forcing an MBID via search-by-ID, or the
final "Select" to apply) closes the review modal instantly, but the real
import work — copy, tag write, art fetch/embed, and the `album_imported`
event that registers the Grace Period/undo record (see
`docs/agents/dev-environment.md`'s "Timing/race facts" section) — keeps
running in the background for several seconds afterward. The UI gives no
indication that anything is still in progress, or that it succeeded/failed,
once the modal closes.

## Why it matters

The user has no way to tell "it's still working" from "it's done" from
"it silently failed," short of manually flipping to the Library or Undo
tab and checking whether the album has appeared yet.

## Evidence

- `.playwright-mcp/03-after-use-id.png` — modal gone immediately after
  submitting the forced MBID.
- `.playwright-mcp/05-after-select-apply.png` — modal gone immediately
  after submitting the final "Select," no toast/spinner/success message.

## Reproduction

1. Start an import review for any inbox album.
2. Submit an MBID override or a final "Select" to apply.
3. Observe: the modal closes immediately; the Library/Undo tabs don't yet
   reflect the result for several seconds afterward, with no in-UI signal
   that work is still happening.

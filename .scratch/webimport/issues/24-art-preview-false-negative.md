# 24: Candidate review's cover-art preview shows a false "unavailable" error that doesn't retry

Status: needs-triage

**Source:** UX walkthrough session (Playwright MCP, browser-driven, per
ADR-0009), reported via `HANDOFF.md`. Reporter-suggested severity: High.
Reporter-suggested category: bug.

## What was observed

The candidate review view showed "art service unavailable — try again" as
static text (not an actual retry button/action) for the correct Mulan
candidate. Moments later, the same album's art rendered correctly in the
Library grid after a full page reload — the underlying fetch had actually
succeeded shortly after the error was shown.

Per `docs/agents/dev-environment.md`'s "fetchart specifics" section,
CAA/archive.org return transient 502s regularly, and the backend fetchart
path (`coverart.py`) already retries and reports an `unavailable` flag
rather than treating a transient failure as fatal. This finding suggests
the review-preview endpoint (which computes **Resolved Art** — see
`CONTEXT.md`) either doesn't share that retry logic, or the frontend
doesn't poll/re-request it the way it should.

## Why it matters

This is a false negative in exactly the feature (dual cover-art preview,
Source Art vs. Resolved Art match/mismatch) the spec calls out as a
first-class differentiator from beets-flask. A user acting on "art
unavailable" as if it were permanent could make a worse decision (e.g.
drag in manual art unnecessarily) than if the transient nature were
surfaced.

## Evidence

- `.playwright-mcp/04-mulan-candidate.png` — "art service unavailable — try
  again" shown on the correct Mulan candidate card.
- `.playwright-mcp/06-library-after-import.png` — broken/missing-art render
  in the Library grid moments later, same album.
- `.playwright-mcp/08-library-fullpage.png` — full page reload shortly
  after shows the real embedded Mulan cover art rendering correctly,
  confirming the failure was transient.

## Reproduction

1. Start an import review, force the target MBID
   (`a5483fb3-634b-4254-a966-de33cefd1f17`) via search-by-ID.
2. Observe the candidate card's Resolved Art slot — it will sometimes show
   the "unavailable" message on first render.
3. Apply the import anyway, then reload the Library tab shortly after: the
   real art is present, proving the initial message was a transient false
   negative.

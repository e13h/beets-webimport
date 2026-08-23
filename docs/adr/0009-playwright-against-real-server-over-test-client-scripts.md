# Playwright against a real running server, over in-process `test_client()` scripts

End-to-end verification drives a real, running `beet webimport` server
through a real browser via the Playwright MCP tools, exercising the actual
frontend (`static/app.js`) and HTTP layer exactly as a human user would —
rather than a Python script acting as the browser via Flask's
`test_client()` and calling `/api/*` routes directly in-process.

The earlier in-process `test_client()` scripts were the original seam
and did real, valuable work (see their results folded into ADRs 0001–0006),
but they bypass the browser entirely: they can't catch frontend bugs,
can't exercise drag-and-drop/long-press interactions, and verify the API
rather than the product. Driving the real server through a real browser
closes that gap and matches how the single user actually interacts with
the plugin.

## Consequences

- The in-process `test_client()` driver scripts have been removed in
  favor of markdown **playbooks** (`docs/playbooks/`) — step-by-step
  Playwright MCP procedures an agent follows against a live `beet webimport`
  server — covering the same scenarios (inbox import, grace-period undo,
  parallel review + duplicates, cover-art preview) plus the previously-
  untested reimport and manual-grouping flows.
- This is slower per run (real server startup, real browser, real network
  calls to MusicBrainz/CAA) than an in-process `test_client()` call, and
  requires a disposable library/server to be running rather than being
  callable as a one-off script — an accepted trade-off for realism.
- Any future fast/CI-friendly regression suite (e.g. pytest against
  `test_client()`) is a separate, lower-fidelity layer that could be added
  back later without contradicting this decision — it would sit alongside
  Playwright playbooks, not replace them.

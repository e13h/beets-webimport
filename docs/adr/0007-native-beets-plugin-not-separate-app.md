# Native beets plugin, not a separate app shelling out to the CLI

The web UI is implemented as a native beets plugin (`beets.plugins.BeetsPlugin`)
that hooks `ImportSession` and plugin events directly in-process, rather than
a standalone app that shells out to the `beet` CLI per request.

This directly targets the reason beets-flask was being replaced: per-view
re-computation with no session/candidate reuse, confirmed by direct SQLite
inspection of its own db, and a measured ~60s beets-flask cost against ~9s
for a raw `beet import -t` on the same album, with no caching benefit on
repeat views. Hooking the importer directly means one in-process
`ImportSession`/`ImportTask` per review, not a fresh CLI invocation (and
re-parsed candidate search) per interaction.

## Consequences

- The plugin must track import/review state itself (see Import
  Session/Import Task in `CONTEXT.md`, and ADR-0004 on why that state is
  intentionally not persisted across restarts) rather than treating each
  request as independently reproducible via a fresh CLI call.
- Existing beets plugins (chroma, musicbrainz, fetchart, embedart, etc.)
  keep working unmodified, since the importer pipeline itself is
  unmodified — only the review-decision hooks (`choose_match`/
  `choose_item`/`get_duplicate_action`) are overridden.

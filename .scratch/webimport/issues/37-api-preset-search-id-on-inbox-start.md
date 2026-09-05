# 37: API — accept a pre-specified search ID on inbox import start

**What to build:** A user who already knows which release an inbox
folder should match can supply that identifier at import-start time, so
the import session's first candidate lookup is a single targeted lookup
against that ID (Direct ID Import) instead of the broad tag/acoustic
search that takes seconds. The endpoint stays backwards compatible with
the existing paths-only body. A lookup that returns no candidates (bad
ID, 404, network failure) must not silently fall back to a heuristic
match or kill the session: it registers a review task with zero
candidates so the UI can surface the failure for correction.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [x] The inbox import-start endpoint accepts a form that pairs each
      path with an optional raw search-ID string, alongside the existing
      paths-only form which continues to work unchanged.
- [x] The supplied ID is passed through to the import session so the
      first candidate lookup is targeted at that ID (reusing the
      session's existing preset-ID machinery, not a new session type).
- [x] The ID is accepted as a raw string pass-through — bare UUID,
      MusicBrainz release URL, Discogs release URL — anything the
      matching backend can parse; no client-side URL parsing.
- [x] A targeted lookup yielding zero candidates registers a review task
      with an empty candidate list (with the attempted ID visible in the
      payload) rather than aborting the session or falling back to
      normal search.
- [x] Verifiable without the UI: driving the endpoint directly with a
      known-good test MBID produces a single-candidate review task, and
      a bogus ID produces an empty-candidate review task.

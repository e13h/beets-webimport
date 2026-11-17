# 42: Candidate art preview re-fetches Cover Art Archive on every click

**Status:** resolved

**Problem:** Every click on a candidate called `/api/coverart/resolve`,
which queried the Cover Art Archive live with no caching: 3.2–4.5s per
click, every time. Source art and resolved art also requested the same
release twice per click.

**Fix (2026-11-17):** `coverart._caa_front_images` caches definitive CAA
answers (art list, or 404 = no art) in memory per `(kind, mbid)` for an
hour. "Couldn't reach CAA" is not cached, so it retries on the next click.
The cache lasts for the process lifetime only, like other plugin state
(ADR-0004).

Measured: first click 2.4s (one lookup instead of two), repeat clicks
~0s. Tests: `tests/test_coverart_cache.py`.

## Comments

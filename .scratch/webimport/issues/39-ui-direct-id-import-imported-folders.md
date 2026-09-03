# 39: UI — Direct ID Import on already-imported folders via the reimport flow

**What to build:** An inbox folder card carrying the already-imported
badge (marker-file detection, ADR-0010) offers the same inline
"Import with ID…" input as fresh folders, but submitting it routes
through the Reimport flow against the existing library record —
direct-firing the reimport endpoint with just the supplied ID
(from-scratch off, no set-fields overrides) rather than starting a
fresh path-driven session over the inbox files. This deliberately
avoids the silent-duplicate trap of re-running a fresh import over an
already-imported folder (ticket 22). The targeted candidate still goes
through the normal review-modal approval. Users who want from-scratch
or a Listening Group override use the existing full Re-import modal,
which remains unchanged on those cards.

**Blocked by:** 38 (UI — Direct ID Import toggle on fresh inbox folders
with retry on failed lookup — reuses the same card toggle pattern)

**Status:** ready-for-agent

- [ ] Already-imported inbox folder cards show the same inline
      "Import with ID…" toggle as fresh cards; fresh-card behavior is
      unchanged.
- [ ] Submitting on an imported card fires the reimport endpoint with
      the supplied ID only (from-scratch off, no set_fields) — the
      query-driven reimport path against the library record, not a
      fresh import of the inbox files.
- [ ] The reimport's targeted candidate appears in the normal review
      modal for approval before apply; from-scratch is not offered
      there (it remains exclusive to the full Re-import modal).
- [ ] If the library album ID is unavailable from the marker data, the
      submission fails with a clear toast rather than falling back to a
      fresh import.
- [ ] Verification against the disposable test setup: import Mulan,
      then Direct-ID-import the same folder with the same MBID — no
      duplicate album is created (no duplicate-decision prompt needed),
      and the review step shows the expected release.

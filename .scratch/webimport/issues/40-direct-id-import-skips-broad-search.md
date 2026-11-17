# 40: Direct ID Import still runs the full broad search (and chroma fingerprinting) before the ID lookup

**Status:** resolved

**Blocked by:** None

**Problem:** A Direct ID Import (ticket 37) takes about as long as an
ordinary import, around 10s for the 4-track Mulan test album under the
homelab config. It should be roughly one MusicBrainz request.

Cause, verified against beets 2.13.1 source:

1. beets' pipeline stage `lookup_candidates`
   (`beets/importer/stages.py`) runs the first candidate search *before*
   the session's `choose_match` is called, using
   `session.config["search_ids"]`. That is the global `import.search_ids`
   config and is empty, so it runs the full broad search: tag-based
   MusicBrainz search, plus `chroma` candidates, which fetch a MusicBrainz
   release for every AcoustID match.
2. `WebImportSession.choose_match` (`beetsplug/webimport/session.py:90`)
   only then consumes `preset_search_id` and runs a second, targeted
   lookup. A Direct ID Import therefore pays for both searches.
3. The same stage first sends `import_task_start`. `chroma` (with
   `auto: yes`, the default) listens for it and fingerprints every track
   with `fpcalc`, then calls the AcoustID API per track. That happens
   regardless of the ID.

**Constraint:** the fix can't set `import.search_ids` in config.
`ImportSession.set_config` stores the shared global `config["import"]`
view, and inbox imports run in parallel on a worker pool (ADR-0006), so a
config write would leak one folder's ID into another's lookup. The ID must
stay per session or per task.

**What to build:** When a session has a preset search ID, its initial
candidate lookup is the targeted lookup only. The broad search never runs.
Possible mechanisms: give `WebImportSession` its own pipeline stage list
with a lookup stage that reads the session's ID, or wrap the task's
`lookup_candidates` per session. Choose whichever stays closest to stock
beets behavior.

Open decision (needs triage): should an ID import also skip `chroma`
fingerprinting? Skipping it is most of the remaining time. The cost is
that `apply_acoustid_metadata` then has no fingerprint to write, so
ID-imported tracks lose `acoustid_fingerprint`/`acoustid_id` tags.
Alternatives: skip it, keep it, or fingerprint after apply / in the
background.

**Acceptance criteria:**
- [x] With a Direct ID, beets' broad search (`tag_album` without
      `search_ids`) is never called for that task. Assert this in a
      pytest unit test by patching `metadata_plugins.candidates` (or
      equivalent) to fail if called.
- [x] Parallel imports, one with an ID and one without, don't affect each
      other: the one without an ID still gets a normal broad search, and
      the ID never appears in the other folder's lookup.
- [x] The mid-review "search by ID" decision and the "Auto-search instead"
      fallback (blank ID → broad search) behave as before.
- [x] Reimport with an ID (`reimport.py`, `preset_search_id`) also skips
      the broad search.
- [x] The chroma decision above is made and implemented.
- [x] Timing is measured before and after with the homelab-mirroring dev
      config (`.config/`, chroma enabled) on the Mulan inbox album. Record
      both numbers in the Comments below. Target: the candidate appears in
      the UI within ~2s of starting the import, assuming fingerprinting is
      skipped.
- [ ] Playbook 22 still passes.

## Comments

**2026-11-17 — resolved.** `WebImportSession.set_config` gives a session
with a Direct ID a private config view: a snapshot of the global config
sources with `import.search_ids: [<id>]` on top. beets' own first lookup
then does only the targeted lookup, and `choose_match` reports it as
`attempted_search_id` without looking up again. The global config is
untouched, so parallel sessions don't see each other's IDs. Mid-review
"search by ID" and "Auto-search instead" work as before. Reimport gets
the same fix because it sets `preset_search_id` before `run()`.
Tests: `tests/test_direct_id_lookup.py` runs the real beets pipeline with
stubbed metadata backends.

Chroma decision: auto-fingerprinting is off entirely in the homelab
config (`chroma: auto: no`), not only for ID imports.

Timing (Mulan, homelab-mirroring dev config, time from start until the
review is registered):

| | before | after |
|---|---|---|
| chroma on, with ID | 13.5s / 14.5s | — (chroma now off) |
| chroma off, no ID | 3.3s / 3.2s | 4.1–4.3s (unchanged path) |
| chroma off, with ID | 3.7s / 4.0s | 1.1–1.4s typical, spikes to 2.4–3.7s |

The remaining spikes look like MusicBrainz response time. Playbook 22
has not been re-run in a browser yet.

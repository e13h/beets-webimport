Status: ready-for-agent

# beets-webimport: Web UI for Import Review, Library Browsing, and Multi-Library Routing

Contains decisions made while sharpening the domain model into
`CONTEXT.md` and `docs/adr/`. Uses that glossary's vocabulary throughout;
where this spec's requirements touch a recorded ADR, the ADR is cited
rather than re-justified.

## Problem Statement

Evan self-hosts a music library (Navidrome + beets + Maloja + ARM/abcde)
and currently reviews/imports new rips through `beets-flask`. That tool
is too slow to use comfortably — each view recomputes from scratch with no
session/candidate reuse (confirmed via direct SQLite inspection of its own
db), taking ~60s per album against beets' own ~9s for the same
`beet import -t` — and it doesn't work with the `chroma` plugin he relies
on for fingerprint matching. He needs a faster, mobile-friendly way to:
review and apply new imports; undo mistakes without risk to source files;
browse and edit his ~800-album library; assign custom tags and per-album
"listening group" routing so Navidrome serves the right libraries to the
right audiences (kids, worship, holiday, etc.); and occasionally redo an
album's metadata from scratch — all without needing a phone/laptop to run
CLI commands, and without adding login/auth friction on a network he
already trusts (Tailscale).

## Solution

A native beets plugin (`beetsplug/webimport/`, see ADR-0007) that hooks
`beets.importer.ImportSession` and beets' plugin events directly, in-
process, and serves its own responsive web UI (touch-friendly on mobile)
for the entire workflow: inbox review with parallel candidate search and
serial apply, dual cover-art preview, grace-period undo, reimport, library
browse/search/edit, custom tag assignment, and Listening Group routing.
No app-level authentication — Tailscale is the trust boundary (ADR-0008).
Existing beets plugins (chroma, musicbrainz, fetchart, embedart, etc.)
work unmodified since only the review-decision hooks are overridden.

## User Stories

### Import flow

1. As the user, I want to drag an album directory into an inbox and have it picked up automatically, so that ripped/burned albums (from ARM or a manual drop) flow into review without a CLI step.
2. As the user, I want the importer to tolerate files being renamed or moved mid-process, so that a slow rip or an ARM naming quirk doesn't crash the review.
3. As the user, I want candidate matches sourced from beets' real matching pipeline (including chroma, musicbrainz, spotify, etc.), so that I get the same match quality as the CLI.
4. As the user, I want to browse and reorder candidates for one album independently of every other album currently under review, so that reviewing several albums doesn't force me to finish one before starting the next.
5. As the user, I want candidate search for multiple albums to happen in parallel (bounded by a worker pool), so that waiting on one album's search doesn't block starting another's.
6. As the user, I want the actual database write / file copy step ("apply") to happen one Import Task at a time even when several albums are under review at once, so that concurrent applies can never race each other into a corrupted or colliding destination path (see ADR-0006 — Apply Lock).
7. As the user, I do not need apply order to match review-completion order — any order is fine as long as applies never overlap (ADR-0006).
8. As the user, I want to paste a MusicBrainz ID or URL directly to preview and accept a specific release, bypassing search entirely, so that I can fix a bad auto-match fast.
9. As the user, I want to drag individual files from the inbox into ad-hoc Staging Bins to split one rip (e.g. a burned playlist CD) into the several real albums/singles it actually contains, so that a multi-album rip doesn't get imported as one wrong album.
10. As the user, I want each Staging Bin, once populated, to go through an ordinary beets import (directory-based grouping) rather than a special in-memory code path, so that split imports are just as canonical/reliable as unsplit ones (ADR-0003).
11. As the user, I want a Staging Bin to survive past its import through the Grace Period rather than being deleted immediately, so that if I undo the import I don't have to redo the tedious splitting work.
12. As the user, I want Staging Bins to be cleared from the inbox automatically once their Grace Period expires, so that the inbox doesn't accumulate stale directories forever.
13. As the user, I want to drag a custom image file onto an album directory in the inbox before import, so that fetchart/embedart picks it up as the preferred art source over any remote lookup.
14. As the user, I want suspected duplicates (per beets' `duplicate_action: ask`) surfaced as an explicit decision in the GUI rather than resolved silently, so that I always know when something might already be in my library.
15. As the user, I want the duplicate decision to offer the same options beets' CLI does — skip new, merge all, remove old, keep all — so that the GUI doesn't invent a different, incompatible decision model (the real hook is `get_duplicate_action`, not `resolve_duplicate` — see `CONTEXT.md`; the PRD's original "keep existing / replace / keep both / merge" wording should not be treated as authoritative).
16. As the user, I want no persistence of in-flight review state across a plugin restart, so that the implementation can stay simple — losing review progress and re-triggering candidate search on restart is an acceptable, explicit trade-off (ADR-0004), because inbox originals are never at risk.

### Dual cover-art preview

17. As the user, I want to see the Source Art (the image tied to my selected candidate) next to the Resolved Art (what fetchart/embedart will actually write, computed via fetchart's real resolution logic — not a reimplementation), so that I can catch cases where the embedded art won't match what I expect.
18. As the user, I want a clear match/mismatch indicator between the two thumbnails, so that I don't have to eyeball-compare them for identical results.
19. As the user, I want Resolved Art computed only for the currently-highlighted candidate (refreshing as I move focus), not upfront for the whole list, so that the candidate list stays fast to load.
20. As the user, I want a "No Cover Art Available" placeholder — not a copy of Resolved Art — shown in the Source Art slot when the selected candidate has no associated image, so that "no source image" and "source matches resolved" are never visually confused.

### Undo / Grace Period

21. As the user, I want a configurable Grace Period (default ~10 minutes) after any import (or reimport) apply during which I can undo it, so that I have a safety net against bad matches without needing a full "are you sure" confirmation up front.
22. As the user, I want undo to be exactly `remove(delete=True)` on the specific `Album`/`Item` DB IDs captured from the real `album_imported`/`item_imported` events for that import — never a re-derived query — so that undo can never accidentally remove an unrelated library item (ADR-0001).
23. As the user, I want the Grace Period timer to be tracked server-side as wall-clock time regardless of whether my browser is currently connected, so that closing a tab doesn't reset or extend my undo window.
24. As the user, I'm fine with losing track of in-progress Grace Periods if the plugin server itself restarts, so that this doesn't need to be built as a persisted/durable feature right now (ADR-0004) — it's accepted as a low-priority future enhancement.
25. As the user, because copy mode leaves inbox originals untouched, I want undo to require no separate "restore the original" step — the inbox file is simply available for review again immediately.

### Post-import: Reimport

26. As the user, I want to select one or more albums from the library view and trigger a reimport that reassigns metadata, as the GUI equivalent of `beet import -L -S <mbid> --from-scratch --set field=value`.
27. As the user, I want to optionally restrict reimport matching to a specific MusicBrainz ID, or otherwise run a normal search via the existing matching plugins.
28. As the user, I want a `--from-scratch` toggle that erases existing metadata before applying new metadata, shown bold/highlighted when checked (no modal confirmation needed) so its destructive nature is visually obvious without adding a click-through step.
29. As the user, I want to set/restore fields (e.g. `navidrome_library`) that `--from-scratch` would otherwise wipe, via the same `--set field=value` mechanism the CLI exposes.
30. As the user, I want a diff view of the new candidate's resulting metadata (old → new) so I can see the effect of `--from-scratch` and `--set` together without a separate "erased fields" pass.
31. As the user, I want reimport to go through the exact same Grace-Period-undo mechanism as a fresh import, so I don't have to learn two different undo models.

### Library browse & metadata editing

32. As the user, I want to browse my library by artist or album, with text search as a first-class way to find something in ~800 albums, so that I'm not stuck scrolling.
33. As the user, I want album art thumbnails sourced from beets' `artpath` field (not `art_path` — see `CONTEXT.md` field-name note) and resized/cached (e.g. 200x200) for grid display, so that browsing stays fast without per-file I/O on every view.
34. As the user, I want art extracted from the file's embedded tags only as a fallback when `artpath` is null, so that albums without a cached art file still show something.
35. As the user, I want an album view showing full album metadata plus its track list, and a track view showing full metadata for an individual track when selected.
36. As the user, I want to edit metadata per-track or across an entire album, including custom fields, so that fixes don't require dropping to the CLI.
37. As the user, I want type-aware inputs (date picker, multi-value chip input for fields like `genres`) where it makes sense, falling back to a plain text box for complex/unusual fields.
38. As the user, I want custom fields to be extensible — not hardcoded to just `navidrome_library`/`mood` — so the plugin can register new field names as my needs change over time.
39. As the user, I want to multi-select across several albums and apply one field change (e.g. set `navidrome_library=kids`) to all of them in a single bulk-edit action.
40. As the user, I want any metadata edit — single field, single track/album, or bulk — that changes an item's computed path to automatically trigger a Move-on-Field-Change, so that files never get stranded out of sync with their own path template (`copy: yes`/`move: no` is the default config, so this is the mechanism that makes edits actually take effect on disk).
41. As the user, I want beets' own `%aunique{}` disambiguation to keep handling ordinary same-named-album collisions during Move-on-Field-Change, as sufficient for MVP.
42. As the user, I do not need any concurrency/conflict handling for simultaneous library view/edit, since I'm the only user of this system.

### Custom tags (Navidrome integration)

43. As the user, I want a reusable, GUI-managed Tag Vocabulary (starting with `mood`, multi-valued) that I maintain ahead of time, so tag names/values stay consistent rather than accumulating typos.
44. As the user, I want to apply a tag to individual tracks or a whole album via drag-and-drop (or its touch equivalent), so tagging is fast during a browsing session.
45. As the user, I want an album-level tag assignment to write down to every track file (`beet write`), so Navidrome's song-level smart-playlist filtering actually picks it up (album-only writes would be invisible to per-song filters).
46. As the user, I understand that a new tag *value* (e.g. a new `mood`) works immediately, but a new tag *name* requires editing `navidrome.toml`'s `Tags.<Name>.Aliases` and running a full Navidrome rescan — an accepted, expected-to-be-rare manual step.

### Multi-library routing (Listening Group)

47. As the user, I want to assign a Listening Group (kids / worship / holiday / talk radio / regular / any new value I type) to an album at import time or via a later metadata edit, so it routes to the right Navidrome library root.
48. As the user, I want Listening Group values to be genuinely free-form — not a fixed, pre-keyed enum — so a brand-new category doesn't require a code or config change (ADR-0002).
49. As the user, I want autocomplete suggestions for Listening Group drawn live from the distinct values already present in my library, so I don't accidentally create near-duplicate groups (`kids` vs `Kids` vs `kidz`) by typo, while still being able to type any value freely, including a brand-new one not yet in use.
50. As the user, I want anything imported without an explicit Listening Group choice to default to `unassigned` (via `import.set_fields.navidrome_library: unassigned`) rather than failing or blocking the import.
51. As the user, I want the library browse view to surface "unassigned" as a clearly filterable state, so I can periodically find and triage everything still sitting there.
52. As the user, I want changing an album's Listening Group — at any time, not just at import — to automatically relocate its files via Move-on-Field-Change, so the field and the file's actual location can never drift apart.
53. As the user, I understand that registering a new top-level folder (e.g. `/music/kids`) as a Navidrome library root is a manual, one-time step I perform in Navidrome's own settings — the plugin does not automate this.

## Implementation Decisions

- **Plugin shape**: native `beets.plugins.BeetsPlugin` subclass registering a `beet webimport` subcommand and a Flask app served in-process — not a CLI-wrapping separate service (ADR-0007). Frontend is vanilla JS/HTML under `beetsplug/webimport/static/` with no build step (intentional simplification, see Further Notes).
- **Import Session / Import Task model**: one `WebImportSession` (subclass of `ImportSession`) per inbox submission, run in a bounded `InboxWorkerPool` for parallel candidate search across submissions. `choose_match`/`choose_item`/`get_duplicate_action` block the calling worker thread on a per-Import-Task decision queue (`ReviewManager`) until the web UI POSTs a decision to `/api/review/<task_id>/decide`. `task_id` identifies an Import Task (beets' `ImportTask`/`SingletonImportTask`); a session may yield more than one task when Staging Bins produce multiple album directories from one submission.
- **Apply Lock**: a single global `threading.Lock`, acquired only right before returning a *final* decision (never on "skip", never on the recursive `search_id` re-review path) and released once that Import Task's apply is confirmed done via the real `album_imported`/`item_imported` event. Exists for path-disambiguation correctness against concurrent `%aunique{}` reads, not for SQLite write-safety (beets' own `Database` already serializes writes internally) — see ADR-0006. No ordering guarantee is provided or required.
- **Manual grouping**: implemented via Staging Bins (ad-hoc inbox subdirectories) rather than direct in-memory `ImportTask`/`SingletonImportTask` construction from arbitrary file lists — confirmed as the permanent design, not a stopgap (ADR-0003). Staging Bins persist through their Grace Period and are cleared from the inbox on expiry.
- **Grace Period / undo**: `GracePeriodManager` tracks pending undo records in-memory, keyed strictly on DB IDs captured from real `album_imported`/`item_imported` events (ADR-0001). Duration is configurable (`webimport.grace_period_seconds` in config, already implemented). Tracked as server-side wall-clock time, independent of client connection state. Not persisted across a plugin restart (ADR-0004) — an accepted low-priority gap, not a target for this spec.
- **Reimport**: `reimport.py` temporarily mutates the global `beets.config["import"]["from_scratch"]`/`["set_fields"]`, runs a library-query (`-L`-equivalent) `WebImportSession`, then restores prior values in a `finally` block, reusing beets' own apply-time metadata-clearing logic rather than reimplementing it (ADR-0005). **Known gap**: this mutation is not currently guarded by the Apply Lock (or any lock) for its full duration, so a concurrent fresh-import review could transiently observe the mutated global config. Recorded as accepted-for-now given solo usage, with a fix understood (hold a lock for the whole config-mutated duration, not just at apply) — see Out of Scope.
- **Duplicate handling / Placement Conflict**: `get_duplicate_action` (not `resolve_duplicate`) is the real beets hook. The GUI decision surfaced must match the real `DuplicateAction` enum: `SKIP` ("Skip new"), `MERGE` ("Merge all"), `REMOVE` ("Remove old"), `KEEP` ("Keep all") — `ASK` is beets' internal default that triggers this decision in the first place, not itself a user-facing option. This is one instance of the broader Placement Conflict concept (`CONTEXT.md`); the other instance — a Move-on-Field-Change destination collision beyond what `%aunique{}` resolves — is deferred past MVP but should reuse this same decision shape when built (see Out of Scope).
- **Cover art**: `coverart.py` resolves Source Art and Resolved Art by mirroring fetchart's real logic — CAA via its JSON API (`/release/{mbid}`, filtering `images[].types` containing `Front`), not the fragile `/front` redirect; recognizes fetchart's real source id `coverart` (not `coverart:release`); retries transient CAA/archive.org 5xx errors; prefers a 500px thumbnail. Resolved Art preview currently covers the `filesystem` and `coverart` (CAA) sources only — other remote sources (itunes, amazon) are honored in ordering but not fetched for preview (see Further Notes).
- **Library data access**: `library.py` exposes browse/search/edit/move operations and a `_jsonable_fields` helper that decodes beets' raw-bytes fields (`Item.path`, `Album.destination()`, `Album.artpath`, etc.) for JSON serialization — reuse this helper for any new endpoint rather than re-deriving byte-handling logic.
- **Listening Group autocomplete**: suggestions are a live `SELECT DISTINCT navidrome_library` query against the current library, not a separately maintained vocabulary list (unlike Tag Vocabulary) — a value only becomes suggestable once something is actually routed to it, which is acceptable since there's no need to pre-stage an empty group.
- **Config-driven behavior already assumed**: `copy: yes`/`move: no`, `duplicate_action: ask`, `import.set_fields.navidrome_library: unassigned`, and a `plugins:` list that must explicitly include `musicbrainz`, `fetchart`, `embedart`, `webimport` alongside whatever matching plugins (e.g. `chroma`) are wanted — beets' `plugins:` config key *replaces* rather than merges with its own default, so omitting any of these silently disables that functionality rather than erroring.

## Testing Decisions

- **Seam**: drive the real, running `beet webimport` server through a real browser via the Playwright MCP tools — the same way the single human user actually interacts with the plugin — rather than an in-process Flask `test_client()` script calling `/api/*` routes directly (ADR-0009). This is a deliberate seam migration: the `test_client()` approach verified the API but structurally could not exercise the frontend, drag-and-drop/long-press interactions, or the real page-load path.
- **Playwright Playbooks (`docs/playbooks/`)**: Markdown **playbooks** (step-by-step Playwright MCP procedures) cover the end-to-end scenarios run against a live server backed by the disposable test setup (`.config/config.yaml`, `.config/library.db`, `.library/`, `.inbox/` — see `CONTEXT.md`):
  - Full inbox import: candidate review → force target MBID via search_id → apply → confirm copy-mode placement, `set_fields`, art embed, and grace-period undo record appears.
  - Grace-period undo: confirm ID-scoped removal wipes the library copy while leaving the inbox original untouched.
  - Parallel review + serial apply + duplicates: two albums submitted at once, reviewed independently, applies never overlap, a duplicate triggers the decision prompt.
  - Cover-art preview: Source Art vs. Resolved Art match indicator against a known release.
  - **New coverage this migration should add** (previously untested): reimport end-to-end (`--from-scratch` + `--set`, diff view, grace/undo behaving as in a fresh import), and manual grouping via Staging Bins (splitting one inbox directory into multiple real albums and confirming each imports canonically).
- **What makes a good playbook**: verify externally-observable behavior through the UI and the resulting library/filesystem state (album appears with correct path/tags/art, undo removes exactly what was captured, duplicate prompt appears and resolves correctly) — not internal call sequences. Playbooks should note the two timing/race facts already documented in `CONTEXT.md` (album can appear in the library list before the import fully finalizes; a `search_id` re-review briefly reuses the old task's queue) since they're realities of the running system, not bugs.
- **Network hosts needed**: `musicbrainz.org`/`*.musicbrainz.org`, `coverartarchive.org`/`*.coverartarchive.org`, `archive.org`/`*.archive.org`, `itunes.apple.com`/`*.mzstatic.com` (already documented in `CONTEXT.md`).
- A fast, mocked/in-process regression layer (e.g. pytest against `test_client()`) is not part of this migration and would be a separate, lower-fidelity addition layered alongside — not instead of — the Playwright playbooks, should it ever be wanted (ADR-0009).

## Out of Scope

- Persistent/durable in-flight review state or Grace Period tracking across a plugin process restart (ADR-0004) — an accepted, explicit gap, revisit only if it becomes painful in practice.
- Concurrent multi-user editing/conflict handling — this is single-user software; no locking or merge semantics beyond the Apply Lock's narrow purpose (ADR-0006, ADR-0008).
- Automatic Navidrome rescan triggering — manual/periodic auto-scan in Navidrome itself is assumed sufficient.
- Guarding reimport's global config mutation with a lock for its full duration (currently only guarded at apply time) — understood as a real, low-priority gap; fix when it doesn't block higher-priority work.
- A prompted skip/overwrite/keep-both decision for Move-on-Field-Change destination collisions beyond what `%aunique{}` already resolves — deferred past MVP; when built, it should reuse the same Placement Conflict decision shape as duplicate handling, not invent a fourth option set.
- Parallel apply (relaxing the Apply Lock to allow concurrent db-writes) — motivation and necessity are unconfirmed; tracked as a candidate spike ticket to determine whether apply-step latency is ever actually a bottleneck for solo usage, not committed work.
- Thumbnail caching/resizing layer for the library grid — currently serves `artpath` directly with no resize/cache step; acceptable at ~800 albums, flagged as needed before assuming it stays fast at greater scale.
- Fetching itunes/amazon sources for Resolved Art preview (ordering is honored, fetching is not) — filesystem + CAA preview is considered sufficient for now.
- A build step / framework migration for the frontend (staying vanilla JS/HTML) — functional, not polished; revisit only if it becomes a real velocity problem.

## Further Notes

- Mobile touch interactions (long-press-to-menu, `attachLongPress` in `app.js`) are implemented as the touch equivalent of drag-and-drop but have never been exercised on a real touch device — only reviewed for logical correctness. Worth an explicit playbook step (or manual pass) on an actual device before treating mobile support as verified.
- The known config landmine — beets' `plugins:` key replacing rather than merging with its default `[musicbrainz]` — has already caused a real, silent bug (CAA source-id mismatch) during prior verification; keep it in mind for any future config-handling change.

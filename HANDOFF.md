# Handoff: beets-webimport

## What this is

A native beets plugin (not a separate app) that replaces beets-flask with
a faster, mobile-friendly web UI for import review, library browsing,
tagging, and multi-library routing, tailored to Evan's self-hosted music
stack (Navidrome + beets + Maloja + ARM/abcde).

Two files matter most for context:

- `beets-web-plugin-prd.md` — the full product requirements. Read this
  first; it's the source of truth for *what* to build and *why* each
  design decision was made (grace-period undo semantics, multi-library
  routing via `$navidrome_library`, dual cover-art preview, etc).
- This file — *where implementation currently stands* against that PRD,
  what's verified vs. not, and what to do next.

Code lives in `beetsplug/webimport/` (a real, pip-installable beets
plugin package: `pip install -e .`, then `beet webimport` starts the
server). Frontend is vanilla JS/HTML in `beetsplug/webimport/static/` —
no build step, no npm, deliberately simple.

## Evan's actual environment (from memory, not this repo)

- Beets runs in a `beets-flask` Docker container today (being replaced),
  rootless Docker, host user `emmasmith`.
- Config highlights (see PRD "Multi-Library Routing" for the real
  `paths:`/`import:` blocks): `copy: yes`, `move: no`,
  `duplicate_action: ask`, `set_fields: {navidrome_library: unassigned}`,
  plugins include `chroma`, `fetchart`, `embedart`, `mbsync`,
  `musicbrainz`, `replaygain`, `scrub`, `web`.
- `$navidrome_library` is a free-form flexible attribute used directly
  in path templates — **not** a fixed enum and **not** matched via
  per-value conditional `paths:` entries. Don't reintroduce that wrong
  assumption (it was in an earlier PRD draft and was corrected).
- Navidrome custom tags must be pre-declared in `navidrome.toml`
  (`Tags.<Name>.Aliases`) — new tag *values* work immediately, new tag
  *names* need a config edit + full rescan. Current field: `mood`.
- Networking is Tailscale + tsdproxy; **no app-level auth** by design
  (network access is the auth boundary).

## Architecture recap

- One `WebImportSession` (subclass of `beets.importer.ImportSession`)
  per inbox album, run in a bounded thread pool (`InboxWorkerPool`) —
  this is what makes candidate review parallel across albums.
- `choose_match`/`choose_item`/`get_duplicate_action` block the calling
  thread on a `queue.Queue` (`ReviewManager`) until the web UI POSTs a
  decision to `/api/review/<task_id>/decide`.
- A single global `threading.Lock` (`apply_lock`) is acquired right
  before returning a *final* decision from choose_match/choose_item
  (not on "skip", not on the recursive search_id re-review path), and
  released by the caller once `session.run()` returns. This serializes
  the actual db-write/move step across concurrently-reviewed tasks
  without serializing search/review. See `queue.py` and `session.py`
  docstrings.
- Undo (`grace.py`) is keyed strictly on DB IDs captured via the real
  `album_imported`/`item_imported` beets events (registered through
  `plugin.register_listener`, not a decorator — see gotcha below) — never
  a re-derived query. `copy` mode means undo = `Album.remove(delete=True)`
  / `Item.remove(delete=True)`, the API equivalent of `beet remove -d`.
- Reimport (`reimport.py`) temporarily flips `beets.config["import"]
  ["from_scratch"]` / `["set_fields"]` for the duration of a
  library-query (`-L`-equivalent) session, then restores prior values —
  reuses beets' own metadata-clearing logic rather than reimplementing
  it.

## Verified vs. not (important — read before assuming anything works)

**Verified against a real installed beets 2.13.1**, including an
in-process Flask `test_client()` smoke test hitting `/api/inbox`,
`/api/library/albums`, `/api/library/albums/<id>`, `/api/tags`,
`/api/undo`, `/`, `/app.js`, and a simulated `album_imported` event
flowing correctly into the undo list:

- Plugin loads and registers the `beet webimport` subcommand.
- `Action`/`DuplicateAction` enums and the `get_duplicate_action` hook
  name (NOT `resolve_duplicate` — an earlier draft had this wrong).
- `ImportTask.lookup_candidates(search_ids=[...])` — real method, right
  signature.
- Byte-vs-str path handling: `ImportSession` wants `os.fsencode()`'d
  paths; `Item.path`, `Album.destination()` return `bytes`; `dict(item)`
  includes raw bytes fields that broke JSON serialization until fixed
  (see `library.py::_jsonable_fields`).
- Field name is `artpath`, not `art_path` (caught by testing, not
  memory).
- `Item.move()`/`Album.move()` real signatures confirmed; gracefully
  skip-and-log when the underlying file doesn't exist rather than
  raising (tested with a library entry pointing at a nonexistent file).
- `plugin.register_listener(event, func)` is the real API — **there is
  no `@plugin.listen(...)` decorator** in this beets version. An earlier
  draft used a decorator and a hacky global-registry workaround; that's
  been removed. If a future beets version changes this, `server.py`'s
  `create_app()` is the only place it's used.

**Now verified end-to-end (2026-08-16, beets 2.13.1, real MB + CAA):**
Driven via HTTP against a live `ImportSession.run()` using the harnesses
in `scripts/` (see `scripts/README.md`). A disposable library lives at
`.config/library.db` + `.library/`, config at `.config/config.yaml`.

- **Real inbox import end-to-end** (`scripts/drive_import.py`):
  `choose_match` blocks and resumes correctly on a real run; forcing a
  search_id (`-S <mbid>`) re-review works; `select` applies; copy-mode
  places files under the path template; `set_fields`
  (`navidrome_library=unassigned`) is applied; fetchart+embedart fetch
  and embed `cover.jpg`; and the real `album_imported` event registers
  the grace-period undo record.
- **Grace-period undo** (`scripts/drive_undo.py`): ID-scoped
  `remove(delete=True)` wipes DB row + files, inbox originals untouched.
- **Parallel review + serial apply + duplicates**
  (`scripts/drive_concurrency.py`): two albums submitted at once are
  reviewed in parallel; applies serialize without leaving the apply_lock
  stuck; a duplicate second copy triggers the duplicate prompt and
  "skip" leaves exactly one album.
- **Cover-art preview** (`coverart.py`, `scripts/drive_art.py`): now
  uses the CAA JSON API like fetchart (was the fragile `/front`
  redirect), recognizes fetchart's real source ids (`coverart`, not the
  old `coverart:release` guess — this was a real bug that silently
  resolved nothing under Evan's actual config), retries transient CAA
  5xx, and prefers a 500px thumbnail. Returns `match: True` against the
  target release.

**Config note:** `plugins:` in config.yaml *replaces* the default
`[musicbrainz]`, so metadata source, fetchart, and embedart must all be
listed explicitly or lookups/art silently do nothing. `.config/config.yaml`
now lists `musicbrainz, fetchart, embedart, webimport`.

**Still NOT tested — remaining risk areas:**

1. **Reimport flow** (`reimport.py`) — the temporary
   `config["import"]["from_scratch"]`/`set_fields` override pattern is
   logically sound (reuses beets' real apply-time logic) but has not
   been run against a real reimport.
2. **Manual file-grouping** (`/api/inbox/group`) — implemented via
   staging bins into subdirectories rather than constructing
   `ImportTask`/`SingletonImportTask` objects directly in-process (see
   docstring in `server.py`). This was a deliberate scope-reduction, not
   a bug, but it means grouping is coarser (whole files moved into
   per-bin folders) than a fully in-memory task-construction approach
   would be. Revisit if the staging-directory approach proves clunky in
   practice.
3. **Thumbnail caching** for the library grid — PRD wants resized/cached
   thumbnails; current implementation serves `artpath` directly with no
   resizing/caching layer. Fine for ~800 albums but should be added
   before assuming it'll stay fast.
4. **Mobile touch interactions** — long-press-to-menu is implemented in
   `app.js` (`attachLongPress`) as the touch equivalent of drag-and-drop
   per the PRD, but has not been tested on an actual touch device, only
   read for logical correctness.

## Known simplifications (intentional, see README.md in the repo)

- Frontend is vanilla JS, not React — functional, not polished.
- Cover art "resolved" preview approximates fetchart (same CAA JSON API
  + source-priority order, but only previews the filesystem + Cover Art
  Archive sources; other remote sources like itunes/amazon are honored
  in ordering but not fetched for preview) rather than invoking the real
  plugin object end-to-end.
- No persistence of in-flight review state across a plugin restart
  (explicitly requested — simpler implementation was prioritized over
  crash-resilience).

## Suggested next steps, in order

1. ~~Real inbox import end-to-end.~~ **Done** — see "Now verified
   end-to-end" above and `scripts/`. Import, undo, parallel review,
   serial apply, and duplicate resolution all exercised against real
   files + MusicBrainz + Cover Art Archive.
2. **Reimport** is the biggest untested path now — drive
   `POST /api/reimport` against the applied Mulan album (e.g. with
   `from_scratch: true` and `set_fields: {navidrome_library: kids}`) and
   confirm the temporary-config override restores cleanly and the
   grace/undo + apply_lock behave as in a fresh import. A
   `scripts/drive_reimport.py` following the same pattern as the other
   drivers would close this loop.
3. Add the thumbnail caching layer for the library grid before treating
   the library-browse tab as done.
4. Revisit the manual-grouping UX once you've tried it —
   it's the part of the PRD I'm least confident matches Evan's actual
   mental model of "drag files into bins," since it's currently
   filesystem-staging rather than a true in-memory task-splitting UI.

## File map

```
beets-webimport/
├── pyproject.toml
├── README.md                    # install instructions + simplification notes
├── beets-web-plugin-prd.md      # full requirements (source of truth for "what")
└── beetsplug/webimport/
    ├── __init__.py              # BeetsPlugin subclass, `beet webimport` command
    ├── session.py                # WebImportSession: choose_match/choose_item/
    │                             #   get_duplicate_action, apply_lock handling
    ├── queue.py                  # ReviewManager (per-task decision queue),
    │                             #   InboxWorkerPool (parallel review)
    ├── grace.py                  # GracePeriodManager: ID-scoped undo
    ├── tags.py                   # tag vocabulary + apply (album -> every track)
    ├── library.py                # browse/search/edit/move, JSON-safe field dicts
    ├── coverart.py                # dual cover-art resolution (simplified fetchart)
    ├── reimport.py                # -L/-S/--from-scratch/--set equivalent
    ├── server.py                  # Flask app, all /api/* routes, event listeners
    └── static/
        ├── index.html
        ├── app.js                 # all frontend logic, no build step
        └── style.css
```

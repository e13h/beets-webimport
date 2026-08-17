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

**NOT yet tested — highest risk areas to check first:**

1. **A real inbox import end-to-end** against actual ripped audio files:
   does `choose_match` actually block/resume correctly when driven by a
   real `ImportSession.run()` (not the isolated unit tests done so
   far)? Does the apply-lock serialization behave under real concurrent
   album reviews? This is the core value proposition of the whole
   project and hasn't been exercised with real files yet.
2. **Cover art resolution** (`coverart.py`) against real Cover Art
   Archive responses — only structurally reviewed, not run against a
   live MBID. Also: this re-implements fetchart's source-priority logic
   rather than driving the real fetchart plugin object, so it will
   silently drift if fetchart's config options change (see README
   "Known simplifications").
3. **Reimport flow** (`reimport.py`) — the temporary
   `config["import"]["from_scratch"]`/`set_fields` override pattern is
   logically sound (reuses beets' real apply-time logic) but has not
   been run against a real reimport.
4. **Duplicate resolution UI** — wired end-to-end at the API level, but
   never triggered against an actual duplicate in a real library.
5. **Manual file-grouping** (`/api/inbox/group`) — implemented via
   staging bins into subdirectories rather than constructing
   `ImportTask`/`SingletonImportTask` objects directly in-process (see
   docstring in `server.py`). This was a deliberate scope-reduction, not
   a bug, but it means grouping is coarser (whole files moved into
   per-bin folders) than a fully in-memory task-construction approach
   would be. Revisit if the staging-directory approach proves clunky in
   practice.
6. **Thumbnail caching** for the library grid — PRD wants resized/cached
   thumbnails; current implementation serves `artpath` directly with no
   resizing/caching layer. Fine for ~800 albums but should be added
   before assuming it'll stay fast.
7. **Mobile touch interactions** — long-press-to-menu is implemented in
   `app.js` (`attachLongPress`) as the touch equivalent of drag-and-drop
   per the PRD, but has not been tested on an actual touch device, only
   read for logical correctness.

## Known simplifications (intentional, see README.md in the repo)

- Frontend is vanilla JS, not React — functional, not polished.
- Cover art "resolved" preview approximates fetchart rather than
  invoking the real plugin object end-to-end.
- No persistence of in-flight review state across a plugin restart
  (explicitly requested — simpler implementation was prioritized over
  crash-resilience).

## Suggested next steps, in order

1. Set up a real (small, disposable) beets library + inbox directory
   with actual ripped albums and run `beet webimport` for real — this
   will surface far more issues than unit-level testing can. Start here
   before adding any new features.
2. Watch specifically for: whether `WebImportSession.run()` truly
   blocks/resumes per-task as expected when multiple albums are
   submitted concurrently (validates the core parallel-review/serial-
   apply design); whether the apply_lock is ever left stuck (e.g. an
   exception during apply that skips the `finally: release()` path is
   the most concerning failure mode — check `server.py::_run_album_import`
   and `reimport.py::run_reimport`, both currently wrap `session.run()`
   in `try/finally`, but a full concurrency stress test hasn't been
   done).
3. Once basic import works, layer in cover art resolution testing
   against real MBIDs, then reimport, then duplicate handling.
4. Add the thumbnail caching layer for the library grid before treating
   the library-browse tab as done.
5. Revisit the manual-grouping UX (item 5 above) once you've tried it —
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

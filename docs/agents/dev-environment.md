# Dev Environment & beets API Notes

Practical, hard-won facts for working effectively in this repo: local
setup, gotchas, and verified beets 2.13.1 API behavior. Pairs with
`CONTEXT.md` (glossary), `.scratch/webimport/spec.md` (the "what/why"
source of truth and current work breakdown), and `docs/adr/`
(hard-to-reverse decisions).

## Local dev environment (already set up)

- **Virtualenv:** `.venv/` at the repo root. Always use `.venv/bin/python`
  and `.venv/bin/beet` — there is no global beets. `pip install -e .` has
  already been run.
- **Python 3.14**, **beets 2.13.1** (verify with `.venv/bin/beet version`).
- **Disposable test setup** (all inside the repo, safe to wipe):
  - Config: `.config/config.yaml`
  - Library DB: `.config/library.db` (git-ignore-worthy; regenerated)
  - Music dir (import destination, copy-mode): `.library/`
  - Inbox: `.inbox/` — contains a 4-track Mulan album for hello-world tests.
- **Run the server:** `BEETSDIR=./.config .venv/bin/beet webimport`
  (serves on `0.0.0.0:8338`).
- **Reset the disposable library between test runs:**
  ```bash
  rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
  rm -f .config/state.pickle && rm -rf .config/webimport   # optional, fuller reset
  ```

## The single most important gotcha: `plugins:` REPLACES the default

beets' default `plugins:` is `[musicbrainz]`. Any `plugins:` list in
`config.yaml` **overrides** it — it does not merge. If you forget to list a
plugin, it silently does nothing:
- Drop `musicbrainz` → candidate lookups return **zero** results (no error).
- Drop `fetchart`/`embedart` → import "succeeds" but no cover art is
  fetched/embedded (`has_art: False`, no `cover.jpg`).

`.config/config.yaml` therefore lists all of:
`musicbrainz, fetchart, embedart, webimport`. Keep it that way.

## Closing the loop without a browser (key technique)

You can drive the whole plugin end-to-end **in-process** by acting as the
browser through Flask's `test_client()` — no manual clicking, no long-running
server. The reusable harnesses live in `scripts/` (run from the repo root):

- `scripts/drive_import.py` — full inbox import (review → force MBID → apply).
- `scripts/drive_undo.py` — grace-period undo.
- `scripts/drive_art.py` — cover-art preview endpoint.
- `scripts/drive_concurrency.py` — parallel review + serial apply + duplicates.

See `scripts/README.md`. The canonical bootstrap inside a driver:
```python
import os; os.environ["BEETSDIR"] = os.path.abspath("./.config")
from beets import config, plugins
from beets.ui import _open_library
config.read()
plugins.load_plugins()            # NOTE: takes NO args in beets 2.13
lib = _open_library(config)
from beetsplug.webimport.server import create_app
plugin = next(p for p in plugins.find_plugins() if p.name == "webimport")
app = create_app(lib, config["webimport"], plugin)
client = app.test_client()
```

Network hosts the drivers need (for terminal sandbox `allow_hosts`):
`musicbrainz.org`, `*.musicbrainz.org`, `coverartarchive.org`,
`*.coverartarchive.org`, `archive.org`, `*.archive.org`,
`itunes.apple.com`, `*.mzstatic.com`.

Target test release (Mulan soundtrack) MBID:
`a5483fb3-634b-4254-a966-de33cefd1f17`.

## Timing/race facts that bite in test drivers (not plugin bugs)

The import runs in a worker thread; the Flask request thread is the "browser".
Two races to design around when scripting:
1. **Album appears in `/api/library/albums` BEFORE the import finalizes.**
   `task.add(lib)` runs during review-apply, but art embedding and the
   `album_imported` event (→ grace/undo record) fire later in
   `manipulate_files`/`finalize`. To know an import is *fully* done, poll
   `/api/undo` (the undo record), not the album list.
2. **`search_id` re-review reuses the pending queue.** After POSTing a
   `search_id` decision, the old task lingers in `pending_review` for a beat
   before the worker pops it and registers the *new* task. Posting to the old
   task_id again returns `{"ok": false}` (its 1-slot queue is full). Wait for a
   pending review whose `task_id` differs from the one you just decided.

## Verified beets 2.13.1 API facts (checked against `.venv` source)

Read beets source directly with file tools under
`.venv/lib/python3.14/site-packages/beets/` (note: `grep`/`find_path` tools
skip `.venv`, so use `read_file` with paths, or `list_directory`).

- `beets/importer/` is a **package** (`session.py`, `stages.py`, `tasks.py`,
  `actions.py`, `state.py`), not a single module.
- `ImportSession.__init__(self, lib, loghandler, paths, query)`.
- Session hooks to override: `choose_match(task)`, `choose_item(task)`,
  `get_duplicate_action(task, found_duplicates)` (NOT `resolve_duplicate`),
  `should_resume(path)`.
- `Action` members: `SKIP, ASIS, TRACKS, APPLY, ALBUMS, RETAG`
  (`APPLY` is internal — `set_choice` asserts you never return it; return the
  match object instead to apply).
- `DuplicateAction` members: `SKIP, MERGE, REMOVE, KEEP, ASK`.
- `ImportTask.lookup_candidates(search_ids: list[str])` — the `search_id`
  re-review path relies on this.
- Events dispatch **kwargs-only**: `plugins.send("album_imported", lib=...,
  album=...)`. Listener params must match by name; extra unknown kwargs are
  filtered out unless the listener has `**kwargs`.
- `plugins.load_plugins()` takes **no** positional args (uses config).
- `BeetsPlugin.register_listener(event, func)` is the real API — there is **no**
  `@plugin.listen(...)` decorator in this version. `listeners` is a shared
  class-level dict.
- `import.set_config()` mutates the global `beets.config["import"]` and, when
  `query is not None`, forces `resume=False`/`incremental=False` (relevant to
  reimport). The pipeline runs `run_parallel` when `config["threaded"]`.

## fetchart specifics that matter for cover-art code

- CAA source **id is `coverart`** (with matching criteria `release` /
  `releasegroup` as a separate axis) — NOT `coverart:release`. Config entries
  may be bare (`coverart`) or qualified (`coverart:release`).
- Default `sources`: `[filesystem, coverart, itunes, amazon, albumart,
  cover_art_url]`.
- fetchart resolves CAA via the **JSON API** (`/release/{mbid}` → parse
  `images[].image`, filter `types` containing `Front`), NOT the
  `/{mbid}/front` redirect (which bounces to archive.org and 502s often).
  `coverart.py` now mirrors this.
- CAA/archive.org return **transient 502s** regularly — retry, don't treat as
  fatal. `coverart.py` retries and reports an `unavailable` flag.

## Field-name / serialization landmines (caught by running, not reading)

- Album art field is `artpath` (bytes), not `art_path`.
- `Item.path`, `Album.destination()`, `Album.artpath` return **bytes**;
  `dict(item)`/`dict(album)` include raw bytes fields that break Flask JSON.
  `library.py::_jsonable_fields` decodes them — reuse it for any new endpoint.
- `ImportSession` wants `os.fsencode()`'d paths.

## Architecture quick-reference (where to look)

- `session.py` — `WebImportSession`; blocks in `choose_*` on the ReviewManager
  queue; acquires the global `apply_lock` only right before returning a *final*
  decision (not on skip / not on the search_id recursion). Caller releases it
  in a `finally` after `session.run()`.
- `queue.py` — `ReviewManager` (per-task 1-slot decision queue),
  `InboxWorkerPool` (bounded thread pool for parallel review).
- `grace.py` — ID-scoped undo (`remove(delete=True)`), keyed on the DB IDs
  captured from real import events. In-memory only, per app instance (not
  persisted across restart — intentional).
- `server.py::create_app` — the **only** place event listeners are registered
  and the whole app is wired; start here to trace any request.
- `reimport.py` — temporarily flips `import.from_scratch`/`set_fields`, runs a
  library-query session, restores config in `finally`. **Least-tested path.**

## Diagnostics note

Pyright runs in a strict-ish mode and floods `coverart.py`/etc. with
"unknown type" / missing-stub warnings for `requests`, `PIL`, and untyped
dicts. These are **noise** in this deliberately-untyped codebase — don't
chase them; only real errors matter.

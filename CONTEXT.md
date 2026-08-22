# CONTEXT.md — repo-specific notes for agents

Practical, hard-won facts for working effectively in this repo. Pairs with
`.scratch/webimport/spec.md` (the "what/why" source of truth and current
work breakdown) and `docs/adr/` (hard-to-reverse decisions). Read those
too; this file is the "how things actually work here" cheat sheet.

## What this project is

A native, pip-installable **beets plugin** (`beetsplug/webimport/`) that
serves a Flask web UI for import review, library browsing, tagging, and
multi-library routing. Frontend is deliberately vanilla JS/HTML in
`beetsplug/webimport/static/` — no build step, no npm.

## Language

**Listening Group**:
User-facing concept for the category (kids, worship, holiday, talk radio,
regular, or any future value) that routes an album to a distinct Navidrome
library root. Implemented as the freeform beets flexible attribute
`navidrome_library` — not a fixed enum; any string typed or selected by the
user is a valid, new group. Autocomplete suggestions are derived live from
the distinct values already present in the library (not a separately
maintained vocabulary list, unlike Tag Vocabulary below) — a group only
appears as a suggestion once something has actually been routed to it, and
the user can always type a new value instead of picking a suggested one.
"Unassigned" is the reserved default value (`import.set_fields.
navidrome_library: unassigned`) applied to anything imported without an
explicit group choice; the library browse view must surface it as a
filterable state so nothing gets lost in it silently.
_Avoid_: navidrome_library (when referring to the user-facing concept —
reserve that name for the underlying field)

**Grace Period**:
The configurable window (default ~10 minutes) after an import or reimport
apply during which the resulting Album/Item can be undone. Tracked
server-side as wall-clock time from the real `album_imported`/`item_imported`
event, independent of whether a browser client is currently connected. Lost
(not restored) if the plugin process restarts before it elapses — an
accepted, low-priority gap (see ADR-0004). Expiry has two effects: the
import becomes permanent (undo no longer available), and the originating
Staging Bin (if any) becomes eligible for inbox cleanup.

**Source Art**:
The cover image associated with the currently-selected import candidate
(from MusicBrainz/Spotify/etc.), one of the two thumbnails shown in
candidate review. Shows a "No Cover Art Available" placeholder when the
candidate has none — never substitutes Resolved Art in its place, so the
match/mismatch indicator stays meaningful.

**Resolved Art**:
The image fetchart/embedart will actually write to the file for the
currently-selected candidate, computed by running fetchart's real
resolution logic (source priority, minimum resolution, aspect ratio, local
`cover.jpg` precedence, overwrite rules) rather than a reimplementation of
those rules. Computed lazily, only for the highlighted candidate.

**Apply Lock**:
The single global mutual-exclusion lock serializing the db-write/move
("apply") step across concurrently-reviewed Import Tasks. Guarantees
applies never overlap; does not guarantee ordering between tasks.
_Avoid_: apply queue (implies a FIFO ordering guarantee that doesn't exist)

**Import Task**:
Beets' own `ImportTask`/`SingletonImportTask` — the unit of review,
identified by `task_id` in the review API (`/api/review/<task_id>/decide`).
One inbox submission normally yields one task; manual grouping can split
it into several, reviewed one after another.
_Avoid_: review unit, session (see Import Session — a session may contain
several tasks)

**Import Session** (`WebImportSession`):
One instance per inbox submission, occupying one slot in the
`InboxWorkerPool` and running beets' `ImportSession` pipeline. Parallel
review happens *across* sessions; the Import Task(s) within a single
session are still visited one at a time by the beets pipeline.

**Move-on-Field-Change**:
The general rule that any metadata edit — single field, single track/album,
or bulk — which changes an item's computed path (per `paths:` templates)
triggers an automatic move of the underlying file(s), since the config runs
`copy: yes`/`move: no` by default. Applies uniformly to every field; not a
special case limited to `navidrome_library`. Relies on beets'
`%aunique{}` template disambiguation for the common case; a genuine
destination collision beyond that is a Placement Conflict (below), deferred
past MVP.

**Placement Conflict**:
The umbrella concept for "two things want the same library slot," resolved
through the same skip/overwrite/keep-both decision shape regardless of what
triggered it. Two distinct triggers, both resolved this way:
- a beets-detected duplicate during import (via `duplicate_action: ask` /
  `get_duplicate_action`), or
- a destination collision from Move-on-Field-Change that `%aunique{}`
  doesn't resolve (deferred past MVP — see carry-forward list).

Naming this once, and reusing the same decision UI for both triggers, is
intentional — avoids inventing a fourth resolution shape later.

**Tag Vocabulary**:
The reusable, GUI-managed set of custom tag names/values (e.g. `mood`) that
the user can apply to tracks/albums via drag-and-drop, distinct from
Listening Group's live-derived autocomplete: Tag Vocabulary is an
explicitly curated list maintained ahead of use, not just "whatever's
already in the library." A new tag *value* is usable immediately; a new
tag *name* additionally requires a `navidrome.toml` edit + full Navidrome
rescan before Navidrome will index it.

**Staging Bin**:
An ad-hoc subdirectory under the inbox that manual grouping moves files
into, so the resulting directory matches one intended real album/single
before beets' own directory-based grouping runs a canonical import on it.
Chosen over constructing `ImportTask`/`SingletonImportTask` objects
directly from an arbitrary in-memory file list, so every import — split or
not — is an ordinary beets import (see ADR-0003). Survives past that
import, through the Grace Period, since splitting a ripped playlist into
bins is tedious and shouldn't have to be redone if the import is undone;
only cleared from the inbox once its Grace Period expires.
_Avoid_: bin (alone), in-memory grouping

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

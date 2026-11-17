# Dev Environment & beets API Notes

Practical, hard-won facts for working effectively in this repo: local
setup, gotchas, and verified beets 2.13.1 API behavior. Pairs with
`CONTEXT.md` (glossary), `.scratch/webimport/spec.md` (the "what/why"
source of truth and current work breakdown), and `docs/adr/`
(hard-to-reverse decisions).

## Local dev environment (already set up)

- **Virtualenv:** `.venv/` at the repo root. Always use `.venv/bin/python`
  and `.venv/bin/beet` — there is no global beets. Install with
  `pip install -e '.[dev]'` (includes `pyacoustid` for the `chroma` plugin).
- **System tools the homelab plugins need:** `brew install chromaprint mp3gain`
  (`fpcalc` for `chroma`; `mp3gain` for `replaygain`, which refuses to load
  without it and aborts every `beet` command).
- **Python 3.14**, **beets 2.13.1** (verify with `.venv/bin/beet version`).
  The homelab container runs `lscr.io/linuxserver/beets:latest`, so its
  beets version can run ahead of this one.
- **Disposable test setup** (all inside the repo, safe to wipe):
  - Config: layered so dev runs the homelab's exact settings (see below).
  - Library DB: `.config/library.db` (git-ignored; regenerated)
  - Music dir (import destination, copy-mode): `.library/`
  - Inbox: `.inbox/` — contains a 4-track Mulan album for hello-world tests.
- **Run the server:** `scripts/dev-server.sh`
  (serves on `0.0.0.0:8338`).
- **Reset the disposable library between test runs:** `scripts/dev-reset.sh`
  (`--start` to restart the server afterwards). Stops a running dev server
  on port 8338 first, then removes the library DB, `.library/`, import
  state, plugin data, and `.webimport_imported` markers. Inbox audio and
  staging bins are never touched.

## The single most important gotcha: `plugins:` REPLACES the default

beets' default `plugins:` is `[musicbrainz]`. Any `plugins:` list in
`config.yaml` **overrides** it — it does not merge. If you forget to list a
plugin, it silently does nothing:
- Drop `musicbrainz` → candidate lookups return **zero** results (no error).
- Drop `fetchart`/`embedart` → import "succeeds" but no cover art is
  fetched/embedded (`has_art: False`, no `cover.jpg`).

The plugin list is whatever the homelab runs (see below); don't trim it locally.

## Dev config mirrors the homelab config

`.config/config.yaml` only does `include: [homelab.yaml, local.yaml]`.
beets applies includes on top of the main file in order, so later files win:

- `.config/homelab.yaml` — **verbatim** copy of
  `selfhosted/services/reptile/beets/config-beets/config.yaml`. All
  behavior settings live here. Change them here, then copy the file to the
  selfhosted repo (or the other way round).
- `.config/local.yaml` — maps container mounts to repo dirs and nothing else:
  `directory` (`/music` → `.library`), `library` and `import.log`
  (`/config` → `.config`), `webimport.inbox_dir` (`/downloads` → `.inbox`).

`tests/test_homelab_config_parity.py` enforces this: the copy must match the
selfhosted repo (skipped if that repo isn't at `../selfhosted`; override with
`HOMELAB_BEETS_CONFIG`), `local.yaml` may only set those path keys, and every
homelab plugin must load locally.

Consequences of the homelab settings that tests and playbooks must expect:
- Albums land at `.library/<navidrome_library>/<albumartist>/<album>/`,
  i.e. `.library/unassigned/...` after a default import.
- `embedart.remove_art_file: yes` deletes the fetched `albumart.jpg` after
  embedding, so `artpath` ends up null. Check for embedded art, not an art
  file; library thumbnails come from the embedded-art fallback.
- `chroma` fingerprints every track on import (AcoustID lookups), which
  costs real time even for a Direct ID Import.
- `scrub: auto: no`: the files' original tags (store IDs, purchase info)
  survive import; beets overwrites only the fields it sets.
- `match.distance_weights.missing_tracks: 0.1` (beets' default is 0.9): a
  few tracks bought from an album match the full release at a low distance
  instead of ~0.5. Expect distances around 0.17 for one track of 11.
- `musicbrainz.search_limit: 2`: broad searches return two releases. For
  store purchases (iTunes `plID`, Amazon "Amazon.com Song ID" comment) the
  review also searches digital releases of the album and adds the best two
  (`purchase.py`), marking ones from the files' year "likely your purchase".
- `webimport` uses its built-in defaults (grace period, `tag_fields`), since
  the homelab sets only host/port/inbox.

## Testing workflows (Playwright playbooks + pytest)

Per ADR-0009 and `CONTEXT.md`, testing is structured in two layers:
1. **Playwright Playbooks (`docs/playbooks/`):** End-to-end user flows driven by an agent using Playwright MCP browser tools against a live `beet webimport` server on `http://localhost:8338`.
2. **Pytest Unit Tests (`tests/`):** Fast, hermetic, offline tests using the disposable `lib` fixture from `tests/conftest.py`.

Network hosts needed for playbooks that hit MusicBrainz/CAA (for terminal sandbox `allow_hosts`):
`musicbrainz.org`, `*.musicbrainz.org`, `coverartarchive.org`,
`*.coverartarchive.org`, `archive.org`, `*.archive.org`,
`itunes.apple.com`, `*.mzstatic.com`.

Target test release (Mulan soundtrack) MBID:
`4e929666-952f-473c-baf2-97c9ca6bfbbe`, the 2020 Digital Media release
whose Apple Music links point at the test files' iTunes album
(`plID` 1440662312). (Older notes and tickets used `a5483fb3-…`, the 1998
US CD release, which has no Apple Music links.)

**The test Mulan files are an iTunes purchase, so a review started without
an ID is matched automatically** through the album's Apple Music link
(`webimport.apple_music_match`, on by default): one candidate, the
digital release, under a "Matched via Apple Music link" banner. A pasted
ID still overrides it. To exercise the broad search, click "Search
normally instead" (`[data-search-normally]`), or set
`webimport: apple_music_match: no` in `.config/local.yaml` for the run
(but don't commit that: the parity test allows only path keys there).

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

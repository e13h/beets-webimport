from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from beets import config as beets_config
from beets import context as beets_context
from beets.util import syspath

from . import activity, artchoice, backfill, coverart, itunes, library, lifecycle, originals, reimport, restore, snapshot, tagpreview, tags, version
from .navidrome import NavidromeClient
from .pendingmove import Mover
from .queue import InboxWorkerPool, ReviewManager
from .session import WebImportSession

log = logging.getLogger("beets.webimport")

STATIC_DIR = Path(__file__).parent / "static"


def _safe(fn):
    """Wraps a route handler so an unexpected exception (e.g. a missing
    file during item.write()/move()) returns a JSON error instead of an
    unhandled 500 traceback."""
    import functools

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 -- deliberately broad, converted to JSON
            log.exception("webimport route error")
            return jsonify({"ok": False, "error": str(exc)}), 500

    return wrapper


def create_app(lib, wi_config, plugin):
    """`plugin` is the live WebImportPlugin instance (a BeetsPlugin) --
    used only to register event listeners via its real `listen()` API."""
    app = Flask(__name__, static_folder=None)

    # beets stores paths relative to the music directory and expands them
    # via a ContextVar that Library() sets only on the thread that opened
    # it. Request threads and worker-pool threads start with an empty
    # context, where paths stay relative: art lookups fail and moves or
    # deletes miss the real files. Bind the music dir on every such thread.
    # (beets' import pipeline copies the context of the thread calling
    # session.run(), so binding the pool workers covers its stages too.)
    def bind_music_dir():
        beets_context.set_music_dir(lib.directory)

    app.before_request(bind_music_dir)

    review_manager = ReviewManager()
    apply_lock = threading.Lock()
    pool = InboxWorkerPool(
        wi_config["candidate_search_workers"].get(int), initializer=bind_music_dir
    )
    # What each import/reimport is doing, for the Inbox tab (activity.py).
    activities = activity.Activities()
    activity.install_request_hook()
    app.config["webimport_activities"] = activities

    def _submit(act: activity.Activity, run) -> None:
        """Queue `run()` in the worker pool, tracked by `act` from now
        until its session ends."""
        activities.add(act)

        def job(_key):
            token = activity.current.set(act)
            act.set("Starting", "working")
            try:
                run()
            except Exception as exc:  # noqa: BLE001 -- shown on the card
                activities.fail(act, str(exc) or exc.__class__.__name__)
                raise
            else:
                activities.finish(act)
            finally:
                activity.current.reset(token)

        pool.submit(act.key, job)

    try:
        data_dir = Path(beets_config.config_dir()) / "webimport"
    except Exception:
        import tempfile

        data_dir = Path(tempfile.gettempdir()) / "webimport"

    tag_store_cfg = wi_config.get("tag_store_path") if isinstance(wi_config, dict) else None
    if tag_store_cfg:
        tag_store = tags.TagStore(Path(tag_store_cfg.get(str)))
    else:
        tag_store = tags.TagStore(data_dir / "tags.json")
    thumbs_dir = data_dir / "thumbs"
    for field in wi_config["tag_fields"].get(list):
        tag_store.add_field(field)

    inbox_dir = wi_config["inbox_dir"].get(str) or ""
    # Shared (not thread-local) import context: beets' importer pipeline
    # is threaded by default, so the album_imported/item_imported events
    # fire on a pipeline stage thread -- not on the worker thread running
    # session.run(). A threading.local would make the listener observe
    # path=None and the marker/album-id capture below would never fire.
    # Only one import apply can be in flight at a time (Apply Lock).
    _import_ctx = {"path": None, "imported_album_id": None}
    _import_ctx_lock = threading.Lock()

    # -- copy mode: remember the imported album for the folder's marker ----
    def _on_album_imported(lib, album):
        with _import_ctx_lock:
            if _import_ctx["path"]:
                _import_ctx["imported_album_id"] = album.id

    plugin.register_listener("album_imported", _on_album_imported)
    # No listeners for events fired while sessions run in parallel
    # (import_task_created / _start): beets' listener wrapper isn't
    # thread-safe. Per-task work happens in the session
    # (WebImportSession._task_created).
    # Import-time album art (fetchart's automatic step is off). Runs in the
    # serialized apply phase, so it never overlaps across parallel imports.
    plugin.register_listener("import_task_files", artchoice.on_import_task_files)
    # After the art: check each file's original can be rebuilt from the
    # imported file (originals.py).
    plugin.register_listener("import_task_files", originals.verify_task)
    # Move mode: keep the folder's other files with the album, drop the
    # safety copies, prune emptied folders (lifecycle.py).
    plugin.register_listener("import_task_files", lifecycle.finish_task)
    try:
        if inbox_dir:
            lifecycle.cleanup_safety(lib, Path(inbox_dir))
            # Folders imported in copy mode: save their originals while
            # their inbox copies exist (only reads albums missing them).
            n = lifecycle.backfill_all(lib, Path(inbox_dir))
            if n:
                log.info("webimport: saved originals for %d earlier-imported tracks", n)
        originals.prune(lib)  # originals from reviews that never imported
    except Exception:  # noqa: BLE001
        log.exception("webimport: startup cleanup failed")

    loghandler = None  # let beets use its default logging
    build = version.info()
    log.info("webimport: running %s%s", build["label"], f", committed {build['date']}" if build["date"] else "")

    # -- Pending Move (ADR-0011) -------------------------------------------
    try:
        nd_cfg = wi_config["navidrome"]
    except KeyError:  # hand-built configs (tests) without the section: off
        nd_cfg = None
    navidrome = NavidromeClient.from_config(nd_cfg) if nd_cfg is not None else None
    mover = Mover(
        lib,
        navidrome,
        lock=apply_lock,
        trigger_scan_after=nd_cfg["scan_request_after"].get(float) if navidrome else 60.0,
        thread_init=bind_music_dir,
    )
    if navidrome is not None:
        log.info("webimport: Navidrome integration on (%s as %s)", navidrome.base, navidrome.user)
    mover.start()
    app.config["webimport_mover"] = mover  # for tests / introspection

    # -- Backfill (ADR-0016): attach store downloads to library tracks -----
    backfiller = (
        backfill.Backfill(lib, Path(inbox_dir), data_dir / "backfill-cache.sqlite", apply_lock,
                          thread_init=bind_music_dir)
        if inbox_dir else None
    )
    app.config["webimport_backfill"] = backfiller

    # -- inbox scanning / import kickoff -----------------------------------
    def _run_album_import(path: str, search_id: str | None = None):
        with _import_ctx_lock:
            _import_ctx["path"] = path
            _import_ctx["imported_album_id"] = None
        session = WebImportSession(
            lib,
            loghandler,
            paths=[os.fsencode(path)],
            query=None,
            review_manager=review_manager,
            config=wi_config,
            apply_lock=apply_lock,
        )
        if search_id:
            session.preset_search_id = search_id
        elif wi_config["apple_music_match"].get(bool):
            # iTunes purchase with a MusicBrainz release linked to its
            # Apple Music listing: search only the linked release(s).
            activity.step("Checking for an iTunes purchase")
            match = itunes.musicbrainz_match_for_dir(Path(path))
            if match and match["release_ids"]:
                session.preset_search_id = list(match["release_ids"])
                session.matched_via = match
        try:
            activity.step("Reading the files")
            session.run()
            with _import_ctx_lock:
                imported_album_id = _import_ctx["imported_album_id"]
            # Copy mode only: in move mode the folder has been emptied
            # (lifecycle.finish_task); there's nothing left to mark.
            if imported_album_id is not None and not lifecycle.move_mode():
                marker_path = Path(path) / ".webimport_imported"
                try:
                    import json
                    from datetime import datetime, timezone

                    marker_data = {
                        "album_id": imported_album_id,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                        "staging_bin": "_grouped" in str(path),
                    }
                    marker_path.write_text(json.dumps(marker_data), encoding="utf-8")
                except Exception as exc:
                    log.warning("webimport: failed to write imported marker to %s: %s", path, exc)
        except Exception:
            # Runs in a pool thread whose future nobody reads: without this
            # the import just vanishes from the UI with no trace.
            log.exception("webimport: import of %s failed", path)
            raise
        finally:
            if session._lock_acquired:
                apply_lock.release()
            with _import_ctx_lock:
                _import_ctx["path"] = None
                _import_ctx["imported_album_id"] = None

    @app.get("/api/inbox")
    def api_inbox_list():
        """Lists album-sized directories under the inbox with import
        status and pending review status."""
        found = []
        base = Path(inbox_dir)
        running_paths = pool.running_paths()
        pending_list = review_manager.list_pending()
        pending_paths = {pr["path"] for pr in pending_list}

        def _add_dir(sub: Path):
            path_str = str(sub)
            marker_file = sub / ".webimport_imported"
            imported = False
            album_id = None
            imported_at = None
            staging_bin = "_grouped" in path_str
            if marker_file.exists():
                try:
                    import json

                    m_data = json.loads(marker_file.read_text(encoding="utf-8"))
                    imported = True
                    album_id = m_data.get("album_id")
                    imported_at = m_data.get("imported_at")
                    if "staging_bin" in m_data:
                        staging_bin = m_data.get("staging_bin", staging_bin)
                except Exception:
                    imported = True

            is_in_progress = path_str in running_paths
            is_pending_review = path_str in pending_paths

            found.append(
                {
                    "path": path_str,
                    "imported": imported,
                    "album_id": album_id,
                    "imported_at": imported_at,
                    "staging_bin": staging_bin,
                    "in_progress": is_in_progress,
                    "pending_review": is_pending_review,
                }
            )

        if base.is_dir():
            for sub in sorted(base.iterdir()):
                if sub.is_dir() and not sub.name.startswith("."):
                    if sub.name == "_grouped":
                        for grp in sorted(sub.iterdir()):
                            if grp.is_dir():
                                for bin_dir in sorted(grp.iterdir()):
                                    if bin_dir.is_dir():
                                        _add_dir(bin_dir)
                    else:
                        _add_dir(sub)
        return jsonify(
            {
                "inbox_dirs": found,
                "pending_review": pending_list,
                "activities": activities.as_json(),
            }
        )

    @app.post("/api/activity/dismiss")
    def api_activity_dismiss():
        """Remove a failed import/reimport's card."""
        key = (request.get_json(force=True) or {}).get("key", "")
        return jsonify({"ok": activities.dismiss(key)})

    @app.post("/api/inbox/delete")
    @_safe
    def api_inbox_delete():
        body = request.get_json(force=True)
        raw_path = body.get("path", "")
        if not raw_path:
            return jsonify({"ok": False, "error": "No path provided"}), 400
        target = Path(raw_path).resolve()
        base = Path(inbox_dir).resolve()
        if not inbox_dir or not str(target).startswith(str(base)) or target == base:
            return jsonify({"ok": False, "error": "Invalid path"}), 400
        if target.is_dir():
            import shutil

            shutil.rmtree(target)
            return jsonify({"ok": True})
        elif target.is_file():
            target.unlink()
            return jsonify({"ok": True})
        return jsonify({"ok": False, "error": "Not found"}), 404

    @app.post("/api/inbox/start")
    def api_inbox_start():
        """Body: {"paths": ["/inbox/preview/Some Album", ...]}
        Optional "search_ids": {"<path>": "<raw ID>"} pairs each path
        with a pre-specified backend search ID (Direct ID Import) -- a
        bare MBID/UUID or any ID-bearing URL the matching backend can
        parse, passed through verbatim (no client- or server-side URL
        parsing). Kicks off one WebImportSession per path in the worker
        pool (parallel candidate search/review)."""
        body = request.get_json(force=True)
        search_ids = body.get("search_ids") or {}
        for path in body.get("paths", []):
            _submit(activity.Activity(key=path, kind="import", label=Path(path).name, path=path),
                    lambda p=path, sid=search_ids.get(path): _run_album_import(p, sid))
        return jsonify({"submitted": len(body.get("paths", []))})

    @app.post("/api/inbox/group")
    @_safe
    def api_inbox_group():
        """Body: {"bins": [{"files": [...]}, {"files": [...], "singleton": true}]}
        Manual grouping support: moves files into per-bin staging
        subdirectories under the inbox so each bin becomes its own
        import task, then submits each bin.

        Simplification: rather than constructing ImportTask/
        SingletonImportTask objects directly in-process (which requires
        deeper hooking into ImportSession.read_tasks), this stages each
        bin into its own directory and imports that directory -- the
        practical effect is the same, and it keeps the file-grouping UI
        decoupled from importer internals that vary across beets
        versions.
        """
        import shutil
        import uuid

        body = request.get_json(force=True)
        base = Path(inbox_dir) / "_grouped" / uuid.uuid4().hex[:8]
        submitted_paths = []
        for i, bin_ in enumerate(body.get("bins", [])):
            bin_dir = base / f"bin_{i}"
            bin_dir.mkdir(parents=True, exist_ok=True)
            for f in bin_.get("files", []):
                src = Path(f)
                if src.exists():
                    shutil.move(str(src), str(bin_dir / src.name))
            _submit(activity.Activity(key=str(bin_dir), kind="import", label=bin_dir.name, path=str(bin_dir)),
                    lambda p=str(bin_dir): _run_album_import(p))
            submitted_paths.append(str(bin_dir))
        return jsonify({"submitted": submitted_paths})

    # -- review decisions ----------------------------------------------
    @app.get("/api/review/<task_id>")
    def api_review_get(task_id):
        pr = review_manager.get(task_id)
        if pr is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"task_id": task_id, "kind": pr.kind, "path": pr.path, "payload": pr.payload})

    def _inbox_folder(raw_path: str) -> Path | None:
        """Resolve `raw_path` to a directory inside the inbox, else None."""
        if not inbox_dir or not raw_path:
            return None
        base = Path(inbox_dir).resolve()
        target = Path(raw_path).resolve()
        if target == base or base not in target.parents or not target.is_dir():
            return None
        return target

    # -- album art choice (see artchoice.py) -----------------------------
    art_sources: dict[str, artchoice.ArtSource] = {}  # task_id -> source (iTunes IDs read once)
    art_sources_lock = threading.Lock()

    def _art_source(pr) -> artchoice.ArtSource | None:
        """An inbox import's folder, or a reimport's library album."""
        if pr is None:
            return None
        with art_sources_lock:
            if pr.task_id in art_sources:
                return art_sources[pr.task_id]
        folder = _inbox_folder(pr.path)
        if folder is not None:
            source = artchoice.ArtSource.inbox(folder)
        elif pr.kind == "match" and pr.task is not None and _in_library(pr.path):
            source = artchoice.ArtSource.library(Path(pr.path), pr.task.items)
        else:
            return None
        with art_sources_lock:
            if len(art_sources) > 200:
                art_sources.clear()
            art_sources[pr.task_id] = source
        return source

    def _in_library(raw_path: str) -> bool:
        base = Path(os.fsdecode(lib.directory)).resolve()
        target = Path(raw_path).resolve()
        return base in target.parents and target.is_dir()

    def _candidate_ids(pr, index) -> tuple | None:
        try:
            c = pr.payload["candidates"][index]
        except (KeyError, IndexError, TypeError):
            return None
        return (c.get("album_id"), c.get("releasegroup_id"))

    @app.post("/api/review/<task_id>/decide")
    def api_review_decide(task_id):
        decision = request.get_json(force=True)
        decision.pop("_art", None)  # server-side only
        action = decision.get("action")
        if action in ("select", "asis"):
            # Resolve the art choice to image bytes now, so a missing or
            # unreachable image is reported before anything is applied.
            pr = review_manager.get(task_id)
            source = _art_source(pr)
            if source is not None:
                ids = _candidate_ids(pr, decision.get("index")) if action == "select" else None
                choice = decision.get("art_choice")
                try:
                    if not choice:
                        choice = artchoice.default_choice(
                            artchoice.options(source),
                            artchoice.candidate_art(*ids) if ids else None)
                    decision["_art"] = artchoice.chosen_image(choice, source, ids)
                except Exception as exc:  # noqa: BLE001 -- don't apply with the wrong art
                    log.exception("webimport: art choice %r failed", choice)
                    return jsonify({"ok": False, "error": f"Couldn't use the chosen art: {exc}"}), 502
        ok = review_manager.submit_decision(task_id, decision)
        return jsonify({"ok": ok})

    @app.get("/api/review/<task_id>/tag_preview")
    @_safe
    def api_review_tag_preview(task_id):
        """What importing with candidate `index` would do to each file's
        tags (computed on copies; nothing is written)."""
        pr = review_manager.get(task_id)
        if pr is None or pr.task is None or pr.kind != "match":
            return jsonify({"error": "no such pending album review"}), 404
        try:
            index = int(request.args.get("index", "0"))
            if not 0 <= index < len(pr.task.candidates):
                raise ValueError
        except ValueError:
            return jsonify({"error": "bad candidate index"}), 400
        return jsonify(tagpreview.preview(pr.task, index))

    @app.get("/api/review/<task_id>/art_options")
    @_safe
    def api_review_art_options(task_id):
        """Art options for a review: an inbox import or a reimport."""
        source = _art_source(review_manager.get(task_id))
        if source is None:
            return jsonify({"keep": None, "folder": None, "itunes": None})
        return jsonify(artchoice.options(source))

    @app.get("/api/inbox/art_options")
    @_safe
    def api_inbox_art_options():
        """Art the files have now, a folder image, and iTunes art."""
        folder = _inbox_folder(request.args.get("path", ""))
        if folder is None:
            return jsonify({"error": "not an inbox folder"}), 400
        return jsonify(artchoice.inbox_options(folder))

    @app.get("/api/coverart/candidate")
    @_safe
    def api_coverart_candidate():
        """The release's Cover Art Archive front (or its release group's),
        downloaded once and served from /api/art/<key>."""
        r = artchoice.candidate_art(request.args.get("release") or None,
                                    request.args.get("releasegroup") or None)
        if r["state"] != "ok":
            return jsonify({"state": r["state"]})
        return jsonify({"state": "ok", "source": r["source"], **artchoice.describe(r["data"])})

    @app.get("/api/art/<key>")
    def api_art_image(key):
        data = artchoice.get(key)
        if data is None:
            return "", 404
        resp = app.response_class(data, mimetype=coverart._detect_mime_type(data))
        # Content-addressed (SHA-1 of the bytes): safe to cache forever.
        resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return resp

    @app.post("/api/inbox/release")
    @_safe
    def api_inbox_release():
        """Remove an imported folder's inbox copy (copy-mode leftovers) once
        every file can be restored exactly from the library."""
        body = request.get_json(force=True)
        if not inbox_dir or not body.get("path"):
            return jsonify({"error": "No path provided"}), 400
        if not apply_lock.acquire(timeout=120):
            return jsonify({"error": "An import is being applied; try again in a moment."}), 409
        try:
            return jsonify(lifecycle.release_folder(lib, Path(body["path"]), Path(inbox_dir)))
        except lifecycle.ReleaseRefused as exc:
            return jsonify({"error": str(exc), "problems": exc.problems}), 409
        finally:
            apply_lock.release()

    @app.get("/api/version")
    def api_version():
        """Which build is running: package version, commit, tags."""
        return jsonify(version.info())

    @app.get("/api/backfill")
    def api_backfill_status():
        """The last inbox-vs-library check, per inbox folder, and any job
        in progress."""
        if backfiller is None:
            return jsonify({"error": "no inbox configured"}), 400
        return jsonify(backfiller.status())

    @app.post("/api/backfill/scan")
    def api_backfill_scan():
        if backfiller is None:
            return jsonify({"error": "no inbox configured"}), 400
        if not backfiller.scan():
            return jsonify({"error": "A check or attach is already running."}), 409
        return jsonify({"started": True})

    @app.post("/api/backfill/apply")
    def api_backfill_apply():
        """Body: {"paths": [inbox folder, ...]}. Attaches or replaces the
        matched tracks in each folder (re-checked first)."""
        if backfiller is None:
            return jsonify({"error": "no inbox configured"}), 400
        paths = (request.get_json(force=True) or {}).get("paths") or []
        if not paths:
            return jsonify({"error": "No folders given"}), 400
        if not backfiller.apply(paths):
            return jsonify({"error": "A check or attach is already running."}), 409
        return jsonify({"started": True})

    # -- library browse / edit -------------------------------------------
    @app.get("/api/library/albums/<int:album_id>/undo_import")
    @_safe
    def api_library_undo_plan(album_id):
        """Dry run of Undo import: where each file would go and anything
        that prevents an exact restore."""
        album = lib.get_album(album_id)
        if album is None:
            return jsonify({"error": "no such album"}), 404
        return jsonify(restore.plan(album, inbox_dir).as_json())

    @app.post("/api/library/albums/<int:album_id>/undo_import")
    @_safe
    def api_library_undo_import(album_id):
        """Put the album's original files back in the inbox (byte for byte)
        and remove the album from the library."""
        album = lib.get_album(album_id)
        if album is None:
            return jsonify({"error": "no such album"}), 404
        if not apply_lock.acquire(timeout=120):
            return jsonify({"error": "An import is being applied; try again in a moment."}), 409
        try:
            result = restore.undo(lib, album, inbox_dir)
            mover.forget("album", album_id)
        except restore.UndoRefused as exc:
            return jsonify({"error": str(exc), **exc.plan.as_json()}), 409
        finally:
            apply_lock.release()
        return jsonify(result)

    @app.get("/api/library/listening_groups")
    def api_library_listening_groups():
        return jsonify(library.get_listening_groups(lib))

    @app.get("/api/library/albums")
    def api_library_albums():
        q = request.args.get("q", "")
        albums = library.search_albums(lib, q)
        states = mover.album_states()
        for a in albums:
            a["pending_move"] = states.get(a["id"], False)  # "waiting" | "misplaced" | False
        return jsonify(albums)

    @app.get("/api/library/pending_moves")
    def api_pending_moves():
        return jsonify({"navidrome": navidrome is not None, "pending": mover.pending()})

    @app.post("/api/library/pending_moves/move_all")
    @_safe
    def api_pending_move_all():
        """Move every album/track found away from its computed path."""
        return jsonify(mover.move_all_misplaced())

    @app.post("/api/library/pending_moves/<kind>/<int:obj_id>/move")
    @_safe
    def api_pending_move_now(kind, obj_id):
        if kind not in ("album", "item"):
            return jsonify({"ok": False, "error": "kind must be album or item"}), 400
        return jsonify({"ok": mover.move_now(kind, obj_id)})

    @app.get("/api/library/albums/<int:album_id>")
    def api_library_album_detail(album_id):
        detail = library.get_album_detail(lib, album_id)
        if detail is None:
            return jsonify({"error": "not found"}), 404
        detail["pending_move"] = next(
            (p for p in mover.pending() if p["kind"] == "album" and p["id"] == album_id), None
        )
        return jsonify(detail)

    @app.get("/api/library/albums/<int:album_id>/explore")
    @_safe
    def api_library_album_explore(album_id):
        data = library.get_album_explorer(lib, album_id)
        if data is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(data)

    @app.get("/api/library/albums/<int:album_id>/filetags")
    @_safe
    def api_library_album_filetags(album_id):
        """Diff of beets DB vs on-disk tags for each track (one file read
        per track). Fetched separately so the explorer renders first."""
        data = library.compare_album_file_tags(lib, album_id)
        if data is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(data)

    @app.get("/api/library/albums/<int:album_id>/artinfo")
    @_safe
    def api_library_album_artinfo(album_id):
        album = lib.get_album(album_id)
        if album is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"art": coverart.get_album_art_info(album)})

    @app.get("/api/library/items/<int:item_id>/art")
    def api_library_item_art(item_id):
        """The image embedded in this track's file (what players read)."""
        import mediafile

        item = lib.get_item(item_id)
        if item is None:
            return "", 404
        try:
            data = mediafile.MediaFile(syspath(item.path)).art
        except Exception:
            data = None
        if not data:
            return "", 404
        return app.response_class(data, mimetype=coverart._detect_mime_type(data))

    @app.get("/api/library/albums/<int:album_id>/art")
    def api_library_album_art(album_id):
        album = lib.get_album(album_id)
        if album is None:
            return "", 404
        thumb = request.args.get("thumb") in ("1", "true", "yes")
        data, mime_type = coverart.get_album_art_data(
            album, cache_dir=thumbs_dir, thumb=thumb
        )
        if data is None:
            return "", 404
        from flask import Response

        return Response(data, mimetype=mime_type)

    @app.post("/api/library/albums/<int:album_id>/fields")
    @_safe
    def api_library_album_set_fields(album_id):
        body = request.get_json(force=True)
        res = library.set_album_fields(
            lib,
            album_id,
            body.get("fields", {}),
            move=body.get("move", True),
            conflict_resolution=body.get("conflict_resolution"),
            mover=mover,
        )
        if res.get("conflict"):
            return jsonify(res), 409
        return jsonify(res)

    @app.post("/api/library/albums/bulk_fields")
    @_safe
    def api_library_bulk_fields():
        body = request.get_json(force=True)
        res = library.bulk_set_field(
            lib,
            body["album_ids"],
            body["field"],
            body["value"],
            move=body.get("move", True),
            conflict_resolution=body.get("conflict_resolution"),
            mover=mover,
        )
        if res.get("conflict"):
            return jsonify(res), 409
        return jsonify(res)

    @app.get("/api/library/items/<int:item_id>")
    def api_library_item_detail(item_id):
        detail = library.get_item_detail(lib, item_id)
        if detail is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(detail)

    @app.post("/api/library/items/<int:item_id>/fields")
    @_safe
    def api_library_item_set_fields(item_id):
        body = request.get_json(force=True)
        res = library.set_item_fields(
            lib,
            item_id,
            body.get("fields", {}),
            move=body.get("move", True),
            conflict_resolution=body.get("conflict_resolution"),
            mover=mover,
        )
        if res.get("conflict"):
            return jsonify(res), 409
        return jsonify(res)

    # -- tags -------------------------------------------------------------
    @app.get("/api/tags")
    def api_tags_list():
        return jsonify({f: tag_store.list_values(f) for f in tag_store.list_fields()})

    @app.post("/api/tags/<field>")
    @_safe
    def api_tags_add_value(field):
        body = request.get_json(force=True)
        tag_store.add_value(field, body["value"])
        return jsonify({"ok": True})

    @app.post("/api/tags/<field>/apply")
    @_safe
    def api_tags_apply(field):
        body = request.get_json(force=True)
        value = body["value"]
        add = body.get("add", True)
        if body.get("scope") == "album":
            album = lib.get_album(body["id"])
            if album is None:
                return jsonify({"ok": False}), 404
            tags.apply_tag_to_album(lib, album, field, value, add=add)
        else:
            item = lib.get_item(body["id"])
            if item is None:
                return jsonify({"ok": False}), 404
            tags.apply_tag_to_item(item, field, value, add=add)
        return jsonify({"ok": True})

    # -- reimport -----------------------------------------------------------
    @app.post("/api/reimport")
    @_safe
    def api_reimport():
        body = request.get_json(force=True)
        album_ids = body["album_ids"]
        search_id = body.get("search_id")
        from_scratch = body.get("from_scratch", False)
        set_fields = body.get("set_fields") or {}

        def _job():
            reimport.run_reimport(
                lib,
                review_manager,
                loghandler,
                album_ids,
                apply_lock=apply_lock,
                search_id=search_id,
                from_scratch=from_scratch,
                set_fields=set_fields,
                mover=mover,
                apple_music_match=wi_config["apple_music_match"].get(bool),
            )

        key = f"reimport:{','.join(map(str, album_ids))}"
        if activities.get(key) is not None and activities.get(key).state != "failed":
            return jsonify({"error": "This album is already being reimported."}), 409
        names = []
        for aid in album_ids:
            album = lib.get_album(aid)
            names.append(f"{album.albumartist} – {album.album}" if album else f"album {aid}")
        _submit(activity.Activity(key=key, kind="reimport", label="; ".join(names), album_ids=list(album_ids)), _job)
        return jsonify({"submitted": True, "key": key})

    # -- static frontend ----------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    return app

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from beets import config as beets_config
from beets.util import syspath

from . import coverart, library, reimport, tags
from .grace import GracePeriodManager
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

    review_manager = ReviewManager()
    apply_lock = threading.Lock()
    grace = GracePeriodManager(lib, wi_config["grace_period_seconds"].get(int))
    pool = InboxWorkerPool(wi_config["candidate_search_workers"].get(int))

    data_dir = Path(beets_config.config_dir()) / "webimport"
    tag_store = tags.TagStore(data_dir / "tags.json")
    for field in wi_config["tag_fields"].get(list):
        tag_store.add_field(field)

    inbox_dir = wi_config["inbox_dir"].get(str) or ""

    # -- capture successful imports for grace-period undo -----------------
    def _on_album_imported(lib, album):
        grace.register("album", album.id, f"{album.albumartist} - {album.album}")

    def _on_item_imported(lib, item):
        grace.register("item", item.id, f"{item.artist} - {item.title}")

    plugin.register_listener("album_imported", _on_album_imported)
    plugin.register_listener("item_imported", _on_item_imported)

    loghandler = None  # let beets use its default logging

    # -- inbox scanning / import kickoff -----------------------------------
    def _run_album_import(path: str):
        session = WebImportSession(
            lib,
            loghandler,
            paths=[os.fsencode(path)],
            query=None,
            review_manager=review_manager,
            config=wi_config,
            apply_lock=apply_lock,
        )
        try:
            session.run()
        finally:
            if session._lock_acquired:
                apply_lock.release()

    @app.get("/api/inbox")
    def api_inbox_list():
        """Lists album-sized directories under the inbox that haven't
        been submitted for import yet, plus anything currently pending
        review."""
        found = []
        base = Path(inbox_dir)
        if base.is_dir():
            for sub in sorted(base.iterdir()):
                if sub.is_dir():
                    found.append(str(sub))
        return jsonify(
            {
                "inbox_dirs": found,
                "pending_review": review_manager.list_pending(),
            }
        )

    @app.post("/api/inbox/start")
    def api_inbox_start():
        """Body: {"paths": ["/inbox/preview/Some Album", ...]}
        Kicks off one WebImportSession per path in the worker pool
        (parallel candidate search/review)."""
        body = request.get_json(force=True)
        for path in body.get("paths", []):
            pool.submit(path, _run_album_import)
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
            pool.submit(str(bin_dir), _run_album_import)
            submitted_paths.append(str(bin_dir))
        return jsonify({"submitted": submitted_paths})

    # -- review decisions ----------------------------------------------
    @app.get("/api/review/<task_id>")
    def api_review_get(task_id):
        pr = review_manager.get(task_id)
        if pr is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"task_id": task_id, "kind": pr.kind, "path": pr.path, "payload": pr.payload})

    @app.post("/api/review/<task_id>/decide")
    def api_review_decide(task_id):
        decision = request.get_json(force=True)
        ok = review_manager.submit_decision(task_id, decision)
        return jsonify({"ok": ok})

    # -- cover art (lazy, per focused candidate) -------------------------
    @app.post("/api/coverart/resolve")
    @_safe
    def api_coverart_resolve():
        body = request.get_json(force=True)
        fetchart_cfg = beets_config["fetchart"].get(dict) if "fetchart" in beets_config else {}
        result = coverart.resolve_candidate_art(
            item_dir=body["item_dir"],
            release_mbid=body.get("release_mbid"),
            release_group_mbid=body.get("release_group_mbid"),
            fetchart_config=fetchart_cfg,
        )
        return jsonify(result)

    # -- grace period / undo --------------------------------------------
    @app.get("/api/undo")
    def api_undo_list():
        return jsonify(grace.list_undoable())

    @app.post("/api/undo/<record_id>")
    def api_undo_do(record_id):
        ok = grace.undo(record_id)
        return jsonify({"ok": ok})

    # -- library browse / edit -------------------------------------------
    @app.get("/api/library/albums")
    def api_library_albums():
        q = request.args.get("q", "")
        return jsonify(library.search_albums(lib, q))

    @app.get("/api/library/albums/<int:album_id>")
    def api_library_album_detail(album_id):
        detail = library.get_album_detail(lib, album_id)
        if detail is None:
            return jsonify({"error": "not found"}), 404
        return jsonify(detail)

    @app.get("/api/library/albums/<int:album_id>/art")
    def api_library_album_art(album_id):
        album = lib.get_album(album_id)
        if album is None or not album.artpath:
            return "", 404
        art_path = Path(syspath(album.artpath))
        return send_from_directory(art_path.parent, art_path.name)

    @app.post("/api/library/albums/<int:album_id>/fields")
    @_safe
    def api_library_album_set_fields(album_id):
        body = request.get_json(force=True)
        ok = library.set_album_fields(
            lib, album_id, body.get("fields", {}), move=body.get("move", True)
        )
        return jsonify({"ok": ok})

    @app.post("/api/library/albums/bulk_fields")
    @_safe
    def api_library_bulk_fields():
        body = request.get_json(force=True)
        updated = library.bulk_set_field(
            lib,
            body["album_ids"],
            body["field"],
            body["value"],
            move=body.get("move", True),
        )
        return jsonify({"updated": updated})

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
        ok = library.set_item_fields(
            lib, item_id, body.get("fields", {}), move=body.get("move", True)
        )
        return jsonify({"ok": ok})

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
            )

        pool.submit(f"reimport:{','.join(map(str, album_ids))}", lambda _p: _job())
        return jsonify({"submitted": True})

    # -- static frontend ----------------------------------------------------
    @app.get("/")
    def index():
        return send_from_directory(STATIC_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(STATIC_DIR, filename)

    return app

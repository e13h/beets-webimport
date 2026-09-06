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

    # -- capture successful imports for grace-period undo -----------------
    def _on_album_imported(lib, album):
        with _import_ctx_lock:
            inbox_path = _import_ctx["path"]
            if inbox_path:
                _import_ctx["imported_album_id"] = album.id
        grace.register(
            "album",
            album.id,
            f"{album.albumartist} - {album.album}",
            inbox_path=inbox_path,
            is_staging_bin=bool(inbox_path and "_grouped" in str(inbox_path)),
        )

    def _on_item_imported(lib, item):
        with _import_ctx_lock:
            inbox_path = _import_ctx["path"]
        grace.register(
            "item",
            item.id,
            f"{item.artist} - {item.title}",
            inbox_path=inbox_path,
            is_staging_bin=bool(inbox_path and "_grouped" in str(inbox_path)),
        )

    plugin.register_listener("album_imported", _on_album_imported)
    plugin.register_listener("item_imported", _on_item_imported)

    loghandler = None  # let beets use its default logging

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
        try:
            session.run()
            with _import_ctx_lock:
                imported_album_id = _import_ctx["imported_album_id"]
            if imported_album_id is not None:
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
        grace.prune_expired()
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
                if sub.is_dir():
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
            }
        )

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
            pool.submit(path, lambda p, sid=search_ids.get(path): _run_album_import(p, sid))
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
    @app.get("/api/library/listening_groups")
    def api_library_listening_groups():
        return jsonify(library.get_listening_groups(lib))

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

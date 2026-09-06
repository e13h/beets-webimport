"""ImportSession subclass that replaces beets' terminal prompts with
calls into the web ReviewManager.

NOTE: beets' importer internals (`ImportTask`, `action`, candidate
matching helpers) have shifted slightly across versions. This targets
current (2.x) beets; if you're on a different version, check
`beets/importer.py` and `beets/autotag/__init__.py` for the exact
attribute names referenced below (`task.candidates`, `action.*`,
`task.lookup_candidates`, `task.should_remove_duplicates`).
"""
from __future__ import annotations

import logging

from beets import autotag, importer
from beets.importer import Action, DuplicateAction
from beets.util import displayable_path

log = logging.getLogger("beets.webimport")


def _serialize_album_match(i, match) -> dict:
    info = match.info
    return {
        "index": i,
        "distance": round(match.distance.distance, 4),
        "artist": info.artist,
        "album": info.album,
        "year": getattr(info, "year", None),
        "label": getattr(info, "label", None),
        "album_id": getattr(info, "album_id", None),
        "data_source": getattr(info, "data_source", None),
        "data_url": getattr(info, "data_url", None),
        "tracks": [
            {
                "index": t.index,
                "title": t.title,
                "length": t.length,
            }
            for t in info.tracks
        ],
        "extra_tracks": len(match.extra_tracks),
        "missing_tracks": len(getattr(match, "extra_items", [])),
    }


def _serialize_item_match(i, match) -> dict:
    info = match.info
    return {
        "index": i,
        "distance": round(match.distance.distance, 4),
        "artist": info.artist,
        "title": info.title,
        "album": getattr(info, "album", None),
        "data_source": getattr(info, "data_source", None),
        "data_url": getattr(info, "data_url", None),
    }


class WebImportSession(importer.ImportSession):
    """One instance is created per inbox path by the worker pool. Blocks
    the calling thread (not the Flask request thread) inside
    choose_match/choose_item/resolve_duplicate until the web UI submits
    a decision via ReviewManager.
    """

    def __init__(self, lib, loghandler, paths, query, review_manager, config, apply_lock=None):
        super().__init__(lib, loghandler, paths, query)
        self.review_manager = review_manager
        self.wi_config = config
        # Consumed once by choose_match, if set by reimport.py, to restrict
        # the very first candidate search to a specific backend ID
        # (equivalent of `-S <id>`) before presenting anything for review.
        self.preset_search_id: str | None = None
        # Serializes the apply phase across concurrently-reviewed tasks
        # (see queue.py docstring). Acquired just before returning a
        # final decision from choose_match/choose_item; released by the
        # caller once session.run() returns.
        self.apply_lock = apply_lock
        self._lock_acquired = False

    # -- album matching -----------------------------------------------
    def choose_match(self, task: importer.ImportTask):
        attempted_search_id = None
        # Consumed once per pass. Set either at session start (Direct ID
        # Import via the inbox-start endpoint / reimport) or by a
        # mid-review "search_id" decision -- including the UI's
        # "Auto-search instead" fallback, which sends a blank ID that
        # runs the normal broad search.
        if self.preset_search_id is not None:
            attempted_search_id, self.preset_search_id = self.preset_search_id, None
            self._lookup_candidates(task, attempted_search_id)

        candidates_payload = [
            _serialize_album_match(i, m) for i, m in enumerate(task.candidates)
        ]
        payload = {
            "path": displayable_path(task.paths[0]) if task.paths else "",
            "items": [displayable_path(i.path) for i in task.items],
            "candidates": candidates_payload,
            "rec": str(task.rec) if task.rec is not None else None,
        }
        if attempted_search_id:
            # Direct ID Import: make the attempted ID visible so the UI
            # can surface a failed/empty lookup for correction instead of
            # it looking like an ordinary zero-result search.
            payload["attempted_search_id"] = attempted_search_id
        pr = self.review_manager.register("match", payload["path"], payload)
        decision = self.review_manager.wait_for_decision(pr.task_id)

        return self._apply_decision_album(task, decision)

    def _lookup_candidates(self, task, search_id: str):
        """Runs the candidate search restricted to a specific backend ID
        (equivalent of `-S <id>`). An empty/blank search_id clears the
        restriction and runs the normal broad tag/acoustic search -- the
        UI's "Auto-search instead" fallback after a failed Direct ID
        lookup. Raw strings pass through verbatim: bare UUID, MusicBrainz
        release URL, Discogs release URL, anything the backend parses."""
        if not search_id or not search_id.strip():
            # Empty list = unrestricted search. lookup_candidates requires
            # the argument in beets 2.x (calling it bare raises TypeError
            # and kills the pipeline thread).
            task.lookup_candidates(search_ids=[])
            return
        try:
            task.lookup_candidates(search_ids=[search_id])
        except AttributeError:
            items = task.items
            _, _, prop = autotag.tag_album(items, search_ids=[search_id])
            task.candidates = prop.candidates
            task.rec = prop.recommendation

    def _acquire_apply_lock(self):
        if self.apply_lock is not None and not self._lock_acquired:
            self.apply_lock.acquire()
            self._lock_acquired = True

    def _apply_decision_album(self, task, decision):
        kind = decision.get("action")

        if kind == "skip":
            return Action.SKIP
        if kind == "asis":
            self._acquire_apply_lock()
            return Action.ASIS
        if kind == "tracks":
            self._acquire_apply_lock()
            return Action.TRACKS
        if kind == "albums":
            self._acquire_apply_lock()
            return Action.ALBUMS

        if kind == "search_id":
            # Re-run the candidate lookup restricted to this backend ID
            # (equivalent of `-S <id>`); a blank ID runs the normal
            # broad search. Routed through the same preset machinery as
            # the initial Direct ID Import so a failed retry also
            # surfaces attempted_search_id to the UI.
            self.preset_search_id = decision["search_id"]
            return self.choose_match(task)

        if kind == "select":
            self._acquire_apply_lock()
            idx = decision["index"]
            return task.candidates[idx]

        # Default: treat unrecognized decisions as a skip rather than
        # silently applying something unintended.
        log.warning("webimport: unrecognized decision %r, skipping", decision)
        return Action.SKIP

    # -- singleton (track) matching ------------------------------------
    def choose_item(self, task: importer.SingletonImportTask):
        candidates_payload = [
            _serialize_item_match(i, m) for i, m in enumerate(task.candidates)
        ]
        payload = {
            "path": displayable_path(task.item.path),
            "candidates": candidates_payload,
            "rec": str(task.rec) if task.rec is not None else None,
        }
        pr = self.review_manager.register("item", payload["path"], payload)
        decision = self.review_manager.wait_for_decision(pr.task_id)

        kind = decision.get("action")
        if kind == "skip":
            return Action.SKIP
        if kind == "asis":
            self._acquire_apply_lock()
            return Action.ASIS
        if kind == "search_id":
            search_id = decision["search_id"]
            try:
                task.lookup_candidates(search_ids=[search_id])
            except AttributeError:
                _, _, prop = autotag.tag_item(task.item, search_ids=[search_id])
                task.candidates = prop.candidates
                task.rec = prop.recommendation
            return self.choose_item(task)
        if kind == "select":
            self._acquire_apply_lock()
            return task.candidates[decision["index"]]

        log.warning("webimport: unrecognized item decision %r, skipping", decision)
        return Action.SKIP

    # -- duplicate resolution -------------------------------------------
    # NOTE: current beets calls this `get_duplicate_action`, not
    # `resolve_duplicate` -- it must return a DuplicateAction enum value
    # (the pipeline itself then performs the remove/skip/merge/keep
    # behavior; this hook only decides which).
    def get_duplicate_action(self, task, found_duplicates) -> DuplicateAction:
        payload = {
            "path": displayable_path(task.paths[0]) if getattr(task, "paths", None) else "",
            "duplicates": [
                {"id": d.id, "album": getattr(d, "album", None) or getattr(d, "title", None)}
                for d in found_duplicates
            ],
        }
        pr = self.review_manager.register("duplicate", payload["path"], payload)
        decision = self.review_manager.wait_for_decision(pr.task_id)

        choice = decision.get("action", "keep")
        mapping = {
            "skip": DuplicateAction.SKIP,
            "remove_old": DuplicateAction.REMOVE,
            "keep_both": DuplicateAction.KEEP,
            "merge": DuplicateAction.MERGE,
        }
        return mapping.get(choice, DuplicateAction.KEEP)

    # -- resume prompt: never interactively prompt; always resume -------
    def should_resume(self, path):
        return True

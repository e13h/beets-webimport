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
import os

import confuse

from beets import autotag, importer
from beets.importer import Action, DuplicateAction
from beets.util import displayable_path

from . import purchase, snapshot

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
        "releasegroup_id": getattr(info, "releasegroup_id", None),
        "media": getattr(info, "media", None),
        "country": getattr(info, "country", None),
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
        # A list restricts the search to several IDs at once (releases
        # linked from an Apple Music listing).
        self.preset_search_id: str | list[str] | None = None
        # Set with preset_search_id when the IDs came from an automatic
        # match (itunes.musicbrainz_match_for_dir) rather than the user.
        # Reported in the review payload; an empty result then falls back
        # to a normal search instead of showing the "no candidate" error.
        self.matched_via: dict | None = None
        # Image bytes chosen in the review, set as the album's art in the
        # file stage (artchoice.on_import_task_files). None: leave art alone.
        self.pending_art: bytes | None = None
        # The ID the pipeline's own first lookup was restricted to (see
        # set_config); reported once by choose_match as attempted_search_id.
        self._initial_search_id: str | None = None
        # Serializes the apply phase across concurrently-reviewed tasks
        # (see queue.py docstring). Acquired just before returning a
        # final decision from choose_match/choose_item; released by the
        # caller once session.run() returns.
        self.apply_lock = apply_lock
        self._lock_acquired = False

    def set_config(self, config):
        """beets' pipeline runs the first candidate lookup itself, before
        choose_match, restricted to `session.config["search_ids"]`. That
        view is the shared global import config, and sessions run in
        parallel, so a Direct ID can't be written there. Instead give this
        session a private config: a snapshot of the global sources with
        the ID overlaid. The pipeline then does only the targeted lookup
        instead of a broad search followed by a second ID lookup."""
        search_ids = self.preset_search_id
        if isinstance(search_ids, str):
            search_ids = [search_ids]
        search_ids = [s for s in (search_ids or []) if s and s.strip()]
        if search_ids:
            overlay = confuse.ConfigSource.of({"import": {"search_ids": search_ids}})
            config = confuse.RootView([overlay, *config.root().sources])["import"]
            self._initial_search_id = ", ".join(search_ids)
            self.preset_search_id = None
        super().set_config(config)

    # -- album matching -----------------------------------------------
    def choose_match(self, task: importer.ImportTask):
        snapshot.capture_task(task, self)
        attempted_search_id = None
        if self._initial_search_id is not None:
            # The pipeline already ran the targeted lookup (set_config).
            attempted_search_id, self._initial_search_id = self._initial_search_id, None
        # Consumed once per pass. Set either at session start (Direct ID
        # Import via the inbox-start endpoint / reimport) or by a
        # mid-review "search_id" decision -- including the UI's
        # "Auto-search instead" fallback, which sends a blank ID that
        # runs the normal broad search.
        if self.preset_search_id is not None:
            attempted_search_id, self.preset_search_id = self.preset_search_id, None
            self._lookup_candidates(task, attempted_search_id)

        matched_via, self.matched_via = self.matched_via, None
        if matched_via is not None and attempted_search_id:
            attempted_search_id = None  # automatic, not the user's ID
            if not task.candidates:
                # Linked release(s) couldn't be fetched: search normally.
                matched_via = {**matched_via, "fallback": True}
                self._lookup_candidates(task, "")

        purchase_info = None
        if not attempted_search_id and (matched_via is None or matched_via.get("fallback")):
            purchase_info = self._add_purchase_candidates(task)

        candidates_payload = [
            _serialize_album_match(i, m) for i, m in enumerate(task.candidates)
        ]
        if purchase_info:
            for c, m in zip(candidates_payload, task.candidates):
                c["looks_purchased"] = purchase.looks_purchased(m.info, purchase_info["year"])
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
        if matched_via is not None:
            payload["matched_via"] = matched_via
        if purchase_info:
            payload["purchase"] = purchase_info
        pr = self.review_manager.register("match", payload["path"], payload)
        decision = self.review_manager.wait_for_decision(pr.task_id)

        return self._apply_decision_album(task, decision)

    def _add_purchase_candidates(self, task) -> dict | None:
        """Store purchases: add the likeliest digital releases of the album
        (see purchase.py) to the candidates and list the ones that look
        like the purchased release first. Returns {"store", "year",
        "added"} for the review payload, or None if not a purchase."""
        if not self.paths or self.query is not None:
            return None
        try:
            folder = os.fsdecode(task.paths[0]) if task.paths else None  # beets keeps bytes
            store = purchase.detect_store(task.items, folder)
            if store is None:
                return None
            hints = purchase.album_hints(task.items)
            existing = [m.info.album_id for m in task.candidates]
            ids = purchase.digital_release_ids(hints, exclude=existing)
            added = 0
            if ids:
                before = list(task.candidates)
                self._lookup_candidates(task, ids)
                found = [m for m in task.candidates if m.info.album_id not in existing]
                added = len(found)
                task.candidates = before + found
            year = hints.get("year")
            task.candidates.sort(key=lambda m: (
                not purchase.looks_purchased(m.info, year), m.distance.distance))
            return {"store": store, "year": year, "added": added}
        except Exception:  # noqa: BLE001 -- never block a review on this
            log.warning("webimport: purchase candidate search failed", exc_info=True)
            return None

    def _lookup_candidates(self, task, search_id: str | list[str]):
        """Runs the candidate search restricted to a specific backend ID
        (equivalent of `-S <id>`). An empty/blank search_id clears the
        restriction and runs the normal broad tag/acoustic search -- the
        UI's "Auto-search instead" fallback after a failed Direct ID
        lookup. Raw strings pass through verbatim: bare UUID, MusicBrainz
        release URL, Discogs release URL, anything the backend parses."""
        if isinstance(search_id, list):
            task.lookup_candidates(search_ids=search_id)
            return
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
        # Resolved by the decide endpoint from the review's art choice.
        self.pending_art = decision.get("_art")

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
        snapshot.capture_task(task, self)
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

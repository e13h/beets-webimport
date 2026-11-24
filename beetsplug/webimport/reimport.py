"""Reimport (GUI equivalent of):

    beet import -L -S <mbid> --from-scratch --set navidrome_library=kids album:aladdin

The `--from-scratch` and `--set` equivalents are given to the session's
own tasks (`apply_reimport_settings`), not written to beets' global import
config: beets reads both only while applying, and the global config is
shared by every session. So a reimport searches and waits for review in
parallel with other imports and takes the Apply Lock only to apply, like
an inbox import (ADR-0005, revised).

When every track of the album has a stored original (ADR-0014), the
reimport starts from the original download's tags instead of the current
ones (`start_from_originals`), as a fresh import of that download would;
`from_scratch` is only offered for albums without them.

Goes through the same WebImportSession / ReviewManager mechanism as a
fresh import (per PRD), and suggests what a fresh import of the store
download would: for an iTunes purchase, the MusicBrainz release(s) linked
to its Apple Music listing and the iTunes Store art; for store purchases,
the likeliest digital releases. The store IDs are read from the files or,
when an earlier import rewrote their tags, from the stored originals.

With Navidrome integration on (a Mover that is `enabled`), the reimport is
two-phase (ADR-0011): the session writes the new tags with file moves
switched off in its private config (`hold_files`), so the files stay
put, and the albums are then handed to the Mover, which moves them once
Navidrome has scanned the new tags. A reimport to another
release changes the tracks' Navidrome IDs; tags and move together would
lose their history.
"""
from __future__ import annotations

import logging
import os

import beets

from .session import WebImportSession

log = logging.getLogger("beets.webimport")


def _build_query(album_ids: list[int]) -> str:
    """The reimport runs an *album* query (beets' query_tasks), so match
    the album's own `id`: `album_id` isn't an album field, and beets
    matches it as a substring there (album_id:6 also found 16, 26, 36...).
    beets' top-level `,` is OR."""
    return " , ".join(f"id:{int(aid)}" for aid in album_ids)


def run_reimport(
    lib,
    review_manager,
    loghandler,
    album_ids: list[int],
    apply_lock=None,
    search_id: str | None = None,
    from_scratch: bool = False,
    set_fields: dict | None = None,
    mover=None,
    apple_music_match: bool = False,
):
    """Runs synchronously in the calling (worker) thread -- caller is
    expected to invoke this inside a background thread/executor, same as
    a fresh inbox import."""
    query_str = _build_query(album_ids)
    two_phase = mover is not None and mover.enabled
    # Reimported items get new rows (beets replaces them by path), so find
    # them again by their paths, which don't change while files are held.
    paths = [item.path for aid in album_ids for item in lib.items(f"album_id:{aid}")]

    session = WebImportSession(
        lib,
        loghandler,
        paths=None,
        query=query_str,
        review_manager=review_manager,
        config=None,
        apply_lock=apply_lock,
    )
    session.hold_files = two_phase
    if search_id:
        session.preset_search_id = search_id  # consumed by choose_match on first pass
    else:
        # As for an inbox folder: iTunes purchases start from the
        # release(s) linked to their Apple Music listing.
        session.apple_match_items = apple_music_match
    session.reimport_set_fields = dict(set_fields or {})
    session.reimport_from_scratch = bool(from_scratch)
    # Only these files may be reimported, whatever the query finds.
    session.reimport_paths = {bytes(p) for p in paths}
    session.start_from_originals = True
    from . import activity

    activity.step("Loading the album from the library")
    try:
        session.run()
    finally:
        # The session takes the Apply Lock when a choice is applied.
        if session._lock_acquired:
            apply_lock.release()
    if two_phase:
        hand_to_mover(lib, mover, paths)


def hand_to_mover(lib, mover, paths) -> None:
    """Queue the albums now holding `paths` for their move."""
    from beets.dbcore.query import PathQuery

    seen = set()
    for path in paths:
        for item in lib.items(PathQuery("path", path)):
            key = item.album_id or -item.id
            if key in seen:
                continue
            seen.add(key)
            mover.relocate_item(item, wrote_tags=True)


def fields_to_set(obj, explicit: dict) -> dict:
    """What a reimport sets on an album or track (`--set` equivalent).

    The config's `import.set_fields` are defaults for new imports (the
    homelab sets `navidrome_library: unassigned`); a reimport applies them
    only where the album has no value, so it keeps its Listening Group.
    The fields set in the Reimport dialog always apply."""
    out = {}
    for field, view in beets.config["import"]["set_fields"].items():
        if field not in explicit and obj.get(field) in (None, ""):
            out[field] = str(view.get())
    out.update({k: str(v) for k, v in explicit.items()})
    return out


def apply_reimport_settings(task, explicit: dict, from_scratch: bool) -> None:
    """Give this reimport's task its settings instead of beets' global
    import config (which beets reads at apply time, and which every
    parallel session shares):

    - `from_scratch`: passed to the match's apply_metadata;
    - `set_fields`: applied right after `task.add`, which has copied the
      replaced album's fields onto the new rows (`reimport_metadata`).
      beets' own `task.set_fields` (global config) is switched off."""
    if not getattr(task, "is_album", False) or getattr(task, "_wi_reimport", None) is not None:
        return
    task._wi_reimport = {"set_fields": dict(explicit), "from_scratch": bool(from_scratch)}

    def apply_metadata():
        if task.match:
            task.match.apply_metadata(from_scratch=bool(from_scratch))

    original_add = task.add

    def add(lib):
        original_add(lib)
        album, items = task.album, list(task.imported_items())
        with lib.transaction():
            for obj in [*items, album]:
                if obj is None:
                    continue
                values = fields_to_set(obj, explicit)
                for field, value in values.items():
                    obj.set_parse(field, format(obj, value))
                if values:
                    obj.store()

    task.apply_metadata = apply_metadata
    task.add = add
    task.set_fields = lambda lib: None


def restore_original_tags(items, music_dir) -> bool:
    """Set each item's tag fields to its stored original's, all or nothing
    (an album half from originals would match as neither). False if any
    track has no original or it can't be rebuilt."""
    from . import originals

    items = list(items)
    tags = []
    for item in items:
        record = originals.load(item)
        if not record:
            return False
        try:
            tags.append(originals.read_tags(record, _abs_path(item.path, music_dir)))
        except Exception:  # noqa: BLE001 -- missing or changed: keep the current tags
            log.warning("webimport: couldn't read the original of %s", item.path, exc_info=True)
            return False
    for item, values in zip(items, tags):
        item.clear()
        for key, value in values.items():
            item[key] = value
    return True


def _abs_path(path, music_dir) -> bytes:
    """beets 2.x may hand out library-relative paths (see
    session._resolve_item_paths); this stage can run without the music dir
    bound, so resolve against the library's own directory."""
    path = os.fsencode(path)
    if not os.path.isabs(path) and music_dir:
        path = os.path.join(os.fsencode(music_dir), path)
    return path

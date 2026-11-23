"""Reimport (GUI equivalent of):

    beet import -L -S <mbid> --from-scratch --set navidrome_library=kids album:aladdin

Rather than reimplementing metadata-clearing/set-fields logic, this
temporarily flips beets' own `import.from_scratch` / `import.set_fields`
config for the duration of the reimport session, then restores the prior
values -- so it applies via the exact same code path the CLI flags use.

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
from contextlib import contextmanager

import beets

from .session import WebImportSession

log = logging.getLogger("beets.webimport")


def _build_query(album_ids: list[int]) -> str:
    """The reimport runs an *album* query (beets' query_tasks), so match
    the album's own `id`: `album_id` isn't an album field, and beets
    matches it as a substring there (album_id:6 also found 16, 26, 36...).
    beets' top-level `,` is OR."""
    return " , ".join(f"id:{int(aid)}" for aid in album_ids)


@contextmanager
def _temporary_import_config(from_scratch: bool, set_fields: dict | None):
    prev_from_scratch = beets.config["import"]["from_scratch"].get(bool)
    prev_set_fields = beets.config["import"]["set_fields"].get(dict)
    try:
        beets.config["import"]["from_scratch"].set(from_scratch)
        if set_fields:
            merged = dict(prev_set_fields or {})
            merged.update(set_fields)
            beets.config["import"]["set_fields"].set(merged)
        yield
    finally:
        beets.config["import"]["from_scratch"].set(prev_from_scratch)
        beets.config["import"]["set_fields"].set(prev_set_fields)


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

    from . import activity

    lock_acquired = False
    if apply_lock is not None:
        if not apply_lock.acquire(blocking=False):
            activity.step("Waiting for another import to finish applying")
            apply_lock.acquire()
        lock_acquired = True
    activity.step("Loading the album from the library")

    try:
        with _temporary_import_config(from_scratch, set_fields):
            session = WebImportSession(
                lib,
                loghandler,
                paths=None,
                query=query_str,
                review_manager=review_manager,
                config=None,
                apply_lock=apply_lock,
            )
            if lock_acquired:
                session._lock_acquired = True
            session.hold_files = two_phase
            if search_id:
                session.preset_search_id = search_id  # consumed by choose_match on first pass
            else:
                # As for an inbox folder: iTunes purchases start from the
                # release(s) linked to their Apple Music listing.
                session.apple_match_items = apple_music_match
            session.reimport_set_fields = dict(set_fields or {})
            # Only these files may be reimported, whatever the query finds.
            session.reimport_paths = {bytes(p) for p in paths}
            session.start_from_originals = True
            session.run()
    finally:
        if lock_acquired:
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


def keep_library_fields(task, explicit: dict) -> None:
    """Make `task.set_fields` apply only the fields the user asked for.

    The config's `import.set_fields` are defaults for new imports (the
    homelab sets `navidrome_library: unassigned`). beets applies them to a
    reimport too, right after copying the replaced album's fields onto the
    new rows (`reimport_metadata`), which would reset every album's
    Listening Group and move its files. So any field the user didn't set
    in the Reimport dialog goes back to what the album and tracks had."""
    if not getattr(task, "is_album", False):
        return
    original = task.set_fields

    def set_fields(lib):
        album, items = task.album, list(task.imported_items())
        keys = [k for k in beets.config["import"]["set_fields"].keys() if k not in explicit]
        before = ({k: album.get(k) for k in keys} if album is not None else {},
                  [{k: item.get(k) for k in keys} for item in items])
        original(lib)
        album_vals, item_vals = before
        with lib.transaction():
            for item, vals in zip(items, item_vals):
                _restore(item, vals)
            if album is not None:
                _restore(album, album_vals)

    task.set_fields = set_fields


def _restore(obj, values: dict) -> None:
    changed = False
    for key, value in values.items():
        if value is None or value == "":
            continue  # the album didn't have it: the default applies
        if obj.get(key) != value:
            obj[key] = value
            changed = True
    if changed:
        obj.store()


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

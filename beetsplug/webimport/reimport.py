"""Reimport (GUI equivalent of):

    beet import -L -S <mbid> --from-scratch --set navidrome_library=kids album:aladdin

Rather than reimplementing metadata-clearing/set-fields logic, this
temporarily flips beets' own `import.from_scratch` / `import.set_fields`
config for the duration of the reimport session, then restores the prior
values -- so it applies via the exact same code path the CLI flags use.

Goes through the same WebImportSession / ReviewManager mechanism as a
fresh import (per PRD).
"""
from __future__ import annotations

from contextlib import contextmanager

import beets

from .session import WebImportSession


def _build_query(album_ids: list[int]) -> str:
    # beets top-level `,` is OR; album_id is a valid Item field.
    return ", ".join(f"album_id:{aid}" for aid in album_ids)


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
):
    """Runs synchronously in the calling (worker) thread -- caller is
    expected to invoke this inside a background thread/executor, same as
    a fresh inbox import."""
    query_str = _build_query(album_ids)

    lock_acquired = False
    if apply_lock is not None:
        apply_lock.acquire()
        lock_acquired = True

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
            if search_id:
                session.preset_search_id = search_id  # consumed by choose_match on first pass
            session.run()
    finally:
        if lock_acquired:
            apply_lock.release()

"""beets 2.13 stores library paths relative to the music directory and
expands them using a ContextVar that `Library()` sets on the thread that
opens the library. Flask request threads and worker-pool threads start
with an empty context, so without rebinding, every path read there stays
relative: art lookups 404, and moves/deletes miss the real files.

Requests are run inside a fresh `contextvars.Context()` to reproduce a new
server thread (Flask's test client otherwise runs on the test's thread,
which already has the music dir set).
"""
from __future__ import annotations

import contextvars
from unittest.mock import MagicMock

from beets import context
from beets.library import Item

from beetsplug.webimport.queue import InboxWorkerPool
from beetsplug.webimport.server import create_app


def _app(lib, tmp_path):
    cfg = {
        "grace_period_seconds": MagicMock(get=lambda typ: 600),
        "candidate_search_workers": MagicMock(get=lambda typ: 1),
        "tag_fields": MagicMock(get=lambda typ: ["mood"]),
        "inbox_dir": MagicMock(get=lambda typ: str(tmp_path / "inbox")),
        "tag_store_path": MagicMock(get=lambda typ: str(tmp_path / "tags.json")),
    }
    return create_app(lib, cfg, MagicMock())


def _album_with_art(lib, tmp_path, create_wav_file):
    album_dir = tmp_path / "music" / "Artist" / "Album"
    track = create_wav_file(album_dir / "01.wav")
    cover = album_dir / "cover.jpg"
    cover.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)
    item = Item.from_path(str(track))
    item.album, item.albumartist = "Album", "Artist"
    lib.add(item)
    album = lib.add_album([item])
    album.artpath = str(cover).encode()
    album.store()
    return album


def test_paths_are_stored_relative(lib, tmp_path, create_wav_file):
    # Precondition for the bug: the homelab DB stores relative paths.
    album = _album_with_art(lib, tmp_path, create_wav_file)
    raw = lib._connection().execute(
        "select artpath from albums where id = ?", (album.id,)
    ).fetchone()[0]
    assert not bytes(raw).startswith(b"/")


def test_album_art_served_from_fresh_request_thread(lib, tmp_path, create_wav_file):
    album = _album_with_art(lib, tmp_path, create_wav_file)
    client = _app(lib, tmp_path).test_client()

    resp = contextvars.Context().run(client.get, f"/api/library/albums/{album.id}/art")
    assert resp.status_code == 200

    albums = contextvars.Context().run(client.get, "/api/library/albums").get_json()
    assert albums[0]["has_art"] is True


def test_worker_pool_threads_have_music_dir(lib):
    pool = InboxWorkerPool(1, initializer=lambda: context.set_music_dir(lib.directory))
    try:
        fut = contextvars.Context().run(pool.submit, "p", lambda p: context.get_music_dir())
        assert fut.result(timeout=5) == lib.directory
    finally:
        pool.shutdown()

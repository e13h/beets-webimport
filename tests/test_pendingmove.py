"""Pending Move (ADR-0011): moves after a tag write wait for a Navidrome
scan that started after the write. Hermetic: Navidrome is a fake."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import beets
import pytest
from beets.library import Item
from mediafile import MediaFile

import beetsplug.webimport.library as wi_lib
from beetsplug.webimport import reimport
from beetsplug.webimport.navidrome import NavidromeError
from beetsplug.webimport.pendingmove import Mover
from beetsplug.webimport.session import WebImportSession


class FakeNavidrome:
    def __init__(self):
        self.scanning = False
        self.last_scan = "T0"
        self.down = False
        self.scan_requests = 0

    def scan_status(self):
        if self.down:
            raise NavidromeError("connection refused")
        return {"scanning": self.scanning, "last_scan": self.last_scan}

    def start_scan(self):
        self.scan_requests += 1

    def finish_scan(self, stamp):
        self.scanning, self.last_scan = False, stamp


@pytest.fixture
def album(lib, tmp_path, create_wav_file):
    src = tmp_path / "music" / "Artist" / "Album" / "01 Song.wav"
    create_wav_file(src)
    item = Item.from_path(str(src))
    item.update({"artist": "Artist", "albumartist": "Artist", "album": "Album",
                 "title": "Song", "track": 1})
    lib.add(item)
    item.write()
    album = lib.add_album([item])
    album.update({"album": "Album", "albumartist": "Artist"})
    album.store()
    return album


def only_item(album):
    return list(album.items())[0]


def file_title(item):
    return MediaFile(os.fsdecode(item.path)).title


def at_computed_path(album):
    item = only_item(album)
    return bytes(item.path) == bytes(item.destination())


def test_without_navidrome_tags_are_written_and_files_move_at_once(lib, album):
    res = wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=Mover(lib, None))
    assert res["move"] == "moved"
    assert at_computed_path(album)
    assert file_title(only_item(album)) == "New"


def test_flexible_field_edit_moves_at_once_without_touching_tags(lib, album):
    item = only_item(album)
    mtime = os.stat(item.path).st_mtime_ns
    mover = Mover(lib, FakeNavidrome())
    lib.path_formats = [("default", "$navidrome_library/$albumartist/$album/$track $title")]

    res = wi_lib.set_album_fields(lib, album.id, {"navidrome_library": "kids"}, mover=mover)

    assert res["move"] == "moved"
    item = only_item(album)
    assert b"/kids/" in bytes(item.path)
    assert os.stat(item.path).st_mtime_ns == mtime  # same bytes Navidrome already saw


def test_tag_edit_writes_tags_now_and_moves_after_a_later_scan(lib, album):
    nd = FakeNavidrome()
    mover = Mover(lib, nd)
    old = bytes(only_item(album).path)

    res = wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)

    assert res["move"] == "pending"
    assert file_title(only_item(album)) == "New"  # phase 1: tags only
    assert bytes(only_item(album).path) == old
    mover.tick()  # Navidrome idle: remember its last scan
    mover.tick()  # no new scan yet
    assert mover.is_pending("album", album.id)
    nd.finish_scan("T1")
    mover.tick()
    assert not mover.is_pending("album", album.id)
    assert at_computed_path(album)


def test_a_scan_already_running_at_the_write_does_not_count(lib, album):
    """lastScan is a finish time: the scan running during the write may
    have read the folder before it. Only the next one is safe."""
    nd = FakeNavidrome()
    nd.scanning = True
    mover = Mover(lib, nd)
    wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)

    mover.tick()
    nd.finish_scan("T1")  # the scan that was running at the write
    mover.tick()
    assert mover.is_pending("album", album.id)
    nd.finish_scan("T2")
    mover.tick()
    assert at_computed_path(album)


def test_flexible_edit_while_pending_keeps_waiting(lib, album):
    nd = FakeNavidrome()
    mover = Mover(lib, nd)
    wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)
    lib.path_formats = [("default", "$navidrome_library/$albumartist/$album/$track $title")]

    res = wi_lib.set_album_fields(lib, album.id, {"navidrome_library": "kids"}, mover=mover)

    assert res["move"] == "pending"
    assert not at_computed_path(album)


def test_unreachable_navidrome_keeps_the_move_pending(lib, album):
    nd = FakeNavidrome()
    nd.down = True
    mover = Mover(lib, nd)
    wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)
    mover.tick()
    [entry] = mover.pending()
    assert "can't reach Navidrome" in entry["reason"]
    assert not at_computed_path(album)


def test_move_now_overrides_the_wait(lib, album):
    mover = Mover(lib, FakeNavidrome())
    wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)
    assert mover.move_now("album", album.id)
    assert at_computed_path(album)
    assert mover.pending() == []


def test_requests_a_scan_when_none_comes(lib, album):
    nd = FakeNavidrome()
    mover = Mover(lib, nd, trigger_scan_after=0)
    wi_lib.set_album_fields(lib, album.id, {"title": "New"}, mover=mover)
    mover.tick()  # arm
    mover.tick()  # still no scan: ask for one
    mover.tick()
    assert nd.scan_requests == 1


def test_mismatches_found_at_startup_wait_for_move_now(lib, album):
    lib.path_formats = [("default", "elsewhere/$title")]
    nd = FakeNavidrome()
    mover = Mover(lib, nd)
    assert mover.discover() == 1
    mover.tick()
    nd.finish_scan("T1")
    mover.tick()
    assert mover.is_pending("album", album.id)
    assert not at_computed_path(album)


def test_reimport_session_holds_files_without_touching_global_config(lib):
    beets.config["import"]["move"].set(True)
    session = WebImportSession(lib, None, None, "x", MagicMock(), None)
    session.hold_files = True
    session.set_config(beets.config["import"])
    assert not session.config["move"].get(bool)
    assert not session.config["copy"].get(bool)
    assert beets.config["import"]["move"].get(bool)  # parallel reviews unaffected


def test_reimported_albums_are_found_by_path_and_queued(lib, album):
    """Reimport replaces item rows, so they're found again by path."""
    mover = Mover(lib, FakeNavidrome())
    path = only_item(album).path
    album.album = "Other Release"
    album.store(inherit=True)  # as a reimport would leave it: new tags, old path
    reimport.hand_to_mover(lib, mover, [path])
    assert mover.is_pending("album", album.id)


def test_move_all_moves_startup_mismatches_but_not_moves_waiting_for_a_scan(lib, album, tmp_path, create_wav_file):
    src = tmp_path / "music" / "Other" / "Waits" / "01 Song.wav"
    create_wav_file(src)
    item = Item.from_path(str(src))
    item.update({"artist": "Other", "albumartist": "Other", "album": "Waits", "title": "Song", "track": 1})
    lib.add(item)
    waiting = lib.add_album([item])
    lib.path_formats = [("default", "elsewhere/$albumartist/$title")]
    mover = Mover(lib, FakeNavidrome())
    assert mover.discover() == 2
    wi_lib.set_album_fields(lib, waiting.id, {"title": "New"}, mover=mover)  # now waits for a scan
    assert mover.album_states() == {album.id: "misplaced", waiting.id: "waiting"}

    assert mover.move_all_misplaced() == {"moved": 1, "failed": []}
    assert at_computed_path(album)
    assert not at_computed_path(waiting)
    assert mover.album_states() == {waiting.id: "waiting"}


def test_move_all_keeps_a_failed_move_listed(lib, album, monkeypatch):
    lib.path_formats = [("default", "elsewhere/$title")]
    mover = Mover(lib, FakeNavidrome())
    mover.discover()
    monkeypatch.setattr(Mover, "_move", lambda self, kind, obj: (_ for _ in ()).throw(OSError("disk full")))
    res = mover.move_all_misplaced()
    assert res["moved"] == 0 and res["failed"][0]["id"] == album.id
    assert mover.album_states() == {album.id: "misplaced"}
    assert "disk full" in mover.pending()[0]["reason"]

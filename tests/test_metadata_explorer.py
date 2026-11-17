"""Read-only metadata explorer: album + track fields, and discrepancies
between the beets database and the tags actually written to each file
(which is what Navidrome reads)."""
from __future__ import annotations

import os

import pytest
from beets.library import Item
from mediafile import MediaFile

from beetsplug.webimport import library


@pytest.fixture
def album(lib, tmp_path, create_wav_file):
    items = []
    for n in (1, 2):
        path = create_wav_file(tmp_path / "music" / "Artist" / "Album" / f"0{n}.wav")
        item = Item.from_path(str(path))
        item.update({"title": f"Song {n}", "artist": "Artist", "albumartist": "Artist",
                     "album": "Album", "track": n, "year": 1999, "genres": ["Rock"]})
        lib.add(item)
        item.write()
        items.append(item)
    alb = lib.add_album(items)
    alb["navidrome_library"] = "kids"  # flexible (custom) field
    alb.store()
    return alb


def test_explorer_returns_album_and_track_fields(lib, album):
    data = library.get_album_explorer(lib, album.id)
    assert data["album"]["fields"]["album"] == "Album"
    assert data["album"]["fields"]["navidrome_library"] == "kids"
    assert "navidrome_library" in data["album"]["custom_fields"]
    assert [t["fields"]["title"] for t in data["tracks"]] == ["Song 1", "Song 2"]
    # Paths are decoded to strings for display.
    assert data["tracks"][0]["fields"]["path"].endswith("01.wav")
    # Which album fields tracks also carry (for "varies" / "from album").
    assert "year" in data["item_keys"] and "artpath" not in data["item_keys"]
    assert "length" in data["readonly_fields"]


def test_explorer_missing_album(lib):
    assert library.get_album_explorer(lib, 999) is None


def test_file_tags_match_after_write(lib, album):
    result = library.compare_album_file_tags(lib, album.id)
    for track in result["tracks"]:
        assert track["error"] is None
        assert track["mismatches"] == [], track["mismatches"]


def test_db_change_not_written_is_a_mismatch(lib, album):
    item = next(iter(album.items()))
    item.title = "Renamed In DB"
    item.store()  # no write(): file still says "Song 1"
    result = library.compare_album_file_tags(lib, album.id)
    by_id = {t["id"]: t for t in result["tracks"]}
    mm = by_id[item.id]["mismatches"]
    assert {"field": "title", "db": "Renamed In DB", "file": "Song 1"} in mm


def test_external_tag_edit_is_a_mismatch(lib, album):
    item = next(iter(album.items()))
    mf = MediaFile(item.path.decode())
    mf.year = 2005
    mf.save()
    result = library.compare_album_file_tags(lib, album.id)
    mm = {m["field"]: m for t in result["tracks"] for m in t["mismatches"]}
    assert mm["year"]["db"] == 1999 and mm["year"]["file"] == 2005


def test_missing_file_reports_error(lib, album):
    item = next(iter(album.items()))
    os.remove(item.path)
    result = library.compare_album_file_tags(lib, album.id)
    by_id = {t["id"]: t for t in result["tracks"]}
    assert by_id[item.id]["error"]

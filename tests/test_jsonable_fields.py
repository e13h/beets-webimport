from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from beets.library import Item, Library

from beetsplug.webimport.library import _jsonable_fields


def test_jsonable_fields_roundtrips_bytes_fields_to_json(lib: Library, tmp_path: Path):
    track_path = os.fsencode(str(tmp_path / "music" / "01 Track.mp3"))
    art_path = os.fsencode(str(tmp_path / "music" / "cover.jpg"))

    item = Item(
        title="Sample Song",
        artist="Sample Artist",
        album="Sample Album",
        path=track_path,
    )
    lib.add(item)

    album = lib.add_album([item])
    album.artpath = art_path
    album.store()

    # Raw dict() with bytes fields fails json.dumps
    with pytest.raises(TypeError):
        json.dumps(dict(item))

    # _jsonable_fields produces serializable dictionaries
    item_jsonable = _jsonable_fields(item)
    album_jsonable = _jsonable_fields(album)

    serialized_item = json.dumps(item_jsonable)
    serialized_album = json.dumps(album_jsonable)

    assert isinstance(serialized_item, str)
    assert isinstance(serialized_album, str)

    # Deserializing back reproduces dictionary with expected primitive types
    parsed_item = json.loads(serialized_item)
    parsed_album = json.loads(serialized_album)
    assert parsed_item["title"] == "Sample Song"
    assert parsed_album["album"] == "Sample Album"


def test_decoded_values_match_original_paths(lib: Library, tmp_path: Path):
    track_path_str = str(tmp_path / "music" / "01 - Chançon d'été.flac")
    art_path_str = str(tmp_path / "music" / "folder.png")

    track_path_bytes = os.fsencode(track_path_str)
    art_path_bytes = os.fsencode(art_path_str)

    item = Item(
        title="Chançon d'été",
        artist="Artiste",
        album="Album",
        path=track_path_bytes,
    )
    lib.add(item)

    album = lib.add_album([item])
    album.artpath = art_path_bytes
    album.store()

    item_dict = _jsonable_fields(item)
    album_dict = _jsonable_fields(album)

    assert item_dict["path"] == os.fsdecode(track_path_bytes)
    assert album_dict["artpath"] == os.fsdecode(art_path_bytes)


def test_none_fields_decode_to_none_without_raising(lib: Library, tmp_path: Path):
    track_path_bytes = os.fsencode(str(tmp_path / "track.mp3"))
    item = Item(
        title="Single",
        artist="Artist",
        album="Album",
        path=track_path_bytes,
    )
    lib.add(item)

    album = lib.add_album([item])
    album.artpath = None
    album.store()

    album_dict = _jsonable_fields(album)
    assert album_dict.get("artpath") is None

    # Should serialize without error
    serialized = json.dumps(album_dict)
    assert json.loads(serialized)["artpath"] is None

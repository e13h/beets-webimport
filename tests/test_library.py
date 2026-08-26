from __future__ import annotations

import os
from pathlib import Path

from beets.library import Item
from beets.util import syspath
import beetsplug.webimport.library as wi_lib


def test_get_listening_groups(lib):
    assert wi_lib.get_listening_groups(lib) == []

    item1 = Item(title="Song 1", artist="Artist", navidrome_library="kids")
    lib.add(item1)
    album1 = lib.add_album([item1])
    album1.album = "Album 1"
    album1.navidrome_library = "kids"
    album1.store()

    item2 = Item(title="Song 2", artist="Artist", navidrome_library="worship")
    lib.add(item2)
    album2 = lib.add_album([item2])
    album2.album = "Album 2"
    album2.navidrome_library = "worship"
    album2.store()

    # Unassigned or empty
    item3 = Item(title="Song 3", artist="Artist", navidrome_library="")
    lib.add(item3)

    groups = wi_lib.get_listening_groups(lib)
    assert groups == ["kids", "worship"]


def test_placement_conflict_detection_and_skip(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    src_file = music_dir / "OriginalArtist" / "Album" / "track1.wav"
    create_wav_file(src_file)

    item = Item.from_path(str(src_file))
    item.artist = "OriginalArtist"
    item.albumartist = "OriginalArtist"
    item.album = "Album"
    item.title = "Track 1"
    item.track = 1
    lib.add(item)
    album = lib.add_album([item])
    album.album = "Album"
    album.albumartist = "OriginalArtist"
    album.store()

    # Pre-occupy colliding destination for NewArtist
    colliding_dest = music_dir / "NewArtist" / "Album" / "01 Track 1.wav"
    create_wav_file(colliding_dest)
    colliding_dest.write_text("unrelated existing content")

    # Attempt to change albumartist to NewArtist without conflict_resolution
    res = wi_lib.set_album_fields(
        lib, album.id, {"albumartist": "NewArtist", "artist": "NewArtist"}, move=True
    )
    assert res.get("conflict") is True
    assert res.get("destination") == str(colliding_dest)

    # Database was reverted / not changed
    reloaded_album = lib.get_album(album.id)
    assert reloaded_album.albumartist == "OriginalArtist"
    reloaded_item = lib.get_item(item.id)
    assert reloaded_item.albumartist == "OriginalArtist"
    assert src_file.exists()
    assert colliding_dest.read_text() == "unrelated existing content"

    # Now explicitly pass conflict_resolution="skip"
    res_skip = wi_lib.set_album_fields(
        lib,
        album.id,
        {"albumartist": "NewArtist", "artist": "NewArtist"},
        move=True,
        conflict_resolution="skip",
    )
    assert res_skip.get("ok") is True
    assert res_skip.get("action") == "skip"
    assert res_skip.get("reverted") is True

    # Confirm DB values are OriginalArtist and files unmoved
    reloaded_album = lib.get_album(album.id)
    assert reloaded_album.albumartist == "OriginalArtist"
    assert src_file.exists()


def test_placement_conflict_overwrite(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    src_file = music_dir / "OriginalArtist" / "Album" / "track1.wav"
    create_wav_file(src_file)

    item = Item.from_path(str(src_file))
    item.artist = "OriginalArtist"
    item.albumartist = "OriginalArtist"
    item.album = "Album"
    item.title = "Track 1"
    item.track = 1
    lib.add(item)
    album = lib.add_album([item])
    album.album = "Album"
    album.albumartist = "OriginalArtist"
    album.store()

    colliding_dest = music_dir / "NewArtist" / "Album" / "01 Track 1.wav"
    create_wav_file(colliding_dest)
    colliding_dest.write_text("old file to overwrite")

    res_ow = wi_lib.set_album_fields(
        lib,
        album.id,
        {"albumartist": "NewArtist", "artist": "NewArtist"},
        move=True,
        conflict_resolution="overwrite",
    )
    assert res_ow.get("ok") is True
    assert res_ow.get("action") == "overwrite"

    reloaded_album = lib.get_album(album.id)
    assert reloaded_album.albumartist == "NewArtist"
    assert colliding_dest.exists()
    reloaded_item = lib.get_item(item.id)
    assert Path(syspath(reloaded_item.path)) == colliding_dest


def test_placement_conflict_keep_both(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    src_file = music_dir / "OriginalArtist" / "Album" / "track1.wav"
    create_wav_file(src_file)

    item = Item.from_path(str(src_file))
    item.artist = "OriginalArtist"
    item.albumartist = "OriginalArtist"
    item.album = "Album"
    item.title = "Track 1"
    item.track = 1
    lib.add(item)
    album = lib.add_album([item])
    album.album = "Album"
    album.albumartist = "OriginalArtist"
    album.store()

    colliding_dest = music_dir / "NewArtist" / "Album" / "01 Track 1.wav"
    create_wav_file(colliding_dest)
    colliding_dest.write_text("existing file to preserve")

    res_kb = wi_lib.set_album_fields(
        lib,
        album.id,
        {"albumartist": "NewArtist", "artist": "NewArtist"},
        move=True,
        conflict_resolution="keep_both",
    )
    assert res_kb.get("ok") is True
    assert res_kb.get("action") == "keep_both"

    reloaded_album = lib.get_album(album.id)
    assert reloaded_album.albumartist == "NewArtist"
    # Both the existing colliding file and new file exist
    assert colliding_dest.exists()
    assert colliding_dest.read_text() == "existing file to preserve"
    reloaded_item = lib.get_item(item.id)
    assert Path(syspath(reloaded_item.path)).exists()
    assert Path(syspath(reloaded_item.path)) != colliding_dest

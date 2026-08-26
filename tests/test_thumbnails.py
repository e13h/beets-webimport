from __future__ import annotations

import io
from pathlib import Path

from beets.library import Item
import beetsplug.webimport.coverart as wi_coverart
import mediafile


def test_thumbnail_from_artpath(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    track_file = music_dir / "Artist" / "Album" / "track1.wav"
    create_wav_file(track_file)

    cover_file = music_dir / "Artist" / "Album" / "cover.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 200)  # JPEG magic bytes

    item = Item.from_path(str(track_file))
    item.artist = "Artist"
    item.album = "Album"
    item.title = "Track 1"
    lib.add(item)
    album = lib.add_album([item])
    album.artpath = str(cover_file).encode("utf-8")
    album.store()

    cache_dir = tmp_path / "cache" / "thumbs"
    data, mime = wi_coverart.get_album_art_data(album, cache_dir=cache_dir, thumb=True)
    assert data is not None
    assert mime == "image/jpeg"
    assert len(list(cache_dir.glob("thumb_album_*"))) == 1


def test_thumbnail_cache_invalidation_on_art_change(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    track_file = music_dir / "Artist" / "Album" / "track1.wav"
    create_wav_file(track_file)

    cover_file = music_dir / "Artist" / "Album" / "cover.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff\xe0" + b"art_v1" * 30)

    item = Item.from_path(str(track_file))
    item.artist = "Artist"
    item.album = "Album"
    item.title = "Track 1"
    lib.add(item)
    album = lib.add_album([item])
    album.artpath = str(cover_file).encode("utf-8")
    album.store()

    cache_dir = tmp_path / "cache" / "thumbs"
    data1, _ = wi_coverart.get_album_art_data(album, cache_dir=cache_dir, thumb=True)
    assert data1 is not None

    # Mutate cover file with new mtime / content
    import time

    time.sleep(0.05)  # slight pause for nanosecond mtime change
    cover_file.write_bytes(b"\xff\xd8\xff\xe0" + b"art_v2_updated" * 30)

    data2, _ = wi_coverart.get_album_art_data(album, cache_dir=cache_dir, thumb=True)
    assert data2 is not None
    assert data2 != data1
    # Only 1 cached thumbnail file should remain for this album
    assert len(list(cache_dir.glob(f"thumb_album_{album.id}_*"))) == 1


def test_thumbnail_fallback_to_embedded_art(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    track_file = music_dir / "Artist" / "Album" / "track1.wav"
    create_wav_file(track_file)

    # Embed art in track
    mf = mediafile.MediaFile(str(track_file))
    raw_embedded_art = b"\xff\xd8\xff\xe0" + b"embedded_image_data" * 20
    mf.art = raw_embedded_art
    mf.save()

    item = Item.from_path(str(track_file))
    item.artist = "Artist"
    item.album = "Album"
    item.title = "Track 1"
    lib.add(item)
    album = lib.add_album([item])
    album.artpath = None  # null artpath
    album.store()

    cache_dir = tmp_path / "cache" / "thumbs"
    data, mime = wi_coverart.get_album_art_data(album, cache_dir=cache_dir, thumb=True)
    assert data is not None
    assert mime == "image/jpeg"
    assert len(list(cache_dir.glob(f"thumb_album_{album.id}_*"))) == 1


def test_thumbnail_no_art_returns_none(lib, tmp_path, create_wav_file):
    music_dir = tmp_path / "music"
    track_file = music_dir / "Artist" / "Album" / "track1.wav"
    create_wav_file(track_file)

    item = Item.from_path(str(track_file))
    item.artist = "Artist"
    item.album = "Album"
    item.title = "Track 1"
    lib.add(item)
    album = lib.add_album([item])
    album.artpath = None
    album.store()

    cache_dir = tmp_path / "cache" / "thumbs"
    data, mime = wi_coverart.get_album_art_data(album, cache_dir=cache_dir, thumb=True)
    assert data is None
    assert mime == ""

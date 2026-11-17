"""Album art details for the metadata explorer: dimensions/size/format
without depending on Pillow, the album's art source, and per-track
embedded art (so tracks with different or missing art stand out)."""
from __future__ import annotations

import struct
import zlib

import pytest
from beets.library import Item
from mediafile import Image as MFImage, MediaFile

from beetsplug.webimport import coverart, library


def jpeg(width, height, filler=b""):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    app0 = b"\xff\xe0" + struct.pack(">H", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    return b"\xff\xd8" + app0 + sof0 + filler + b"\xff\xd9"


def png(width, height):
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = struct.pack(">I", len(ihdr)) + b"IHDR" + ihdr + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr))
    return b"\x89PNG\r\n\x1a\n" + chunk


@pytest.mark.parametrize("data,dims,mime", [
    (jpeg(600, 500), (600, 500), "image/jpeg"),
    (png(1400, 1400), (1400, 1400), "image/png"),
    (b"GIF89a" + struct.pack("<HH", 320, 240) + b"\x00" * 8, (320, 240), "image/gif"),
])
def test_image_info_without_pillow(monkeypatch, data, dims, mime):
    monkeypatch.setattr(coverart, "HAVE_PIL", False)
    info = coverart.image_info(data)
    assert (info["width"], info["height"]) == dims
    assert info["mime"] == mime
    assert info["bytes"] == len(data)
    assert len(info["sha1"]) == 40


def test_image_info_unparseable_still_reports_size():
    info = coverart.image_info(b"\xff\xd8garbage")
    assert info["width"] is None and info["bytes"] == 9


def _embed(path, data):
    mf = MediaFile(str(path))
    mf.images = [MFImage(data=data, type=3)]  # 3 = front cover
    mf.save()


@pytest.fixture
def album(lib, tmp_path, create_wav_file):
    items = []
    for n in (1, 2, 3):
        path = create_wav_file(tmp_path / "music" / "A" / "B" / f"0{n}.wav")
        item = Item.from_path(str(path))
        item.update({"title": f"T{n}", "album": "B", "albumartist": "A", "track": n})
        lib.add(item)
        item.write()
        items.append(item)
    _embed(items[0].path.decode(), jpeg(600, 600))
    _embed(items[1].path.decode(), jpeg(500, 500))  # different art
    # items[2]: no embedded art
    for item in items:
        item.read()  # refresh mtime so files don't look modified outside beets
        item.store()
    return lib.add_album(items)


def test_album_art_info_embedded(lib, album):
    info = coverart.get_album_art_info(album)
    assert info["source"] == "embedded"
    assert (info["width"], info["height"]) == (600, 600)
    assert info["track_id"] == sorted(album.items(), key=lambda i: i.track)[0].id


def test_album_art_info_prefers_art_file(lib, album, tmp_path):
    cover = tmp_path / "music" / "A" / "B" / "cover.png"
    cover.write_bytes(png(1000, 1000))
    album.artpath = str(cover).encode()
    album.store()
    info = coverart.get_album_art_info(album)
    assert info["source"] == "file" and info["path"].endswith("cover.png")
    assert (info["width"], info["height"]) == (1000, 1000)


def test_album_without_art(lib, tmp_path, create_wav_file):
    path = create_wav_file(tmp_path / "music" / "X" / "Y" / "01.wav")
    item = Item.from_path(str(path))
    lib.add(item)
    alb = lib.add_album([item])
    assert coverart.get_album_art_info(alb) is None


def test_filetags_include_each_tracks_embedded_art(lib, album):
    result = library.compare_album_file_tags(lib, album.id)
    arts = {t["id"]: t["art"] for t in result["tracks"]}
    by_track = {i.track: i.id for i in album.items()}
    assert arts[by_track[1]]["width"] == 600
    assert arts[by_track[2]]["width"] == 500
    assert arts[by_track[1]]["sha1"] != arts[by_track[2]]["sha1"]
    assert arts[by_track[3]] is None

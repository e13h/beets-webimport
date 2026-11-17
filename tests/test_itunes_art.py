"""iTunes art override: detect an iTunes purchase in an inbox folder, look
up its artwork by catalog ID, and save it as the folder's cover image so
fetchart's filesystem source uses it instead of Cover Art Archive."""
from __future__ import annotations

import struct

import pytest

from beetsplug.webimport import itunes


def jpeg(width, height):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof0 + b"\xff\xd9"


ART100 = "https://is1-ssl.mzstatic.com/image/thumb/Music/v4/aa/bb/x.jpg/100x100bb.jpg"
LOOKUP = {"resultCount": 1, "results": [{
    "wrapperType": "collection", "collectionId": 1440662312,
    "collectionName": "Mulan (Original Motion Picture Soundtrack)",
    "artistName": "Lea Salonga & Donny Osmond",
    "collectionViewUrl": "https://music.apple.com/us/album/mulan/1440662312?uo=4",
    "artworkUrl100": ART100, "trackCount": 12,
}]}


class Resp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status, payload, content
        self.ok = status == 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


@pytest.fixture
def fake_net(monkeypatch):
    calls = []

    def get(url, params=None, **kw):
        calls.append((url, params))
        if "itunes.apple.com/lookup" in url:
            return Resp(payload=LOOKUP)
        if "mzstatic.com" in url:
            return Resp(content=jpeg(1500, 1500))
        return Resp(404)

    monkeypatch.setattr(itunes.requests, "get", get)
    itunes.clear_cache()
    yield calls
    itunes.clear_cache()


@pytest.fixture
def purchase_dir(tmp_path, monkeypatch):
    d = tmp_path / "inbox" / "Mulan"
    d.mkdir(parents=True)
    (d / "01 Song.m4a").write_bytes(b"not really mp4")
    (d / "notes.txt").write_text("x")
    tags = {str(d / "01 Song.m4a"): {"plID": [1440662312], "sfID": [143441]}}
    monkeypatch.setattr(itunes, "_read_mp4_tags", lambda p: tags.get(str(p)))
    return d


def test_detects_collection_and_storefront(purchase_dir):
    assert itunes.detect_ids(purchase_dir) == {"collection_id": 1440662312, "country": "us"}


def test_no_itunes_ids(tmp_path, monkeypatch):
    d = tmp_path / "rip"
    d.mkdir()
    (d / "01.flac").write_bytes(b"")
    monkeypatch.setattr(itunes, "_read_mp4_tags", lambda p: None)
    assert itunes.detect_ids(d) is None


def test_full_resolution_url():
    assert itunes.full_res_url(ART100).endswith("/10000x10000bb.jpg")


def test_lookup_art_downloads_full_res_once(purchase_dir, fake_net):
    info = itunes.art_for_dir(purchase_dir)
    assert info["collection_id"] == 1440662312
    assert info["collection_name"].startswith("Mulan")
    assert info["store_url"].startswith("https://music.apple.com/")
    assert (info["width"], info["height"]) == (1500, 1500)
    assert info["existing_cover"] is None
    # Lookup used the purchase storefront; second call is cached.
    assert fake_net[0][1]["country"] == "us"
    itunes.art_for_dir(purchase_dir)
    assert len(fake_net) == 2  # one lookup + one image download


def test_save_cover_writes_cover_jpg(purchase_dir, fake_net):
    path = itunes.save_cover(purchase_dir)
    assert path.name == "cover.jpg"
    assert path.read_bytes() == jpeg(1500, 1500)


def test_save_cover_keeps_existing_cover(purchase_dir, fake_net):
    (purchase_dir / "cover.png").write_bytes(b"user art")
    assert itunes.art_for_dir(purchase_dir)["existing_cover"] == "cover.png"
    itunes.save_cover(purchase_dir)
    assert (purchase_dir / "cover.jpg").exists()
    assert not (purchase_dir / "cover.png").exists()
    assert (purchase_dir / "cover.png.before-itunes").read_bytes() == b"user art"


def test_lookup_without_results(purchase_dir, monkeypatch):
    monkeypatch.setattr(itunes.requests, "get", lambda *a, **k: Resp(payload={"resultCount": 0, "results": []}))
    itunes.clear_cache()
    info = itunes.art_for_dir(purchase_dir)
    assert info["collection_id"] == 1440662312 and info["error"]

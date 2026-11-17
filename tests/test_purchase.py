"""Store purchases: find the digital release the files were bought as."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from beetsplug.webimport import itunes, purchase


class Resp:
    def __init__(self, payload, status=200):
        self._payload, self.status_code, self.ok = payload, status, status == 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(self.status_code)


def release(rid, date, tracks):
    return {"id": rid, "date": date, "track-count": tracks}


@pytest.fixture
def mb(monkeypatch):
    calls = []
    results = {"releases": []}

    def get(url, params=None, **kw):
        calls.append(params)
        return Resp(results)

    monkeypatch.setattr(purchase.mbapi.requests, "get", get)
    monkeypatch.setattr(purchase.mbapi, "MIN_INTERVAL", 0)
    purchase.clear_cache()
    yield results, calls
    purchase.clear_cache()


def item(**kw):
    return {"album": "A Rush Of Blood To The Head", "albumartist": "Coldplay", "year": 2006,
            "tracktotal": 11, "comments": "Amazon.com Song ID: 201954864", **kw}


def test_detects_amazon_from_comment(tmp_path, monkeypatch):
    monkeypatch.setattr(itunes, "_read_mp4_tags", lambda p: None)
    assert purchase.detect_store([item()], tmp_path) == "amazon"
    assert purchase.detect_store([item(comments="ripped by me")], tmp_path) is None


def test_detects_amazon_with_bytes_path(tmp_path, monkeypatch):
    # The session passes os.fsdecode(task.paths[0]); make sure str works end to end.
    import os

    monkeypatch.setattr(itunes, "_read_mp4_tags", lambda p: None)
    assert purchase.detect_store([item()], os.fsdecode(os.fsencode(str(tmp_path)))) == "amazon"


def test_detects_itunes_from_store_id(tmp_path, monkeypatch):
    monkeypatch.setattr(itunes, "detect_ids", lambda folder: {"collection_id": 1, "country": "us"})
    assert purchase.detect_store([item(comments="")], tmp_path) == "itunes"


def test_ranks_year_then_track_count(mb):
    results, calls = mb
    results["releases"] = [
        release("cd-ish", "2016-06-17", 11),
        release("wrong-count", "2006-01-01", 14),
        release("best", "2006-08-14", 11),
        release("undated", None, 11),
    ]
    ids = purchase.digital_release_ids(purchase.album_hints([item()]))
    assert ids == ["best", "wrong-count"]
    q = calls[0]["query"]
    assert 'release:"A Rush Of Blood To The Head"' in q and 'format:"Digital Media"' in q


def test_closest_track_count_when_no_year_match(mb):
    results, _ = mb
    results["releases"] = [release("r16", None, 16), release("r12", None, 12), release("r14", None, 14)]
    hints = purchase.album_hints([item(year=2010, tracktotal=13)])
    assert purchase.digital_release_ids(hints)[0] in {"r12", "r14"}
    assert "r16" not in purchase.digital_release_ids(hints)


def test_excludes_existing_and_caches(mb):
    results, calls = mb
    results["releases"] = [release("a", "2006", 11), release("b", "2006", 11)]
    hints = purchase.album_hints([item()])
    assert purchase.digital_release_ids(hints, exclude=["a"]) == ["b"]
    purchase.digital_release_ids(hints)
    assert len(calls) == 1


def test_quotes_are_escaped(mb):
    _, calls = mb
    purchase.digital_release_ids(purchase.album_hints([item(album='Say "Hi"')]))
    assert 'release:"Say \\"Hi\\""' in calls[0]["query"]


def test_missing_tags_or_failure_add_nothing(monkeypatch):
    assert purchase.digital_release_ids({"album": None, "artist": "x"}) == []
    monkeypatch.setattr(purchase.mbapi, "get", lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    purchase.clear_cache()
    assert purchase.digital_release_ids(purchase.album_hints([item()])) == []


def test_looks_purchased():
    assert purchase.looks_purchased(SimpleNamespace(media="Digital Media", year=2006), 2006)
    assert not purchase.looks_purchased(SimpleNamespace(media="CD", year=2006), 2006)
    assert not purchase.looks_purchased(SimpleNamespace(media="Digital Media", year=2016), 2006)
    assert not purchase.looks_purchased(SimpleNamespace(media="Digital Media", year=2006), None)

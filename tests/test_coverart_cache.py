"""Cover Art Archive lookups behind the candidate art preview are cached,
so clicking between candidates doesn't re-hit CAA (3-4s per lookup)."""

import pytest
import requests

import beetsplug.webimport.coverart as coverart

MBID = "a5483fb3-634b-4254-a966-de33cefd1f17"
CFG = {"minwidth": 0, "enforce_ratio": False, "sources": ["coverart:release", "coverart:releasegroup"]}


class FakeResp:
    def __init__(self, status, payload=None):
        self.status_code = status
        self.ok = 200 <= status < 300
        self._payload = payload

    def json(self):
        return self._payload


FRONT = {"images": [{"front": True, "types": ["Front"], "image": "http://x/full.jpg",
                     "thumbnails": {"500": "http://x/500.jpg"}}]}


@pytest.fixture(autouse=True)
def clear_cache():
    coverart.clear_caa_cache()
    yield
    coverart.clear_caa_cache()


def _fake_get(responses, calls):
    def get(url, **kw):
        calls.append(url)
        r = responses.pop(0) if len(responses) > 1 else responses[0]
        if isinstance(r, Exception):
            raise r
        return r
    return get


def test_repeated_resolves_hit_caa_once(monkeypatch):
    calls = []
    monkeypatch.setattr(coverart.requests, "get", _fake_get([FakeResp(200, FRONT)], calls))
    for _ in range(3):
        r = coverart.resolve_candidate_art("/nonexistent", MBID, None, CFG)
        assert r["match"] and r["source_url"] == "http://x/500.jpg"
    # Resolved art and source art are the same release lookup: one request total.
    assert calls == [f"https://coverartarchive.org/release/{MBID}"]


def test_no_art_404_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(coverart.requests, "get", _fake_get([FakeResp(404)], calls))
    for _ in range(2):
        r = coverart.resolve_candidate_art("/nonexistent", MBID, None, CFG)
        assert r["source_url"] is None and not r["unavailable"]
    assert len(calls) == 1


def test_unreachable_is_not_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(coverart.requests, "get",
                        _fake_get([requests.ConnectionError(), FakeResp(200, FRONT)], calls))
    first = coverart.resolve_candidate_art("/nonexistent", MBID, None, CFG)
    assert first["unavailable"]
    second = coverart.resolve_candidate_art("/nonexistent", MBID, None, CFG)
    assert second["source_url"] == "http://x/500.jpg" and not second["unavailable"]


def test_mapping_style_sources_resolve(monkeypatch):
    """fetchart sources written as YAML mappings (`- coverart: release`,
    as in the homelab config) arrive as one-key dicts."""
    from collections import OrderedDict

    calls = []
    monkeypatch.setattr(coverart.requests, "get", _fake_get([FakeResp(200, FRONT)], calls))
    cfg = {"sources": ["filesystem", OrderedDict({"coverart": "release"}), OrderedDict({"coverart": "releasegroup"})]}
    r = coverart.resolve_candidate_art("/nonexistent", MBID, None, cfg)
    assert r["resolved_source"] == "coverart:release"
    assert r["match"]

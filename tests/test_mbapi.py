"""webimport's MusicBrainz requests share beets' rate-limited session."""
from types import SimpleNamespace

import requests

from beetsplug.webimport import mbapi


def test_uses_beets_session_and_returns_404_responses(monkeypatch):
    calls = []
    not_found = SimpleNamespace(status_code=404)

    class Session:
        def get(self, url, **kw):
            calls.append(url)
            raise requests.HTTPError(response=not_found)

    monkeypatch.setattr(mbapi, "_beets_session", lambda: Session())
    monkeypatch.setattr(mbapi.requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("bypassed")))
    assert mbapi.get("url", {"resource": "x"}) is not_found
    assert calls == ["https://musicbrainz.org/ws/2/url"]


def test_falls_back_to_local_limiter(monkeypatch):
    monkeypatch.setattr(mbapi, "_beets_session", lambda: None)
    monkeypatch.setattr(mbapi, "MIN_INTERVAL", 0)
    monkeypatch.setattr(mbapi.requests, "get", lambda url, **k: SimpleNamespace(status_code=200, url=url))
    assert mbapi.get("release", {}).url == "https://musicbrainz.org/ws/2/release"

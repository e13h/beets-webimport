from __future__ import annotations

import hashlib

import pytest

from beetsplug.webimport.navidrome import NavidromeClient, NavidromeError


class FakeResponse:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        pass

    def json(self):
        return {"subsonic-response": self.body}


class FakeHTTP:
    def __init__(self, body):
        self.body = body
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append((url, params))
        return FakeResponse(self.body)


def test_scan_status_uses_salted_token_auth():
    http = FakeHTTP({"status": "ok", "scanStatus": {"scanning": False, "lastScan": "2026-11-18T04:45:59Z"}})
    client = NavidromeClient("https://nd.example/", "webimport", "secret", session=http)

    assert client.scan_status() == {"scanning": False, "last_scan": "2026-11-18T04:45:59Z"}
    url, params = http.calls[0]
    assert url == "https://nd.example/rest/getScanStatus"
    assert "p" not in params  # the password itself is never sent
    assert params["t"] == hashlib.md5(("secret" + params["s"]).encode()).hexdigest()


def test_api_errors_raise():
    http = FakeHTTP({"status": "failed", "error": {"code": 50, "message": "User is not authorized"}})
    client = NavidromeClient("https://nd.example", "webimport", "secret", session=http)
    with pytest.raises(NavidromeError, match="not authorized"):
        client.start_scan()


def test_off_without_url_or_user(monkeypatch):
    class View:
        def __init__(self, v):
            self.v = v

        def get(self, typ=None):
            return self.v

    cfg = {"url": View(""), "user": View("webimport"), "password": View("")}
    assert NavidromeClient.from_config(cfg) is None
    monkeypatch.setenv("WEBIMPORT_NAVIDROME_PASSWORD", "from-env")
    cfg["url"] = View("https://nd.example")
    assert NavidromeClient.from_config(cfg)._password == "from-env"

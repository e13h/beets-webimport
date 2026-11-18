"""Minimal Navidrome (Subsonic API) client: only what Pending Move needs.

Every Subsonic call needs credentials. Any user can read the scan status,
which is server-wide (one assigned library is enough). Starting a scan
needs an admin user, so `start_scan` is best-effort.

Note: `lastScan` is when the last scan *finished*, so "lastScan is newer
than my write" does not prove that scan saw the write (it may have started
before it). pendingmove.py handles that.
"""
from __future__ import annotations

import hashlib
import os
import secrets

import requests

PASSWORD_ENV = "WEBIMPORT_NAVIDROME_PASSWORD"


class NavidromeError(Exception):
    pass


class NavidromeClient:
    def __init__(self, url: str, user: str, password: str, timeout: float = 5.0, session=None):
        self.base = url.rstrip("/")
        self.user = user
        self._password = password
        self.timeout = timeout
        self._http = session or requests.Session()

    @classmethod
    def from_config(cls, cfg) -> "NavidromeClient | None":
        """`cfg` is the `webimport.navidrome` config view. Returns None
        (integration off) unless a URL and a user are set. The password
        comes from the config or, preferably, the environment."""
        url = cfg["url"].get(str) or ""
        user = cfg["user"].get(str) or ""
        if not url or not user:
            return None
        password = cfg["password"].get(str) or os.environ.get(PASSWORD_ENV, "")
        return cls(url, user, password)

    def _call(self, method: str, **params) -> dict:
        salt = secrets.token_hex(6)
        token = hashlib.md5((self._password + salt).encode()).hexdigest()
        query = {"u": self.user, "t": token, "s": salt, "v": "1.16.1", "c": "beets-webimport", "f": "json"}
        query.update(params)
        try:
            resp = self._http.get(f"{self.base}/rest/{method}", params=query, timeout=self.timeout)
            resp.raise_for_status()
            body = resp.json()["subsonic-response"]
        except (requests.RequestException, ValueError, KeyError) as exc:
            raise NavidromeError(f"{method}: {exc}") from exc
        if body.get("status") != "ok":
            err = body.get("error") or {}
            raise NavidromeError(f"{method}: {err.get('message', 'failed')} (code {err.get('code')})")
        return body

    def scan_status(self) -> dict:
        """{"scanning": bool, "last_scan": str | None}"""
        st = self._call("getScanStatus").get("scanStatus", {})
        return {"scanning": bool(st.get("scanning")), "last_scan": st.get("lastScan")}

    def start_scan(self) -> None:
        self._call("startScan")

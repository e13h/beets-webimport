"""Rate-limited requests to the MusicBrainz web service.

webimport's own MusicBrainz requests (Apple Music link lookup, digital
release search) go through here. MusicBrainz allows one request per
second per client, and beets' candidate lookups run at the same time, so
when the musicbrainz plugin is loaded its rate-limited session (a
process-wide singleton, with retries on 503) is used for ours too. Without
it, a local limiter applies.
"""
from __future__ import annotations

import threading
import time

import requests

BASE = "https://musicbrainz.org/ws/2"
TIMEOUT = 10
# MusicBrainz asks clients to identify themselves with a contact URL.
HEADERS = {"User-Agent": "beets-webimport/0.1 ( https://github.com/beetbox/beets )"}
MIN_INTERVAL = 1.1

_lock = threading.Lock()
_last_request = 0.0


def _beets_session():
    """The musicbrainz plugin's rate-limited session, if the plugin is loaded."""
    try:
        from beets import plugins

        for plugin in plugins.find_plugins():
            if plugin.name == "musicbrainz" and hasattr(plugin, "mb_api"):
                return plugin.mb_api.session
    except Exception:  # noqa: BLE001 -- fall back to the local limiter
        pass
    return None


def get(path: str, params) -> requests.Response:
    """GET {BASE}/{path} within the rate limit. Returns the response
    unchecked (callers decide what a 404 means)."""
    session = _beets_session()
    if session is not None:
        try:
            return session.get(f"{BASE}/{path}", params=params, timeout=TIMEOUT)
        except requests.HTTPError as exc:  # beets' session raises on error statuses
            if exc.response is not None:
                return exc.response
            raise
    global _last_request
    with _lock:
        wait = _last_request + MIN_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            return requests.get(f"{BASE}/{path}", params=params, timeout=TIMEOUT, headers=HEADERS)
        finally:
            _last_request = time.monotonic()

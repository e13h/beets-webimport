"""Activity: what each import or reimport is doing right now, for the
Inbox tab's single list.

An Activity exists from the moment an import or reimport is requested
until its session ends: queued in the worker pool, working (with the
current step and the web services it has called), waiting for a review
decision, applying. The job binds it to a ContextVar before running the
beets session; beets' pipeline copies the context into its stage threads,
so steps and HTTP requests made anywhere in the session are attributed to
it. Held in memory only (ADR-0004).
"""
from __future__ import annotations

import contextvars
import itertools
import threading
import time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

current: contextvars.ContextVar["Activity | None"] = contextvars.ContextVar("webimport_activity", default=None)

# Hosts the UI names; anything else is shown by host name.
SERVICES = {
    "musicbrainz.org": "MusicBrainz",
    "coverartarchive.org": "Cover Art Archive",
    "archive.org": "Cover Art Archive",
    "itunes.apple.com": "Apple (iTunes)",
    "mzstatic.com": "Apple artwork",
    "acoustid.org": "AcoustID",
    "discogs.com": "Discogs",
    "spotify.com": "Spotify",
}

_order = itertools.count()


def _service(host: str) -> str:
    for suffix, name in SERVICES.items():
        if host == suffix or host.endswith("." + suffix):
            return name
    return host


def _what(url: str) -> str:
    """A short description of a request, e.g. "release lookup"."""
    parts = urlsplit(url)
    path = [p for p in parts.path.split("/") if p]
    if parts.hostname and parts.hostname.endswith("musicbrainz.org") and len(path) >= 3:
        entity = path[2]
        return f"{entity} search" if "query=" in (parts.query or "") else f"{entity} lookup"
    if parts.hostname == "itunes.apple.com":
        return "album lookup"
    return path[0] if path else ""


@dataclass
class Activity:
    key: str  # inbox folder path, or "reimport:<album ids>"
    kind: str  # "import" | "reimport"
    label: str
    path: str | None = None  # the inbox folder, for imports
    album_ids: list[int] = field(default_factory=list)
    state: str = "queued"  # queued | working | review | applying | failed
    step: str = "Waiting in the queue"
    error: str | None = None
    since: float = field(default_factory=time.time)
    order: int = field(default_factory=lambda: next(_order))
    requests: dict[str, int] = field(default_factory=dict)
    last_request: str | None = None
    waiting_on: str | None = None  # a request in flight
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def set(self, step: str, state: str | None = None) -> None:
        with self._lock:
            self.step = step
            if state:
                self.state = state

    def as_json(self, queue_position: int | None = None) -> dict:
        with self._lock:
            return {
                "key": self.key, "kind": self.kind, "label": self.label, "path": self.path,
                "album_ids": list(self.album_ids), "state": self.state, "step": self.step,
                "error": self.error, "since": self.since, "order": self.order,
                "requests": dict(self.requests), "last_request": self.last_request,
                "waiting_on": self.waiting_on, "queue_position": queue_position,
            }


class Activities:
    def __init__(self):
        self._items: dict[str, Activity] = {}
        self._lock = threading.Lock()

    def add(self, act: Activity) -> Activity:
        with self._lock:
            self._items[act.key] = act
        return act

    def get(self, key: str) -> Activity | None:
        with self._lock:
            return self._items.get(key)

    def finish(self, act: Activity) -> None:
        """The session ended normally: the card goes (an imported inbox
        folder is gone from the inbox; a skipped one shows as before)."""
        with self._lock:
            if self._items.get(act.key) is act:
                del self._items[act.key]

    def fail(self, act: Activity, error: str) -> None:
        with act._lock:
            act.state, act.error, act.step = "failed", error, "Failed"

    def dismiss(self, key: str) -> bool:
        with self._lock:
            act = self._items.get(key)
            if act is None or act.state != "failed":
                return False
            del self._items[key]
            return True

    def as_json(self) -> list[dict]:
        with self._lock:
            acts = sorted(self._items.values(), key=lambda a: a.order)
        queued = [a for a in acts if a.state == "queued"]
        return [a.as_json(queued.index(a) if a in queued else None) for a in acts]


def step(text: str, state: str | None = None) -> None:
    """Report the current step of whatever activity this thread works for."""
    act = current.get()
    if act is not None:
        act.set(text, state)


# -- HTTP introspection ------------------------------------------------------

_installed = False


def install_request_hook() -> None:
    """Count every HTTP request an activity makes (beets' MusicBrainz client,
    webimport's own Apple / MusicBrainz / Cover Art Archive calls), by
    service, and show the one in flight. Wraps requests.Session.send once."""
    global _installed
    if _installed:
        return
    import requests

    original = requests.Session.send

    def send(self, request, **kwargs):
        act = current.get()
        if act is None:
            return original(self, request, **kwargs)
        url = getattr(request, "url", "") or ""
        service = _service(urlsplit(url).hostname or "")
        what = f"{service}: {_what(url)}".rstrip(": ")
        with act._lock:
            act.requests[service] = act.requests.get(service, 0) + 1
            act.waiting_on = what
        try:
            return original(self, request, **kwargs)
        finally:
            with act._lock:
                act.last_request, act.waiting_on = what, None

    requests.Session.send = send
    _propagate_context_to_metadata_lookups()
    _installed = True


def _propagate_context_to_metadata_lookups() -> None:
    """beets queries its metadata sources (MusicBrainz, ...) concurrently in
    a ThreadPoolExecutor (metadata_plugins._yield_from_plugins), whose
    threads start with an empty context, so their requests wouldn't be
    attributed. Give that module a pool that runs each call in the
    submitting thread's context."""
    from concurrent.futures import ThreadPoolExecutor

    try:
        from beets import metadata_plugins
    except ImportError:  # older beets: lookups run in the calling thread
        return
    if not isinstance(getattr(metadata_plugins, "ThreadPoolExecutor", None), type):
        return

    class ContextThreadPoolExecutor(ThreadPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            ctx = contextvars.copy_context()
            return super().submit(ctx.run, fn, *args, **kwargs)

    metadata_plugins.ThreadPoolExecutor = ContextThreadPoolExecutor

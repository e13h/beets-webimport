"""Activity (Inbox tab progress): every import/reimport is visible from the
moment it's requested, with its queue position, step, and web requests."""
from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest
import requests

from beetsplug.webimport import activity, reimport
from beetsplug.webimport.queue import ReviewManager


def test_requests_are_counted_per_service_for_the_current_activity(monkeypatch):
    activity.install_request_hook()
    sent = []
    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send",
                        lambda self, req, **kw: sent.append(req.url) or MagicMock(status_code=200, headers={}, url=req.url,
                                                                                  is_redirect=False, history=[]))
    act = activity.Activity(key="k", kind="import", label="x")
    token = activity.current.set(act)
    try:
        requests.get("https://musicbrainz.org/ws/2/release/abc?fmt=json")
        requests.get("https://musicbrainz.org/ws/2/release?query=x&fmt=json")
        requests.get("https://itunes.apple.com/lookup?id=1")
    finally:
        activity.current.reset(token)
    requests.get("https://musicbrainz.org/ws/2/release/def")  # no activity: not counted
    assert act.requests == {"MusicBrainz": 2, "Apple (iTunes)": 1}
    assert act.last_request == "Apple (iTunes): album lookup" and act.waiting_on is None
    assert len(sent) == 4


def test_review_registration_marks_the_owner_and_state():
    act = activity.Activity(key="/inbox/A", kind="import", label="A")
    rm = ReviewManager()
    token = activity.current.set(act)
    try:
        pr = rm.register("match", "/inbox/A/sub", {"candidates": []})
    finally:
        activity.current.reset(token)
    assert pr.owner == "/inbox/A" and act.state == "review"
    assert rm.list_pending()[0]["owner"] == "/inbox/A"


def test_queue_positions_fail_and_dismiss():
    acts = activity.Activities()
    a, b, c = (acts.add(activity.Activity(key=k, kind="import", label=k)) for k in "abc")
    a.set("Searching", "working")
    assert [(j["key"], j["queue_position"]) for j in acts.as_json()] == [("a", None), ("b", 0), ("c", 1)]
    assert not acts.dismiss("a")  # only failed cards can be dismissed
    acts.fail(a, "boom")
    assert acts.dismiss("a")
    acts.finish(b)
    assert [j["key"] for j in acts.as_json()] == ["c"]


@pytest.fixture
def app(lib, tmp_path):
    from beetsplug.webimport.server import create_app

    cfg = {k: MagicMock(get=lambda typ, v=v: v) for k, v in {
        "grace_period_seconds": 600, "candidate_search_workers": 1, "tag_fields": ["mood"],
        "inbox_dir": str(tmp_path / "inbox"), "tag_store_path": str(tmp_path / "t.json"),
        "apple_music_match": False}.items()}
    (tmp_path / "inbox").mkdir()
    return create_app(lib, cfg, MagicMock()).test_client()


def _album(lib, title):
    from beets.library import Item

    item = Item(title="t", album=title, albumartist="X", path=b"/nowhere.mp3")
    lib.add(item)
    return lib.add_album([item])


def test_reimport_is_listed_at_once_queued_then_working_then_gone(app, lib, monkeypatch):
    release = threading.Event()
    started = []

    def run_reimport(lib_, rm, lh, album_ids, **kw):
        started.append(album_ids)
        activity.step("Searching for matching releases")
        release.wait(5)

    monkeypatch.setattr(reimport, "run_reimport", run_reimport)
    a1, a2 = _album(lib, "First"), _album(lib, "Second")
    assert app.post("/api/reimport", json={"album_ids": [a1.id]}).get_json()["key"] == f"reimport:{a1.id}"
    app.post("/api/reimport", json={"album_ids": [a2.id]})
    deadline = time.monotonic() + 5
    while not started and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.05)
    acts = app.get("/api/inbox").get_json()["activities"]
    assert [(a["label"], a["state"], a["queue_position"]) for a in acts] == [
        ("X – First", "working", None), ("X – Second", "queued", 0)]
    assert acts[0]["step"] == "Searching for matching releases"
    assert app.post("/api/reimport", json={"album_ids": [a1.id]}).status_code == 409  # already running
    release.set()
    deadline = time.monotonic() + 5
    while app.get("/api/inbox").get_json()["activities"] and time.monotonic() < deadline:
        time.sleep(0.02)
    assert app.get("/api/inbox").get_json()["activities"] == []


def test_failed_job_stays_listed_until_dismissed(app, lib, monkeypatch):
    def run_reimport(*a, **kw):
        raise RuntimeError("MusicBrainz is down")

    monkeypatch.setattr(reimport, "run_reimport", run_reimport)
    album = _album(lib, "Broken")
    app.post("/api/reimport", json={"album_ids": [album.id]})
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        acts = app.get("/api/inbox").get_json()["activities"]
        if acts and acts[0]["state"] == "failed":
            break
        time.sleep(0.02)
    assert acts[0]["error"] == "MusicBrainz is down"
    assert app.post("/api/activity/dismiss", json={"key": acts[0]["key"]}).get_json() == {"ok": True}
    assert app.get("/api/inbox").get_json()["activities"] == []


def test_metadata_source_lookups_run_in_the_callers_context():
    """beets queries metadata sources in its own thread pool; their requests
    must still count for the activity."""
    from beets import metadata_plugins

    activity.install_request_hook()
    act = activity.Activity(key="k", kind="import", label="x")
    token = activity.current.set(act)
    try:
        with metadata_plugins.ThreadPoolExecutor() as ex:
            seen = ex.submit(lambda: activity.current.get()).result()
    finally:
        activity.current.reset(token)
    assert seen is act

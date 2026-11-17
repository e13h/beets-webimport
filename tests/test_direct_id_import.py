from __future__ import annotations

import threading
from unittest.mock import MagicMock

import pytest

from beetsplug.webimport.server import create_app
from beetsplug.webimport.session import WebImportSession


@pytest.fixture
def inbox_app(lib, tmp_path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    folder = inbox_dir / "Test Album"
    folder.mkdir()
    (folder / "track.wav").write_bytes(b"audio")

    plugin_mock = MagicMock()
    plugin_mock.register_listener = MagicMock()

    cfg = {
        "grace_period_seconds": MagicMock(get=lambda typ: 600),
        "candidate_search_workers": MagicMock(get=lambda typ: 2),
        "tag_fields": MagicMock(get=lambda typ: ["mood"]),
        "inbox_dir": MagicMock(get=lambda typ: str(inbox_dir)),
        "tag_store_path": MagicMock(get=lambda typ: str(tmp_path / "tags.json")),
        "apple_music_match": MagicMock(get=lambda typ: True),
    }
    app = create_app(lib, cfg, plugin_mock)
    return app, app.test_client(), str(folder)


@pytest.fixture
def capture_session(monkeypatch):
    """Stubs WebImportSession.run so the endpoint test observes the
    session without running the real beets pipeline, and captures the
    session object for assertions."""
    captured = {"done": threading.Event()}

    def fake_run(self):
        captured["preset_search_id"] = self.preset_search_id
        captured["matched_via"] = self.matched_via
        # Simulate the real choose_match behavior of consuming the preset
        # before registering review, then register a review task so the
        # endpoint's success can be observed without network.
        self.preset_search_id = None
        pr = self.review_manager.register(
            "match", "fake-path", {"candidates": [], "rec": None}
        )
        self.review_manager.submit_decision(pr.task_id, {"action": "skip"})
        captured["done"].set()

    monkeypatch.setattr(WebImportSession, "run", fake_run)
    return captured


def _wait(captured, timeout=5.0):
    assert captured["done"].wait(timeout=timeout)


def test_inbox_start_paths_only_body_still_works(
    inbox_app, capture_session
):
    app, client, folder = inbox_app
    resp = client.post("/api/inbox/start", json={"paths": [folder]})
    assert resp.status_code == 200
    assert resp.get_json() == {"submitted": 1}


def test_inbox_start_with_search_id_sets_preset_id(
    inbox_app, capture_session
):
    app, client, folder = inbox_app
    resp = client.post(
        "/api/inbox/start",
        json={"paths": [folder], "search_ids": {folder: "abc-123"}},
    )
    assert resp.status_code == 200
    assert resp.get_json() == {"submitted": 1}
    _wait(capture_session)
    assert capture_session["preset_search_id"] == "abc-123"


def test_inbox_start_without_search_id_leaves_preset_unset(
    inbox_app, capture_session
):
    app, client, folder = inbox_app
    resp = client.post("/api/inbox/start", json={"paths": [folder]})
    assert resp.status_code == 200
    _wait(capture_session)
    assert capture_session["preset_search_id"] is None


def test_choose_match_blank_search_id_runs_broad_search(lib, tmp_path, monkeypatch):
    """A blank search_id (the UI's 'Auto-search instead' fallback) must
    run the normal unrestricted search, not pass a blank ID to the
    backend."""
    from beetsplug.webimport.queue import ReviewManager

    rm = ReviewManager()
    session = WebImportSession(
        lib, None, paths=[str(tmp_path / "f").encode()], query=None,
        review_manager=rm, config=None,
    )

    calls = []

    class FakeTask:
        items = []
        paths = [str(tmp_path / "f").encode()]
        candidates = []
        rec = None

        # Mirrors real beets 2.x ImportTask.lookup_candidates:
        # the argument is required, not optional.
        def lookup_candidates(self, search_ids):
            calls.append(search_ids)
            self.candidates = []

    task = FakeTask()
    session._lookup_candidates(task, "")
    assert calls[0] == []  # unrestricted search, no TypeError

    session._lookup_candidates(task, "   ")
    assert calls[1] == []

    session._lookup_candidates(task, "real-id")
    assert calls[2] == ["real-id"]


def test_choose_match_preset_good_id_single_candidate_review(lib, tmp_path, monkeypatch):
    """Known-good ID: a targeted lookup yielding one candidate registers
    a single-candidate review task (ticket 37's 'verifiable without the
    UI' success half)."""
    from beetsplug.webimport.queue import ReviewManager

    rm = ReviewManager()
    session = WebImportSession(
        lib, None, paths=[str(tmp_path / "f").encode()], query=None,
        review_manager=rm, config=None,
    )
    session.preset_search_id = "a5483fb3-634b-4254-a966-de33cefd1f17"

    registered = {}
    real_register = rm.register

    def spy_register(kind, path, payload):
        registered.update(payload, kind=kind)
        pr = real_register(kind, path, payload)
        rm.submit_decision(pr.task_id, {"action": "skip"})
        return pr

    monkeypatch.setattr(rm, "register", spy_register)

    class FakeInfo:
        artist = "Jerry Goldsmith"
        album = "Mulan"
        year = 1998
        label = None
        album_id = "a5483fb3-634b-4254-a966-de33cefd1f17"
        data_source = "MusicBrainz"
        data_url = None
        tracks = []

    class FakeMatch:
        info = FakeInfo()

        class distance:
            distance = 0.0

        extra_tracks = []
        extra_items = []

    class FakeTask:
        items = []
        paths = [str(tmp_path / "f").encode()]
        candidates = []
        rec = None

        def lookup_candidates(self, search_ids=None):
            self.candidates = [FakeMatch()]

    session.choose_match(FakeTask())

    assert registered["kind"] == "match"
    assert len(registered["candidates"]) == 1
    assert registered["candidates"][0]["album_id"] == "a5483fb3-634b-4254-a966-de33cefd1f17"
    assert registered["attempted_search_id"] == "a5483fb3-634b-4254-a966-de33cefd1f17"


def test_choose_match_preset_id_empty_candidates_registers_review(
    lib, tmp_path, monkeypatch
):
    """A targeted lookup that yields zero candidates must register a
    review task with an empty candidate list (and the attempted ID in
    the payload) instead of aborting or falling back to normal search."""
    from beetsplug.webimport.queue import ReviewManager

    rm = ReviewManager()
    session = WebImportSession(
        lib,
        None,
        paths=[str(tmp_path / "folder").encode()],
        query=None,
        review_manager=rm,
        config=None,
    )
    session.preset_search_id = "bogus-id"

    registered = {}
    real_register = rm.register

    def spy_register(kind, path, payload):
        registered.update(payload)
        pr = real_register(kind, path, payload)
        # Unblock the session thread immediately: the test observes what
        # choose_match registered, not the decision outcome.
        rm.submit_decision(pr.task_id, {"action": "skip"})
        return pr

    monkeypatch.setattr(rm, "register", spy_register)

    class FakeTask:
        items = []
        paths = [str(tmp_path / "folder").encode()]
        candidates = []
        rec = None

        def lookup_candidates(self, search_ids):
            self.candidates = []  # backend found nothing

    task = FakeTask()
    session.choose_match(task)

    assert registered["candidates"] == []
    assert registered["attempted_search_id"] == "bogus-id"
    # ...and it was registered as a reviewable task, not aborted:
    assert len(rm.list_pending()) == 0  # consumed by the auto-skip decision
    assert "attempted_search_id" in registered


def test_inbox_start_uses_apple_music_match(inbox_app, capture_session, monkeypatch):
    from beetsplug.webimport import itunes

    via = {"source": "apple_music", "collection_id": 1, "release_ids": ["r1", "r2"]}
    monkeypatch.setattr(itunes, "musicbrainz_match_for_dir", lambda folder: via)
    app, client, folder = inbox_app
    client.post("/api/inbox/start", json={"paths": [folder]})
    _wait(capture_session)
    assert capture_session["preset_search_id"] == ["r1", "r2"]
    assert capture_session["matched_via"] == via


def test_explicit_id_wins_over_apple_music_match(inbox_app, capture_session, monkeypatch):
    from beetsplug.webimport import itunes

    monkeypatch.setattr(itunes, "musicbrainz_match_for_dir", lambda folder: pytest.fail("not consulted"))
    app, client, folder = inbox_app
    client.post("/api/inbox/start", json={"paths": [folder], "search_ids": {folder: "mine"}})
    _wait(capture_session)
    assert capture_session["preset_search_id"] == "mine"
    assert capture_session["matched_via"] is None


def test_no_linked_release_runs_normal_search(inbox_app, capture_session, monkeypatch):
    from beetsplug.webimport import itunes

    monkeypatch.setattr(itunes, "musicbrainz_match_for_dir",
                        lambda folder: {"source": "apple_music", "collection_id": 1, "release_ids": []})
    app, client, folder = inbox_app
    client.post("/api/inbox/start", json={"paths": [folder]})
    _wait(capture_session)
    assert capture_session["preset_search_id"] is None

"""Direct ID Import runs only the targeted ID lookup (ticket 40).

beets' pipeline does the first candidate lookup itself, before
choose_match, using session.config["search_ids"]. These tests run the real
beets import pipeline on a real (silent) audio file, with the metadata
backends stubbed, and record which lookups happen.
"""
from __future__ import annotations

import threading
import time

import pytest
from beets import config, metadata_plugins

from beetsplug.webimport.queue import ReviewManager
from beetsplug.webimport.session import WebImportSession

MBID = "a5483fb3-634b-4254-a966-de33cefd1f17"


@pytest.fixture
def lookups(monkeypatch):
    """Record broad searches (`candidates`) and ID lookups (`albums_for_ids`)."""
    calls = {"broad": 0, "ids": []}

    def candidates(*a, **kw):
        calls["broad"] += 1
        return iter(())

    def albums_for_ids(ids):
        calls["ids"].append(list(ids))
        return iter(())

    monkeypatch.setattr(metadata_plugins, "candidates", candidates)
    monkeypatch.setattr(metadata_plugins, "albums_for_ids", albums_for_ids)
    return calls


@pytest.fixture(autouse=True)
def quiet_import_config():
    """Stateless, sequential import config for the test; restored after."""
    config["import"].get()  # force beets' lazy config load before snapshotting
    saved = list(config.sources)
    config.set({
        "threaded": False,
        "import": {"incremental": False, "resume": False, "write": False,
                   "copy": False, "search_ids": []},
    })
    yield
    config.sources[:] = saved


def _run_import(lib, folder, search_id, decisions):
    """Run a real session on `folder`, answering each review with the next
    decision from `decisions`. Returns the review payloads seen."""
    rm = ReviewManager()
    session = WebImportSession(lib, None, [str(folder).encode()], None, rm, None)
    if search_id:
        session.preset_search_id = search_id
    payloads = []
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    pending_decisions = list(decisions)
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            if pending_decisions and pr["task_id"] not in {p["task_id"] for p in payloads}:
                payloads.append(pr)
                rm.submit_decision(pr["task_id"], pending_decisions.pop(0))
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive(), "import session did not finish"
    return [p["payload"] for p in payloads]


@pytest.fixture
def album_dir(tmp_path, create_wav_file):
    folder = tmp_path / "inbox" / "Some Album"
    create_wav_file(folder / "01 Track.wav")
    return folder


def test_direct_id_skips_broad_search(lib, album_dir, lookups):
    payloads = _run_import(lib, album_dir, MBID, [{"action": "skip"}])
    assert lookups["broad"] == 0
    assert lookups["ids"] == [[MBID]]
    assert payloads[0]["attempted_search_id"] == MBID
    assert payloads[0]["candidates"] == []


def test_without_id_runs_broad_search(lib, album_dir, lookups):
    payloads = _run_import(lib, album_dir, None, [{"action": "skip"}])
    assert lookups["broad"] == 1
    assert "attempted_search_id" not in payloads[0]


def test_direct_id_does_not_leak_into_global_config(lib, album_dir, lookups):
    _run_import(lib, album_dir, MBID, [{"action": "skip"}])
    assert config["import"]["search_ids"].as_str_seq() == []


def test_auto_search_fallback_after_direct_id(lib, album_dir, lookups):
    # Failed ID lookup -> user clicks "Auto-search instead" (blank ID).
    payloads = _run_import(
        lib, album_dir, MBID,
        [{"action": "search_id", "search_id": ""}, {"action": "skip"}],
    )
    assert lookups["ids"] == [[MBID]]
    assert lookups["broad"] == 1
    assert len(payloads) == 2


DIGITAL = "4e929666-952f-473c-baf2-97c9ca6bfbbe"
VIA = {"source": "apple_music", "collection_id": 1440662312, "release_ids": [DIGITAL]}


def _run_matched(lib, folder, matched_via, decisions):
    """Like _run_import, but as the server does for an Apple Music link match."""
    rm = ReviewManager()
    session = WebImportSession(lib, None, [str(folder).encode()], None, rm, None)
    session.preset_search_id = list(matched_via["release_ids"])
    session.matched_via = matched_via
    payloads = []
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            if decisions and pr["task_id"] not in {p["task_id"] for p in payloads}:
                payloads.append(pr)
                rm.submit_decision(pr["task_id"], decisions.pop(0))
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive()
    return [p["payload"] for p in payloads]


def test_apple_match_uses_linked_releases_only(lib, album_dir, lookups, monkeypatch):
    from beets.autotag.hooks import AlbumInfo, TrackInfo

    album = AlbumInfo(tracks=[TrackInfo(title="Track", track_id="t1")], album="Mulan",
                      album_id=DIGITAL, artist="X", artist_id="a1", data_source="MusicBrainz")
    monkeypatch.setattr(metadata_plugins, "albums_for_ids",
                        lambda ids: (lookups["ids"].append(list(ids)), iter([album]))[1])
    payloads = _run_matched(lib, album_dir, VIA, [{"action": "skip"}])
    assert lookups["broad"] == 0
    assert lookups["ids"] == [[DIGITAL]]
    assert payloads[0]["matched_via"] == VIA
    assert len(payloads[0]["candidates"]) == 1
    assert "attempted_search_id" not in payloads[0]


def test_apple_match_without_candidates_falls_back_to_search(lib, album_dir, lookups):
    # Linked release couldn't be fetched: search normally, no error banner.
    payloads = _run_matched(lib, album_dir, VIA, [{"action": "skip"}])
    assert lookups["ids"] == [[DIGITAL]]
    assert lookups["broad"] == 1
    assert payloads[0]["matched_via"]["fallback"] is True
    assert "attempted_search_id" not in payloads[0]

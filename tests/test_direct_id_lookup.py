"""Direct ID Import runs only the targeted ID lookup (ticket 40).

beets' pipeline does the first candidate lookup itself, before
choose_match, using session.config["search_ids"]. These tests run the real
beets import pipeline on a real (silent) audio file, with the metadata
backends stubbed, and record which lookups happen.
"""
from __future__ import annotations

import os
import threading
import time

import pytest
from beets import config, metadata_plugins
from beets import context as beets_context

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


def _album(album_id, media, year):
    from beets.autotag.hooks import AlbumInfo, TrackInfo

    return AlbumInfo(tracks=[TrackInfo(title="Track", track_id="t-" + album_id)], album="Some Album",
                     album_id=album_id, artist="X", artist_id="a1", data_source="MusicBrainz",
                     media=media, year=year)


def test_purchase_adds_digital_release_and_lists_it_first(lib, album_dir, lookups, monkeypatch):
    from beetsplug.webimport import purchase

    broad = [_album("cd-2002", "CD", 2002)]
    digital = {"dig-2006": _album("dig-2006", "Digital Media", 2006)}
    monkeypatch.setattr(metadata_plugins, "candidates",
                        lambda *a, **k: (lookups.__setitem__("broad", lookups["broad"] + 1), iter(broad))[1])
    monkeypatch.setattr(metadata_plugins, "albums_for_ids",
                        lambda ids: (lookups["ids"].append(list(ids)), iter([digital[i] for i in ids if i in digital]))[1])
    def detect_store(items, folder, library=False):
        assert isinstance(folder, str)  # task.paths holds bytes
        return "amazon"

    monkeypatch.setattr(purchase, "detect_store", detect_store)
    monkeypatch.setattr(purchase, "album_hints", lambda items: {"album": "Some Album", "artist": "X", "year": 2006, "tracktotal": 11})
    monkeypatch.setattr(purchase, "digital_release_ids", lambda hints, exclude=(): ["dig-2006"])

    payloads = _run_import(lib, album_dir, None, [{"action": "skip"}])
    cands = payloads[0]["candidates"]
    assert [c["album_id"] for c in cands] == ["dig-2006", "cd-2002"]
    assert [c["index"] for c in cands] == [0, 1]  # indexes follow the new order
    assert cands[0]["looks_purchased"] and not cands[1]["looks_purchased"]
    assert payloads[0]["purchase"] == {"store": "amazon", "year": 2006, "added": 1}


def test_not_a_purchase_leaves_candidates_alone(lib, album_dir, lookups, monkeypatch):
    from beetsplug.webimport import purchase

    monkeypatch.setattr(purchase, "detect_store", lambda items, folder: None)
    payloads = _run_import(lib, album_dir, None, [{"action": "skip"}])
    assert "purchase" not in payloads[0]
    assert lookups["ids"] == []


def test_user_id_skips_purchase_search(lib, album_dir, lookups, monkeypatch):
    from beetsplug.webimport import purchase

    monkeypatch.setattr(purchase, "detect_store", lambda items, folder: pytest.fail("not consulted"))
    _run_import(lib, album_dir, MBID, [{"action": "skip"}])


# -- reimport: suggest what a fresh import of the store download would --------

@pytest.fixture
def library_album(lib, tmp_path, create_wav_file):
    from beets.library import Item

    path = tmp_path / "music" / "X" / "Mulan" / "01 Track.wav"
    create_wav_file(path)
    item = Item.from_path(str(path))
    item.update({"artist": "X", "albumartist": "X", "album": "Mulan", "title": "Track", "track": 1})
    lib.add(item)
    return lib.add_album([item])


def _run_reimport(lib, album, decisions, apple=True):
    rm = ReviewManager()
    session = WebImportSession(lib, None, None, f"album_id:{album.id}", rm, None)
    session.apple_match_items = apple
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


def test_reimport_starts_from_the_apple_linked_release(lib, library_album, lookups, monkeypatch):
    from beets.autotag.hooks import AlbumInfo, TrackInfo

    from beetsplug.webimport import itunes

    seen = []
    monkeypatch.setattr(itunes, "musicbrainz_match_for_items",
                        lambda items: (seen.append([i.title for i in items]), VIA)[1])
    album = AlbumInfo(tracks=[TrackInfo(title="Track", track_id="t1")], album="Mulan",
                      album_id=DIGITAL, artist="X", artist_id="a1", data_source="MusicBrainz")
    monkeypatch.setattr(metadata_plugins, "albums_for_ids",
                        lambda ids: (lookups["ids"].append(list(ids)), iter([album]))[1])
    # "Search again" (blank ID) after the suggestion runs a normal search,
    # without matching the Apple listing a second time.
    payloads = _run_reimport(lib, library_album, [{"action": "search_id", "search_id": ""}, {"action": "skip"}])
    assert seen == [["Track"]]
    assert lookups["ids"] == [[DIGITAL]]
    assert payloads[0]["matched_via"] == VIA
    assert [c["album_id"] for c in payloads[0]["candidates"]] == [DIGITAL]
    assert "matched_via" not in payloads[1]


def test_reimport_without_apple_match_searches_normally(lib, library_album, lookups, monkeypatch):
    from beetsplug.webimport import itunes, purchase

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: pytest.fail("not asked"))
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    payloads = _run_reimport(lib, library_album, [{"action": "skip"}], apple=False)
    assert lookups["ids"] == [] and "matched_via" not in payloads[0]


def test_reimport_of_a_purchase_adds_digital_releases(lib, library_album, lookups, monkeypatch):
    from beetsplug.webimport import itunes, purchase

    calls = []
    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store",
                        lambda items, folder, library=False: calls.append((folder, library)) or "itunes")
    monkeypatch.setattr(purchase, "album_hints", lambda items: {"album": "Mulan", "artist": "X", "year": 1998, "tracktotal": 1})
    monkeypatch.setattr(purchase, "digital_release_ids", lambda hints, exclude=(): [])
    payloads = _run_reimport(lib, library_album, [{"action": "skip"}])
    assert calls == [(None, True)]
    assert payloads[0]["purchase"]["store"] == "itunes"


@pytest.mark.parametrize("explicit, expected", [({}, "kids"), ({"navidrome_library": "main"}, "main")])
def test_reimport_keeps_the_albums_fields_over_config_defaults(lib, library_album, lookups, monkeypatch, explicit, expected):
    """`import.set_fields` (homelab: navidrome_library: unassigned) are
    defaults for new imports; a reimport keeps what the album has unless
    the Reimport dialog sets it."""
    from beetsplug.webimport import itunes, purchase

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    config["import"]["set_fields"].set({"navidrome_library": "unassigned", "comments": "new"})
    library_album["navidrome_library"] = "kids"
    library_album.store()
    for item in library_album.items():
        item["navidrome_library"] = "kids"
        item.store()

    rm = ReviewManager()
    session = WebImportSession(lib, None, None, f"album_id:{library_album.id}", rm, None)
    session.reimport_set_fields = explicit

    def run():  # as the server's worker threads do
        beets_context.set_music_dir(lib.directory)
        session.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    kinds = []
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            kinds.append(pr["kind"])
            rm.submit_decision(pr["task_id"], {"action": "asis"})
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive()
    assert kinds == ["match"]  # no false "duplicate of itself"
    album = next(iter(lib.albums()))
    assert album["navidrome_library"] == expected
    assert [i["navidrome_library"] for i in album.items()] == [expected]
    assert [i.comments for i in album.items()] == ["new"]  # a default the album didn't have still applies


def test_reimport_starts_from_the_stored_originals_tags(lib, tmp_path, create_wav_file, lookups, monkeypatch):
    import json

    from beets.library import Item
    from mediafile import MediaFile

    from beetsplug.webimport import itunes, originals, purchase

    monkeypatch.setattr(originals, "store_root", lambda: tmp_path / "store")
    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    path = create_wav_file(tmp_path / "music" / "X" / "Album" / "01.wav")
    mf = MediaFile(str(path))
    mf.update({"title": "Bought Title", "artist": "Store Artist", "album": "Store Album", "track": 1})
    mf.save()
    record = originals.capture(path)
    item = Item.from_path(str(path))
    item.update({"title": "Edited", "artist": "X", "albumartist": "X", "album": "Album", "label": "Old Label"})
    item["original_file"] = json.dumps(record)
    lib.add(item)
    item.write()
    album = lib.add_album([item])

    rm = ReviewManager()
    session = WebImportSession(lib, None, None, f"album_id:{album.id}", rm, None)
    session.start_from_originals = True
    payloads = []

    def run():
        beets_context.set_music_dir(lib.directory)
        session.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            payloads.append(pr["payload"])
            rm.submit_decision(pr["task_id"], {"action": "asis"})
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive()
    assert payloads[0]["from_original"] is True
    new = next(iter(lib.items()))
    assert (new.title, new.artist, new.album, new.label) == ("Bought Title", "Store Artist", "Store Album", "")
    assert originals.load(new) == record  # still restorable afterwards


@pytest.fixture
def thirteen_albums(lib, tmp_path, create_wav_file):
    from beets.library import Item

    albums = []
    for i in range(1, 14):
        path = create_wav_file(tmp_path / "music" / "X" / f"A{i}" / "01.wav")
        item = Item.from_path(str(path))
        item.update({"title": "t", "album": f"A{i}", "albumartist": "X", "artist": "X", "track": 1})
        lib.add(item)
        albums.append(lib.add_album([item]))
    return albums


def _reviews_of(lib, session):
    rm = session.review_manager
    seen = []

    def run():
        beets_context.set_music_dir(lib.directory)
        session.run()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            if pr["task_id"] not in {s["task_id"] for s in seen}:
                seen.append(pr)
                rm.submit_decision(pr["task_id"], {"action": "skip"})
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive()
    return [s["path"] for s in seen]


def test_reimport_of_album_2_reviews_only_album_2(lib, thirteen_albums, lookups, monkeypatch):
    """Production bug: the query album_id:6 matched albums 16, 26, 36...
    (an album query matches album_id as a substring)."""
    from beetsplug.webimport import itunes, purchase, reimport

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    album2 = thirteen_albums[1]
    rm = ReviewManager()
    reviewed = []
    orig_register = rm.register

    def register(kind, path, payload, task=None):
        reviewed.append(path)
        return orig_register(kind, path, payload, task=task)

    rm.register = register

    def run():
        beets_context.set_music_dir(lib.directory)
        reimport.run_reimport(lib, rm, None, [album2.id])

    t = threading.Thread(target=run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            rm.submit_decision(pr["task_id"], {"action": "skip"})
        time.sleep(0.02)
    t.join(timeout=1)
    assert not t.is_alive()
    assert reviewed == [os.fsdecode(album2.item_dir())]


def test_reimport_skips_albums_it_wasnt_asked_for(lib, thirteen_albums, lookups, monkeypatch):
    """Guard: whatever the query finds, only the requested albums' files
    reach a review."""
    from beetsplug.webimport import itunes, purchase

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    album2 = thirteen_albums[1]
    session = WebImportSession(lib, None, None, "album_id:2", ReviewManager(), None)  # the old, too-broad query
    session.reimport_paths = {bytes(i.path) for i in album2.items()}
    assert _reviews_of(lib, session) == [os.fsdecode(album2.item_dir())]


def test_reimport_query_matches_album_ids_exactly(lib, thirteen_albums):
    from beetsplug.webimport.reimport import _build_query

    ids = [a.id for a in lib.albums(_build_query([2, 3]))]
    assert sorted(ids) == [2, 3]


def _drive(rm, threads, decide, timeout=10):
    """Answer reviews with decide(pending list) until the threads end."""
    deadline = time.monotonic() + timeout
    answered = set()
    while any(t.is_alive() for t in threads) and time.monotonic() < deadline:
        pending = [p for p in rm.list_pending() if p["task_id"] not in answered]
        for task_id, decision in decide(pending):
            answered.add(task_id)
            rm.submit_decision(task_id, decision)
        time.sleep(0.02)
    for t in threads:
        t.join(timeout=1)
    assert not any(t.is_alive() for t in threads)


def test_two_reimports_wait_for_review_at_the_same_time(lib, thirteen_albums, lookups, monkeypatch):
    """A reimport takes the Apply Lock only to apply, so several can be
    ready for review at once (it used to hold it for the whole session)."""
    from beetsplug.webimport import itunes, purchase, reimport

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    rm, apply_lock = ReviewManager(), threading.Lock()

    def run(aid):
        beets_context.set_music_dir(lib.directory)
        reimport.run_reimport(lib, rm, None, [aid], apply_lock=apply_lock, set_fields={"navidrome_library": "kids"})

    threads = [threading.Thread(target=run, args=(a.id,), daemon=True) for a in thirteen_albums[:2]]
    for t in threads:
        t.start()
    seen = {}

    def decide(pending):
        for p in pending:
            seen[p["task_id"]] = p
        if len(seen) < 2:
            return []
        seen["lock_free_with_both_in_review"] = not apply_lock.locked()
        return [(tid, {"action": "skip"}) for tid in list(seen) if tid != "lock_free_with_both_in_review"]

    _drive(rm, threads, decide)
    assert seen.get("lock_free_with_both_in_review") is True
    assert not apply_lock.locked()


def test_reimport_settings_stay_out_of_the_global_config(lib, library_album, monkeypatch):
    """from_scratch and the dialog's fields apply to the reimport's task
    only; beets' global import config, read by parallel sessions, is never
    changed."""
    from beets.autotag.hooks import AlbumInfo, TrackInfo

    from beetsplug.webimport import itunes, purchase, reimport, tagpreview

    monkeypatch.setattr(itunes, "musicbrainz_match_for_items", lambda items: None)
    monkeypatch.setattr(purchase, "detect_store", lambda items, folder, library=False: None)
    info = AlbumInfo(tracks=[TrackInfo(title="Track", track_id="t1", index=1, length=1.0)], album="Mulan",
                     album_id="r1", artist="X", artist_id="a1", data_source="MusicBrainz")
    monkeypatch.setattr(metadata_plugins, "candidates", lambda *a, **kw: iter([info]))
    monkeypatch.setattr(metadata_plugins, "albums_for_ids", lambda ids: iter(()))
    config["import"]["set_fields"].set({"navidrome_library": "unassigned"})
    for item in library_album.items():
        item.comments = "from the old tags"
        item.store()

    rm, apply_lock = ReviewManager(), threading.Lock()
    during = {}

    def run():
        beets_context.set_music_dir(lib.directory)
        reimport.run_reimport(lib, rm, None, [library_album.id], apply_lock=apply_lock,
                              from_scratch=True, set_fields={"navidrome_library": "kids"})

    t = threading.Thread(target=run, daemon=True)
    t.start()

    def decide(pending):
        out = []
        for p in pending:
            during["from_scratch"] = config["import"]["from_scratch"].get(bool)
            during["set_fields"] = config["import"]["set_fields"].get(dict)
            pv = tagpreview.preview(rm.get(p["task_id"]).task, 0)
            during["preview"] = (pv["from_scratch"], pv["set_fields"])
            out.append((p["task_id"], {"action": "select", "index": 0}))
        return out

    _drive(rm, [t], decide)
    assert during["from_scratch"] is False
    assert during["set_fields"] == {"navidrome_library": "unassigned"}
    assert during["preview"] == (True, [{"field": "navidrome_library", "value": "kids"}])
    album = next(iter(lib.albums()))
    assert album.mb_albumid == "r1"
    assert album["navidrome_library"] == "kids"
    assert [i.comments for i in album.items()] == [""]  # cleared: from scratch
    assert not apply_lock.locked()

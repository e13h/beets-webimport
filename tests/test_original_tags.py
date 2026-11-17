"""Original-tag snapshots: what each file's tags were before beets changed
them, captured when an inbox import starts and stored on the item."""
from __future__ import annotations

import json
import threading
import time
from types import SimpleNamespace

import pytest
from beets import config
from beets.library import Item
from mediafile import MediaFile
from mutagen.id3 import APIC, PRIV, TXXX
from mutagen.wave import WAVE

from beetsplug.webimport import library, snapshot
from beetsplug.webimport.queue import ReviewManager
from beetsplug.webimport.session import WebImportSession


@pytest.fixture
def tagged_wav(tmp_path, create_wav_file):
    path = create_wav_file(tmp_path / "inbox" / "Album" / "01.wav")
    mf = MediaFile(str(path))
    mf.update({"title": "Original Title", "artist": "Original Artist", "album": "Album",
               "track": 1, "year": 2001, "mb_trackid": "orig-track-id"})
    mf.save()
    w = WAVE(str(path))
    w.tags.add(TXXX(desc="Store ID", text=["12345"]))     # not a beets field
    w.tags.add(PRIV(owner="someone@example.com", data=b"secret"))  # private
    w.tags.add(APIC(mime="image/jpeg", type=3, data=b"\xff\xd8\xff" + b"0" * 50))  # image
    w.save()
    return path


def test_capture_fields_and_other_tags(tagged_wav):
    item = Item.from_path(str(tagged_wav))
    snap = snapshot.capture(item)
    assert snap["version"] == 1
    assert snap["source_path"].endswith("01.wav")
    f = snap["fields"]
    assert f["title"] == "Original Title" and f["year"] == 2001 and f["mb_trackid"] == "orig-track-id"
    assert "length" not in f and "bitrate" not in f  # audio properties, not tags
    other = snap["other"]
    assert other.get("TXXX:Store ID") == ["12345"]
    assert not any(k.upper().startswith(("PRIV", "APIC")) for k in other)
    # Tags beets maps to fields aren't repeated under "other".
    assert not any(k.startswith("TIT2") for k in other)


def test_mp4_privacy_and_image_atoms_excluded():
    assert snapshot._excluded_raw_key("apID")
    assert snapshot._excluded_raw_key("ownr")
    assert snapshot._excluded_raw_key("covr")
    assert not snapshot._excluded_raw_key("plID")
    assert not snapshot._excluded_raw_key("----:com.apple.iTunes:iTunSMPB")


def _session(paths=True):
    s = WebImportSession.__new__(WebImportSession)
    s.paths = [b"/inbox/x"] if paths else None
    s.query = None if paths else "id:1"
    return s


def test_listener_snapshots_inbox_items(tagged_wav):
    item = Item.from_path(str(tagged_wav))
    task = SimpleNamespace(is_album=True, items=[item])
    snapshot.on_import_task_start(task=task, session=_session())
    assert json.loads(item[snapshot.SNAPSHOT_FIELD])["fields"]["title"] == "Original Title"


def test_listener_never_overwrites_existing_snapshot(tagged_wav):
    item = Item.from_path(str(tagged_wav))
    item[snapshot.SNAPSHOT_FIELD] = '{"version": 1, "fields": {"title": "First"}}'
    snapshot.on_import_task_start(task=SimpleNamespace(is_album=True, items=[item]), session=_session())
    assert json.loads(item[snapshot.SNAPSHOT_FIELD])["fields"]["title"] == "First"


def test_listener_skips_library_reimports(tagged_wav):
    item = Item.from_path(str(tagged_wav))
    snapshot.on_import_task_start(task=SimpleNamespace(is_album=True, items=[item]), session=_session(paths=False))
    assert snapshot.SNAPSHOT_FIELD not in item


def test_listener_ignores_other_sessions(tagged_wav):
    item = Item.from_path(str(tagged_wav))
    plain = SimpleNamespace(paths=[b"/x"], query=None)  # e.g. a CLI `beet import`
    snapshot.on_import_task_start(task=SimpleNamespace(is_album=True, items=[item]), session=plain)
    assert snapshot.SNAPSHOT_FIELD not in item


@pytest.fixture
def import_config():
    config["import"].get()
    saved = list(config.sources)
    config.set({"threaded": False, "autotag": True, "import": {
        "incremental": False, "resume": False, "write": True, "copy": False, "search_ids": []}})
    yield
    config.sources[:] = saved


def test_real_import_stores_snapshot_and_explorer_shows_it(lib, tagged_wav, import_config, monkeypatch):
    from beets import metadata_plugins
    monkeypatch.setattr(metadata_plugins, "candidates", lambda *a, **k: iter(()))
    monkeypatch.setattr(metadata_plugins, "albums_for_ids", lambda ids: iter(()))
    snapshot.register(lambda event, fn: _listeners.setdefault(event, []).append(fn))
    from beets import plugins
    orig_send = plugins.send

    def send(event, **kw):
        for fn in _listeners.get(event, []):
            fn(**kw)
        return orig_send(event, **kw)

    monkeypatch.setattr(plugins, "send", send)

    rm = ReviewManager()
    session = WebImportSession(lib, None, [str(tagged_wav.parent).encode()], None, rm, None)
    t = threading.Thread(target=session.run, daemon=True)
    t.start()
    deadline = time.monotonic() + 10
    while t.is_alive() and time.monotonic() < deadline:
        for pr in rm.list_pending():
            rm.submit_decision(pr["task_id"], {"action": "asis"})
        time.sleep(0.02)
    t.join(timeout=2)

    album = next(iter(lib.albums()))
    data = library.get_album_explorer(lib, album.id)
    track = data["tracks"][0]
    assert track["original"]["fields"]["title"] == "Original Title"
    assert track["original"]["other"]["TXXX:Store ID"] == ["12345"]
    # The raw JSON field is not shown as an ordinary custom field.
    assert snapshot.SNAPSHOT_FIELD not in track["fields"]
    assert snapshot.SNAPSHOT_FIELD not in track["custom_fields"]


_listeners: dict = {}


@pytest.fixture(autouse=True)
def _reset_listeners():
    _listeners.clear()
    yield
    _listeners.clear()

"""Move mode: inbox folder lifecycle (lifecycle.py) and the round trip
import -> Undo import."""
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import confuse
import pytest
from beets import config
from beets.library import Item

from beetsplug.webimport import artchoice, lifecycle, originals, restore

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    root = tmp_path / "store"
    monkeypatch.setattr(originals, "store_root", lambda: root)
    lifecycle._same_mount_cache.clear()
    return root


def _tree(folder: Path) -> dict:
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def _album_folder(inbox: Path) -> Path:
    folder = inbox / "Artist - Album"
    (folder / "Scans").mkdir(parents=True)
    shutil.copy(FIXTURES / "tone.mp3", folder / "01 Tone.mp3")
    shutil.copy(FIXTURES / "tone.flac", folder / "02 Tone.flac")
    (folder / "cover.jpg").write_bytes(b"\xff\xd8 cover bytes")
    (folder / "rip.log").write_text("EAC log")
    (folder / "Scans" / "back.jpg").write_bytes(b"\xff\xd8 back")
    return folder


def _run_import(lib, folder, inbox, monkeypatch, *, move=True):
    from beets import metadata_plugins, plugins

    from beetsplug.webimport.queue import ReviewManager
    from beetsplug.webimport.session import WebImportSession

    config["import"].get()
    saved = list(config.sources)
    config.set({"threaded": False, "import": {"incremental": False, "resume": False, "write": True,
                                              "copy": not move, "move": move, "search_ids": []}})
    monkeypatch.setattr(metadata_plugins, "candidates", lambda *a, **k: iter(()))
    orig_send = plugins.send

    def send(event, **kw):
        if event == "import_task_files":
            artchoice.on_import_task_files(**kw)
            originals.verify_task(**kw)
            lifecycle.finish_task(**kw)
        return orig_send(event, **kw)

    monkeypatch.setattr(plugins, "send", send)
    wi = confuse.RootView([confuse.ConfigSource.of({"inbox_dir": str(inbox)})])
    try:
        rm = ReviewManager()
        session = WebImportSession(lib, None, [str(folder).encode()], None, rm, wi)
        t = threading.Thread(target=session.run, daemon=True)
        t.start()
        deadline = time.monotonic() + 15
        while t.is_alive() and time.monotonic() < deadline:
            for pr in rm.list_pending():
                rm.submit_decision(pr["task_id"], {"action": "asis"})
            time.sleep(0.02)
        t.join(timeout=2)
    finally:
        config.sources[:] = saved
    return next(iter(lib.albums()))


def test_move_import_empties_inbox_and_undo_restores_folder_exactly(lib, tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    folder = _album_folder(inbox)
    before = _tree(folder)

    album = _run_import(lib, folder, inbox, monkeypatch)

    assert not folder.exists(), "the inbox folder is emptied and pruned"
    assert len(album.items()) == 2
    assert inbox.exists()
    assert list(inbox.iterdir()) == [], "safety folder removed too"
    assert all(os.path.exists(i.path) for i in album.items())
    comps = lifecycle.load_companions(album)
    assert sorted(f["rel"] for f in comps["files"]) == ["Scans/back.jpg", "cover.jpg", "rip.log"]
    assert all(originals.can_restore(originals.load(i), i.path) for i in album.items())

    lib_files = [os.fsdecode(i.path) for i in album.items()]
    assert all(f.startswith(os.fsdecode(lib.directory)) for f in lib_files)
    result = restore.undo(lib, album, str(inbox))

    assert result["audio_files"] == 2 and result["other_files"] == 3
    assert _tree(folder) == before, "byte-identical folder, other files included"
    assert lib.get_album(album.id) is None
    assert not any(os.path.exists(f) for f in lib_files)
    root = originals.store_root()
    assert not root.exists() or not any(root.iterdir()), "stored originals cleaned up"


def test_copy_mode_import_leaves_inbox_alone(lib, tmp_path, monkeypatch):
    inbox = tmp_path / "inbox"
    folder = _album_folder(inbox)
    before = _tree(folder)
    _run_import(lib, folder, inbox, monkeypatch, move=False)
    assert _tree(folder) == before


def test_safety_copy_is_a_hard_link_across_mounts(tmp_path, monkeypatch):
    src = tmp_path / "inbox" / "a.mp3"
    src.parent.mkdir()
    shutil.copy(FIXTURES / "tone.mp3", src)
    rec = {"sha256": "abc", "name": "a.mp3"}
    monkeypatch.setattr(lifecycle, "_rename_would_succeed", lambda s, l: False)
    dest = lifecycle.make_safety_copy(src, rec, tmp_path / "inbox", tmp_path / "music")
    assert dest.stat().st_ino == src.stat().st_ino


def test_safety_copy_is_a_real_copy_when_rename_would_succeed(tmp_path):
    src = tmp_path / "inbox" / "a.mp3"
    src.parent.mkdir()
    shutil.copy(FIXTURES / "tone.mp3", src)
    # Same filesystem, no bind mounts: beets would rename and then rewrite
    # the file in place, which a hard link would see.
    dest = lifecycle.make_safety_copy(src, {"sha256": "abc", "name": "a.mp3"}, tmp_path / "inbox", tmp_path / "music")
    assert dest.stat().st_ino != src.stat().st_ino
    assert dest.read_bytes() == src.read_bytes()


def test_verify_falls_back_to_the_safety_copy(lib, tmp_path, monkeypatch):
    from types import SimpleNamespace

    from beetsplug.webimport.session import WebImportSession

    src = tmp_path / "inbox" / "a.mp3"
    src.parent.mkdir()
    shutil.copy(FIXTURES / "tone.mp3", src)
    rec = originals.capture(src)
    safety = tmp_path / "safety.mp3"
    shutil.copy(src, safety)
    src.unlink()  # moved away, as in move mode
    item = Item(path=str(tmp_path / "lib.mp3"), title="x")
    shutil.copy(safety, item.path)
    item[originals.FIELD] = json.dumps(rec)
    lib.add(item)
    monkeypatch.setattr(originals, "can_restore", lambda r, p: False)
    task = SimpleNamespace(imported_items=lambda: [item], _webimport_safety={rec["sha256"]: safety})
    session = WebImportSession.__new__(WebImportSession)
    originals.verify_task(session, task)
    assert originals.load(item)["format"] == "full"
    assert (originals.store_root() / rec["sha256"] / "full").read_bytes() == safety.read_bytes()


def test_cleanup_safety_recovers_only_orphans(lib, tmp_path):
    root = tmp_path / "inbox"
    safety = root / lifecycle.SAFETY_DIRNAME
    safety.mkdir(parents=True)
    (safety / "aaa.mp3").write_bytes(b"in library")
    linked_src = root / "Album" / "b.mp3"
    linked_src.parent.mkdir()
    linked_src.write_bytes(b"still in inbox")
    os.link(linked_src, safety / "bbb.mp3")
    (safety / "ccc.mp3").write_bytes(b"orphan")
    item = Item(path=str(tmp_path / "x.mp3"), title="x")
    item[originals.FIELD] = json.dumps({"sha256": "aaa"})
    lib.add(item)

    recovered = lifecycle.cleanup_safety(lib, root)

    assert recovered == [str(root / lifecycle.RECOVERED_DIRNAME / "ccc.mp3")]
    assert not safety.exists()
    assert linked_src.read_bytes() == b"still in inbox"


def _copy_mode_imported(lib, tmp_path):
    """An album imported in copy mode before originals existed: retagged
    library copy, untouched inbox folder with a marker."""
    inbox = tmp_path / "inbox"
    folder = inbox / "Old"
    folder.mkdir(parents=True)
    shutil.copy(FIXTURES / "tone_moov_front.m4a", folder / "01.m4a")
    (folder / "cover.jpg").write_bytes(b"cover")
    libfile = tmp_path / "music" / "Old" / "01 New.m4a"
    libfile.parent.mkdir(parents=True)
    shutil.copy(folder / "01.m4a", libfile)
    item = Item.from_path(str(libfile))
    item.update({"title": "Retagged", "album": "Old"})
    item.write()
    album = lib.add_album([item])
    (folder / lifecycle.MARKER).write_text(json.dumps({"album_id": album.id}))
    return inbox, folder, album


def test_backfill_then_release_then_undo(lib, tmp_path):
    inbox, folder, album = _copy_mode_imported(lib, tmp_path)
    before = _tree(folder)
    assert lifecycle.backfill_all(lib, inbox) == 1
    assert lifecycle.backfill_all(lib, inbox) == 0  # nothing left to do: no file reads
    rec = originals.load(album.items()[0])
    assert rec["source_path"] == str(folder / "01.m4a")

    r = lifecycle.release_folder(lib, folder, inbox)
    assert r == {"removed": str(folder.resolve()), "audio_files": 1, "other_files": 1}
    assert not folder.exists()

    restore.undo(lib, lib.get_album(album.id), str(inbox))
    assert {k: v for k, v in _tree(folder).items()} == {k: v for k, v in before.items() if k != lifecycle.MARKER}


def test_release_refuses_with_unknown_audio(lib, tmp_path):
    inbox, folder, _ = _copy_mode_imported(lib, tmp_path)
    shutil.copy(FIXTURES / "tone.mp3", folder / "02 extra.mp3")
    with pytest.raises(lifecycle.ReleaseRefused) as exc:
        lifecycle.release_folder(lib, folder, inbox)
    assert "02 extra.mp3" in exc.value.problems[0]
    assert (folder / "01.m4a").exists()

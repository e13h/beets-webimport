"""Undo import from the library: originals back in the inbox, album gone."""
import hashlib
import json
import os
import shutil
from pathlib import Path

import pytest
from beets.library import Item

from beetsplug.webimport import originals, restore

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    root = tmp_path / "store"
    monkeypatch.setattr(originals, "store_root", lambda: root)
    return root


@pytest.fixture
def imported(tmp_path, lib):
    """An album 'imported' from inbox/Album: originals captured, library
    copies retagged, marker written. Returns (album, inbox folder, {name: sha})."""
    inbox = tmp_path / "inbox"
    folder = inbox / "Album"
    folder.mkdir(parents=True)
    libdir = tmp_path / "music" / "Artist" / "Album"
    libdir.mkdir(parents=True)
    items, shas = [], {}
    for n, name in enumerate(["tone.mp3", "tone_moov_front.m4a", "tone.ogg"], 1):
        src = folder / f"0{n} {name}"
        shutil.copy(FIXTURES / name, src)
        os.utime(src, (1_000_000_000, 1_000_000_000))
        os.chmod(src, 0o640)
        shas[src.name] = hashlib.sha256(src.read_bytes()).hexdigest()
        record = originals.capture(src)
        dst = libdir / src.name
        shutil.copy(src, dst)
        item = Item.from_path(str(dst))
        item.update(dict(title=f"New title {n}", album="New Album", artist="New", track=n))
        item.write()
        item[originals.FIELD] = json.dumps(record)
        items.append(item)
    album = lib.add_album(items)
    (folder / restore.MARKER).write_text(json.dumps({"album_id": album.id}))
    return album, inbox, folder, shas


def _shas(folder: Path) -> dict:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.iterdir() if not p.name.startswith(".")}


def test_move_mode_undo_restores_exact_files(imported, lib, store):
    album, inbox, folder, shas = imported
    lib_files = [os.fsdecode(i.path) for i in album.items()]
    for p in folder.iterdir():  # move mode: the inbox originals are gone
        if not p.name.startswith("."):
            p.unlink()

    result = restore.undo(lib, album, str(inbox))

    assert result["restored"] == 3 and result["already_in_inbox"] == 0
    assert _shas(folder) == shas
    assert all(os.stat(folder / n).st_mtime == 1_000_000_000 for n in shas)
    assert all(os.stat(folder / n).st_mode & 0o777 == 0o640 for n in shas)
    assert not (folder / restore.MARKER).exists()
    assert not any(os.path.exists(f) for f in lib_files)
    assert lib.get_album(album.id) is None and not list(lib.items())
    assert not any(store.iterdir())  # stored originals cleaned up
    assert not [p for p in folder.iterdir() if p.name.startswith(".webimport-restore-")]


def test_copy_mode_leaves_identical_inbox_files(imported, lib):
    album, inbox, folder, shas = imported
    before = {p.name: p.stat().st_ino for p in folder.iterdir()}
    result = restore.undo(lib, album, str(inbox))
    assert result["already_in_inbox"] == 3 and result["restored"] == 0
    assert _shas(folder) == shas
    assert {p.name: p.stat().st_ino for p in folder.iterdir()} == {k: v for k, v in before.items() if k != restore.MARKER}


def test_conflicting_file_refuses_and_changes_nothing(imported, lib):
    album, inbox, folder, _ = imported
    (folder / "01 tone.mp3").write_bytes(b"something else")
    with pytest.raises(restore.UndoRefused) as exc:
        restore.undo(lib, album, str(inbox))
    assert "different file" in exc.value.plan.problems[0]
    assert lib.get_album(album.id) is not None
    assert all(os.path.exists(i.path) for i in album.items())
    assert (folder / restore.MARKER).exists()


def test_album_without_originals_is_refused(imported, lib):
    album, inbox, _, _ = imported
    item = album.items()[0]
    del item[originals.FIELD]
    item.store()
    p = restore.plan(album, str(inbox))
    assert not p.as_json()["ok"] and "imported before originals were kept" in p.problems[0]


def test_failed_rebuild_refuses_and_cleans_up(imported, lib):
    album, inbox, folder, _ = imported
    for p in folder.iterdir():
        if not p.name.startswith("."):
            p.unlink()
    lib_mp3 = next(os.fsdecode(i.path) for i in album.items() if i.path.endswith(b".mp3"))
    data = bytearray(Path(lib_mp3).read_bytes())
    data[-500] ^= 0xFF  # audio changed after import
    Path(lib_mp3).write_bytes(bytes(data))

    with pytest.raises(restore.UndoRefused):
        restore.undo(lib, album, str(inbox))
    assert [p.name for p in folder.iterdir()] == [restore.MARKER]  # no partial restore
    assert lib.get_album(album.id) is not None


def test_destination_outside_inbox_is_refused(imported, lib, tmp_path):
    album, _, _, _ = imported
    p = restore.plan(album, str(tmp_path / "somewhere-else"))
    assert len(p.problems) == 3 and "isn't in the inbox" in p.problems[0]

from __future__ import annotations

from pathlib import Path

from beets.library import Item, Library

from beetsplug.webimport.grace import GracePeriodManager


def test_register_and_list_undoable_with_decreasing_seconds(lib: Library):
    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    rec_id = mgr.register("album", 1, "Test Artist - Test Album")
    assert rec_id is not None

    undoables = mgr.list_undoable()
    assert len(undoables) == 1
    assert undoables[0]["record_id"] == rec_id
    assert undoables[0]["kind"] == "album"
    assert undoables[0]["label"] == "Test Artist - Test Album"
    assert 0 < undoables[0]["seconds_remaining"] <= 600


def test_expiry_pruning_and_cannot_undo_expired(lib: Library):
    mgr = GracePeriodManager(lib, grace_period_seconds=10)
    rec_id = mgr.register("album", 1, "Test Artist - Expired Album")

    # Manually backdate imported_at
    mgr._records[rec_id].imported_at -= 20

    # Pruned on list_undoable
    assert mgr.list_undoable() == []

    # Undo fails on expired record
    assert mgr.undo(rec_id) is False


def test_undo_removes_db_entry_and_files_scoped_to_id(
    lib: Library, tmp_path: Path, create_wav_file
):
    # Setup album 1 with files
    file1 = create_wav_file(tmp_path / "music" / "Artist1" / "Album1" / "track1.wav")
    item1 = Item.from_path(str(file1))
    lib.add(item1)
    album1 = lib.add_album([item1])

    # Setup album 2 with files (should remain untouched)
    file2 = create_wav_file(tmp_path / "music" / "Artist2" / "Album2" / "track2.wav")
    item2 = Item.from_path(str(file2))
    lib.add(item2)
    album2 = lib.add_album([item2])

    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    rec_id1 = mgr.register("album", album1.id, "Artist1 - Album1")

    assert file1.exists()
    assert file2.exists()

    # Perform undo on album 1
    ok = mgr.undo(rec_id1)
    assert ok is True

    # Album 1 and file 1 should be gone
    assert lib.get_album(album1.id) is None
    assert not file1.exists()

    # Album 2 and file 2 must remain untouched
    assert lib.get_album(album2.id) is not None
    assert file2.exists()


def test_undo_item_removes_item_and_file_scoped_to_id(
    lib: Library, tmp_path: Path, create_wav_file
):
    file1 = create_wav_file(tmp_path / "music" / "Singleton" / "track1.wav")
    item1 = Item.from_path(str(file1))
    lib.add(item1)

    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    rec_id = mgr.register("item", item1.id, "Singleton - track1")

    ok = mgr.undo(rec_id)
    assert ok is True
    assert lib.get_item(item1.id) is None
    assert not file1.exists()


def test_undo_unknown_or_already_consumed_id(lib: Library):
    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    rec_id = mgr.register("album", 999, "Unknown Album")

    # First undo fails because db object doesn't exist
    assert mgr.undo(rec_id) is False

    # Second attempt fails because record was already consumed/popped
    assert mgr.undo(rec_id) is False

    # Arbitrary random record fails
    assert mgr.undo("nonexistent-record-id") is False

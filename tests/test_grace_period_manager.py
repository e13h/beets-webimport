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


def test_staging_bin_survives_immediately_after_apply(lib: Library, tmp_path: Path):
    bin_dir = tmp_path / "inbox" / "_grouped" / "grp123" / "bin_0"
    bin_dir.mkdir(parents=True, exist_ok=True)
    audio_file = bin_dir / "track.wav"
    audio_file.write_text("audio")

    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    _ = mgr.register(
        "album",
        1,
        "Artist - Album",
        inbox_path=str(bin_dir),
        is_staging_bin=True,
    )

    # Immediately after apply / register, bin and files still exist untouched
    assert bin_dir.exists()
    assert audio_file.exists()
    assert len(mgr.list_undoable()) == 1


def test_staging_bin_preserved_if_undone_within_grace_period(
    lib: Library, tmp_path: Path, create_wav_file
):
    # Setup library files & album
    music_file = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track.wav")
    item = Item.from_path(str(music_file))
    lib.add(item)
    album = lib.add_album([item])
    assert album.id is not None

    # Setup staging bin in inbox with marker
    bin_dir = tmp_path / "inbox" / "_grouped" / "grp456" / "bin_0"
    bin_dir.mkdir(parents=True, exist_ok=True)
    inbox_file = bin_dir / "track.wav"
    inbox_file.write_text("audio")
    marker_file = bin_dir / ".webimport_imported"
    marker_file.write_text("{}")

    mgr = GracePeriodManager(lib, grace_period_seconds=10)
    rec_id = mgr.register(
        "album",
        album.id,
        "Artist - Album",
        inbox_path=str(bin_dir),
    )
    # Staging bin flag is auto-inferred from _grouped in path
    assert mgr._records[rec_id].is_staging_bin is True

    # Perform undo within grace period
    ok = mgr.undo(rec_id)
    assert ok is True
    assert lib.get_album(album.id) is None
    assert not marker_file.exists()
    assert bin_dir.exists()
    assert inbox_file.exists()

    # When time passes and pruning runs, staging bin remains preserved
    mgr.prune_expired()
    assert bin_dir.exists()
    assert inbox_file.exists()


def test_staging_bin_cleaned_up_on_grace_period_expiry(
    lib: Library, tmp_path: Path
):
    group_dir = tmp_path / "inbox" / "_grouped" / "grp789"
    bin_0 = group_dir / "bin_0"
    bin_0.mkdir(parents=True, exist_ok=True)
    (bin_0 / "track0.wav").write_text("audio0")

    bin_1 = group_dir / "bin_1"
    bin_1.mkdir(parents=True, exist_ok=True)
    (bin_1 / "track1.wav").write_text("audio1")

    mgr = GracePeriodManager(lib, grace_period_seconds=10)
    rec_0 = mgr.register("album", 1, "Album 0", inbox_path=str(bin_0))
    rec_1 = mgr.register("album", 2, "Album 1", inbox_path=str(bin_1))

    # Backdate bin_0 past grace period, bin_1 remains active
    mgr._records[rec_0].imported_at -= 20

    mgr.prune_expired()
    # bin_0 is removed on expiry
    assert not bin_0.exists()
    # bin_1 is still within grace period and preserved
    assert bin_1.exists()
    assert group_dir.exists()

    # Now expire bin_1 as well
    mgr._records[rec_1].imported_at -= 20
    mgr.prune_expired()

    # bin_1 is removed, and empty parent group_dir and _grouped are cleaned up
    assert not bin_1.exists()
    assert not group_dir.exists()
    assert not (tmp_path / "inbox" / "_grouped").exists()


def test_non_staging_inbox_folder_not_cleaned_up_on_expiry(
    lib: Library, tmp_path: Path
):
    inbox_dir = tmp_path / "inbox" / "Standard Album"
    inbox_dir.mkdir(parents=True, exist_ok=True)
    track = inbox_dir / "track.wav"
    track.write_text("audio")

    mgr = GracePeriodManager(lib, grace_period_seconds=10)
    rec_id = mgr.register("album", 1, "Standard Album", inbox_path=str(inbox_dir), is_staging_bin=False)

    # Backdate past grace period
    mgr._records[rec_id].imported_at -= 20

    mgr.prune_expired()
    # Undo record is pruned
    assert mgr.list_undoable() == []
    # Standard inbox directory and files remain intact
    assert inbox_dir.exists()
    assert track.exists()

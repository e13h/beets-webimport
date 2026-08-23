from __future__ import annotations

from pathlib import Path

from beets.library import Item, Library

from beetsplug.webimport.tags import TagStore, _split_tags, apply_tag_to_album, apply_tag_to_item


def test_tag_store_add_and_persistence(tmp_path: Path):
    json_path = tmp_path / "tags.json"
    store = TagStore(json_path)

    store.add_field("mood")
    store.add_value("mood", "chill")
    store.add_value("mood", "energetic")
    store.add_value("mood", "chill")  # duplicate should not duplicate

    assert store.list_fields() == ["mood"]
    assert store.list_values("mood") == ["chill", "energetic"]

    # Test remove value
    store.remove_value("mood", "chill")
    assert store.list_values("mood") == ["energetic"]

    # Verify persistence across new store instance
    store2 = TagStore(json_path)
    assert store2.list_fields() == ["mood"]
    assert store2.list_values("mood") == ["energetic"]


def test_apply_tag_to_album_writes_down_to_all_tracks(
    lib: Library, tmp_path: Path, create_wav_file
):
    file1 = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track1.wav")
    file2 = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track2.wav")

    item1 = Item.from_path(str(file1))
    item2 = Item.from_path(str(file2))
    lib.add(item1)
    lib.add(item2)
    album = lib.add_album([item1, item2])

    # Apply first tag
    apply_tag_to_album(lib, album, "mood", "uplifting", add=True)

    # Re-fetch from library to confirm database persistence
    refreshed_album = lib.get_album(album.id)
    assert refreshed_album.get("mood") == "uplifting"
    for it in refreshed_album.items():
        assert it.get("mood") == "uplifting"

    # Apply second tag (multi-value)
    apply_tag_to_album(lib, album, "mood", "summer", add=True)
    refreshed_album = lib.get_album(album.id)
    album_tags = _split_tags(refreshed_album.get("mood"))
    assert "uplifting" in album_tags
    assert "summer" in album_tags

    for it in refreshed_album.items():
        item_tags = _split_tags(it.get("mood"))
        assert "uplifting" in item_tags
        assert "summer" in item_tags

    # Remove one tag
    apply_tag_to_album(lib, album, "mood", "uplifting", add=False)
    refreshed_album = lib.get_album(album.id)
    assert _split_tags(refreshed_album.get("mood")) == ["summer"]
    for it in refreshed_album.items():
        assert _split_tags(it.get("mood")) == ["summer"]


def test_apply_tag_to_item_affects_only_target_track(
    lib: Library, tmp_path: Path, create_wav_file
):
    file1 = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track1.wav")
    file2 = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track2.wav")

    item1 = Item.from_path(str(file1))
    item2 = Item.from_path(str(file2))
    lib.add(item1)
    lib.add(item2)
    album = lib.add_album([item1, item2])

    apply_tag_to_item(item1, "mood", "melancholic", add=True)

    # Re-fetch from library
    refreshed_item1 = lib.get_item(item1.id)
    refreshed_item2 = lib.get_item(item2.id)
    refreshed_album = lib.get_album(album.id)

    assert refreshed_item1.get("mood") == "melancholic"
    assert refreshed_item2.get("mood", "") == ""
    assert refreshed_album.get("mood", "") == ""

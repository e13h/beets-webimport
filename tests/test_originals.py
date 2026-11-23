"""Originals: rebuild each inbox file byte for byte after beets rewrites it."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest
from beets.library import Item
from mediafile import MediaFile

from beetsplug.webimport import originals

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
ART = bytes.fromhex("ffd8ffe000104a46494600010100000100010000") + b"\0" * 300_000 + b"\xff\xd9"


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    root = tmp_path / "store"
    monkeypatch.setattr(originals, "store_root", lambda: root)
    return root


def _rewrite_like_an_import(path: Path):
    """Heavier than a real import: every common tag changes, lyrics grow the
    tag block, and new art is embedded."""
    item = Item.from_path(str(path))
    item.update(dict(title="A much longer title " * 5, artist="Someone Else", album="New Album",
                     albumartist="Someone Else", year=2020, month=1, day=10, comments="",
                     mb_albumid="4e929666-952f-473c-baf2-97c9ca6bfbbe", lyrics="la " * 4000,
                     genres=["a", "b"], label="Label"))
    item.write()
    mf = MediaFile(str(path))
    mf.art = ART
    mf.save()


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.iterdir()))
def test_rebuilds_original_byte_for_byte(tmp_path, name):
    src = tmp_path / "inbox" / name
    src.parent.mkdir()
    shutil.copy(FIXTURES / name, src)
    original = src.read_bytes()
    record = originals.capture(src)
    assert record["format"] != "full", "should split, not keep whole"
    assert record["stored_bytes"] < len(original)

    lib_copy = tmp_path / "library" / name
    lib_copy.parent.mkdir()
    shutil.copy(src, lib_copy)
    _rewrite_like_an_import(lib_copy)
    assert lib_copy.read_bytes() != original

    assert originals.rebuild(record, lib_copy) == original


def test_ogg_audio_pages_were_renumbered_and_are_restored(tmp_path):
    src = tmp_path / "tone.ogg"
    shutil.copy(FIXTURES / "tone.ogg", src)
    record = originals.capture(src)
    _rewrite_like_an_import(src)  # big comment packet: more header pages
    data = src.read_bytes()
    s = originals.split(data, str(src))
    assert originals._ogg_pages(data[s.start:])[0][4] != record["ogg_seq0"]
    assert hashlib.sha256(originals.rebuild(record, src)).hexdigest() == record["sha256"]


def test_refuses_when_audio_changed(tmp_path):
    src = tmp_path / "tone.mp3"
    shutil.copy(FIXTURES / "tone.mp3", src)
    record = originals.capture(src)
    data = bytearray(src.read_bytes())
    s = originals.split(bytes(data), str(src))
    data[s.start + 200] ^= 0xFF
    src.write_bytes(bytes(data))
    with pytest.raises(originals.RestoreError):
        originals.rebuild(record, src)
    assert not originals.can_restore(record, src)


def test_unsplittable_formats_are_kept_whole(tmp_path, create_wav_file):
    wav = create_wav_file(tmp_path / "a.wav")
    original = wav.read_bytes()
    record = originals.capture(wav)
    assert record["format"] == "full"
    wav.write_bytes(b"changed")
    assert originals.rebuild(record, wav) == original


def test_identical_files_share_storage(tmp_path, store):
    for d in ("a", "b"):
        (tmp_path / d).mkdir()
        shutil.copy(FIXTURES / "tone.flac", tmp_path / d / "t.flac")
    r1 = originals.capture(tmp_path / "a" / "t.flac")
    r2 = originals.capture(tmp_path / "b" / "t.flac")
    assert r1["sha256"] == r2["sha256"]
    assert [p.name for p in store.iterdir()] == [r1["sha256"]]


def test_prune_keeps_only_referenced(tmp_path, store, lib):
    shutil.copy(FIXTURES / "tone.mp3", tmp_path / "a.mp3")
    shutil.copy(FIXTURES / "tone.flac", tmp_path / "b.flac")
    kept = originals.capture(tmp_path / "a.mp3")
    orphan = originals.capture(tmp_path / "b.flac")
    item = Item(path=str(tmp_path / "a.mp3"), title="x")
    item[originals.FIELD] = json.dumps(kept)
    lib.add(item)
    assert originals.prune(lib) == 1
    assert [p.name for p in store.iterdir()] == [kept["sha256"]]
    assert orphan["sha256"] not in originals.referenced(lib)


@pytest.mark.parametrize("name", ["tone_moov_front.m4a", "tone.mp3", "tone.flac"])
def test_read_tags_gives_the_originals_tags_without_writing(tmp_path, name):
    path = tmp_path / name
    shutil.copy(FIXTURES / name, path)
    mf = MediaFile(str(path))
    mf.update({"title": "Bought Title", "artist": "Store Artist", "album": "Store Album", "track": 3})
    mf.save()
    record = originals.capture(path)
    _rewrite_like_an_import(path)
    before = path.read_bytes()
    tags = originals.read_tags(record, str(path))
    assert (tags["title"], tags["artist"], tags["album"], tags["track"]) == ("Bought Title", "Store Artist", "Store Album", 3)
    assert not tags["mb_albumid"] and not tags["label"]
    assert path.read_bytes() == before


def test_reimport_restores_original_tags_all_or_nothing(tmp_path):
    from beetsplug.webimport.reimport import restore_original_tags

    items = []
    for i, title in enumerate(["One", "Two"]):
        path = tmp_path / f"{i}.mp3"
        shutil.copy(FIXTURES / "tone.mp3", path)
        mf = MediaFile(str(path))
        mf.update({"title": title, "album": "Bought"})
        mf.save()
        record = originals.capture(path)
        _rewrite_like_an_import(path)
        item = Item.from_path(str(path))
        item["original_file"] = json.dumps(record)
        items.append(item)
    without = Item.from_path(items[1].path)  # no stored original
    assert restore_original_tags([items[0], without], b"") is False
    assert items[0].title.startswith("A much longer title")  # untouched

    assert restore_original_tags(items, b"") is True
    assert [(i.title, i.album, i.label, i.mb_albumid) for i in items] == [("One", "Bought", "", ""), ("Two", "Bought", "", "")]

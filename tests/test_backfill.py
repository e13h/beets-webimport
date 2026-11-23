"""Backfill (ADR-0016): attach store downloads to tracks already in the
library, swapping in better-quality files, and Undo import afterwards."""
import hashlib
import json
import os
import shutil
import threading
import time
from pathlib import Path

import pytest
from beets.library import Item
from mediafile import Image, ImageType, MediaFile

from beetsplug.webimport import backfill, lifecycle, originals, restore

FIXTURES = Path(__file__).parent / "fixtures" / "audio"
FP_A = [0x12345678 * (i + 1) & 0xFFFFFFFF for i in range(200)]
FP_B = [0x9ABCDEF1 * (i + 7) & 0xFFFFFFFF for i in range(200)]


@pytest.fixture(autouse=True)
def store(tmp_path, monkeypatch):
    root = tmp_path / "config" / "webimport-originals"
    monkeypatch.setattr(originals, "store_root", lambda: root)
    return root


@pytest.fixture
def fingerprints(monkeypatch):
    """Fingerprint by file name stem: files whose stem starts with "same"
    are one recording; anything else is another."""
    def fake(path):
        return FP_A if Path(path).stem.lower().startswith(("same", "0")) else FP_B
    monkeypatch.setattr(backfill, "fingerprint", fake)
    monkeypatch.setattr(backfill, "fpcalc_path", lambda: "fpcalc")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def tagged(src: Path, dst: Path, **tags) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(src, dst)
    m = MediaFile(str(dst))
    for k, v in tags.items():
        setattr(m, k, v)
    m.save()
    return dst


def library_album(lib, fixture: str, name: str, art: bytes | None = None, **fields):
    music = Path(os.fsdecode(lib.directory))
    path = music / "Artist" / "Album" / name
    tagged(FIXTURES / fixture, path)
    item = Item.from_path(str(path))
    item.update({"title": "Library Title", "artist": "Artist", "album": "Album", "albumartist": "Artist",
                 "track": 1, **fields})
    item.write()
    if art:
        m = MediaFile(str(path))
        m.images = [Image(data=art, desc="", type=ImageType.front)]
        m.save()
    album = lib.add_album([item])
    return album, lib.get_item(item.id)


def run(lib, inbox: Path, tmp_path: Path):
    cache = backfill.Cache(tmp_path / "cache.sqlite")
    index = backfill.LibraryIndex(lib, cache)
    cards = backfill.inbox_cards(inbox)
    files = [f for c in cards for f in lifecycle._audio_files(c)]
    return cache, index, backfill.analyze(lib, files, cache, index)


# -- pure functions ------------------------------------------------------------------------

def q(fmt, kbps=0, depth=0, rate=44100):
    return backfill.Quality(fmt, kbps * 1000, rate, depth, 200.0)


def test_quality_compare():
    assert backfill.compare(q("MP3", 256), q("OGG", 112)) == "better"
    assert backfill.compare(q("AAC", 256), q("AAC", 256)) == "equal"
    assert backfill.compare(q("MP3", 245), q("AAC", 256)) == "equal"  # within 10%
    assert backfill.compare(q("MP3", 128), q("MP3", 320)) == "worse"
    assert backfill.compare(q("FLAC", depth=16), q("MP3", 320)) == "better"
    assert backfill.compare(q("MP3", 320), q("FLAC", depth=16)) == "worse"
    assert backfill.compare(q("FLAC", depth=24, rate=96000), q("FLAC", depth=16)) == "better"


def test_similarity():
    assert backfill.similarity(FP_A, FP_A) == 1.0
    assert backfill.similarity(FP_A, [0] * 5 + FP_A) == 1.0  # time offset
    assert backfill.similarity(FP_A, FP_B) < 0.7
    assert backfill.similarity(None, FP_A) == 0.0


# -- matching --------------------------------------------------------------------------------

def test_identical_audio_attaches_and_undo_restores_the_download(lib, tmp_path, fingerprints):
    album, item = library_album(lib, "tone.mp3", "01 Library.mp3")
    lib_bytes = sha(Path(os.fsdecode(item.path)))
    inbox = tmp_path / "inbox"
    dl = tagged(FIXTURES / "tone.mp3", inbox / "Artist" / "x.mp3", title="Store Title", comments="Amazon.com Song ID: 1")
    before = sha(dl)

    cache, index, tracks = run(lib, inbox, tmp_path)
    assert [(t.action, t.how, t.item_ids) for t in tracks] == [("attach", "identical", [item.id])]

    r = backfill.apply_folder(lib, inbox / "Artist", inbox, cache, index)
    assert (r["attached"], r["replaced"]) == (1, 0)
    assert not (inbox / "Artist").exists()  # used download left the inbox; folder pruned
    assert sha(Path(os.fsdecode(item.path))) == lib_bytes  # library file untouched
    assert originals.load(lib.get_item(item.id))["sha256"] == before

    restore.undo(lib, lib.get_album(album.id), str(inbox))
    assert sha(dl) == before


def test_better_download_replaces_library_file_keeping_tags_and_art(lib, tmp_path, fingerprints, monkeypatch):
    album, item = library_album(lib, "tone.ogg", "01 Same.ogg", art=b"\xff\xd8\xff\xe0library-art",
                                navidrome_library="kids", mb_trackid="abc-123")
    old_path = Path(os.fsdecode(item.path))
    old_bytes = sha(old_path)
    inbox = tmp_path / "inbox"
    dl = tagged(FIXTURES / "tone.mp3", inbox / "Artist" / "Album" / "Same.mp3", title="Store Title",
                rg_track_gain=-3.5)
    before = sha(dl)
    monkeypatch.setattr(backfill, "compare", lambda a, b: "better")

    cache, index, tracks = run(lib, inbox, tmp_path)
    assert [(t.action, t.how) for t in tracks] == [("replace", "same recording")]

    r = backfill.apply_folder(lib, inbox / "Artist", inbox, cache, index)
    assert r["replaced"] == 1 and not r["errors"]

    new = lib.get_item(item.id)
    new_path = Path(os.fsdecode(new.path))
    assert new_path == old_path.with_suffix(".mp3") and not old_path.exists()
    assert (new.format, new.title, new.mb_trackid, new.navidrome_library) == ("MP3", "Library Title", "abc-123", "kids")
    m = MediaFile(str(new_path))
    assert m.title == "Library Title"  # library tags on the new file
    assert m.images[0].data == b"\xff\xd8\xff\xe0library-art"  # library art carried over
    assert new.rg_track_gain == pytest.approx(-3.5)  # loudness of the new audio, file and DB agree
    held = list((originals.store_root().parent / "webimport-replaced").rglob("01 Same.ogg"))
    assert len(held) == 1 and sha(held[0]) == old_bytes
    assert hashlib.sha256(originals.rebuild(originals.load(new), new.path)).hexdigest() == before
    assert not dl.exists()

    restore.undo(lib, lib.get_album(album.id), str(inbox))
    assert sha(dl) == before  # the download, exactly as downloaded


def test_worse_download_and_unknown_files_stay(lib, tmp_path, fingerprints, monkeypatch):
    library_album(lib, "tone.flac", "01 Same.flac")
    inbox = tmp_path / "inbox"
    worse = tagged(FIXTURES / "tone.mp3", inbox / "Mixed" / "same.mp3")
    other = tagged(FIXTURES / "tone.ogg", inbox / "Mixed" / "other.ogg")
    monkeypatch.setattr(backfill, "compare", lambda a, b: "worse")

    cache, index, tracks = run(lib, inbox, tmp_path)
    assert {Path(t.path).name: t.action for t in tracks} == {"same.mp3": "keep_library", "other.ogg": "new"}

    r = backfill.apply_folder(lib, inbox / "Mixed", inbox, cache, index)
    assert (r["attached"], r["replaced"], r["left"]) == (0, 0, 2)
    assert worse.exists() and other.exists()


def test_library_track_is_claimed_by_one_download(lib, tmp_path, fingerprints):
    _, item = library_album(lib, "tone.mp3", "01 Library.mp3")
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "A" / "one.mp3", title="One")
    tagged(FIXTURES / "tone.mp3", inbox / "A" / "two.mp3", title="Two")

    _, _, tracks = run(lib, inbox, tmp_path)
    assert sorted(t.action for t in tracks) == ["attach", "duplicate"]


def test_track_with_saved_original_is_left_alone(lib, tmp_path, fingerprints):
    _, item = library_album(lib, "tone.mp3", "01 Library.mp3")
    item[originals.FIELD] = json.dumps({"sha256": "x" * 64})
    item.store()
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "A" / "one.mp3")

    _, _, tracks = run(lib, inbox, tmp_path)
    assert [t.action for t in tracks] == ["already_saved"]


def test_folder_files_go_with_the_album_only_when_all_its_audio_did(lib, tmp_path, fingerprints):
    album, _ = library_album(lib, "tone.mp3", "01 Library.mp3")
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "Whole" / "Album" / "01.mp3")
    (inbox / "Whole" / "Album" / "Digital Booklet.pdf").write_bytes(b"%PDF booklet")

    cache, index, _ = run(lib, inbox, tmp_path)
    backfill.apply_folder(lib, inbox / "Whole", inbox, cache, index)
    comp = lifecycle.load_companions(lib.get_album(album.id))
    assert [f["rel"] for f in comp["files"]] == ["Digital Booklet.pdf"]
    assert not (inbox / "Whole").exists()

    restore.undo(lib, lib.get_album(album.id), str(inbox))
    assert (inbox / "Whole" / "Album" / "Digital Booklet.pdf").read_bytes() == b"%PDF booklet"


def test_mixed_folder_keeps_its_other_files(lib, tmp_path, fingerprints):
    library_album(lib, "tone.mp3", "01 Library.mp3")
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "Mixed" / "01.mp3")
    tagged(FIXTURES / "tone.ogg", inbox / "Mixed" / "new.ogg")
    (inbox / "Mixed" / "cover.jpg").write_bytes(b"\xff\xd8")

    cache, index, _ = run(lib, inbox, tmp_path)
    backfill.apply_folder(lib, inbox / "Mixed", inbox, cache, index)
    assert (inbox / "Mixed" / "cover.jpg").exists() and (inbox / "Mixed" / "new.ogg").exists()


# -- job ---------------------------------------------------------------------------------------

def test_scan_and_apply_job(lib, tmp_path, fingerprints):
    _, item = library_album(lib, "tone.mp3", "01 Library.mp3")
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "A" / "one.mp3")
    tagged(FIXTURES / "tone.ogg", inbox / "B" / "new.ogg")
    job = backfill.Backfill(lib, inbox, tmp_path / "cache.sqlite", threading.Lock())

    def wait():
        deadline = time.monotonic() + 20
        while job.status()["running"] and time.monotonic() < deadline:
            time.sleep(0.02)
        return job.status()

    assert job.scan()
    st = wait()
    assert st["error"] is None
    assert {Path(k).name: v["counts"] for k, v in st["results"].items()} == {"A": {"attach": 1}, "B": {"new": 1}}
    assert st["results"][str(inbox / "A")]["actionable"]

    assert job.apply([str(inbox / "A"), "/etc"])  # outside the inbox: ignored
    st = wait()
    assert st["last_apply"]["attached"] == 1
    assert set(Path(k).name for k in st["results"]) == {"B"}
    assert originals.load(lib.get_item(item.id))


def test_stale_db_length_still_matches_but_real_length_must_agree(lib, tmp_path, fingerprints, monkeypatch):
    # The homelab DB had OGG lengths 3-5 s off the files'.
    _, item = library_album(lib, "tone.ogg", "01 Same.ogg")
    item.length = item.length + 5
    item.store()
    inbox = tmp_path / "inbox"
    tagged(FIXTURES / "tone.mp3", inbox / "A" / "same.mp3")
    monkeypatch.setattr(backfill, "compare", lambda a, b: "better")
    _, _, tracks = run(lib, inbox, tmp_path)
    assert [t.action for t in tracks] == ["replace"]

    # Fingerprints agree but the files' real lengths don't: an edit, not a match.
    real = backfill.quality_of_file
    def longer_library(p):
        q = real(p)
        if q and p.suffix == ".ogg":
            q.length += 10
        return q
    monkeypatch.setattr(backfill, "quality_of_file", longer_library)
    _, _, tracks = run(lib, inbox, tmp_path / "fresh")
    assert [t.action for t in tracks] == ["new"]

"""Album art choice for an inbox import: the folder is arranged so
fetchart's filesystem source picks the chosen art."""
from __future__ import annotations

import struct
from unittest.mock import MagicMock

import pytest

from beetsplug.webimport import sourceart


def jpeg(width, height, tag=b""):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof0 + tag + b"\xff\xd9"


A, B = jpeg(600, 600, b"a"), jpeg(500, 500, b"b")


def touch(folder, *names):
    for n in names:
        (folder / n).write_bytes(b"x")


def test_folder_images_follow_fetchart_order(tmp_path):
    touch(tmp_path, "back.jpg", "front.png", "cover.jpg", "booklet.jpeg", "notes.txt", ".hidden.jpg")
    (tmp_path / "scans").mkdir()
    touch(tmp_path / "scans", "cover.jpg")  # subfolders: ignored, as in fetchart
    names = [p.name for p in sourceart.folder_images(tmp_path)]
    assert names == ["cover.jpg", "front.png", "back.jpg", "booklet.jpeg"]


def test_cautious_uses_only_well_named_images(tmp_path):
    touch(tmp_path, "back.jpg", "my_cover.jpg")
    assert [p.name for p in sourceart.folder_images(tmp_path, cautious=True)] == ["my_cover.jpg"]


def test_embedded_art_picks_most_common_image(tmp_path, monkeypatch):
    monkeypatch.setattr(sourceart, "_audio_art", lambda f: [("1.mp3", A), ("2.mp3", A), ("3.mp3", B), ("4.mp3", None)])
    sourceart._embedded_cache.clear()
    art = sourceart.embedded_art(tmp_path)
    assert art["data"] == A and (art["width"], art["height"]) == (600, 600)
    assert (art["tracks_with_art"], art["tracks_with_this_art"], art["tracks_total"], art["distinct_images"]) == (3, 2, 4, 2)


def test_no_embedded_art(tmp_path, monkeypatch):
    monkeypatch.setattr(sourceart, "_audio_art", lambda f: [("1.mp3", None)])
    sourceart._embedded_cache.clear()
    assert sourceart.embedded_art(tmp_path) is None


def test_save_as_cover_sets_aside_every_image_fetchart_would_use(tmp_path):
    touch(tmp_path, "folder.jpg", "back.jpg")
    path = sourceart.save_as_cover(tmp_path, A, "image/jpeg")
    assert path.name == "cover.jpg" and path.read_bytes() == A
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "back.jpg.before-webimport", "cover.jpg", "folder.jpg.before-webimport"]
    assert sourceart.folder_images(tmp_path) == [path]


# -- endpoints ----------------------------------------------------------------

@pytest.fixture
def app_folder(lib, tmp_path, monkeypatch):
    from beetsplug.webimport.server import create_app

    inbox = tmp_path / "inbox"
    folder = inbox / "Album"
    folder.mkdir(parents=True)
    monkeypatch.setattr(sourceart, "_audio_art", lambda f: [("1.mp3", A)])
    sourceart._embedded_cache.clear()
    from beetsplug.webimport import itunes
    monkeypatch.setattr(itunes, "detect_ids", lambda f: None)
    cfg = {k: MagicMock(get=lambda typ, v=v: v) for k, v in {
        "grace_period_seconds": 600, "candidate_search_workers": 1, "tag_fields": ["mood"],
        "inbox_dir": str(inbox), "tag_store_path": str(tmp_path / "t.json"),
        "apple_music_match": False}.items()}
    app = create_app(lib, cfg, MagicMock())
    return app, app.test_client(), folder


def test_source_art_lists_embedded_and_folder(app_folder):
    app, client, folder = app_folder
    (folder / "cover.jpg").write_bytes(B)
    body = client.get("/api/inbox/source_art", query_string={"path": str(folder)}).get_json()
    assert (body["embedded"]["width"], body["embedded"]["tracks_total"]) == (600, 1)
    assert "data" not in body["embedded"]
    assert body["folder"]["name"] == "cover.jpg" and body["folder"]["width"] == 500
    assert body["itunes"] is None
    assert client.get(body["embedded"]["image_url"]).data == A
    assert client.get(body["folder"]["image_url"]).data == B


def test_source_art_rejects_paths_outside_inbox(app_folder, tmp_path):
    app, client, folder = app_folder
    assert client.get("/api/inbox/source_art", query_string={"path": str(tmp_path)}).status_code == 400


@pytest.mark.parametrize("choice, expected", [
    ("embedded", ["cover.jpg", "folder.jpg.before-webimport"]),
    ("candidate", ["folder.jpg.before-webimport"]),
    ("folder", ["folder.jpg"]),
])
def test_decide_arranges_folder_for_choice(app_folder, monkeypatch, choice, expected):
    from beetsplug.webimport import queue

    app, client, folder = app_folder
    (folder / "folder.jpg").write_bytes(B)
    submitted = []
    monkeypatch.setattr(queue.ReviewManager, "get", lambda self, tid: queue.PendingReview(tid, "match", str(folder), {}))
    monkeypatch.setattr(queue.ReviewManager, "submit_decision", lambda self, tid, d: submitted.append(d) or True)
    resp = client.post("/api/review/t1/decide", json={"action": "select", "index": 0, "art_choice": choice})
    assert resp.get_json() == {"ok": True}
    assert sorted(p.name for p in folder.iterdir()) == expected
    assert submitted


def test_skip_ignores_art_choice(app_folder, monkeypatch):
    from beetsplug.webimport import queue

    app, client, folder = app_folder
    (folder / "folder.jpg").write_bytes(B)
    monkeypatch.setattr(queue.ReviewManager, "submit_decision", lambda self, tid, d: True)
    client.post("/api/review/t1/decide", json={"action": "skip", "art_choice": "candidate"})
    assert [p.name for p in folder.iterdir()] == ["folder.jpg"]

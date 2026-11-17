"""Album art choice: options, Cover Art Archive downloads (once per release,
shared by concurrent requests), the default, and applying the choice as the
album's art during import without touching the inbox folder."""
from __future__ import annotations

import os
import struct
import threading
import time
from unittest.mock import MagicMock

import pytest

from beetsplug.webimport import artchoice, coverart, itunes


def jpeg(width, height, tag=b""):
    sof0 = b"\xff\xc0" + struct.pack(">HBHHB", 11, 8, height, width, 1) + b"\x01\x11\x00"
    return b"\xff\xd8" + sof0 + tag + b"\xff\xd9"


SMALL, BIG = jpeg(600, 600, b"s"), jpeg(1500, 1500, b"b")
REL, RG = "rel-1", "rg-1"


class Resp:
    def __init__(self, status=200, payload=None, content=b""):
        self.status_code, self._payload, self.content = status, payload, content
        self.ok = 200 <= status < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise artchoice.requests.HTTPError(str(self.status_code))


@pytest.fixture(autouse=True)
def clean():
    artchoice.clear()
    coverart.clear_caa_cache()
    artchoice._embedded_cache.clear()
    yield
    artchoice.clear()
    coverart.clear_caa_cache()


@pytest.fixture
def caa(monkeypatch):
    """Fake Cover Art Archive: `art` maps (kind, mbid) -> image bytes;
    missing keys are 404 (no art). Records every request."""
    art = {}
    calls = []
    fail = {"times": 0}

    def get(url, **kw):
        calls.append(url)
        time.sleep(0.02)  # widen the window for concurrent callers
        if fail["times"]:
            fail["times"] -= 1
            raise artchoice.requests.ConnectionError("blip")
        if url.startswith("https://coverartarchive.org/"):
            kind = "release" if "/release/" in url else "releasegroup"
            mbid = url.rsplit("/", 1)[1]
            if (kind, mbid) not in art:
                return Resp(404)
            return Resp(payload={"images": [{"front": True, "types": ["Front"], "image": f"http://img/{kind}/{mbid}.jpg"}]})
        if url.startswith("http://img/"):
            kind, name = url[len("http://img/"):].split("/")
            return Resp(content=art[(kind, name[:-4])])
        return Resp(404)

    monkeypatch.setattr(coverart.requests, "get", get)
    monkeypatch.setattr(artchoice.requests, "get", get)
    monkeypatch.setattr(artchoice.time, "sleep", lambda s: None)
    return art, calls, fail


def test_candidate_art_downloads_once_for_concurrent_requests(caa):
    art, calls, _ = caa
    art[("release", REL)] = BIG
    results = []
    threads = [threading.Thread(target=lambda: results.append(artchoice.candidate_art(REL, RG))) for _ in range(3)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert [r["state"] for r in results] == ["ok"] * 3
    assert all(r["data"] == BIG and r["source"] == "release" for r in results)
    assert len(calls) == 2  # one JSON lookup + one image download
    artchoice.candidate_art(REL, RG)
    assert len(calls) == 2  # cached


def test_falls_back_to_release_group(caa):
    art, _, _ = caa
    art[("releasegroup", RG)] = SMALL
    r = artchoice.candidate_art(REL, RG)
    assert r["state"] == "ok" and r["source"] == "releasegroup" and r["data"] == SMALL


def test_no_art_anywhere(caa):
    assert artchoice.candidate_art(REL, RG) == {"state": "none"}


def test_transient_failure_is_retried_and_not_cached(caa, monkeypatch):
    art, calls, fail = caa
    art[("release", REL)] = BIG
    monkeypatch.setattr(coverart, "CAA_RETRIES", 0)
    fail["times"] = 1
    assert artchoice.candidate_art(REL, None)["state"] == "unavailable"
    assert artchoice.candidate_art(REL, None)["state"] == "ok"


def test_image_download_retries_transient_errors(caa):
    art, calls, fail = caa
    art[("release", REL)] = BIG
    coverart._caa_front_images(REL, "release")  # JSON cached first
    fail["times"] = 2  # the next two image requests fail
    assert artchoice.candidate_art(REL, None)["data"] == BIG


def test_store_is_content_addressed_and_size_capped(monkeypatch):
    monkeypatch.setattr(artchoice, "STORE_MAX_BYTES", len(SMALL) + len(BIG))
    a = artchoice.describe(SMALL)
    assert a["image_url"] == f"/api/art/{a['key']}" and (a["width"], a["height"]) == (600, 600)
    artchoice.put(BIG)
    artchoice.put(jpeg(10, 10, b"x"))  # evicts the oldest
    assert artchoice.get(a["key"]) is None


def test_folder_image_prefers_cover_names(tmp_path):
    for n in ("back.jpg", "front.png", "cover.jpg", "notes.txt", ".hidden.jpg"):
        (tmp_path / n).write_bytes(b"x")
    assert artchoice.folder_image(tmp_path).name == "cover.jpg"
    (tmp_path / "cover.jpg").unlink()
    assert artchoice.folder_image(tmp_path).name == "front.png"


def test_embedded_art_picks_most_common_image(tmp_path, monkeypatch):
    monkeypatch.setattr(artchoice, "_audio_art", lambda f: [("1", SMALL), ("2", SMALL), ("3", BIG), ("4", None)])
    art = artchoice.embedded_art(tmp_path)
    assert art["data"] == SMALL
    assert (art["tracks_with_this_art"], art["tracks_total"], art["distinct_images"]) == (2, 4, 2)


@pytest.mark.parametrize("options, candidate, expected", [
    ({"folder": {"width": 1}, "itunes": {"image_url": "x"}}, None, "folder"),
    ({"itunes": {"image_url": "x"}, "keep": {"width": 9999, "height": 9999}}, None, "itunes"),
    ({"itunes": {"error": "gone"}, "keep": {"width": 600, "height": 600}}, None, "keep"),
    ({"keep": {"width": 600, "height": 600}}, {"state": "ok", "width": 1500, "height": 1500}, "candidate"),
    ({"keep": {"width": 1500, "height": 1500}}, {"state": "ok", "width": 600, "height": 600}, "keep"),
    ({}, {"state": "ok", "width": 600, "height": 600}, "candidate"),
    ({"keep": {"width": 600, "height": 600}}, {"state": "none"}, "keep"),
    ({}, None, "keep"),
])
def test_default_choice(options, candidate, expected):
    assert artchoice.default_choice(options, candidate) == expected


# -- endpoints ----------------------------------------------------------------

@pytest.fixture
def app_folder(lib, tmp_path, monkeypatch):
    from beetsplug.webimport.server import create_app

    inbox = tmp_path / "inbox"
    folder = inbox / "Album"
    folder.mkdir(parents=True)
    monkeypatch.setattr(artchoice, "_audio_art", lambda f: [("1.mp3", SMALL)])
    monkeypatch.setattr(itunes, "detect_ids", lambda f: None)
    cfg = {k: MagicMock(get=lambda typ, v=v: v) for k, v in {
        "grace_period_seconds": 600, "candidate_search_workers": 1, "tag_fields": ["mood"],
        "inbox_dir": str(inbox), "tag_store_path": str(tmp_path / "t.json"),
        "apple_music_match": False}.items()}
    app = create_app(lib, cfg, MagicMock())
    return app, app.test_client(), folder


def test_art_options_and_cached_image(app_folder):
    app, client, folder = app_folder
    (folder / "cover.jpg").write_bytes(BIG)
    body = client.get("/api/inbox/art_options", query_string={"path": str(folder)}).get_json()
    assert (body["keep"]["width"], body["keep"]["tracks_total"]) == (600, 1)
    assert body["folder"]["name"] == "cover.jpg" and body["folder"]["width"] == 1500
    assert body["itunes"] is None
    img = client.get(body["keep"]["image_url"])
    assert img.data == SMALL and "immutable" in img.headers["Cache-Control"]


def test_art_options_rejects_paths_outside_inbox(app_folder, tmp_path):
    app, client, folder = app_folder
    assert client.get("/api/inbox/art_options", query_string={"path": str(tmp_path)}).status_code == 400


def test_candidate_endpoint(app_folder, caa):
    art, _, _ = caa
    art[("release", REL)] = BIG
    app, client, folder = app_folder
    body = client.get("/api/coverart/candidate", query_string={"release": REL, "releasegroup": RG}).get_json()
    assert body["state"] == "ok" and body["source"] == "release" and body["width"] == 1500
    assert client.get(body["image_url"]).data == BIG
    none = client.get("/api/coverart/candidate", query_string={"release": "other"}).get_json()
    assert none == {"state": "none"}


@pytest.fixture
def decide(app_folder, monkeypatch):
    from beetsplug.webimport import queue

    app, client, folder = app_folder
    submitted = []
    payload = {"candidates": [{"album_id": REL, "releasegroup_id": RG}]}
    monkeypatch.setattr(queue.ReviewManager, "get",
                        lambda self, tid: queue.PendingReview(tid, "match", str(folder), payload))
    monkeypatch.setattr(queue.ReviewManager, "submit_decision", lambda self, tid, d: submitted.append(d) or True)

    def post(body):
        resp = client.post("/api/review/t1/decide", json=body)
        return resp, (submitted[-1] if submitted else None)

    return post, folder


@pytest.mark.parametrize("choice, expected", [("keep", None), ("candidate", BIG), ("folder", b"folder-img")])
def test_decide_resolves_choice_to_bytes(decide, caa, choice, expected):
    art, _, _ = caa
    art[("release", REL)] = BIG
    post, folder = decide
    (folder / "cover.png").write_bytes(b"folder-img")
    resp, sent = post({"action": "select", "index": 0, "art_choice": choice})
    assert resp.get_json() == {"ok": True}
    assert sent["_art"] == expected
    assert sorted(p.name for p in folder.iterdir()) == ["cover.png"]  # inbox untouched


def test_decide_without_choice_applies_default(decide, caa):
    art, _, _ = caa
    art[("release", REL)] = BIG  # 1500px beats the files' 600px art
    post, _ = decide
    _, sent = post({"action": "select", "index": 0})
    assert sent["_art"] == BIG


def test_unavailable_choice_is_reported_not_applied(decide, caa):
    post, _ = decide
    resp, sent = post({"action": "select", "index": 0, "art_choice": "candidate"})  # CAA has no art
    assert resp.status_code == 502 and "no art" in resp.get_json()["error"]
    assert sent is None


def test_client_cannot_inject_art_bytes(decide):
    post, _ = decide
    _, sent = post({"action": "skip", "_art": "x"})
    assert "_art" not in sent


# -- applying during a real import ------------------------------------------------

def test_import_sets_chosen_art_and_leaves_inbox_alone(lib, tmp_path, create_wav_file, monkeypatch):
    from beets import config, metadata_plugins, plugins

    from beetsplug.webimport.queue import ReviewManager
    from beetsplug.webimport.session import WebImportSession

    config["import"].get()
    saved = list(config.sources)
    config.set({"threaded": False, "import": {"incremental": False, "resume": False, "write": False,
                                              "copy": True, "search_ids": []}})
    monkeypatch.setattr(metadata_plugins, "candidates", lambda *a, **k: iter(()))
    art_set = []
    orig_send = plugins.send

    def send(event, **kw):
        if event == "import_task_files":
            artchoice.on_import_task_files(**kw)
        if event == "art_set":
            art_set.append(kw["album"])
        return orig_send(event, **kw)

    monkeypatch.setattr(plugins, "send", send)
    folder = tmp_path / "inbox" / "Album"
    create_wav_file(folder / "01.wav")
    try:
        rm = ReviewManager()
        session = WebImportSession(lib, None, [str(folder).encode()], None, rm, None)
        t = threading.Thread(target=session.run, daemon=True)
        t.start()
        deadline = time.monotonic() + 10
        while t.is_alive() and time.monotonic() < deadline:
            for pr in rm.list_pending():
                rm.submit_decision(pr["task_id"], {"action": "asis", "_art": BIG})
            time.sleep(0.02)
        t.join(timeout=2)
    finally:
        config.sources[:] = saved

    album = next(iter(lib.albums()))
    assert art_set and art_set[0].id == album.id
    assert not os.fsdecode(album.artpath).startswith(str(folder))  # in the library
    with open(album.artpath, "rb") as f:
        assert f.read() == BIG
    assert sorted(os.listdir(folder)) == ["01.wav"]  # inbox untouched

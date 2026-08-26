from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from beets.library import Item, Library

from beetsplug.webimport.grace import GracePeriodManager
from beetsplug.webimport.server import create_app


def test_undo_cleans_marker_file(lib: Library, tmp_path: Path, create_wav_file):
    inbox_folder = tmp_path / "inbox" / "Test Album"
    inbox_folder.mkdir(parents=True, exist_ok=True)
    marker_file = inbox_folder / ".webimport_imported"
    marker_file.write_text(json.dumps({"album_id": 1, "imported_at": "2026-08-23T00:00:00Z", "staging_bin": False}))

    music_file = create_wav_file(tmp_path / "music" / "Artist" / "Album" / "track1.wav")
    item = Item.from_path(str(music_file))
    lib.add(item)
    album = lib.add_album([item])
    assert album.id is not None

    mgr = GracePeriodManager(lib, grace_period_seconds=600)
    rec_id = mgr.register("album", album.id, "Artist - Album", inbox_path=str(inbox_folder))

    assert marker_file.exists()
    ok = mgr.undo(rec_id)
    assert ok is True
    assert not marker_file.exists()
    assert lib.get_album(album.id) is None


def test_api_inbox_reports_imported_markers(lib: Library, tmp_path: Path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    folder_a = inbox_dir / "Album A"
    folder_a.mkdir()

    folder_b = inbox_dir / "Album B"
    folder_b.mkdir()
    marker_b = folder_b / ".webimport_imported"
    marker_b.write_text(json.dumps({"album_id": 42, "imported_at": "2026-08-23T01:00:00Z", "staging_bin": False}))

    plugin_mock = MagicMock()
    plugin_mock.register_listener = MagicMock()

    cfg = {
        "grace_period_seconds": MagicMock(get=lambda typ: 600),
        "candidate_search_workers": MagicMock(get=lambda typ: 2),
        "tag_fields": MagicMock(get=lambda typ: ["mood"]),
        "inbox_dir": MagicMock(get=lambda typ: str(inbox_dir)),
        "tag_store_path": MagicMock(get=lambda typ: str(tmp_path / "tags.json")),
    }

    app = create_app(lib, cfg, plugin_mock)
    client = app.test_client()

    resp = client.get("/api/inbox")
    assert resp.status_code == 200
    data = resp.get_json()

    dirs = {d["path"]: d for d in data["inbox_dirs"]}
    assert str(folder_a) in dirs
    assert dirs[str(folder_a)]["imported"] is False
    assert dirs[str(folder_a)]["album_id"] is None

    assert str(folder_b) in dirs
    assert dirs[str(folder_b)]["imported"] is True
    assert dirs[str(folder_b)]["album_id"] == 42


def test_api_inbox_delete_endpoint(lib: Library, tmp_path: Path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    folder = inbox_dir / "ToDelete"
    folder.mkdir()
    (folder / "track.wav").write_text("audio")

    plugin_mock = MagicMock()
    plugin_mock.register_listener = MagicMock()

    cfg = {
        "grace_period_seconds": MagicMock(get=lambda typ: 600),
        "candidate_search_workers": MagicMock(get=lambda typ: 2),
        "tag_fields": MagicMock(get=lambda typ: ["mood"]),
        "inbox_dir": MagicMock(get=lambda typ: str(inbox_dir)),
        "tag_store_path": MagicMock(get=lambda typ: str(tmp_path / "tags_delete.json")),
    }

    app = create_app(lib, cfg, plugin_mock)
    client = app.test_client()

    # Deleting outside inbox should fail
    resp = client.post("/api/inbox/delete", json={"path": "/etc/passwd"})
    assert resp.status_code == 400

    # Deleting valid folder inside inbox succeeds
    resp = client.post("/api/inbox/delete", json={"path": str(folder)})
    assert resp.status_code == 200
    assert resp.get_json()["ok"] is True
    assert not folder.exists()


def test_api_inbox_reports_in_progress_and_pending_review(lib: Library, tmp_path: Path):
    inbox_dir = tmp_path / "inbox"
    inbox_dir.mkdir(parents=True, exist_ok=True)

    folder_c = inbox_dir / "Album C"
    folder_c.mkdir()

    plugin_mock = MagicMock()
    plugin_mock.register_listener = MagicMock()

    cfg = {
        "grace_period_seconds": MagicMock(get=lambda typ: 600),
        "candidate_search_workers": MagicMock(get=lambda typ: 2),
        "tag_fields": MagicMock(get=lambda typ: ["mood"]),
        "inbox_dir": MagicMock(get=lambda typ: str(inbox_dir)),
        "tag_store_path": MagicMock(get=lambda typ: str(tmp_path / "tags_state.json")),
    }

    app = create_app(lib, cfg, plugin_mock)
    client = app.test_client()

    resp = client.get("/api/inbox")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["inbox_dirs"][0]["in_progress"] is False
    assert data["inbox_dirs"][0]["pending_review"] is False

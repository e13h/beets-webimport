"""End-to-end driver: acts as the browser against the webimport Flask app.

Runs the real import pipeline (which hits MusicBrainz) in the worker pool,
then drives the review decision via the HTTP API using Flask's test client.
"""
import os
import time

os.environ["BEETSDIR"] = os.path.abspath("./.config")

from beets import config, plugins  # noqa: E402
from beets.ui import _open_library  # noqa: E402

TARGET_RELEASE = "a5483fb3-634b-4254-a966-de33cefd1f17"


def wait_for_pending(client, timeout=120, exclude_task_id=None):
    """Wait for a pending review. If exclude_task_id is given, wait for a
    review whose task_id differs from it -- avoids racing the worker
    thread between popping an old task and registering the next one."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = client.get("/api/inbox").get_json()["pending_review"]
        pending = [p for p in pending if p["task_id"] != exclude_task_id]
        if pending:
            return pending
        time.sleep(1)
    raise TimeoutError("no pending review appeared")


def main():
    config.read()
    plugins.load_plugins()
    lib = _open_library(config)

    from beetsplug.webimport.server import create_app

    plugin = next(p for p in plugins.find_plugins() if p.name == "webimport")
    app = create_app(lib, config["webimport"], plugin)
    client = app.test_client()

    inbox = client.get("/api/inbox").get_json()
    path = inbox["inbox_dirs"][0]
    print("Starting import of:", path)
    client.post("/api/inbox/start", json={"paths": [path]})

    pending = wait_for_pending(client)
    pr = pending[0]
    print(f"\nPending review kind={pr['kind']} path={pr['path']}")
    cands = pr["payload"]["candidates"]
    print(f"Got {len(cands)} candidate(s), rec={pr['payload'].get('rec')}")
    for c in cands[:5]:
        print(f"  [{c['index']}] dist={c['distance']} {c['artist']} - "
              f"{c.get('album')} ({c.get('year')}) src={c.get('data_source')} "
              f"id={c.get('album_id')}")

    # Force the exact target MusicBrainz release, then review the result.
    print(f"\nForcing search_id={TARGET_RELEASE}")
    old_task_id = pr["task_id"]
    client.post(f"/api/review/{old_task_id}/decide",
                json={"action": "search_id", "search_id": TARGET_RELEASE})

    pending = wait_for_pending(client, exclude_task_id=old_task_id)
    pr = pending[0]
    cands = pr["payload"]["candidates"]
    print(f"After search_id: task={pr['task_id']} {len(cands)} candidate(s)")
    for c in cands[:5]:
        print(f"  [{c['index']}] dist={c['distance']} {c['artist']} - "
              f"{c.get('album')} id={c.get('album_id')}")

    print("\nSelecting candidate 0 (apply)")
    r = client.post(f"/api/review/{pr['task_id']}/decide",
                    json={"action": "select", "index": 0})
    print("decide ->", r.get_json())

    # Wait for the import to *fully* finalize: the album_imported event
    # (which registers the grace-period undo record) fires only after
    # manipulate_files runs fetchart/embedart. Polling the album list
    # alone races, because the album is added to the DB earlier.
    deadline = time.time() + 60
    undo = []
    while time.time() < deadline:
        undo = client.get("/api/undo").get_json()
        if undo:
            break
        time.sleep(1)
    albums = client.get("/api/library/albums").get_json()

    print("\n=== Library albums after import ===")
    for a in albums:
        print(a)

    print("\n=== Undo list (grace period) ===")
    print(client.get("/api/undo").get_json())

    if albums:
        detail = client.get(f"/api/library/albums/{albums[0]['id']}").get_json()
        print("\n=== Album detail tracks ===")
        for t in detail["tracks"]:
            print(f"  {t['track']}. {t['title']}")
        print("navidrome_library =",
              detail["fields"].get("navidrome_library"))


if __name__ == "__main__":
    main()

"""Concurrency + duplicate-resolution driver.

Submits TWO albums at once to validate:
  1. Parallel candidate review  (both appear in pending_review together)
  2. Serial apply via apply_lock (no deadlock / stuck lock)
  3. Duplicate resolution        (2nd album duplicates the 1st)
"""
import os
import shutil
import time

os.environ["BEETSDIR"] = os.path.abspath("./.config")

from beets import config, plugins  # noqa: E402
from beets.ui import _open_library  # noqa: E402

TARGET_RELEASE = "a5483fb3-634b-4254-a966-de33cefd1f17"
INBOX = os.path.abspath("./.inbox")
ALBUM1 = os.path.join(INBOX, "Mulan (Original Motion Picture Soundtrack)")
ALBUM2 = os.path.join(INBOX, "Mulan COPY")


def find_task(client, path_substr, exclude=()):
    for _ in range(120):
        pending = client.get("/api/inbox").get_json()["pending_review"]
        for pr in pending:
            if path_substr in pr["path"] and pr["task_id"] not in exclude:
                return pr
        time.sleep(1)
    raise TimeoutError(f"no review for {path_substr}")


def resolve_to_target(client, pr):
    """Drive a match review to select the target release, following the
    search_id re-review (returns the final applied task_id)."""
    old = pr["task_id"]
    client.post(f"/api/review/{old}/decide",
                json={"action": "search_id", "search_id": TARGET_RELEASE})
    # wait for the re-review (new task id, same path)
    for _ in range(120):
        pending = client.get("/api/inbox").get_json()["pending_review"]
        match = [p for p in pending
                 if p["path"] == pr["path"] and p["task_id"] != old
                 and p["kind"] == "match"]
        if match:
            new = match[0]
            client.post(f"/api/review/{new['task_id']}/decide",
                        json={"action": "select", "index": 0})
            return new["task_id"]
        time.sleep(1)
    raise TimeoutError("search_id re-review never appeared")


def main():
    # Second album = copy of the first (guaranteed duplicate).
    if os.path.isdir(ALBUM2):
        shutil.rmtree(ALBUM2)
    shutil.copytree(ALBUM1, ALBUM2)

    config.read()
    plugins.load_plugins()
    lib = _open_library(config)

    from beetsplug.webimport.server import create_app
    plugin = next(p for p in plugins.find_plugins() if p.name == "webimport")
    app = create_app(lib, config["webimport"], plugin)
    client = app.test_client()

    print("Submitting BOTH albums concurrently...")
    client.post("/api/inbox/start", json={"paths": [ALBUM1, ALBUM2]})

    # 1. Parallel review: both should be pending at the same time.
    deadline = time.time() + 120
    both = []
    while time.time() < deadline:
        pending = client.get("/api/inbox").get_json()["pending_review"]
        if len(pending) >= 2:
            both = pending
            break
        time.sleep(1)
    print(f"Simultaneously pending reviews: {len(both)} "
          f"(parallel review {'OK' if len(both) >= 2 else 'NOT observed'})")
    for pr in both:
        print(f"   - {pr['kind']}: {os.path.basename(pr['path'])} "
              f"cands={len(pr['payload'].get('candidates', []))}")

    # 2. Apply the first album fully.
    pr1 = find_task(client, "Motion Picture Soundtrack")
    print("\nResolving album 1 -> target release, applying...")
    resolve_to_target(client, pr1)

    # wait for album 1 to finalize
    for _ in range(60):
        if client.get("/api/undo").get_json():
            break
        time.sleep(1)
    print("Album 1 applied. Library:",
          [a["album"] for a in client.get("/api/library/albums").get_json()])

    # 3. Album 2 -> select target -> should now trigger duplicate review.
    print("\nResolving album 2 -> target release (expect duplicate prompt)...")
    pr2 = find_task(client, "Mulan COPY")
    resolve_to_target(client, pr2)

    dup = None
    for _ in range(60):
        pending = client.get("/api/inbox").get_json()["pending_review"]
        d = [p for p in pending if p["kind"] == "duplicate"]
        if d:
            dup = d[0]
            break
        time.sleep(1)

    if dup:
        print("Duplicate prompt received:",
              dup["payload"]["duplicates"])
        print("Deciding: skip new (keep existing)")
        client.post(f"/api/review/{dup['task_id']}/decide",
                    json={"action": "skip"})
        time.sleep(3)
    else:
        print("No duplicate prompt observed (unexpected).")

    albums = client.get("/api/library/albums").get_json()
    print("\nFinal library albums:", len(albums))
    for a in albums:
        print("  ", a["album"], "tracks=", a["track_count"])

    # No stuck lock: a subsequent trivial API call still responds.
    print("\nLock health check -> /api/inbox responds:",
          client.get("/api/inbox").status_code == 200)

    shutil.rmtree(ALBUM2, ignore_errors=True)


if __name__ == "__main__":
    main()

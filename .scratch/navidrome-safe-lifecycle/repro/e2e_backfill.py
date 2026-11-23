#!/usr/bin/env python3
"""End-to-end check that Backfill (ADR-0016) keeps Navidrome history.

  .venv/bin/python .scratch/navidrome-safe-lifecycle/repro/e2e_backfill.py [--keep]

Seeds the dev library from .backfill-fixture (scripts/dev-seed-backfill.sh:
homelab files, no stored originals), starts Navidrome 0.64.2 on .library
laid out like the homelab (root + one library per Listening Group, watcher
on, 5s), gives every Navidrome track a playlist entry, a star and two
plays, then runs Backfill through the webimport API (check, attach all):
identical tracks only get originals, swapped tracks get a new file (Train:
.ogg -> .mp3, a path change; Cinderella: same path, new audio). Reports
whether every original Navidrome row kept its history. Needs Docker.
"""
import shutil
import signal
import subprocess
import sys
import time

import e2e_webimport as e

KEEP = "--keep" in sys.argv
e.WORK = e.HERE / "work-backfill"
GROUPS = ("kids", "main")


def start_navidrome():
    e.run(["docker", "rm", "-f", e.ND])
    (e.WORK / "nd-data").mkdir(parents=True)
    e.run(["docker", "run", "-d", "--name", e.ND, "-p", f"{e.ND_PORT}:4533",
           "-e", "ND_SCANNER_WATCHERWAIT=5s", "-e", "ND_ENABLEINSIGHTSCOLLECTOR=false",
           "-v", f"{e.WORK / 'nd-data'}:/data", "-v", f"{e.LIBRARY}:/music:ro",
           "deluan/navidrome:0.64.2"])
    e.wait(lambda: e._ok(e.NDB + "/ping"), "Navidrome")
    e.http("POST", e.NDB + "/auth/createAdmin", {"username": "admin", "password": "admin"})
    tok = e.http("POST", e.NDB + "/auth/login", {"username": "admin", "password": "admin"})["token"]
    h = {"x-nd-authorization": f"Bearer {tok}"}
    for g in GROUPS:
        e.http("POST", e.NDB + "/api/library", {"name": g, "path": f"/music/{g}"}, h)
    e.http("POST", e.NDB + "/api/user", {"userName": "webimport", "name": "webimport",
                                         "password": "password", "isAdmin": False}, h)


def rows(con):
    return con.execute(
        "select m.id, m.library_id, m.path, m.missing, m.title, m.suffix, coalesce(a.play_count,0) plays, "
        "coalesce(a.starred,0) starred from media_file m left join annotation a "
        "on a.item_id=m.id and a.item_type='media_file' order by m.library_id, m.path").fetchall()


def report(before, con):
    now = {r["id"]: r for r in rows(con)}
    lost = 0
    for b in before:
        r = now.get(b["id"])
        kept = (r is not None and not r["missing"] and (r["plays"], r["starred"]) == (b["plays"], b["starred"]))
        lost += not kept
        moved = r is not None and r["path"] != b["path"]
        e.log(f"  lib {b['library_id']} {b['path'][-52:]:52} -> {'kept' if kept else 'LOST'}"
              + (f"  now {r['path'][-30:]}" if moved else "")
              + ("" if r is None else f" (plays {r['plays']}, starred {bool(r['starred'])})"))
    extra = [r for r in now.values() if r["id"] not in {b["id"] for b in before} and not r["missing"]]
    for r in extra:
        e.log(f"  NEW ROW (no history): lib {r['library_id']} {r['path']}")
    pl = e.sub("getPlaylists")["playlists"]["playlist"][0]
    entries = e.sub("getPlaylist", id=pl["id"])["playlist"].get("entry", [])
    e.log(f"  playlist: {len(entries)}/{len(before)} entries playable")
    return lost, len(extra), len(entries)


def main():
    shutil.rmtree(e.WORK, ignore_errors=True)
    e.WORK.mkdir(parents=True)
    e.log("seeding the dev library from .backfill-fixture")
    e.run([str(e.REPO / "scripts/dev-seed-backfill.sh")])
    for g in GROUPS:
        (e.LIBRARY / g / ".keep").touch()
    start_navidrome()
    e.sub("startScan")
    e.wait(lambda: not e.sub("getScanStatus")["scanStatus"]["scanning"]
           and [r for r in rows(e.nd_db()) if not r["missing"]], "the first scan", timeout=180)
    time.sleep(3)
    before = [dict(r) for r in rows(e.nd_db()) if not r["missing"]]
    ids = [r["id"] for r in before]
    e.sub("createPlaylist", name="e2e", songId=ids)
    for i in ids:
        e.sub("star", id=i)
        e.sub("scrobble", id=i, submission="true")
        e.sub("scrobble", id=i, submission="true")
    time.sleep(1)
    before = [dict(r) for r in rows(e.nd_db()) if not r["missing"]]
    assert all(r["plays"] == 2 and r["starred"] for r in before), "history not recorded"
    e.log(f"{len(before)} Navidrome rows given history")

    proc = e.start_webimport()
    try:
        e.wi("POST", "/api/backfill/scan")
        st = e.wait(lambda: (s := e.wi("GET", "/api/backfill")) and not s["running"] and s, "the check", 300)
        paths = [p for p, r in st["results"].items() if r["actionable"]]
        e.log("check: " + "; ".join(f"{p.split('/')[-1]} {r['counts']}" for p, r in st["results"].items()))
        stamp = e.last_scan()
        e.wi("POST", "/api/backfill/apply", {"paths": paths})
        st = e.wait(lambda: (s := e.wi("GET", "/api/backfill")) and not s["running"] and s, "the attach", 300)
        e.log(f"attach: {st['last_apply']}")
        e.wait_for_scan_after(stamp)
        e.settle()
        e.settle()
        lost, extra, playable = report(before, e.nd_db())
        e.log(f"RESULT: lost {lost}/{len(before)}, new rows without history {extra}, "
              f"playlist {playable}/{len(before)}")
    finally:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=10)
        (e.WORK / "navidrome.log").write_text(
            subprocess.run(["docker", "logs", e.ND], capture_output=True, text=True).stderr)
        if not KEEP:
            e.run(["docker", "rm", "-f", e.ND])


if __name__ == "__main__":
    main()

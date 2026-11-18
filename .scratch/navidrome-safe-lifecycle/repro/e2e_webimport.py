#!/usr/bin/env python3
"""End-to-end check of Pending Move with the real plugin and a real Navidrome.

  .venv/bin/python .scratch/navidrome-safe-lifecycle/repro/e2e_webimport.py on|off [--keep]

Resets the dev library (scripts/dev-reset.sh), starts Navidrome 0.64.2 on
.library (watcher on, 5s like the homelab; libraries: root + unassigned +
kids) and `beet webimport` on :8338 (with the Navidrome integration "on"
or "off"), imports the Mulan purchase as the 2020 digital release, gives
every Navidrome row history, then:
  1. Library-tab reimport to the 1998 CD release (new MBIDs; tags + path change)
  2. Listening Group change unassigned -> kids (beets-only field)
and reports whether each original Navidrome row kept its history.
Needs network (MusicBrainz) and Docker.
"""
import json
import os
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

MODE = sys.argv[1] if len(sys.argv) > 1 else "on"
KEEP = "--keep" in sys.argv
HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORK = HERE / "work-e2e"
LIBRARY = REPO / ".library"
INBOX = REPO / ".inbox"
MULAN = INBOX / "Mulan (Original Motion Picture Soundtrack)"
DIGITAL = "4e929666-952f-473c-baf2-97c9ca6bfbbe"  # import as this
CD_1998 = "a5483fb3-634b-4254-a966-de33cefd1f17"  # reimport to this
ND, ND_PORT = "nd-e2e", 14534
NDB = f"http://localhost:{ND_PORT}"
WI = "http://localhost:8338"


def log(*a):
    print(f"[{time.strftime('%H:%M:%S')}]", *a, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode:
        raise RuntimeError(f"{cmd}: {r.stdout}{r.stderr}")
    return r.stdout


def http(method, url, payload=None, headers=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(payload).encode() if payload is not None else None,
                                 headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def wi(method, path, payload=None):
    return http(method, WI + path, payload)


def sub(method, user="admin", pw="admin", **params):
    q = [("u", user), ("p", pw), ("v", "1.16.1"), ("c", "e2e"), ("f", "json")]
    for k, v in params.items():
        for x in v if isinstance(v, list) else [v]:
            q.append((k, x))
    body = http("GET", f"{NDB}/rest/{method}?{urllib.parse.urlencode(q)}")["subsonic-response"]
    if body["status"] != "ok":
        raise RuntimeError(body)
    return body


def wait(pred, what, timeout=180, every=1.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        v = pred()
        if v:
            return v
        time.sleep(every)
    raise RuntimeError(f"timed out waiting for {what}")


def nd_db():
    snap = WORK / "snap"
    shutil.rmtree(snap, ignore_errors=True)
    snap.mkdir(parents=True)
    for suf in ("", "-wal", "-shm"):
        p = WORK / "nd-data" / f"navidrome.db{suf}"
        if p.exists():
            shutil.copy(p, snap / p.name)
    con = sqlite3.connect(snap / "navidrome.db")
    con.row_factory = sqlite3.Row
    return con


def wait_for_scan_after(stamp, watcher_grace=15):
    """Wait until Navidrome finished a scan that it reports after `stamp`.
    Docker Desktop on macOS drops some file events (renames inside an
    existing folder), so if the watcher doesn't scan within
    `watcher_grace` seconds, start the scan it would have started."""
    def done():
        st = sub("getScanStatus")["scanStatus"]
        return not st["scanning"] and st.get("lastScan") != stamp and st
    try:
        return wait(done, "a watcher scan", timeout=watcher_grace)
    except RuntimeError:
        log("  (no watcher scan; starting one as admin, standing in for the watcher)")
        sub("startScan")
        return wait(done, "a Navidrome scan", timeout=120)


def last_scan():
    return sub("getScanStatus")["scanStatus"].get("lastScan")


def settle():
    """Let the watcher's scan for whatever just changed run and finish."""
    stamp = last_scan()
    try:
        wait_for_scan_after(stamp)
    except RuntimeError:
        pass  # nothing changed on disk
    time.sleep(2)


def mulan_rows(con):
    return con.execute(
        "select m.id, m.library_id, m.path, m.missing, m.title, coalesce(a.play_count,0) plays, "
        "coalesce(a.starred,0) starred from media_file m left join annotation a "
        "on a.item_id=m.id and a.item_type='media_file' where m.album like '%Mulan%' "
        "order by m.library_id, m.path").fetchall()


def start_navidrome():
    run(["docker", "rm", "-f", ND])
    (WORK / "nd-data").mkdir(parents=True)
    run(["docker", "run", "-d", "--name", ND, "-p", f"{ND_PORT}:4533",
         "-e", "ND_SCANNER_WATCHERWAIT=5s", "-e", "ND_ENABLEINSIGHTSCOLLECTOR=false",
         "-e", "ND_LOGLEVEL=debug",
         "-v", f"{WORK / 'nd-data'}:/data", "-v", f"{LIBRARY}:/music:ro",
         "deluan/navidrome:0.64.2"])
    wait(lambda: _ok(NDB + "/ping"), "Navidrome")
    http("POST", NDB + "/auth/createAdmin", {"username": "admin", "password": "admin"})
    tok = http("POST", NDB + "/auth/login", {"username": "admin", "password": "admin"})["token"]
    h = {"x-nd-authorization": f"Bearer {tok}"}
    for g in ("unassigned", "kids"):
        http("POST", NDB + "/api/library", {"name": g, "path": f"/music/{g}"}, h)
    # The plugin's account: a regular user (can read scan status, can't start scans).
    http("POST", NDB + "/api/user", {"userName": "webimport", "name": "webimport",
                                     "password": "password", "isAdmin": False}, h)


def _ok(url):
    try:
        urllib.request.urlopen(url, timeout=2)
        return True
    except Exception:
        return False


def start_webimport():
    # "on" uses the dev config as is (.config/local.yaml points webimport at
    # this container as webimport/password); "off" switches the integration off.
    args = []
    if MODE == "off":
        cfg = WORK / "navidrome-off.yaml"
        cfg.write_text("webimport:\n  navidrome:\n    url: ''\n")
        args = ["-c", str(cfg)]
    env = {**os.environ, "BEETSDIR": str(REPO / ".config")}
    env.pop("WEBIMPORT_NAVIDROME_PASSWORD", None)
    logf = open(WORK / "webimport.log", "w")
    proc = subprocess.Popen([str(REPO / ".venv/bin/beet"), *args, "webimport"],
                            cwd=REPO, env=env, stdout=logf, stderr=subprocess.STDOUT)
    wait(lambda: _ok(WI + "/api/library/pending_moves"), "webimport")
    return proc


def decide_next_review(exclude=()):
    pr = wait(lambda: next((p for p in wi("GET", "/api/inbox")["pending_review"]
                            if p["task_id"] not in exclude), None), "a review", timeout=240)
    cands = pr["payload"].get("candidates") or []
    log(f"review {pr['task_id']}: {len(cands)} candidate(s); first = "
        f"{cands[0].get('album') if cands else None} {cands[0].get('album_id') if cands else ''}")
    wi("POST", f"/api/review/{pr['task_id']}/decide", {"action": "select", "index": 0})
    return pr["task_id"]


def album_id():
    albums = wi("GET", "/api/library/albums?q=")
    return albums[0]["id"] if albums else None


def report(title, before, con):
    rows = {r["id"]: r for r in mulan_rows(con)}
    lost = 0
    log(f"--- {title}")
    for b in before:
        r = rows.get(b["id"])
        kept = (r is not None and not r["missing"]
                and (r["plays"], r["starred"]) == (b["plays"], b["starred"]))
        lost += not kept
        state = "kept" if kept else ("LOST (row missing)" if r is not None and r["missing"] else "LOST")
        log(f"  lib {b['library_id']} {b['path'][-55:]:55} -> {state}"
            + (f" now lib {r['library_id']} {r['path'][-45:]}"
               if r is not None and (r["path"], r["library_id"]) != (b["path"], b["library_id"]) else "")
            + (f" (plays {r['plays']}, starred {bool(r['starred'])})" if r is not None else ""))
    pl = sub("getPlaylists")["playlists"]["playlist"][0]
    entries = sub("getPlaylist", id=pl["id"])["playlist"].get("entry", [])
    log(f"  playlist: {len(entries)}/{len(before)} entries playable")
    return lost


def main():
    WORK.mkdir(exist_ok=True)
    shutil.rmtree(WORK, ignore_errors=True)
    WORK.mkdir()
    run(["docker", "rm", "-f", ND])
    log(f"mode={MODE}: resetting dev library")
    run([str(REPO / "scripts/dev-reset.sh")])
    for g in ("unassigned", "kids"):
        (LIBRARY / g).mkdir(parents=True, exist_ok=True)
        # Like the homelab, where group folders hold other albums: keep the
        # group root from being pruned when this album leaves it (a vanished
        # library root makes Navidrome skip that library's missing files).
        (LIBRARY / g / ".keep").touch()
    start_navidrome()
    proc = start_webimport()
    try:
        log("importing Mulan as the 2020 digital release")
        wi("POST", "/api/inbox/start", {"paths": [str(MULAN)], "search_ids": {str(MULAN): DIGITAL}})
        decide_next_review()
        wait(lambda: not MULAN.exists(), "the import to finish", timeout=300)
        aid = wait(album_id, "the album")
        settle()
        con = nd_db()
        before = [dict(r) for r in mulan_rows(con) if not r["missing"]]
        assert before, "Navidrome didn't index the import"
        ids = [r["id"] for r in before]
        sub("createPlaylist", name="e2e", songId=ids)
        for i in ids:
            sub("star", id=i)
            sub("scrobble", id=i, submission="true")
            sub("scrobble", id=i, submission="true")
        time.sleep(1)
        before = [dict(r) for r in mulan_rows(nd_db()) if not r["missing"]]
        assert all(r["plays"] == 2 and r["starred"] for r in before), before
        log(f"{len(before)} Navidrome rows given history (album id {aid})")

        log("1. Library-tab reimport to the 1998 CD release")
        stamp = last_scan()
        wi("POST", "/api/reimport", {"album_ids": [aid], "search_id": CD_1998})
        decide_next_review()
        def reimported():
            a = album_id()
            return a and wi("GET", f"/api/library/albums/{a}")["fields"].get("mb_albumid") == CD_1998 and a
        aid2 = wait(reimported, "the reimported album")
        time.sleep(1)  # run_reimport hands the album to the Mover after session.run()
        pend = wi("GET", "/api/library/pending_moves")["pending"]
        log(f"right after reimport: pending moves = {pend}")
        if MODE == "on":
            assert pend and pend[0]["kind"] == "album", "expected the reimported album to be pending"
            # Phase 1 only: tags written in place, files not moved yet.
            assert (LIBRARY / "unassigned").rglob("*Original Walt Disney*"), "files moved early"
            stamp = last_scan()
            wait_for_scan_after(stamp)  # the scan that sees the new tags
            wait(lambda: not wi("GET", "/api/library/pending_moves")["pending"], "the pending move", timeout=60)
            log("pending move resolved")
        wait_for_scan_after(stamp)
        settle()
        lost1 = report("after reimport", before, nd_db())

        log("2. Listening Group unassigned -> kids")
        before2 = [dict(r) for r in mulan_rows(nd_db()) if not r["missing"]]
        res = wi("POST", f"/api/library/albums/{aid2}/fields", {"fields": {"navidrome_library": "kids"}, "move": True})
        log(f"save result: {res}")
        settle()
        settle()
        lost2 = report("after group move", before2, nd_db())
        log(f"RESULT mode={MODE}: reimport lost {lost1}/{len(before)}, group move lost {lost2}/{len(before2)}")
    finally:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=10)
        (WORK / "navidrome.log").write_text(subprocess.run(["docker", "logs", ND], capture_output=True, text=True).stderr)
        if not KEEP:
            run(["docker", "rm", "-f", ND])


if __name__ == "__main__":
    main()

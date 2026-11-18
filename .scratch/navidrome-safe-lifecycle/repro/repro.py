#!/usr/bin/env python3
"""Spike 01 repro: does Navidrome keep history when beets edits change paths?

Builds a throwaway beets library + Navidrome 0.64.2 container mirroring the
homelab layout (library 1 = /music root, plus overlapping per-Listening-Group
libraries /music/main and /music/kids), gives every track history (playlist
entry, star, 2 plays) in BOTH libraries, then runs one beets edit shape per
album and reports, per original Navidrome row, whether the history survived.

Usage (from the repo root, Docker running):
    .venv/bin/python .scratch/navidrome-safe-lifecycle/repro/repro.py [--keep]

--keep leaves the container running (http://localhost:14533, admin/admin).
By default scans are triggered explicitly (watcher disabled) so each "scan"
step is deterministic. --watch instead runs the homelab setting (watcher,
5s debounce) and each "scan" step waits for the watcher-triggered scan.
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
WORK = HERE / "work"
MUSIC = WORK / "music"  # mounted as /music
DATA = WORK / "navidrome-data"  # mounted as /data
SRC = WORK / "src"
BEETSDIR = WORK / "beets"
BEET = str(REPO / ".venv" / "bin" / "beet")

IMAGE = os.environ.get("ND_IMAGE", "deluan/navidrome:0.64.2")
CONTAINER = "nd-repro"
PORT = 14533
BASE = f"http://localhost:{PORT}"
GROUP_LIBS = ["main", "kids"]
WATCH = "--watch" in sys.argv
TOKEN = None

BEETS_CONFIG = f"""
plugins: []
directory: {MUSIC}
library: {BEETSDIR}/library.db
asciify_paths: yes
per_disc_numbering: no
paths:
  default: $navidrome_library/$albumartist/$album%aunique{{}}/$track $title
  singleton: $navidrome_library/Non-Album/$artist/$title
  comp: $navidrome_library/Compilations/$album%aunique{{}}/$track $title
import:
  write: yes
  copy: no
  move: yes
  resume: no
  incremental: no
  quiet: yes
  log: {BEETSDIR}/beet.log
"""

# Each case: (id, description, steps). Steps are ("beet", [args]) run with
# the case's query appended where "{q}" appears, or ("scan",).
# "W" = webimport today: DB store + move, tags NOT written (set_*_fields).
NEW_TITLE = "Song One Edited"
CASES = [
    ("A", "tag-only edit (genre), path unchanged",
     [("beet", ["modify", "-y", "-w", "-m", "{q}", "genre=Jazz"]), ("scan",)]),
    ("B", "retitle track 1: write tags + rename, one scan (beet modify)",
     [("beet", ["modify", "-y", "-w", "-m", "{q}", "track:1", f"title={NEW_TITLE}"]), ("scan",)]),
    ("Bw", "retitle track 1: rename only, tags untouched (webimport today)",
     [("beet", ["modify", "-y", "-W", "-m", "{q}", "track:1", f"title={NEW_TITLE}"]), ("scan",)]),
    ("C", "rename album: write tags + rename, one scan",
     [("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "album={album} Renamed"]), ("scan",)]),
    ("Cw", "rename album: rename only, tags untouched (webimport today)",
     [("beet", ["modify", "-y", "-a", "-W", "-m", "{q}", "album={album} Renamed"]), ("scan",)]),
    ("D", "Listening Group main->kids (path-only; flex field, no tag change)",
     [("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "navidrome_library=kids"]), ("scan",)]),
    ("G", "rename album + group main->kids: write tags + rename, one scan",
     [("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "album={album} Renamed", "navidrome_library=kids"]), ("scan",)]),
    ("E", "retitle, two-phase tags first: write, scan, move, scan (ADR-0011)",
     [("beet", ["modify", "-y", "-w", "-M", "{q}", "track:1", f"title={NEW_TITLE}"]), ("scan",),
      ("beet", ["move", "{q}"]), ("scan",)]),
    ("F", "retitle, two-phase move first: rename, scan, write, scan (ND docs)",
     [("beet", ["modify", "-y", "-W", "-m", "{q}", "track:1", f"title={NEW_TITLE}"]), ("scan",),
      ("beet", ["write", "{q}"]), ("scan",)]),
    ("H", "rename album, two-phase tags first",
     [("beet", ["modify", "-y", "-a", "-w", "-M", "{q}", "album={album} Renamed"]), ("scan",),
      ("beet", ["move", "{q}"]), ("scan",)]),
    ("I", "rename album + group main->kids, two-phase tags first",
     [("beet", ["modify", "-y", "-a", "-w", "-M", "{q}", "album={album} Renamed", "navidrome_library=kids"]),
      ("scan",), ("beet", ["move", "{q}"]), ("scan",)]),
    # Files beets never wrote (as-is imports): the move is their first write.
    ("D0", "group move main->kids on files beets never wrote (as-is import)",
     [("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "navidrome_library=kids"]), ("scan",)]),
    # New Listening Group whose folder isn't a Navidrome library yet;
    # registered afterwards (the manual step from ADR-0002).
    ("U", "group move main->talk (unregistered), scan, register talk, scan",
     [("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "navidrome_library=talk-{var}"]), ("scan",),
      ("addlib", "talk-{var}"), ("scan",)]),
    # Library-tab reimport to a different release: new MBIDs + new album name.
    # Navidrome's PID.Track `musicbrainz_trackid` is the RELEASE-track id
    # (beets mb_releasetrackid), not the recording id (beets mb_trackid).
    ("R", "reimport-like: new MBIDs + rename album, one scan",
     [("beet", ["modify", "-y", "-w", "-M", "{q}", "track:1", "mb_trackid={uuid:t1}", "mb_releasetrackid={uuid:rt1}"]),
      ("beet", ["modify", "-y", "-w", "-M", "{q}", "track:2", "mb_trackid={uuid:t2}", "mb_releasetrackid={uuid:rt2}"]),
      ("beet", ["modify", "-y", "-a", "-w", "-m", "{q}", "album={album} Renamed", "mb_albumid={uuid:al}"]),
      ("scan",)]),
    ("R2", "reimport-like, two-phase tags first",
     [("beet", ["modify", "-y", "-w", "-M", "{q}", "track:1", "mb_trackid={uuid:t1}", "mb_releasetrackid={uuid:rt1}"]),
      ("beet", ["modify", "-y", "-w", "-M", "{q}", "track:2", "mb_trackid={uuid:t2}", "mb_releasetrackid={uuid:rt2}"]),
      ("beet", ["modify", "-y", "-a", "-w", "-M", "{q}", "album={album} Renamed", "mb_albumid={uuid:al}"]),
      ("scan",), ("beet", ["move", "{q}"]), ("scan",)]),
]
NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")
VARIANTS = ["mb", "nomb"]  # with / without MusicBrainz IDs
TRACKS = ["Song One", "Song Two"]


def log(*a):
    print(*a, flush=True)


def run(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        raise RuntimeError(f"{cmd} failed:\n{r.stdout}\n{r.stderr}")
    return r.stdout


def beet(*args):
    return run([BEET, *args], env={**os.environ, "BEETSDIR": str(BEETSDIR)})


# ---------------------------------------------------------------- navidrome
def subsonic(method, **params):
    q = [("u", "admin"), ("p", "admin"), ("v", "1.16.1"), ("c", "repro"), ("f", "json")]
    for k, v in params.items():
        for x in v if isinstance(v, list) else [v]:
            q.append((k, x))
    url = f"{BASE}/rest/{method}?{urllib.parse.urlencode(q)}"
    with urllib.request.urlopen(url) as r:
        body = json.load(r)["subsonic-response"]
    if body.get("status") != "ok":
        raise RuntimeError(f"{method}: {body}")
    return body


def native(method, path, payload=None, token=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"Content-Type": "application/json",
                 **({"x-nd-authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def start_navidrome():
    run(["docker", "rm", "-f", CONTAINER])
    run(["docker", "run", "-d", "--name", CONTAINER, "-p", f"{PORT}:4533",
         "-e", f"ND_SCANNER_WATCHERWAIT={'5s' if WATCH else '0'}",
         "-e", "ND_SCANNER_SCANONSTARTUP=false",
         "-e", "ND_ENABLEINSIGHTSCOLLECTOR=false",
         "-e", "ND_LOGLEVEL=debug",
         "-v", f"{DATA}:/data", "-v", f"{MUSIC}:/music:ro", IMAGE])
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/ping")
            break
        except Exception:
            time.sleep(1)
    native("POST", "/auth/createAdmin", {"username": "admin", "password": "admin"})
    global TOKEN
    TOKEN = native("POST", "/auth/login", {"username": "admin", "password": "admin"})["token"]
    for g in GROUP_LIBS:
        add_library(g)


def add_library(name):
    native("POST", "/api/library", {"name": name, "path": f"/music/{name}"}, TOKEN)


def scan(explicit=True):
    before = subsonic("getScanStatus")["scanStatus"].get("lastScan")
    if explicit:
        subsonic("startScan")
    for _ in range(300 if explicit else 60):
        time.sleep(0.5)
        st = subsonic("getScanStatus")["scanStatus"]
        if not st["scanning"] and st.get("lastScan") != before:
            time.sleep(1)  # let post-scan refreshes settle
            return
    raise RuntimeError("scan did not finish" if explicit else
                       "watcher never scanned (fs events not reaching the container?)")


def db():
    """Consistent-enough snapshot of navidrome.db (copied with its WAL)."""
    snap = WORK / "snap"
    shutil.rmtree(snap, ignore_errors=True)
    snap.mkdir()
    for suf in ("", "-wal", "-shm"):
        p = DATA / f"navidrome.db{suf}"
        if p.exists():
            shutil.copy(p, snap / p.name)
    con = sqlite3.connect(snap / "navidrome.db")
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------------------ fixtures
def make_sources():
    freq = 300
    for cid, _, _ in CASES:
        for var in VARIANTS:
            d = SRC / f"{cid}-{var}"
            d.mkdir(parents=True)
            for n, title in enumerate(TRACKS, 1):
                freq += 7
                run(["ffmpeg", "-loglevel", "error", "-f", "lavfi",
                     "-i", f"sine=frequency={freq}:duration=2", "-q:a", "9",
                     "-metadata", f"title={title}", "-metadata", "artist=Repro Artist",
                     "-metadata", "album_artist=Repro Artist",
                     "-metadata", f"album=Case {cid} {var}", "-metadata", f"track={n}",
                     str(d / f"{n:02d}.mp3")])


def import_sources():
    for d in sorted(SRC.iterdir()):
        beet("import", "-A", "--set", "navidrome_library=main",
             "--set", f"repro_case={d.name}", str(d))
        if d.name.endswith("-mb"):
            ns = NS
            beet("modify", "-y", "-a", "-w", f"repro_case::^{d.name}$",
                 f"mb_albumid={uuid.uuid5(ns, d.name + '/album')}")
            for n in (1, 2):
                beet("modify", "-y", "-w", f"repro_case::^{d.name}$", f"track:{n}",
                     f"mb_trackid={uuid.uuid5(ns, f'{d.name}/{n}')}",
                     f"mb_releasetrackid={uuid.uuid5(ns, f'{d.name}/rt{n}')}")
    # beets' as-is import doesn't write tags; real imports do. Settle every
    # file to what beets writes so the edits below are the only tag changes.
    beet("write", "-f", "^repro_case::^D0-")


def beets_paths(case):
    out = beet("ls", "-f", "$track|$path", f"repro_case::^{case}$")
    res = {}
    for line in out.splitlines():
        t, p = line.split("|", 1)
        res[int(t)] = "/music/" + str(Path(p).relative_to(MUSIC))
    return res


def lib_rel(lib_path, abs_path):
    return str(Path(abs_path).relative_to(lib_path))


def give_history(con):
    """Playlist per case containing every row (root + group copy), star + 2 plays."""
    libs = {r["id"]: r["path"] for r in con.execute("select id, path from library")}
    baseline = {}  # (case, track, lib_id) -> media_file id
    for cid, _, _ in CASES:
        for var in VARIANTS:
            case = f"{cid}-{var}"
            ids = []
            for t, p in beets_paths(case).items():
                for lib_id, lpath in libs.items():
                    if not p.startswith(lpath.rstrip("/") + "/"):
                        continue
                    row = con.execute(
                        "select id from media_file where library_id=? and path=? and missing=0",
                        (lib_id, lib_rel(lpath, p))).fetchone()
                    if row is None:
                        raise RuntimeError(f"no ND row for {p} in library {lib_id}")
                    baseline[(case, t, lib_id)] = row["id"]
                    ids.append(row["id"])
            subsonic("createPlaylist", name=f"pl-{case}", songId=ids)
            for i in ids:
                subsonic("star", id=i)
                subsonic("scrobble", id=i, submission="true")
                subsonic("scrobble", id=i, submission="true")
    return baseline, libs


# ------------------------------------------------------------------- report
def evaluate(con, baseline, libs):
    libs = {r["id"]: r["path"] for r in con.execute("select id, path from library")}
    lib_name = {i: ("root" if p == "/music" else p.rsplit("/", 1)[1]) for i, p in libs.items()}
    rows = []
    for cid, desc, _ in CASES:
        for var in VARIANTS:
            case = f"{cid}-{var}"
            new_paths = beets_paths(case)
            pl = con.execute(
                "select pt.media_file_id from playlist_tracks pt join playlist p on p.id=pt.playlist_id "
                "where p.name=?", (f"pl-{case}",)).fetchall()
            pl_ids = {r[0] for r in pl}
            for (bc, t, lib_id), mid in sorted(baseline.items()):
                if bc != case:
                    continue
                mf = con.execute("select path, missing, pid, library_id from media_file where id=?",
                                 (mid,)).fetchone()
                ann = con.execute(
                    "select play_count, starred from annotation where item_id=? and item_type='media_file'",
                    (mid,)).fetchone()
                np = new_paths[t]
                if mf is None:
                    status = "GONE"
                elif mf["missing"]:
                    status = "MISSING"
                else:
                    status = "kept"
                # live row(s) for the file's new location, any library
                live = []
                for l_id, lpath in libs.items():
                    if np.startswith(lpath.rstrip("/") + "/"):
                        live += con.execute(
                            "select id, library_id from media_file "
                            "where missing=0 and library_id=? and path=?",
                            (l_id, lib_rel(lpath, np))).fetchall()
                base_ids = set(baseline.values())
                fresh = [f"{lib_name[r['library_id']]}:{r['id'][:6]}" for r in live
                         if r["id"] not in base_ids]
                rows.append({
                    "case": case, "desc": desc, "track": t, "lib": lib_name[lib_id],
                    "status": status if not mf or mf["library_id"] == lib_id
                    else f"{status} (moved to {lib_name[mf['library_id']]})",
                    "path_now": mf["path"] if mf else "-",
                    "plays": ann["play_count"] if ann else 0,
                    "starred": bool(ann["starred"]) if ann else False,
                    "in_playlist": mid in pl_ids,
                    "orphan_rows": ", ".join(fresh),
                })
    return rows


def render(rows):
    out = ["| case | edit | trk | row's library | original row | history on live row | new history-less row(s) |",
           "|---|---|---|---|---|---|---|"]
    for r in rows:
        hist = (f"plays={r['plays']} starred={r['starred']} playlist={r['in_playlist']}"
                if r["status"] == "kept" else "lost (row missing)")
        out.append(f"| {r['case']} | {r['desc']} | {r['track']} | {r['lib']} | {r['status']} "
                   f"| {hist} | {r['orphan_rows']} |")
    return "\n".join(out)


def summarize(rows):
    """One line per case: which original rows lost their history, per variant."""
    agg = {}
    for r in rows:
        cid, var = r["case"].rsplit("-", 1)
        agg.setdefault((cid, r["desc"]), {}).setdefault(var, []).append(r)

    def cell(rs):
        lost = [f"{r['lib']}#{r['track']}" for r in rs if not r["status"].startswith("kept")]
        if lost:
            return "LOST " + ", ".join(lost)
        return "kept" + (" (row moved library)" if any("moved to" in r["status"] for r in rs) else "")

    out = ["| case | edit | with MBIDs | without MBIDs |", "|---|---|---|---|"]
    for (cid, desc), v in agg.items():
        out.append(f"| {cid} | {desc} | {cell(v['mb'])} | {cell(v['nomb'])} |")
    return "\n".join(out)


def main():
    keep = "--keep" in sys.argv
    run(["docker", "rm", "-f", CONTAINER])
    shutil.rmtree(WORK, ignore_errors=True)
    for d in (MUSIC, DATA, SRC, BEETSDIR):
        d.mkdir(parents=True)
    for g in GROUP_LIBS:
        (MUSIC / g).mkdir()
    (BEETSDIR / "config.yaml").write_text(BEETS_CONFIG)

    log("generating + importing fixtures…")
    make_sources()
    import_sources()
    log(f"starting {IMAGE}…")
    start_navidrome()
    scan()
    baseline, libs = give_history(db())
    log(f"{len(baseline)} Navidrome rows given history")

    for cid, desc, steps in CASES:
        for var in VARIANTS:
            case = f"{cid}-{var}"
            album = f"Case {cid} {var}"
            log(f"case {case}: {desc}")
            prev = None
            for step in steps:
                if step[0] == "scan":
                    # after adding a library there is no fs event: scan explicitly
                    scan(explicit=not WATCH or prev == "addlib")
                elif step[0] == "addlib":
                    add_library(step[1].replace("{var}", var))
                else:
                    args = []
                    for a in step[1]:
                        a = (a.replace("{q}", f"repro_case::^{case}$").replace("{album}", album)
                             .replace("{var}", var))
                        for k in ("t1", "t2", "rt1", "rt2", "al"):
                            a = a.replace("{uuid:%s}" % k, str(uuid.uuid5(NS, f"{case}/new-{k}")))
                        args.append(a)
                    beet(*args)
                prev = step[0]

    rows = evaluate(db(), baseline, libs)
    table = summarize(rows) + "\n\n## Per row\n\n" + render(rows)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = HERE / f"results-{stamp}.md"
    out.write_text(f"# Repro results {stamp} ({IMAGE})\n\n{table}\n")
    print(table)
    log(f"\nwritten to {out}")
    (WORK / "navidrome.log").write_text(
        subprocess.run(["docker", "logs", CONTAINER], capture_output=True, text=True).stderr)
    if not keep:
        run(["docker", "rm", "-f", CONTAINER])


if __name__ == "__main__":
    main()

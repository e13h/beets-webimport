"""What happens to an inbox folder in move mode (ADR-0015).

beets moves each album's audio files into the library. webimport keeps
everything needed to put the folder back exactly (Undo import, restore.py):

- the audio files' originals (originals.py), captured at review;
- the folder's other files ("companions": cover.jpg, .cue, .log, scans),
  kept whole and recorded on the album (`original_folder`);
- a safety copy of each audio file while the import runs: a hard link in
  `<inbox>/.webimport-safety/` (free, survives beets' copy-then-delete
  move), or a real copy when the inbox and library share a mount (then
  beets renames the file and rewrites it in place, which a hard link
  would see). It's removed once the import is checked; if the check
  fails it becomes the stored original.

After a checked import the companions are removed and empty folders
pruned, so the inbox only holds what's still to import.

Folders imported in copy mode (before ADR-0015) still hold their files
and the `.webimport_imported` marker. At startup their originals are
saved from those files (`backfill_all`); "Remove inbox copy"
(`release_folder`) then checks every file can be rebuilt exactly and
deletes the folder.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from beets import config

from . import originals

log = logging.getLogger("beets.webimport")

MARKER = ".webimport_imported"
SAFETY_DIRNAME = ".webimport-safety"
RECOVERED_DIRNAME = "_recovered"
COMPANIONS_FIELD = "original_folder"
AUDIO_EXTS = {".mp3", ".m4a", ".mp4", ".m4b", ".aac", ".alac", ".flac", ".ogg", ".oga", ".opus",
              ".wma", ".wav", ".aif", ".aiff", ".ape", ".wv", ".mpc", ".dsf", ".dff"}
CLUTTER = {".DS_Store", "Thumbs.db", "desktop.ini", MARKER}


def move_mode() -> bool:
    return bool(config["import"]["move"].get(bool))


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _inbox_root(session) -> Path | None:
    try:
        root = session.wi_config["inbox_dir"].get(str) if session.wi_config is not None else None
    except Exception:  # noqa: BLE001
        root = None
    return Path(root) if root else None


def _is_webimport_inbox_session(session) -> bool:
    from .session import WebImportSession

    return isinstance(session, WebImportSession) and bool(session.paths) and session.query is None


def _task_items(task):
    return task.items if getattr(task, "is_album", True) else [task.item]


# -- companions ----------------------------------------------------------------------

def companion_files(folder: Path) -> list[Path]:
    """Non-audio files in `folder` (recursively), skipping hidden files,
    clutter, and webimport's own folders."""
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != RECOVERED_DIRNAME)
        for name in sorted(filenames):
            if name.startswith(".") or name in CLUTTER or os.path.splitext(name)[1].lower() in AUDIO_EXTS:
                continue
            out.append(Path(dirpath) / name)
    return out


def capture_companions(folder: Path) -> dict:
    """Store each companion file whole; return the album record."""
    files = []
    for path in companion_files(folder):
        data = path.read_bytes()
        sha = hashlib.sha256(data).hexdigest()
        blob = originals.store_root() / sha / "full"
        if not blob.exists():
            originals._write_atomic(blob, data)
        st = path.stat()
        files.append({"rel": str(path.relative_to(folder)), "sha256": sha, "size": len(data),
                      "mtime": st.st_mtime, "mode": st.st_mode & 0o7777})
    return {"folder": str(folder), "files": files}


def load_companions(album) -> dict | None:
    raw = album.get(COMPANIONS_FIELD) if album is not None else None
    if not raw:
        return None
    try:
        rec = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return rec if isinstance(rec, dict) and isinstance(rec.get("files"), list) else None


def _merge_companions(album, rec: dict) -> None:
    existing = load_companions(album)
    if existing and existing.get("folder") == rec["folder"]:
        known = {f["rel"] for f in existing["files"]}
        rec = {**existing, "files": existing["files"] + [f for f in rec["files"] if f["rel"] not in known]}
    album[COMPANIONS_FIELD] = json.dumps(rec)
    album.store()


def _remove_companions(rec: dict) -> None:
    folder = Path(rec["folder"])
    for f in rec["files"]:
        p = folder / f["rel"]
        try:
            if p.is_file() and _sha256(p) == f["sha256"]:
                p.unlink()
        except OSError:
            pass


def _prune(folder: Path, root: Path) -> None:
    """Remove `folder` and its parents up to (not including) `root` while
    they hold nothing but clutter."""
    folder, root = folder.resolve(), root.resolve()
    if not folder.is_relative_to(root) or folder == root:
        return
    for d in sorted((Path(p) for p, _, _ in os.walk(folder)), key=lambda p: len(p.parts), reverse=True):
        try:
            if all(n in CLUTTER for n in os.listdir(d)):
                shutil.rmtree(d)
        except OSError:
            pass
    parent = folder.parent
    while parent != root and parent.is_relative_to(root):
        try:
            if all(n in CLUTTER for n in os.listdir(parent)):
                shutil.rmtree(parent)
            else:
                break
        except OSError:
            break
        parent = parent.parent


# -- safety copies ---------------------------------------------------------------------

_same_mount_cache: dict[tuple[str, str], bool] = {}


def _rename_would_succeed(sample: Path, libdir: Path) -> bool:
    """Whether beets' move will be a rename (same mount): then the moved
    file is rewritten in place and a hard link can't serve as a backup."""
    key = (str(sample.parent), str(libdir))
    if key not in _same_mount_cache:
        probe = libdir / f".webimport-probe-{os.getpid()}"
        try:
            libdir.mkdir(parents=True, exist_ok=True)
            os.link(sample, probe)
            probe.unlink()
            _same_mount_cache[key] = True
        except OSError:
            _same_mount_cache[key] = False
    return _same_mount_cache[key]


def _safety_path(root: Path, record: dict) -> Path:
    return root / SAFETY_DIRNAME / (record["sha256"] + os.path.splitext(record.get("name", ""))[1])


def make_safety_copy(src: Path, record: dict, root: Path, libdir: Path) -> Path | None:
    dest = _safety_path(root, record)
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not _rename_would_succeed(src, libdir):
            os.link(src, dest)
            return dest
    except OSError:
        pass
    fd, tmp = tempfile.mkstemp(dir=dest.parent, prefix=".tmp-")
    os.close(fd)
    shutil.copy2(src, tmp)
    os.replace(tmp, dest)
    return dest


# -- import hooks ------------------------------------------------------------------------

def on_review(task, session) -> None:
    """At review (before beets touches anything), in move mode: a safety
    copy of each audio file and the folder's companions."""
    if not move_mode() or not _is_webimport_inbox_session(session):
        return
    root = _inbox_root(session)
    if root is None:
        return
    libdir = Path(os.fsdecode(session.lib.directory))
    safety = getattr(task, "_webimport_safety", {})
    folders = set()
    for item in _task_items(task):
        rec = originals.load(item)
        src = Path(os.fsdecode(item.path))
        folders.add(src.parent)
        if rec is None or rec["sha256"] in safety:
            continue
        try:
            safety[rec["sha256"]] = make_safety_copy(src, rec, root, libdir)
        except OSError:
            log.exception("couldn't make a safety copy of %s", src)
    task._webimport_safety = safety
    if not hasattr(task, "_webimport_companions"):
        comps = []
        for folder in sorted(folders):
            if folder.resolve() == root.resolve():
                continue  # loose files at the inbox root: other files there aren't this album's
            try:
                comps.append(capture_companions(folder))
            except OSError:
                log.exception("couldn't keep the other files in %s", folder)
        task._webimport_companions = comps


def finish_task(session, task) -> None:
    """After a checked import (import_task_files, after originals.verify_task),
    in move mode: record and remove the companions, drop the safety
    copies, prune empty folders."""
    if not move_mode() or not _is_webimport_inbox_session(session):
        return
    root = _inbox_root(session)
    album = task.album if getattr(task, "is_album", False) else None
    comps = getattr(task, "_webimport_companions", [])
    if album is not None:
        for rec in comps:
            if rec["files"]:
                _merge_companions(album, rec)
                _remove_companions(rec)
    for path in getattr(task, "_webimport_safety", {}).values():
        if path is not None:
            try:
                path.unlink()
            except OSError:
                pass
    if root is not None:
        try:
            (root / SAFETY_DIRNAME).rmdir()  # only if empty (another import may be using it)
        except OSError:
            pass
        for rec in comps:
            _prune(Path(rec["folder"]), root)
        for item in _task_items(task):
            rec = originals.load(item)
            if rec and rec.get("source_path"):
                _prune(Path(rec["source_path"]).parent, root)


def cleanup_safety(lib, root: Path) -> list[str]:
    """At startup: drop safety copies from finished imports. One whose file
    isn't in the library and has no other link (the inbox original is gone,
    e.g. the server stopped mid-import) is moved to `_recovered/` in the
    inbox. Returns the recovered paths."""
    folder = root / SAFETY_DIRNAME
    if not folder.is_dir():
        return []
    used = originals.referenced(lib)
    recovered = []
    for p in folder.iterdir():
        if p.name.startswith(".tmp-"):
            p.unlink(missing_ok=True)
            continue
        sha = p.name.split(".", 1)[0]
        if sha in used or p.stat().st_nlink > 1:
            p.unlink(missing_ok=True)
            continue
        dest = root / RECOVERED_DIRNAME / p.name
        dest.parent.mkdir(exist_ok=True)
        os.replace(p, dest)
        recovered.append(str(dest))
        log.warning("webimport: recovered %s from an interrupted import", dest)
    try:
        folder.rmdir()
    except OSError:
        pass
    return recovered


# -- folders imported in copy mode ---------------------------------------------------------

def _audio_sha(path: Path) -> str | None:
    data = path.read_bytes()
    s = originals.split(data, str(path))
    return hashlib.sha256(data[s.start:s.end]).hexdigest() if s else None


def _audio_files(folder: Path) -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk(folder):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        out += [Path(dirpath) / n for n in sorted(filenames)
                if not n.startswith(".") and os.path.splitext(n)[1].lower() in AUDIO_EXTS]
    return out


def match_folder(folder: Path, album) -> tuple[dict, list[Path], list]:
    """Pair the folder's audio files with the album's items by their audio
    bytes. Returns ({inbox path: item}, unmatched files, unmatched items)."""
    by_audio: dict[str, list] = {}
    for item in album.items():
        try:
            sha = _audio_sha(Path(os.fsdecode(item.path)))
        except OSError:
            sha = None
        by_audio.setdefault(sha, []).append(item)
    pairs, loose = {}, []
    for f in _audio_files(folder):
        try:
            sha = _audio_sha(f)
        except OSError:
            sha = None
        cands = by_audio.get(sha) if sha else None
        if cands:
            pairs[f] = cands.pop(0)
        else:
            loose.append(f)
    leftover = [i for items in by_audio.values() for i in items]
    return pairs, loose, leftover


def backfill_album(album, folder: Path) -> int:
    """Save originals for the album's items from their inbox copies (copy
    mode). Only reads files when some item has no original yet."""
    if all(originals.load(i) for i in album.items()):
        return 0
    pairs, _, _ = match_folder(folder, album)
    n = 0
    for src, item in pairs.items():
        if originals.load(item):
            continue
        rec = originals.capture(src)
        if rec["format"] != "full" and not originals.can_restore(rec, item.path):
            originals._write_atomic(originals.store_root() / rec["sha256"] / "full", src.read_bytes())
            rec["format"] = "full"
        item[originals.FIELD] = json.dumps(rec)
        item.store()
        n += 1
    return n


def marker_folders(root: Path) -> list[tuple[Path, dict]]:
    out = []
    if not root.is_dir():
        return out
    for marker in root.rglob(MARKER):
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        out.append((marker.parent, data))
    return out


def backfill_all(lib, root: Path) -> int:
    n = 0
    for folder, data in marker_folders(root):
        album = lib.get_album(data.get("album_id")) if data.get("album_id") else None
        if album is None:
            continue
        try:
            n += backfill_album(album, folder)
        except Exception:  # noqa: BLE001 -- one bad folder shouldn't stop startup
            log.exception("webimport: couldn't save originals from %s", folder)
    return n


class ReleaseRefused(Exception):
    def __init__(self, message: str, problems: list[str]):
        super().__init__(message)
        self.problems = problems


def release_folder(lib, folder: Path, root: Path) -> dict:
    """Remove an imported folder's inbox copy (copy-mode leftovers) once
    every audio file in it can be rebuilt exactly from the library; its
    other files are kept with the album for Undo import."""
    folder = folder.resolve()
    if not folder.is_relative_to(root.resolve()) or folder == root.resolve():
        raise ReleaseRefused("Not a folder in the inbox.", [])
    try:
        data = json.loads((folder / MARKER).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ReleaseRefused("This folder hasn't been imported.", [])
    album = lib.get_album(data.get("album_id")) if data.get("album_id") else None
    if album is None:
        raise ReleaseRefused("Its album is no longer in the library.", [])
    backfill_album(album, folder)
    pairs, loose, _ = match_folder(folder, album)
    problems = [f"{p.name}: not part of the imported album." for p in loose]
    for src, item in pairs.items():
        rec = originals.load(item)
        if rec is None or rec["sha256"] != _sha256(src):
            problems.append(f"{src.name}: its saved original doesn't match this file.")
        elif not originals.can_restore(rec, item.path):
            problems.append(f"{src.name}: can't be rebuilt exactly from the library.")
    if problems:
        raise ReleaseRefused("Some files can't be restored exactly, so the inbox copy was kept.", problems)
    comps = capture_companions(folder)
    if comps["files"]:
        _merge_companions(album, comps)
    shutil.rmtree(folder)
    _prune(folder.parent, root)
    return {"removed": str(folder), "audio_files": len(pairs), "other_files": len(comps["files"])}

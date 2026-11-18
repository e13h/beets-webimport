"""Undo import from the library: put an album's files back in the inbox
exactly as they were, and remove the album from beets.

Each file is rebuilt from its stored original (originals.py, checked by
SHA-256) and written to its original inbox path. Nothing is touched until
every file has been rebuilt and written to a temporary file next to its
destination; only then are the files moved into place and the album
removed (`remove(delete=True)`, scoped to this album's ID, as ADR-0001).

A destination that already holds the identical file (copy mode: the inbox
original is still there) is left as is. A destination holding a different
file is a conflict: nothing is done.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import lifecycle, originals

MARKER = ".webimport_imported"


class UndoRefused(Exception):
    def __init__(self, message: str, plan: "Plan"):
        super().__init__(message)
        self.plan = plan


@dataclass
class FilePlan:
    item_id: int | None  # None: one of the folder's other files (lifecycle.py)
    title: str
    library_path: str
    dest: str
    action: str  # "write" | "present" (identical file already there)
    record: dict = field(repr=False, default_factory=dict)


@dataclass
class Plan:
    album_id: int
    files: list[FilePlan] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def folders(self) -> list[str]:
        return sorted({os.path.dirname(f.dest) for f in self.files})

    def as_json(self) -> dict:
        return {
            "album_id": self.album_id,
            "ok": not self.problems,
            "problems": self.problems,
            "folders": self.folders,
            "files": [{"item_id": f.item_id, "title": f.title, "dest": f.dest, "action": f.action}
                      for f in self.files],
            "to_write": sum(f.action == "write" for f in self.files),
            "audio_files": sum(f.item_id is not None for f in self.files),
            "other_files": sum(f.item_id is None for f in self.files),
            "already_in_inbox": sum(f.action == "present" for f in self.files),
        }


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _umask() -> int:
    mask = os.umask(0)
    os.umask(mask)
    return mask


def _inside(path: str, base: str) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(base).resolve())
    except (OSError, ValueError):
        return False


def plan(album, inbox_dir: str) -> Plan:
    """What undo would do, and why it can't (problems). Reads files to
    check for conflicts but changes nothing."""
    p = Plan(album_id=album.id)
    if not inbox_dir:
        p.problems.append("No inbox folder is configured (webimport.inbox_dir).")
        return p
    seen: set[str] = set()
    for item in album.items():
        label = f"{item.track}. {item.title}" if item.track else item.title
        rec = originals.load(item)
        if rec is None:
            p.problems.append(f"{label}: imported before originals were kept, so it can't be restored.")
            continue
        if rec.get("restorable") is False:
            p.problems.append(f"{label}: its original couldn't be kept when it was imported.")
            continue
        dest = rec.get("source_path") or ""
        if not dest or not _inside(dest, inbox_dir):
            p.problems.append(f"{label}: its original location ({dest or 'unknown'}) isn't in the inbox.")
            continue
        if dest in seen:
            p.problems.append(f"{label}: another track has the same original location.")
            continue
        seen.add(dest)
        action = "write"
        if os.path.lexists(dest):
            if os.path.isfile(dest) and _sha256_file(dest) == rec["sha256"]:
                action = "present"
            else:
                p.problems.append(f"{label}: a different file is already at {dest}.")
                continue
        p.files.append(FilePlan(item.id, label, os.fsdecode(item.path), dest, action, rec))
    comps = lifecycle.load_companions(album)
    for c in (comps or {}).get("files", []):
        dest = os.path.join(comps["folder"], c["rel"])
        if not _inside(dest, inbox_dir) or dest in seen:
            p.problems.append(f"{c['rel']}: its original location isn't in the inbox.")
            continue
        seen.add(dest)
        action = "write"
        if os.path.lexists(dest):
            if os.path.isfile(dest) and _sha256_file(dest) == c["sha256"]:
                action = "present"
            else:
                p.problems.append(f"{c['rel']}: a different file is already at {dest}.")
                continue
        p.files.append(FilePlan(None, c["rel"], "", dest, action, {**c, "format": "full"}))
    if not any(f.item_id is not None for f in p.files) and not p.problems:
        p.problems.append("The album has no tracks.")
    return p


def _remove_markers(folders: list[str], album_id: int) -> None:
    for folder in folders:
        marker = Path(folder) / MARKER
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            data = {}
        if data.get("album_id") in (None, album_id):
            try:
                marker.unlink()
            except OSError:
                pass


def undo(lib, album, inbox_dir: str) -> dict:
    """Restore the album's files to the inbox and remove it from the
    library. Raises UndoRefused (nothing changed) if any file can't be
    restored exactly."""
    p = plan(album, inbox_dir)
    if p.problems:
        raise UndoRefused("Some tracks can't be restored.", p)

    # 1. Rebuild every file into a temp file beside its destination.
    staged: list[tuple[FilePlan, str]] = []
    try:
        for f in p.files:
            if f.action != "write":
                continue
            data = originals.rebuild(f.record, f.library_path)  # SHA-256 checked
            os.makedirs(os.path.dirname(f.dest), exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=os.path.dirname(f.dest), prefix=".webimport-restore-")
            with os.fdopen(fd, "wb") as out:
                out.write(data)
            staged.append((f, tmp))
    except (originals.RestoreError, OSError) as exc:
        for _, tmp in staged:
            try:
                os.unlink(tmp)
            except OSError:
                pass
        p.problems.append(str(exc))
        raise UndoRefused(f"Couldn't rebuild the original files: {exc}", p) from exc

    # 2. Move them into place (same directory: atomic renames).
    for f, tmp in staged:
        # mkstemp creates 0600; give the file its original permissions
        # (or the usual umask default) so other services can read it.
        os.chmod(tmp, f.record.get("mode") or (0o666 & ~_umask()))
        os.replace(tmp, f.dest)
        mtime = f.record.get("mtime")
        if mtime:
            try:
                os.utime(f.dest, (mtime, mtime))
            except OSError:
                pass

    # 3. Remove the album (library files, art, DB rows) and the markers.
    shas = {f.record["sha256"] for f in p.files}
    album.remove(delete=True)
    _remove_markers(p.folders, p.album_id)
    still_used = originals.referenced(lib)
    for sha in shas - still_used:
        originals.remove(sha)

    out = p.as_json()
    out["restored"] = out.pop("to_write")
    return out

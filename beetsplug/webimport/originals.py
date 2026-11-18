"""Original files, restorable byte for byte.

beets rewrites only a file's tag areas, never its audio bytes (verified for
MP3, MP4/M4A, FLAC, Ogg Vorbis and Opus). So for each inbox file we keep
everything that *isn't* audio, before anything is written:

- MP3:  the ID3v2 tag(s) before the audio; ID3v1 / APEv2 / Lyrics3 after
- MP4:  every atom except the single `mdat` (moov with the tags and art)
- FLAC: `fLaC` plus all metadata blocks (tags, pictures, padding)
- Ogg:  the header pages (codec setup, comments, pictures)

and to rebuild the original we put those bytes back around the current
file's audio. Ogg is one step more: when the comment packet changes size,
the audio pages are renumbered and their checksums recomputed, so the
original page numbers are put back (and the checksums recomputed).

The rebuilt file is checked against the original's SHA-256 before it's
used; if it doesn't match, restore refuses. Formats without a splitter
(WAV, AIFF, …) or files that don't split cleanly are kept whole.

Storage: `<library dir>/webimport-originals/<sha256>/` with `head` and
`tail` (or `full`). The item's `original_file` attribute records the
SHA-256, size, format and audio-region checksum.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
from dataclasses import dataclass
from pathlib import Path

FIELD = "original_file"
STORE_DIRNAME = "webimport-originals"


class RestoreError(Exception):
    pass


# -- splitting a file into head | audio | tail ------------------------------------

@dataclass
class Split:
    kind: str           # "mp3" | "mp4" | "flac" | "ogg"
    start: int          # audio region start
    end: int            # audio region end (exclusive)
    ogg_seq0: int | None = None  # original sequence number of the first audio page


def _synchsafe(b: bytes) -> int:
    return (b[0] << 21) | (b[1] << 14) | (b[2] << 7) | b[3]


def _id3v2_end(d: bytes, pos: int = 0) -> int:
    """End of any ID3v2 tags at `pos` (several can be stacked)."""
    while d[pos:pos + 3] == b"ID3" and len(d) >= pos + 10:
        pos += 10 + _synchsafe(d[pos + 6:pos + 10]) + (10 if d[pos + 5] & 0x10 else 0)
    return pos


def _trailer_start(d: bytes, end: int) -> int:
    """Start of trailing tags: ID3v1, Lyrics3v2, APEv2 (in that order from
    the end of the file)."""
    if end >= 128 and d[end - 128:end - 125] == b"TAG":
        end -= 128
    if end >= 15 and d[end - 9:end] == b"LYRICS200":
        end -= int(d[end - 15:end - 9]) + 15
    if end >= 32 and d[end - 32:end - 24] == b"APETAGEX":
        size = struct.unpack("<I", d[end - 20:end - 16])[0]
        flags = struct.unpack("<I", d[end - 12:end - 8])[0]
        end -= size + (32 if flags & 0x80000000 else 0)
    return end


def _split_mp3(d: bytes) -> Split | None:
    start, end = _id3v2_end(d), _trailer_start(d, len(d))
    if d[start:start + 1] != b"\xff" or start >= end:
        return None
    return Split("mp3", start, end)


def _split_mp4(d: bytes) -> Split | None:
    if d[4:8] != b"ftyp":
        return None
    pos, mdats = 0, []
    while pos + 8 <= len(d):
        size, typ = struct.unpack(">I4s", d[pos:pos + 8])
        if size == 1:
            size = struct.unpack(">Q", d[pos + 8:pos + 16])[0]
        elif size == 0:
            size = len(d) - pos
        if size < 8:
            return None
        if typ == b"mdat":
            mdats.append((pos, pos + size))
        pos += size
    if pos != len(d) or len(mdats) != 1:  # fragmented / odd layout: keep whole
        return None
    return Split("mp4", *mdats[0])


def _split_flac(d: bytes) -> Split | None:
    pos = _id3v2_end(d)
    if d[pos:pos + 4] != b"fLaC":
        return None
    pos += 4
    while True:
        if pos + 4 > len(d):
            return None
        header = d[pos]
        pos += 4 + int.from_bytes(d[pos + 1:pos + 4], "big")
        if header & 0x80:
            break
    end = _trailer_start(d, len(d))
    return Split("flac", pos, end) if pos < end else None


def _ogg_pages(d: bytes):
    """(offset, length, granule, serial, seq) for each page; None if malformed."""
    pages, pos = [], 0
    while pos < len(d):
        if d[pos:pos + 4] != b"OggS" or pos + 27 > len(d):
            return None
        nseg = d[pos + 26]
        length = 27 + nseg + sum(d[pos + 27:pos + 27 + nseg])
        granule, serial, seq = struct.unpack("<qII", d[pos + 6:pos + 22])
        pages.append((pos, length, granule, serial, seq))
        pos += length
    return pages


def _split_ogg(d: bytes) -> Split | None:
    pages = _ogg_pages(d)
    if not pages or len({p[3] for p in pages}) != 1:  # chained / multiplexed: keep whole
        return None
    # Header pages end no packet with audio, so their granule is 0 (or -1
    # for a page in the middle of a large comment packet).
    first = next((i for i, p in enumerate(pages) if p[2] not in (0, -1)), None)
    if first is None:
        return None
    return Split("ogg", pages[first][0], len(d), ogg_seq0=pages[first][4])


_SPLITTERS = {
    ".mp3": _split_mp3,
    ".m4a": _split_mp4, ".mp4": _split_mp4, ".m4b": _split_mp4, ".alac": _split_mp4, ".aac": _split_mp4,
    ".flac": _split_flac,
    ".ogg": _split_ogg, ".oga": _split_ogg, ".opus": _split_ogg,
}


def split(data: bytes, path: str) -> Split | None:
    fn = _SPLITTERS.get(os.path.splitext(path)[1].lower())
    try:
        return fn(data) if fn else None
    except (struct.error, IndexError, ValueError):
        return None


# -- Ogg page renumbering --------------------------------------------------------

def _ogg_crc_table():
    table = []
    for i in range(256):
        r = i << 24
        for _ in range(8):
            r = ((r << 1) ^ 0x04C11DB7) if r & 0x80000000 else (r << 1)
        table.append(r & 0xFFFFFFFF)
    return table


_OGG_CRC = _ogg_crc_table()


def _ogg_crc(page: bytes) -> int:
    crc = 0
    for b in page:
        crc = ((crc << 8) & 0xFFFFFFFF) ^ _OGG_CRC[((crc >> 24) & 0xFF) ^ b]
    return crc


def _renumber_ogg(region: bytes, seq0: int) -> bytes:
    pages = _ogg_pages(region)
    if pages is None:
        raise RestoreError("audio pages are malformed")
    out = bytearray()
    for i, (pos, length, _g, _s, seq) in enumerate(pages):
        page = bytearray(region[pos:pos + length])
        if seq != seq0 + i:
            page[18:22] = struct.pack("<I", seq0 + i)
            page[22:26] = b"\0\0\0\0"
            page[22:26] = struct.pack("<I", _ogg_crc(bytes(page)))
        out += page
    return bytes(out)


def _audio(data: bytes, s: Split, *, normalize_ogg_to: int | None = None) -> bytes:
    region = data[s.start:s.end]
    if s.kind == "ogg" and normalize_ogg_to is not None:
        region = _renumber_ogg(region, normalize_ogg_to)
    return region


# -- store -------------------------------------------------------------------------

def store_root() -> Path:
    from beets import config

    return Path(config["library"].as_filename()).parent / STORE_DIRNAME


def _write_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp-")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, path)


def capture(path: str | bytes) -> dict:
    """Keep what's needed to rebuild the file at `path` exactly; return the
    record for the item's `original_file` attribute."""
    path = os.fsdecode(path)
    data = Path(path).read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    folder = store_root() / sha
    s = split(data, path)
    record = {"sha256": sha, "size": len(data), "name": os.path.basename(path), "source_path": path,
              "mtime": os.stat(path).st_mtime, "mode": os.stat(path).st_mode & 0o7777}
    if s is None:
        if not (folder / "full").exists():
            _write_atomic(folder / "full", data)
        record["format"] = "full"
        return record
    if not (folder / "head").exists():
        _write_atomic(folder / "tail", data[s.end:])
        _write_atomic(folder / "head", data[:s.start])
    record.update(format=s.kind, audio_sha256=hashlib.sha256(data[s.start:s.end]).hexdigest(),
                  stored_bytes=s.start + len(data) - s.end)
    if s.ogg_seq0 is not None:
        record["ogg_seq0"] = s.ogg_seq0
    return record


def load(item) -> dict | None:
    raw = item.get(FIELD) if hasattr(item, "get") else None
    if not raw:
        return None
    try:
        rec = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return rec if isinstance(rec, dict) and rec.get("sha256") else None


def rebuild(record: dict, current_path: str | bytes) -> bytes:
    """The original file's bytes, rebuilt from the stored non-audio bytes and
    the audio in `current_path`. Raises RestoreError unless the result's
    SHA-256 matches the original."""
    folder = store_root() / record["sha256"]
    if record.get("format") == "full":
        try:
            data = (folder / "full").read_bytes()
        except OSError as exc:
            raise RestoreError(f"the stored original is missing ({exc})") from exc
    else:
        try:
            head, tail = (folder / "head").read_bytes(), (folder / "tail").read_bytes()
        except OSError as exc:
            raise RestoreError(f"the stored original is missing ({exc})") from exc
        current = Path(os.fsdecode(current_path)).read_bytes()
        s = split(current, os.fsdecode(current_path))
        if s is None or s.kind != record["format"]:
            raise RestoreError("couldn't find the audio in the current file")
        data = head + _audio(current, s, normalize_ogg_to=record.get("ogg_seq0")) + tail
    if hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise RestoreError("the rebuilt file doesn't match the original (the audio was changed after import)")
    return data


def can_restore(record: dict, current_path) -> bool:
    try:
        rebuild(record, current_path)
        return True
    except (RestoreError, OSError):
        return False


def remove(sha: str) -> None:
    shutil.rmtree(store_root() / sha, ignore_errors=True)


def referenced(lib) -> set[str]:
    """SHA-256s of every stored original still needed: items' audio files
    and albums' other folder files (lifecycle.COMPANIONS_FIELD)."""
    with lib.transaction() as tx:
        items = tx.query("SELECT value FROM item_attributes WHERE key = ?", (FIELD,))
        albums = tx.query("SELECT value FROM album_attributes WHERE key = ?", ("original_folder",))
    out = set()
    for (value,) in items:
        try:
            out.add(json.loads(value)["sha256"])
        except (TypeError, ValueError, KeyError):
            pass
    for (value,) in albums:
        try:
            out.update(f["sha256"] for f in json.loads(value)["files"])
        except (TypeError, ValueError, KeyError):
            pass
    return out


def prune(lib, keep: set[str] = frozenset()) -> int:
    """Delete stored originals no library item refers to (e.g. from reviews
    that were skipped). `keep`: SHA-256s of files in pending reviews."""
    root = store_root()
    if not root.is_dir():
        return 0
    used = referenced(lib) | set(keep)
    removed = 0
    for entry in root.iterdir():
        if entry.is_dir() and entry.name not in used:
            shutil.rmtree(entry, ignore_errors=True)
            removed += 1
    return removed


def verify_task(session, task) -> None:
    """After an import (import_task_files: tags written and art embedded),
    check every item's original can be rebuilt from the imported file. If
    not and the inbox original is still there (copy mode), keep it whole."""
    from .session import WebImportSession

    if not isinstance(session, WebImportSession):
        return
    for item in task.imported_items():
        record = load(item)
        if record is None or record.get("format") == "full" or can_restore(record, item.path):
            continue
        # The inbox original (copy mode) or the safety copy (move mode,
        # lifecycle.py).
        data = None
        safety = getattr(task, "_webimport_safety", {}).get(record["sha256"])
        for src in (record.get("source_path"), safety):
            try:
                candidate = Path(src).read_bytes() if src else None
            except OSError:
                candidate = None
            if candidate is not None and hashlib.sha256(candidate).hexdigest() == record["sha256"]:
                data = candidate
                break
        if data is not None:
            _write_atomic(store_root() / record["sha256"] / "full", data)
            record["format"] = "full"
            record.pop("audio_sha256", None)
        else:
            record["restorable"] = False
        item[FIELD] = json.dumps(record)
        item.store()

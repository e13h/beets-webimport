"""Backfill: attach store downloads in the inbox to library tracks that
were imported before originals were kept (ADR-0016).

For each audio file in an inbox folder:
- identical audio to a library track: save the file as that track's
  original (Undo import then rebuilds it byte for byte). The library file
  is untouched.
- the same recording, encoded differently (Chromaprint fingerprints
  agree, lengths within a few seconds): if the download is at least as
  good, it replaces the library file. The library's tags and embedded art
  are written onto it first, so the track looks the same in beets and
  Navidrome, and the download itself is saved as the original. The old
  library file goes to a holding folder, never deleted. If the library
  copy is better, nothing changes and the download stays in the inbox.
- no match: the file stays in the inbox for a normal import.

Matching never uses titles or tags: they differ between store files and
MusicBrainz-tagged library files (and curly vs straight apostrophes).
Fingerprints and audio checksums are cached by path, size and mtime.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from beets import context as beets_context
from mediafile import MediaFile

from . import lifecycle, originals

log = logging.getLogger("beets.webimport")

FP_SECONDS = 120  # fingerprint the first two minutes
SIM_MIN = 0.85  # same recording: measured 0.90+, different recordings far below
LENGTH_TOLERANCE = 3.0  # seconds
EQUAL_BITRATE_BAND = 0.1  # within 10%: same quality
LOSSLESS = {"FLAC", "ALAC", "WAV", "AIFF", "APE", "WavPack", "TrueAudio"}
PROPERTY_FIELDS = ("length", "bitrate", "bitrate_mode", "format", "samplerate", "bitdepth",
                   "channels", "encoder_info", "encoder_settings")
# Loudness describes the encoding, not the recording: the new file's own
# values (e.g. iTunes Sound Check) are kept, and the library's dropped.
GAIN_FIELDS = ("rg_track_gain", "rg_track_peak", "rg_album_gain", "rg_album_peak",
               "r128_track_gain", "r128_album_gain")
STALE_FLEX = ("acoustid_fingerprint",)
REPLACED_DIRNAME = "webimport-replaced"


# -- fingerprints ------------------------------------------------------------------------

def fpcalc_path() -> str | None:
    return os.environ.get("FPCALC") or shutil.which("fpcalc")


def fingerprint(path: Path) -> list[int] | None:
    exe = fpcalc_path()
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-raw", "-length", str(FP_SECONDS), str(path)],
                             capture_output=True, text=True, timeout=120).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines():
        if line.startswith("FINGERPRINT="):
            try:
                return [int(x) & 0xFFFFFFFF for x in line[12:].split(",") if x]
            except ValueError:
                return None
    return None


def similarity(a: list[int] | None, b: list[int] | None, max_offset: int = 8) -> float:
    """Share of matching fingerprint bits at the best small time offset."""
    if not a or not b:
        return 0.0
    best = 0.0
    for off in range(-max_offset, max_offset + 1):
        lo, hi = max(0, -off), min(len(a), len(b) - off)
        if hi - lo < 50:
            continue
        diff = sum((a[i] ^ b[i + off]).bit_count() for i in range(lo, hi))
        best = max(best, 1 - diff / (32 * (hi - lo)))
    return best


class Cache:
    """Audio checksums and fingerprints by (path, size, mtime)."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute("create table if not exists files (path text primary key, size int, mtime int,"
                       " audio_sha text, fp blob)")

    def _db(self):
        return sqlite3.connect(self.path, timeout=30)

    def _key(self, p: Path):
        st = p.stat()
        return str(p), st.st_size, st.st_mtime_ns

    def _get(self, p: Path, col: str):
        key = self._key(p)
        with self._lock, self._db() as db:
            row = db.execute(f"select {col} from files where path=? and size=? and mtime=?", key).fetchone()
        return key, (row[0] if row else None)

    def _put(self, key, col: str, value) -> None:
        with self._lock, self._db() as db:
            db.execute("insert into files (path, size, mtime) values (?,?,?) on conflict(path) do update"
                       " set size=excluded.size, mtime=excluded.mtime,"
                       " audio_sha=case when files.size=excluded.size and files.mtime=excluded.mtime"
                       " then files.audio_sha end,"
                       " fp=case when files.size=excluded.size and files.mtime=excluded.mtime"
                       " then files.fp end", key)
            db.execute(f"update files set {col}=? where path=?", (value, key[0]))

    def audio_sha(self, p: Path) -> str | None:
        key, val = self._get(p, "audio_sha")
        if val:
            return val
        data = p.read_bytes()
        s = originals.split(data, str(p))
        val = hashlib.sha256(data[s.start:s.end] if s else data).hexdigest()
        self._put(key, "audio_sha", val)
        return val

    def fingerprint(self, p: Path) -> list[int] | None:
        key, val = self._get(p, "fp")
        if val is not None:
            return json.loads(val) or None
        fp = fingerprint(p)
        self._put(key, "fp", json.dumps(fp or []))
        return fp


# -- quality ---------------------------------------------------------------------------

@dataclass
class Quality:
    format: str
    bitrate: int
    samplerate: int
    bitdepth: int
    length: float

    @property
    def lossless(self) -> bool:
        return self.format in LOSSLESS

    def label(self) -> str:
        if self.lossless:
            bits = f"{self.bitdepth}-bit/" if self.bitdepth else ""
            return f"{self.format} {bits}{self.samplerate / 1000:g} kHz"
        return f"{self.format} {round(self.bitrate / 1000)} kbps"


def quality_of_file(p: Path) -> Quality | None:
    try:
        m = MediaFile(str(p))
    except Exception:  # noqa: BLE001 -- unreadable file: not audio we can use
        return None
    return Quality(m.format or "", int(m.bitrate or 0), int(m.samplerate or 0), int(m.bitdepth or 0),
                   float(m.length or 0))


def quality_of_item(item) -> Quality:
    return Quality(item.format or "", int(item.bitrate or 0), int(item.samplerate or 0),
                   int(item.bitdepth or 0), float(item.length or 0))


def compare(download: Quality, current: Quality) -> str:
    """'better', 'equal' or 'worse': the download relative to the library."""
    if download.lossless != current.lossless:
        return "better" if download.lossless else "worse"
    if download.lossless:
        a, b = (download.bitdepth, download.samplerate), (current.bitdepth, current.samplerate)
        return "better" if a > b else "worse" if a < b else "equal"
    if not current.bitrate or not download.bitrate:
        return "equal"
    ratio = download.bitrate / current.bitrate
    if ratio > 1 + EQUAL_BITRATE_BAND:
        return "better"
    if ratio < 1 - EQUAL_BITRATE_BAND:
        return "worse"
    return "equal"


# -- matching ------------------------------------------------------------------------------

@dataclass
class Track:
    path: str
    action: str  # attach | replace | keep_library | already_saved | duplicate | new | unreadable
    item_ids: list[int] = field(default_factory=list)
    album_id: int | None = None
    album: str = ""
    title: str = ""  # the library track's title
    how: str = ""  # identical | same recording
    similarity: float | None = None
    download: str = ""
    library: str = ""
    note: str = ""


@dataclass
class FolderResult:
    path: str
    tracks: list[Track]

    def counts(self) -> dict:
        out: dict[str, int] = {}
        for t in self.tracks:
            out[t.action] = out.get(t.action, 0) + 1
        return out

    def actionable(self) -> bool:
        return any(t.action in ("attach", "replace") for t in self.tracks)

    def as_json(self) -> dict:
        albums: dict[int, str] = {}
        for t in self.tracks:
            if t.album_id is not None:
                albums[t.album_id] = t.album
        return {"path": self.path, "counts": self.counts(), "actionable": self.actionable(),
                "albums": [{"id": k, "album": v} for k, v in albums.items()],
                "tracks": [asdict(t) for t in self.tracks]}


class LibraryIndex:
    """The library's tracks by audio checksum and by length."""

    def __init__(self, lib, cache: Cache, progress=None):
        self.lib, self.cache = lib, cache
        self.items = {}
        self.by_sha: dict[str, list] = {}
        self.by_length: list = []
        items = list(lib.items())
        for n, item in enumerate(items):
            if progress:
                progress(n, len(items), "Reading the library")
            p = Path(os.fsdecode(item.path))
            try:
                sha = cache.audio_sha(p)
            except OSError:
                continue
            self.items[item.id] = item
            self.by_sha.setdefault(sha, []).append(item)
            self.by_length.append((float(item.length or 0), item))
        self.by_length.sort(key=lambda x: x[0])

    def near_length(self, length: float) -> list:
        return [i for (l, i) in self.by_length if abs(l - length) <= LENGTH_TOLERANCE]


def _album_name(lib, item) -> tuple[int | None, str]:
    if not item.album_id:
        return None, f"{item.artist} – {item.title} (single track)"
    a = lib.get_album(item.album_id)
    return item.album_id, (f"{a.albumartist} – {a.album}" if a else item.album)


def _match_file(lib, index: LibraryIndex, cache: Cache, p: Path) -> list[tuple[Track, list]]:
    """Candidate decisions for one inbox file, best first: (track, items)."""
    q = quality_of_file(p)
    if q is None:
        return [(Track(str(p), "unreadable", note="couldn't read this file's audio"), [])]
    sha = cache.audio_sha(p)
    found = []
    for item in index.by_sha.get(sha, []):
        found.append(("identical", 1.0, item))
    if not found:
        cands = index.near_length(q.length)
        fp = cache.fingerprint(p) if cands else None
        if fp:
            for item in cands:
                sim = similarity(fp, cache.fingerprint(Path(os.fsdecode(item.path))))
                if sim >= SIM_MIN:
                    found.append(("same recording", round(sim, 3), item))
    if not found:
        return [(Track(str(p), "new", download=q.label()), [])]
    found.sort(key=lambda x: -x[1])
    out = []
    for how, sim, item in found:
        lq = quality_of_item(item)
        album_id, album = _album_name(lib, item)
        t = Track(str(p), "", [item.id], album_id, album, item.title, how,
                  None if how == "identical" else sim, q.label(), lq.label())
        has_original = originals.load(item) is not None
        if how == "identical":
            t.action = "already_saved" if has_original else "attach"
        else:
            verdict = compare(q, lq)
            if verdict == "worse":
                t.action, t.note = "keep_library", "the library copy is better quality"
            elif has_original:
                t.action, t.note = "already_saved", "this track already has a saved original"
            else:
                t.action = "replace"
                t.note = "better quality" if verdict == "better" else "same quality: the library gets the purchased file"
        out.append((t, [item]))
    return out


def analyze(lib, files: list[Path], cache: Cache, index: LibraryIndex, progress=None) -> list[Track]:
    """Decide each file. A library track is claimed by at most one file:
    identical first, then the best quality, then the closest match."""
    decisions = []
    for n, p in enumerate(files):
        if progress:
            progress(n, len(files), "Matching inbox files")
        try:
            decisions.append(_match_file(lib, index, cache, p))
        except OSError as exc:
            decisions.append([(Track(str(p), "unreadable", note=str(exc)), [])])
    rank = {"attach": 0, "replace": 1}
    claims: dict[int, tuple] = {}
    for di, options in enumerate(decisions):
        for oi, (t, items) in enumerate(options):
            if t.action not in rank:
                continue
            key = (rank[t.action], -(t.similarity or 1.0))
            for item in items:
                if item.id not in claims or key < claims[item.id][0]:
                    claims[item.id] = (key, di, oi)
    out = []
    for di, options in enumerate(decisions):
        first = options[0][0]
        mine = [(oi, t, items) for oi, (t, items) in enumerate(options) if t.action in rank
                and all(claims.get(i.id, (None, di, oi))[1:] == (di, oi) for i in items)]
        if mine:
            # All library tracks this file is the best match for (e.g. the
            # same song on an album and on a single).
            t = mine[0][1]
            t.item_ids = [i.id for _, _, items in mine for i in items]
            out.append(t)
        elif first.action in rank:
            first.action, first.note = "duplicate", "another inbox file matches this library track better"
            out.append(first)
        else:
            out.append(first)
    return out


def inbox_cards(root: Path) -> list[Path]:
    """The folders the Inbox tab shows (top level; staging bins)."""
    cards = []
    if not root.is_dir():
        return cards
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.name.startswith("."):
            continue
        if sub.name == "_grouped":
            cards += [b for g in sorted(sub.iterdir()) if g.is_dir() for b in sorted(g.iterdir()) if b.is_dir()]
        else:
            cards.append(sub)
    return cards


# -- applying ------------------------------------------------------------------------------

def replaced_root() -> Path:
    return originals.store_root().parent / REPLACED_DIRNAME


class ApplyError(Exception):
    pass


def _copy_art(src_file: Path, dst_file: Path) -> None:
    try:
        images = MediaFile(str(src_file)).images
    except Exception:  # noqa: BLE001
        return
    if images:
        mf = MediaFile(str(dst_file))
        mf.images = images
        mf.save()


def replace_item(lib, item, download: Path, record: dict, holding: Path) -> str:
    """Swap the library file for `download`, carrying over the library's
    tags and embedded art. The old file is copied to `holding` first.
    Returns the new library path."""
    old = Path(os.fsdecode(item.path))
    libdir = Path(os.fsdecode(lib.directory))
    final = old.with_suffix(download.suffix.lower())
    if final != old and final.exists():
        raise ApplyError(f"{final.name} already exists next to the library file")
    tmp = old.parent / f".webimport-replace-{uuid.uuid4().hex[:8]}{download.suffix.lower()}"
    shutil.copy2(download, tmp)
    try:
        mf = MediaFile(str(tmp))
        props = {f: getattr(mf, f, None) for f in PROPERTY_FIELDS}
        for f in GAIN_FIELDS:
            item[f] = getattr(mf, f, None)
        # Library tags onto the new file (the download's other tags, e.g.
        # purchase info, stay, as on a normal import).
        item.write(path=os.fsencode(str(tmp)))
        _copy_art(old, tmp)
        rel = old.relative_to(libdir) if old.is_relative_to(libdir) else Path(old.name)
        keep = holding / rel
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old, keep)
        os.replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        item.load()
        raise
    if final != old:
        old.unlink(missing_ok=True)
    for f, v in props.items():
        if v is not None:
            item[f] = v
    for f in STALE_FLEX:
        if f in item:
            del item[f]
    item.path = os.fsencode(str(final))
    item.mtime = item.current_mtime()
    item[originals.FIELD] = json.dumps(record)
    item.store()
    return str(final)


def _record_for(src: Path, current: Path) -> dict:
    rec = originals.capture(src)
    if rec["format"] != "full" and not originals.can_restore(rec, str(current)):
        originals._write_atomic(originals.store_root() / rec["sha256"] / "full", src.read_bytes())
        rec["format"] = "full"
    return rec


def apply_folder(lib, card: Path, root: Path, cache: Cache, index: LibraryIndex) -> dict:
    """Carry out the decisions for one inbox card. Re-analyses first, so it
    acts on the files as they are now."""
    files = lifecycle._audio_files(card)
    tracks = analyze(lib, files, cache, index)
    holding = replaced_root() / time.strftime("%Y%m%d-%H%M%S")
    done = {"attached": 0, "replaced": 0, "left": 0, "errors": [], "albums": set()}
    used: dict[str, list[int]] = {}  # inbox file -> album ids
    for t in tracks:
        if t.action not in ("attach", "replace"):
            done["left"] += 1
            continue
        src = Path(t.path)
        items = [lib.get_item(i) for i in t.item_ids]
        items = [i for i in items if i is not None]
        try:
            if t.action == "attach":
                rec = _record_for(src, Path(os.fsdecode(items[0].path)))
                for item in items:
                    if not originals.can_restore(rec, item.path) and rec["format"] != "full":
                        raise ApplyError("the original can't be rebuilt from the library file")
                    item[originals.FIELD] = json.dumps(rec)
                    item.store()
                done["attached"] += len(items)
            else:
                rec = originals.capture(src)
                for item in items:
                    new_path = replace_item(lib, item, src, rec, holding)
                    if rec["format"] != "full" and not originals.can_restore(rec, new_path):
                        raise ApplyError("the download can't be rebuilt from the new library file")
                done["replaced"] += len(items)
        except Exception as exc:  # noqa: BLE001 -- report and keep the download
            log.exception("webimport: backfill of %s failed", src)
            done["errors"].append(f"{src.name}: {exc}")
            continue
        used[str(src)] = [i.album_id for i in items]
        done["albums"].update(i.album_id for i in items if i.album_id)
        src.unlink(missing_ok=True)

    _take_companions(lib, files, used)
    lifecycle._prune(card, root)
    done["albums"] = sorted(done["albums"])
    return done


def _take_companions(lib, files: list[Path], used: dict[str, list[int]]) -> None:
    """When all the audio under a folder went to one album, keep the
    folder's other files (booklets, cover.jpg) with that album, as an
    import does. Mixed folders keep theirs."""
    by_album: dict[int, list[Path]] = {}
    for f, album_ids in used.items():
        if len(set(album_ids)) == 1 and album_ids[0]:
            by_album.setdefault(album_ids[0], []).append(Path(f))
    for album_id, fs in by_album.items():
        d = Path(os.path.commonpath([f.parent for f in fs]))
        if not all(set(used.get(str(f), [None])) == {album_id} for f in files if f.is_relative_to(d)):
            continue
        if not lifecycle.companion_files(d):
            continue
        album = lib.get_album(album_id)
        if album is None:
            continue
        rec = lifecycle.capture_companions(d)
        lifecycle._merge_companions(album, rec)
        lifecycle._remove_companions(rec)


# -- job ------------------------------------------------------------------------------------

class Backfill:
    """One background job at a time: a scan of the whole inbox, or applying
    it to some cards. The UI polls `status()`."""

    def __init__(self, lib, root: Path, cache_path: Path, apply_lock: threading.Lock,
                 thread_init=None):
        self.lib, self.root = lib, root
        self.cache = Cache(cache_path)
        self.apply_lock = apply_lock
        self.thread_init = thread_init
        self._guard = threading.Lock()
        self.state = {"running": False, "kind": None, "phase": "", "done": 0, "total": 0,
                      "error": None, "scanned_at": None, "last_apply": None}
        self.results: dict[str, dict] = {}

    def status(self) -> dict:
        with self._guard:
            return {**self.state, "results": dict(self.results), "fpcalc": bool(fpcalc_path())}

    def _progress(self, done, total, phase):
        with self._guard:
            self.state.update(done=done, total=total, phase=phase)

    def _start(self, kind: str, fn) -> bool:
        with self._guard:
            if self.state["running"]:
                return False
            self.state.update(running=True, kind=kind, phase="Starting", done=0, total=0, error=None)

        def run():
            # Library paths resolve per thread in beets 2.x.
            beets_context.set_music_dir(self.lib.directory)
            if self.thread_init:
                self.thread_init()
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                log.exception("webimport: backfill %s failed", kind)
                with self._guard:
                    self.state["error"] = str(exc)
            finally:
                with self._guard:
                    self.state["running"] = False

        threading.Thread(target=run, name=f"webimport-backfill-{kind}", daemon=True).start()
        return True

    def scan(self) -> bool:
        def work():
            index = LibraryIndex(self.lib, self.cache, self._progress)
            cards = inbox_cards(self.root)
            files = [(c, f) for c in cards for f in lifecycle._audio_files(c)]
            tracks = analyze(self.lib, [f for _, f in files], self.cache, index, self._progress)
            results: dict[str, list] = {str(c): [] for c in cards}
            for (c, _), t in zip(files, tracks):
                results[str(c)].append(t)
            with self._guard:
                self.results = {k: FolderResult(k, v).as_json() for k, v in results.items() if v}
                self.state["scanned_at"] = time.time()
        return self._start("scan", work)

    def apply(self, cards: list[str]) -> bool:
        def work():
            summary = {"attached": 0, "replaced": 0, "left": 0, "errors": [], "albums": []}
            for n, c in enumerate(cards):
                self._progress(n, len(cards), "Attaching to the library")
                card = Path(c).resolve()
                if not card.is_relative_to(self.root.resolve()) or card == self.root.resolve() or not card.is_dir():
                    continue
                with self.apply_lock:
                    # Fresh index per folder: replacing files changes it
                    # (checksums are cached, so this is quick).
                    index = LibraryIndex(self.lib, self.cache)
                    r = apply_folder(self.lib, card, self.root, self.cache, index)
                    index = LibraryIndex(self.lib, self.cache)
                for k in ("attached", "replaced", "left"):
                    summary[k] += r[k]
                summary["errors"] += r["errors"]
                summary["albums"] += r["albums"]
                remaining = lifecycle._audio_files(card) if card.is_dir() else []
                tracks = analyze(self.lib, remaining, self.cache, index) if remaining else []
                with self._guard:
                    if tracks:
                        self.results[c] = FolderResult(c, tracks).as_json()
                    else:
                        self.results.pop(c, None)
            with self._guard:
                self.state["last_apply"] = summary
        return self._start("apply", work)

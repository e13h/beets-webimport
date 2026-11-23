"""Album art choice for inbox imports.

webimport owns import-time album art (the homelab config sets
`fetchart: auto: no`). The review shows what the files have now and the
options for after import:

- "keep":      leave the files' embedded art as it is (nothing is written)
- "candidate": the selected release's Cover Art Archive front, falling
               back to its release group's, as fetchart would
- "itunes":    the iTunes Store artwork, for iTunes purchases
- "folder":    an image file in the inbox folder

The server holds the bytes of every option it shows (content-addressed,
in memory), so previews, sizes, and what gets embedded are the same
image. On apply, the chosen image becomes the album's art via
`Album.set_art`, which fires `art_set`; embedart embeds it and (with
`remove_art_file`) deletes the copy. The inbox folder is never modified.
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import threading
import time
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path

import requests

from . import coverart, itunes
from .coverart import image_info

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
FOLDER_IMAGE_NAMES = ("cover", "front", "folder", "album", "art")
EXT_FOR_MIME = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}
DOWNLOAD_RETRIES = 3
DOWNLOAD_TIMEOUT = 20
HEADERS = {"User-Agent": "beets-webimport/0.1"}

# -- image store: content-addressed, size-capped LRU ---------------------------

STORE_MAX_BYTES = 200 * 1024 * 1024
_store: OrderedDict[str, bytes] = OrderedDict()
_store_bytes = 0
_store_lock = threading.Lock()


def put(data: bytes) -> str:
    """Keep `data` and return its key (SHA-1 of the bytes)."""
    global _store_bytes
    key = hashlib.sha1(data).hexdigest()
    with _store_lock:
        if key in _store:
            _store.move_to_end(key)
            return key
        _store[key] = data
        _store_bytes += len(data)
        while _store_bytes > STORE_MAX_BYTES and len(_store) > 1:
            _, old = _store.popitem(last=False)
            _store_bytes -= len(old)
    return key


def get(key: str) -> bytes | None:
    with _store_lock:
        data = _store.get(key)
        if data is not None:
            _store.move_to_end(key)
        return data


def describe(data: bytes) -> dict:
    """image_info plus the URL the browser loads it from."""
    key = put(data)
    return {**image_info(data), "key": key, "image_url": f"/api/art/{key}"}


def clear() -> None:
    global _store_bytes
    with _store_lock:
        _store.clear()
        _store_bytes = 0
    with _caa_lock:
        _caa_results.clear()


# -- art in the inbox folder ------------------------------------------------------

def folder_image(folder: Path) -> Path | None:
    """The image file in the folder that looks most like a cover: names
    containing cover/front/folder/album/art first, else any image."""
    folder = Path(folder)
    try:
        names = sorted(n for n in os.listdir(folder)
                       if not n.startswith(".") and n.lower().endswith(IMAGE_EXTS)
                       and (folder / n).is_file())
    except OSError:
        return None
    if not names:
        return None

    def rank(name):
        stem = os.path.splitext(name.lower())[0]
        hits = [i for i, word in enumerate(FOLDER_IMAGE_NAMES) if word in stem]
        return (min(hits) if hits else len(FOLDER_IMAGE_NAMES), name)

    return folder / min(names, key=rank)


def _audio_art(folder: Path) -> list[tuple[str, bytes | None]]:
    from mediafile import MediaFile

    found = []
    for name in sorted(os.listdir(folder)):
        path = folder / name
        if name.startswith(".") or name.lower().endswith(IMAGE_EXTS) or not path.is_file():
            continue
        try:
            mf = MediaFile(str(path))
        except Exception:  # noqa: BLE001 -- not an audio file
            continue
        try:
            art = mf.art
        except Exception:  # noqa: BLE001
            art = None
        found.append((name, art))
    return found


_embedded_cache: dict[tuple, dict | None] = {}


def embedded_art(folder: Path) -> dict | None:
    """The art embedded in the folder's audio files: the most common image
    (`data`) plus how many tracks carry it. None if no file has art.
    Cached on the folder's file names and mtimes."""
    folder = Path(folder)
    try:
        key = (str(folder), tuple(sorted((e.name, e.stat().st_mtime) for e in os.scandir(folder))))
    except OSError:
        return None
    if key in _embedded_cache:
        return _embedded_cache[key]
    tracks = _audio_art(folder)
    counts = Counter(hashlib.sha1(a).hexdigest() for _, a in tracks if a)
    images = {hashlib.sha1(a).hexdigest(): a for _, a in tracks if a}
    result = None
    if counts:
        sha, count = counts.most_common(1)[0]
        result = {"data": images[sha], "tracks_with_art": sum(counts.values()),
                  "tracks_with_this_art": count, "tracks_total": len(tracks),
                  "distinct_images": len(counts)}
    _embedded_cache.clear()  # one entry is enough: the folder under review
    _embedded_cache[key] = result
    return result


@dataclass
class ArtSource:
    """Where a review's art options come from: the album's folder (its
    files' art, "keep"), whether an image file in it is an option (inbox
    folders only: in the library that's beets' own copy of the current
    art), and the iTunes IDs, if the album is an iTunes purchase."""
    folder: Path
    itunes_ids: dict | None
    folder_images: bool = True

    @classmethod
    def inbox(cls, folder: Path) -> "ArtSource":
        return cls(Path(folder), itunes.detect_ids(folder))

    @classmethod
    def library(cls, folder: Path, items) -> "ArtSource":
        """A reimport: the IDs may survive only in the stored originals."""
        return cls(Path(folder), itunes.detect_ids_for_items(items), folder_images=False)


def options(source: ArtSource) -> dict:
    """Art the files already have ("keep"), an image file in the folder,
    and iTunes Store art for iTunes purchases. Each present option is
    described (size, image_url); absent ones are None."""
    folder = source.folder
    out: dict = {"keep": None, "folder": None, "itunes": None}
    emb = embedded_art(folder)
    if emb:
        out["keep"] = {**describe(emb["data"]), **{k: v for k, v in emb.items() if k != "data"}}
    img = folder_image(folder) if source.folder_images else None
    if img is not None:
        try:
            out["folder"] = {**describe(img.read_bytes()), "name": img.name}
        except OSError:
            pass
    ids = source.itunes_ids
    if ids is not None:
        info, data = itunes.lookup_album(ids["collection_id"], ids["country"])
        meta = {k: info.get(k) for k in ("collection_id", "collection_name", "artist", "store_url", "error")}
        out["itunes"] = {**describe(data), **meta} if data else meta
    return out


def inbox_options(folder: Path) -> dict:
    return options(ArtSource.inbox(folder))


# -- Cover Art Archive ------------------------------------------------------------

CAA_TTL = 3600.0
_caa_results: dict[tuple[str, str], tuple[float, dict]] = {}
_caa_lock = threading.Lock()
_inflight: dict[tuple[str, str], threading.Lock] = {}


def _download(url: str) -> bytes:
    """GET with retries on connection errors and 5xx (the Internet Archive
    returns transient 502s regularly)."""
    last: Exception | None = None
    for attempt in range(DOWNLOAD_RETRIES):
        try:
            resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT, headers=HEADERS)
            if resp.status_code < 500:
                resp.raise_for_status()
                return resp.content
            last = requests.HTTPError(f"{resp.status_code} from {url}")
        except requests.HTTPError:
            raise
        except requests.RequestException as exc:
            last = exc
        time.sleep(0.5 * (attempt + 1))
    raise last or RuntimeError("download failed")


def _caa_one(mbid: str, kind: str) -> dict:
    """{"state": "ok", "data"} | {"state": "none"} | {"state": "unavailable"}
    for one release or release group. One download per (kind, mbid), shared
    by concurrent callers; "unavailable" is not cached."""
    key = (kind, mbid)
    with _caa_lock:
        hit = _caa_results.get(key)
        if hit and time.monotonic() - hit[0] < CAA_TTL:
            return hit[1]
        flight = _inflight.setdefault(key, threading.Lock())
    with flight:
        with _caa_lock:  # another caller may have finished meanwhile
            hit = _caa_results.get(key)
            if hit and time.monotonic() - hit[0] < CAA_TTL:
                return hit[1]
        images = coverart._caa_front_images(mbid, kind)
        if images is None:
            return {"state": "unavailable"}
        if not images:
            result = {"state": "none"}
        else:
            try:
                result = {"state": "ok", "data": _download(images[0]["image"])}
            except Exception:  # noqa: BLE001 -- transient; retried on next request
                return {"state": "unavailable"}
        with _caa_lock:
            _caa_results[key] = (time.monotonic(), result)
        return result


def candidate_art(release_id: str | None, releasegroup_id: str | None) -> dict:
    """The selected release's CAA front image, else its release group's
    (fetchart's coverart order). {"state": "ok", "source", "data", plus
    image_info} or
    {"state": "none" | "unavailable"}."""
    unavailable = False
    for kind, mbid in (("release", release_id), ("releasegroup", releasegroup_id)):
        if not mbid:
            continue
        r = _caa_one(mbid, kind)
        if r["state"] == "ok":
            return {**r, "source": kind, **image_info(r["data"])}
        unavailable = unavailable or r["state"] == "unavailable"
    return {"state": "unavailable" if unavailable else "none"}


# -- choosing -------------------------------------------------------------------

def _area(opt) -> int:
    return (opt.get("width") or 0) * (opt.get("height") or 0) if opt else 0


def default_choice(options: dict, candidate: dict | None) -> str:
    """The choice the review preselects (and the server applies when a
    decision arrives without one). Mirrored in app.js.

    An image in the folder was put there deliberately; iTunes art is the
    store's original; otherwise the larger of the files' own art and the
    release's Cover Art Archive art (keep the files' art if CAA has none)."""
    if options.get("folder"):
        return "folder"
    itunes_opt = options.get("itunes")
    if itunes_opt and itunes_opt.get("image_url"):
        return "itunes"
    keep = options.get("keep")
    if candidate and candidate.get("state") == "ok" and (not keep or _area(candidate) > _area(keep)):
        return "candidate"
    return "keep"


def chosen_image(choice: str, source: ArtSource, candidate_ids: tuple | None) -> bytes | None:
    """The bytes to set as album art for `choice`; None for "keep".
    Raises ValueError if the choice isn't available."""
    if choice == "keep":
        return None
    if choice == "candidate":
        if not candidate_ids:
            raise ValueError("Cover Art Archive art needs a selected release.")
        r = candidate_art(*candidate_ids)
        if r["state"] != "ok":
            raise ValueError("The Cover Art Archive has no art for this release"
                             if r["state"] == "none" else "The Cover Art Archive couldn't be reached.")
        return r["data"]
    if choice == "itunes":
        ids = source.itunes_ids
        if ids is None:
            raise ValueError("Not an iTunes purchase.")
        info, data = itunes.lookup_album(ids["collection_id"], ids["country"])
        if not data:
            raise ValueError(info.get("error") or "No iTunes artwork available.")
        return data
    if choice == "folder":
        img = folder_image(source.folder) if source.folder_images else None
        if img is None:
            raise ValueError("No image file in the folder.")
        return img.read_bytes()
    raise ValueError(f"Unknown art choice {choice!r}")


def on_import_task_files(session, task):
    """Set the chosen image as the imported album's art (import_task_files
    runs in the serialized apply phase, after files are copied). art_set
    makes embedart embed it."""
    from .session import WebImportSession

    if not isinstance(session, WebImportSession):
        return
    data, session.pending_art = session.pending_art, None
    if not data or not getattr(task, "is_album", False) or task.album is None:
        return
    ext = EXT_FOR_MIME.get(coverart._detect_mime_type(data), ".jpg")
    fd, tmp = tempfile.mkstemp(suffix=ext, prefix="webimport-art-")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        task.album.set_art(os.fsencode(tmp), copy=True)
        task.album.store()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass

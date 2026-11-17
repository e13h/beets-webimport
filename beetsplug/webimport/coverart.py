"""Cover art helpers: image metadata (size, type) and Cover Art Archive
lookups. Cover Art Archive lookups use the JSON API, as fetchart does
(picking the first Front image). Choosing and applying import-time art is
in artchoice.py; library art (explorer, thumbnails) uses get_album_art_*.
"""
from __future__ import annotations

import io
import threading
import time
from pathlib import Path

import requests

try:
    from PIL import Image

    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False



def _detect_mime_type(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    elif data.startswith(b"GIF87a") or data.startswith(b"GIF89a"):
        return "image/gif"
    elif data.startswith(b"RIFF") and len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def get_album_art_data(
    album,
    cache_dir: Path | None = None,
    thumb: bool = False,
    size: tuple[int, int] = (200, 200),
) -> tuple[bytes | None, str]:
    """Retrieves art data for an album (from album.artpath or extracted embedded art),
    caching resized thumbnails (200x200) when thumb=True.
    Returns (image_bytes, mime_type) or (None, '').
    """
    from beets.util import syspath

    raw_bytes: bytes | None = None
    mtime: int = 0

    if album.artpath:
        art_path = Path(syspath(album.artpath))
        if art_path.exists() and art_path.is_file():
            try:
                raw_bytes = art_path.read_bytes()
                mtime = int(art_path.stat().st_mtime_ns)
            except OSError:
                raw_bytes = None

    if raw_bytes is None:
        # Fall back to extracting embedded art from tracks
        for item in album.items():
            try:
                item_path = Path(syspath(item.path))
                if item_path.exists():
                    import mediafile

                    mf = mediafile.MediaFile(str(item_path))
                    if mf.art:
                        raw_bytes = mf.art
                        mtime = int(item_path.stat().st_mtime_ns)
                        break
            except Exception:
                continue

    if raw_bytes is None or len(raw_bytes) == 0:
        return None, ""

    mime_type = _detect_mime_type(raw_bytes)

    if not thumb:
        return raw_bytes, mime_type

    # Thumbnail generation & caching
    if cache_dir is not None:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"thumb_album_{album.id}_{mtime}_{size[0]}x{size[1]}.jpg"
        if cache_file.exists():
            try:
                return cache_file.read_bytes(), "image/jpeg"
            except OSError:
                pass

    thumb_bytes = raw_bytes
    thumb_mime = mime_type

    if HAVE_PIL:
        try:
            with Image.open(io.BytesIO(raw_bytes)) as im:
                if im.mode in ("RGBA", "LA", "P"):
                    im = im.convert("RGB")
                im.thumbnail(size)
                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=85)
                thumb_bytes = buf.getvalue()
                thumb_mime = "image/jpeg"
        except Exception:
            thumb_bytes = raw_bytes
            thumb_mime = mime_type

    if cache_dir is not None:
        try:
            # Clean up older cached thumbnails for this album
            for old_f in cache_dir.glob(f"thumb_album_{album.id}_*"):
                try:
                    old_f.unlink()
                except OSError:
                    pass
            cache_file = cache_dir / f"thumb_album_{album.id}_{mtime}_{size[0]}x{size[1]}.jpg"
            cache_file.write_bytes(thumb_bytes)
        except OSError:
            pass

    return thumb_bytes, thumb_mime


def _image_dims(data: bytes) -> tuple[int, int] | None:
    if HAVE_PIL:
        try:
            with Image.open(io.BytesIO(data)) as im:
                return im.width, im.height
        except Exception:
            pass
    return _header_dims(data)


def _header_dims(data: bytes) -> tuple[int, int] | None:
    """Image dimensions from the file header alone (JPEG/PNG/GIF/WebP), so
    the explorer can report art size without Pillow installed."""
    import struct

    try:
        if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
            return struct.unpack(">II", data[16:24])
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return struct.unpack("<HH", data[6:10])
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            kind = data[12:16]
            if kind == b"VP8X":
                w = int.from_bytes(data[24:27], "little") + 1
                h = int.from_bytes(data[27:30], "little") + 1
                return w, h
            if kind == b"VP8 ":
                w, h = struct.unpack("<HH", data[26:30])
                return w & 0x3FFF, h & 0x3FFF
            if kind == b"VP8L":
                b = int.from_bytes(data[21:25], "little")
                return (b & 0x3FFF) + 1, ((b >> 14) & 0x3FFF) + 1
        if data.startswith(b"\xff\xd8"):
            # Walk JPEG segments to the first start-of-frame marker.
            i = 2
            while i + 9 < len(data):
                if data[i] != 0xFF:
                    i += 1
                    continue
                marker = data[i + 1]
                if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
                    i += 1 if marker == 0xFF else 2
                    continue
                (length,) = struct.unpack(">H", data[i + 2:i + 4])
                if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                              0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                    h, w = struct.unpack(">HH", data[i + 5:i + 9])
                    return w, h
                i += 2 + length
    except (struct.error, IndexError):
        pass
    return None


def image_info(data: bytes) -> dict:
    """Size/format details for an image, for display. Width/height are
    None if the header can't be parsed."""
    import hashlib

    dims = _image_dims(data)
    return {
        "width": dims[0] if dims else None,
        "height": dims[1] if dims else None,
        "bytes": len(data),
        "mime": _detect_mime_type(data),
        "sha1": hashlib.sha1(data).hexdigest(),
    }


def get_album_art_info(album) -> dict | None:
    """Where the album's art comes from (same precedence as
    get_album_art_data: art file, else the first track with embedded
    art) plus its image details. None if the album has no art."""
    from beets.util import syspath
    import mediafile

    if album.artpath:
        art_path = Path(syspath(album.artpath))
        try:
            data = art_path.read_bytes()
        except OSError:
            data = None
        if data:
            return {"source": "file", "path": str(art_path), **image_info(data)}

    for item in sorted(album.items(), key=lambda i: (i.disc or 1, i.track or 0, i.id)):
        try:
            data = mediafile.MediaFile(syspath(item.path)).art
        except Exception:
            continue
        if data:
            return {"source": "embedded", "track_id": item.id, **image_info(data)}
    return None


# Cover Art Archive is fronted by archive.org and occasionally returns
# transient 5xx (esp. via the /front redirect). Mirror fetchart's approach:
# query the JSON API and pick the Front image, retrying briefly on 5xx.
CAA_RETRIES = 2


def _caa_api_url(mbid: str, kind: str) -> str:
    # kind: "release" or "releasegroup"
    segment = "release" if kind == "release" else "release-group"
    return f"https://coverartarchive.org/{segment}/{mbid}"


# CAA lookups take 1-3s each (three redirect hops), so definitive answers (art list, or 404 = no art) are
# cached in memory per (kind, mbid). "Couldn't check" (None) is never
# cached, so a transient outage retries on the next click. Process
# lifetime only, like the rest of the plugin's state (ADR-0004).
CAA_CACHE_TTL = 3600.0
_caa_cache: dict[tuple[str, str], tuple[float, list[dict]]] = {}
_caa_cache_lock = threading.Lock()


def clear_caa_cache() -> None:
    with _caa_cache_lock:
        _caa_cache.clear()


def _caa_front_images(mbid: str, kind: str) -> list[dict] | None:
    key = (kind, mbid)
    now = time.monotonic()
    with _caa_cache_lock:
        hit = _caa_cache.get(key)
        if hit is not None and now - hit[0] < CAA_CACHE_TTL:
            return hit[1]
    images = _fetch_caa_front_images(mbid, kind)
    if images is not None:
        with _caa_cache_lock:
            _caa_cache[key] = (now, images)
    return images


def _fetch_caa_front_images(mbid: str, kind: str) -> list[dict] | None:
    """Query the CAA JSON API and return the list of Front image records
    (each a dict with "image" + "thumbnails"), newest-first as CAA orders
    them. Returns None if the release is unknown or the service is
    unreachable (so callers can distinguish "no art" from "couldn't check").
    """
    url = _caa_api_url(mbid, kind)
    for _ in range(CAA_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                timeout=5,
                headers={"User-Agent": "beets-webimport/0.1"},
            )
        except requests.RequestException:
            continue  # connection hiccup: retry, then report "couldn't check"
        if resp.status_code == 404:
            return []  # release exists in MB but has no art
        if resp.ok:
            try:
                data = resp.json()
            except ValueError:
                return None
            return [
                img for img in data.get("images", [])
                if "Front" in img.get("types", []) or img.get("front")
            ]
        # Transient upstream error (typically 502/503 from archive.org).
        if resp.status_code < 500:
            return None
    return None

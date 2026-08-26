"""Dual cover-art preview.

Per PRD: show the candidate's source art alongside what fetchart would
actually resolve/write, computed lazily (only for the currently focused
candidate).

Simplification (see README "Known simplifications"): this re-implements
fetchart's *source priority + minwidth/enforce_ratio filtering* against
your actual `fetchart:` config rather than driving the real fetchart
plugin object end-to-end, so it stays in sync with source order and
resolution rules but does not execute embedart's file write. Cover Art
Archive lookups use the same JSON API fetchart does (picking the first
Front image), so the preview matches what an import would embed. If
fetchart gains new *remote* source types you use, add them to the
source-dispatch in `resolve_candidate_art` accordingly.
"""
from __future__ import annotations

import io
from pathlib import Path

import requests

try:
    from PIL import Image

    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

COVER_FILENAMES = ("cover", "folder", "albumart", "front")
COVER_EXTS = (".jpg", ".jpeg", ".png")


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
                mtime = int(art_path.stat().st_mtime)
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
                        mtime = int(item_path.stat().st_mtime)
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


def _local_cover_file(item_dir: Path) -> Path | None:
    if not item_dir.is_dir():
        return None
    for f in item_dir.iterdir():
        if f.suffix.lower() in COVER_EXTS and f.stem.lower() in COVER_FILENAMES:
            return f
    return None


def _image_dims(data: bytes) -> tuple[int, int] | None:
    if not HAVE_PIL:
        return None
    try:
        with Image.open(io.BytesIO(data)) as im:
            return im.width, im.height
    except Exception:
        return None


def _passes_filters(data: bytes, minwidth: int, enforce_ratio) -> bool:
    dims = _image_dims(data)
    if dims is None:
        return True  # can't verify without Pillow -- don't block on it
    w, h = dims
    if minwidth and w < minwidth:
        return False
    # fetchart's enforce_ratio may be a bool or a margin string (e.g.
    # "5%"/"4px"); treat any truthy value as "must be square-ish". We
    # approximate the margin as exact-square since this is a preview.
    if enforce_ratio and w != h:
        return False
    return True


# Cover Art Archive is fronted by archive.org and occasionally returns
# transient 5xx (esp. via the /front redirect). Mirror fetchart's approach:
# query the JSON API and pick the Front image, retrying briefly on 5xx.
CAA_RETRIES = 2


def _caa_api_url(mbid: str, kind: str) -> str:
    # kind: "release" or "releasegroup"
    segment = "release" if kind == "release" else "release-group"
    return f"https://coverartarchive.org/{segment}/{mbid}"


def _caa_front_images(mbid: str, kind: str) -> list[dict] | None:
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
            return None
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


def _preview_url(img: dict) -> str:
    """Prefer a mid-size thumbnail for the preview (lighter on mobile),
    falling back to the full image."""
    thumbs = img.get("thumbnails") or {}
    return thumbs.get("500") or thumbs.get("large") or img["image"]


def _parse_source(src) -> tuple[str, str | None]:
    """fetchart `sources:` entries are either a bare source id
    (e.g. "coverart", "filesystem") or an id qualified by a matching
    criterion (e.g. "coverart:release"). confuse also parses mapping-style
    entries into (key, value) pairs. Normalize both to (name, criterion).
    """
    if isinstance(src, (list, tuple)) and len(src) == 2:
        name, criterion = src
        return str(name).strip(), str(criterion).strip()
    text = str(src).strip()
    if ":" in text:
        name, criterion = text.split(":", 1)
        return name.strip(), criterion.strip()
    return text, None


def _try_caa(mbid: str, kind: str):
    """Return (preview_url, unavailable) for the CAA front art of `mbid`.
    `preview_url` is None if there's no front art; `unavailable` is True
    only when the service couldn't be reached (transient), so callers can
    surface "couldn't check" instead of "no art"."""
    images = _caa_front_images(mbid, kind)
    if images is None:
        return None, True
    if not images:
        return None, False
    return _preview_url(images[0]), False


def resolve_candidate_art(item_dir: str, release_mbid: str | None,
                           release_group_mbid: str | None,
                           fetchart_config: dict) -> dict:
    """Returns {"source_url": ..., "resolved_url": ..., "resolved_source": ...}
    for the currently-focused candidate."""
    minwidth = fetchart_config.get("minwidth", 0)
    enforce_ratio = fetchart_config.get("enforce_ratio", False)
    # fetchart's default source order; the Cover Art Archive source id is
    # "coverart" (optionally qualified with ":release"/":releasegroup").
    sources = fetchart_config.get(
        "sources", ["filesystem", "coverart", "itunes", "amazon", "albumart"]
    )

    resolved_url = None
    resolved_source = None
    unavailable = False

    for src in sources:
        name, criterion = _parse_source(src)

        if name == "filesystem":
            local = _local_cover_file(Path(item_dir))
            if local is not None:
                try:
                    data = local.read_bytes()
                except OSError:
                    continue
                if _passes_filters(data, minwidth, enforce_ratio):
                    resolved_url = f"file://{local}"
                    resolved_source = "filesystem"
                    break

        elif name == "coverart":
            # A bare "coverart" entry means try release then releasegroup;
            # a qualified entry restricts to that one criterion.
            criteria = [criterion] if criterion else ["release", "releasegroup"]
            for crit in criteria:
                mbid = release_mbid if crit == "release" else release_group_mbid
                if not mbid:
                    continue
                url, was_unavailable = _try_caa(mbid, crit)
                unavailable = unavailable or was_unavailable
                if url:
                    resolved_url = url
                    resolved_source = f"coverart:{crit}"
                    break
            if resolved_url:
                break
        # Other remote sources (itunes, amazon, ...) are not previewed
        # here; the source-priority order is still honored, so if an
        # earlier source resolves we stop before reaching them.

    # Source-side art: the candidate's own front art on CAA (what the
    # release "comes with"), shown alongside the resolved pick.
    source_url = None
    if release_mbid:
        source_url, src_unavailable = _try_caa(release_mbid, "release")
        unavailable = unavailable or src_unavailable

    return {
        "source_url": source_url,
        "resolved_url": resolved_url,
        "resolved_source": resolved_source,
        "unavailable": unavailable,
        "match": (source_url is not None and resolved_url == source_url),
    }

"""Dual cover-art preview.

Per PRD: show the candidate's source art alongside what fetchart would
actually resolve/write, computed lazily (only for the currently focused
candidate).

Simplification (see README "Known simplifications"): this re-implements
fetchart's *source priority + minwidth/enforce_ratio filtering* against
your actual `fetchart:` config rather than driving the real fetchart
plugin object end-to-end, so it stays in sync with source order and
resolution rules but does not execute embedart's file write. If fetchart
gains new source types you use, extend `_candidate_sources` accordingly.
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


def _passes_filters(data: bytes, minwidth: int, enforce_ratio: bool) -> bool:
    dims = _image_dims(data)
    if dims is None:
        return True  # can't verify without Pillow -- don't block on it
    w, h = dims
    if minwidth and w < minwidth:
        return False
    if enforce_ratio and w != h:
        return False
    return True


def _caa_url(mbid: str, kind: str) -> str:
    # kind: "release" or "release-group"
    segment = "release" if kind == "release" else "release-group"
    return f"https://coverartarchive.org/{segment}/{mbid}/front"


def resolve_candidate_art(item_dir: str, release_mbid: str | None,
                           release_group_mbid: str | None,
                           fetchart_config: dict) -> dict:
    """Returns {"source_url": ..., "resolved_url": ..., "resolved_source": ...}
    for the currently-focused candidate."""
    minwidth = fetchart_config.get("minwidth", 0)
    enforce_ratio = fetchart_config.get("enforce_ratio", False)
    sources = fetchart_config.get("sources", ["filesystem", "coverart:release"])

    resolved_url = None
    resolved_source = None

    for src in sources:
        if src == "filesystem":
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
        elif src in ("coverart:release", "coverart: release") and release_mbid:
            url = _caa_url(release_mbid, "release")
            try:
                resp = requests.get(url, timeout=5)
                if resp.ok and _passes_filters(resp.content, minwidth, enforce_ratio):
                    resolved_url = url
                    resolved_source = "coverart:release"
                    break
            except requests.RequestException:
                pass
        elif src in ("coverart:releasegroup", "coverart: releasegroup") and release_group_mbid:
            url = _caa_url(release_group_mbid, "release-group")
            try:
                resp = requests.get(url, timeout=5)
                if resp.ok and _passes_filters(resp.content, minwidth, enforce_ratio):
                    resolved_url = url
                    resolved_source = "coverart:releasegroup"
                    break
            except requests.RequestException:
                pass

    source_url = _caa_url(release_mbid, "release") if release_mbid else None

    return {
        "source_url": source_url,
        "resolved_url": resolved_url,
        "resolved_source": resolved_source,
        "match": (source_url is not None and resolved_url == source_url),
    }

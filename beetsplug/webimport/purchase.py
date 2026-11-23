"""Store purchases: find the digital release the files were bought as.

Files bought from a download store were sold as a digital release, which
is often not among the few candidates a broad search returns
(`musicbrainz.search_limit`). For a purchase, search MusicBrainz for
digital releases of the album, keep the best two by the files' year and
track total (both are in the search results, so no extra requests), and
add them as candidates. Candidates that look like the purchased release
(Digital Media, same year as the files) are marked and listed first.

Detection: iTunes files carry a store album ID (`plID`); Amazon MP3 store
files carry an "Amazon.com Song ID: …" comment.
"""
from __future__ import annotations

import logging
import threading
from collections import Counter
from pathlib import Path

from . import itunes, mbapi

log = logging.getLogger("beets.webimport")

DIGITAL = "Digital Media"
MAX_EXTRA = 2
AMAZON_COMMENT = "Amazon.com Song ID"

_cache: dict[tuple, list[dict]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()


def detect_store(items, folder, library: bool = False) -> str | None:
    """"itunes", "amazon", or None. `library`: items already in the
    library (a reimport), whose store IDs may survive only in their stored
    originals."""
    if folder and itunes.detect_ids(Path(folder)) is not None:
        return "itunes"
    if library and itunes.detect_ids_for_items(items) is not None:
        return "itunes"
    if any(AMAZON_COMMENT in (item.get("comments") or "") for item in items):
        return "amazon"
    return None


def _most_common(values):
    values = [v for v in values if v]
    return Counter(values).most_common(1)[0][0] if values else None


def album_hints(items) -> dict:
    """What the files say about the album they came from."""
    return {
        "album": _most_common(i.get("album") for i in items),
        "artist": _most_common(i.get("albumartist") or i.get("artist") for i in items),
        "year": _most_common(i.get("year") for i in items),
        "tracktotal": _most_common(i.get("tracktotal") for i in items),
    }


def _phrase(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _search(album: str, artist: str) -> list[dict]:
    """Digital releases of `album` by `artist`: [{id, year, track_count}]."""
    key = (album.lower(), artist.lower())
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    query = f"release:{_phrase(album)} AND artist:{_phrase(artist)} AND format:{_phrase(DIGITAL)}"
    resp = mbapi.get("release", {"query": query, "limit": 25, "fmt": "json"})
    resp.raise_for_status()
    releases = []
    for r in resp.json().get("releases", []):
        date = r.get("date") or ""
        releases.append({
            "id": r["id"],
            "year": int(date[:4]) if date[:4].isdigit() else None,
            "track_count": r.get("track-count"),
        })
    with _cache_lock:
        _cache[key] = releases
    return releases


def digital_release_ids(hints: dict, exclude=(), limit: int = MAX_EXTRA) -> list[str]:
    """Up to `limit` digital releases of the files' album, best first:
    same year as the files, then closest track count, then dated ones.
    Empty if the files lack album/artist tags or MusicBrainz fails."""
    if not hints.get("album") or not hints.get("artist"):
        return []
    try:
        releases = _search(hints["album"], hints["artist"])
    except Exception:  # noqa: BLE001 -- the broad search results still stand
        log.warning("webimport: digital release search failed", exc_info=True)
        return []
    year, total = hints.get("year"), hints.get("tracktotal")

    def rank(r):
        return (
            not (year and r["year"] == year),
            abs((r["track_count"] or 0) - total) if total else 0,
            r["year"] is None,
        )

    exclude = set(exclude)
    ranked = sorted((r for r in releases if r["id"] not in exclude), key=rank)
    return [r["id"] for r in ranked[:limit]]


def looks_purchased(info, year) -> bool:
    """A candidate that looks like the release the files were bought as."""
    return bool(year) and DIGITAL in (info.media or "") and info.year == year

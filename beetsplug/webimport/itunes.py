"""iTunes art override for inbox imports.

Files bought from the iTunes Store carry their catalog IDs in MP4 atoms:
`plID` (album/collection) and `sfID` (storefront). From the collection ID,
Apple's public lookup API returns the exact artwork URL, which serves the
original upload when asked for a size at or above it.

The review offers that image as an album art choice (artchoice.py).

It also finds the matching MusicBrainz release: MusicBrainz releases
link to their Apple Music / iTunes listing, and its URL lookup returns the
release for an exact link. Editors store links in several shapes
(`music.apple.com/gb/album/<id>`, `itunes.apple.com/us/album/id<id>`, with
or without the album-name slug), so one request asks for every likely
shape at once.

Only catalog IDs and the country code are sent to Apple, and only Apple
links to MusicBrainz.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

import logging

import requests

from . import mbapi
from .coverart import image_info

log = logging.getLogger("beets")

LOOKUP_URL = "https://itunes.apple.com/lookup"
MP4_EXTS = (".m4a", ".m4p", ".m4b", ".mp4")
TIMEOUT = 10
HEADERS = {"User-Agent": "beets-webimport/0.1"}

# iTunes Store storefront IDs (the sfID atom) -> lookup `country`.
STOREFRONTS = {
    143441: "us", 143444: "gb", 143455: "ca", 143460: "au", 143461: "nz",
    143443: "de", 143442: "fr", 143450: "it", 143454: "es", 143452: "nl",
    143462: "jp", 143466: "kr", 143468: "mx", 143503: "br", 143465: "cn",
    143456: "se", 143457: "no", 143458: "dk", 143447: "fi", 143449: "ie",
    143445: "at", 143459: "ch", 143446: "be", 143467: "in",
}

# Extra stores beyond STOREFRONTS that MusicBrainz editors commonly link.
EXTRA_STORE_COUNTRIES = ("pl", "pt", "tw", "hk", "sg", "za", "ar", "cl", "co", "ru", "tr")

_cache: dict[int, tuple[dict, bytes | None]] = {}
_cache_lock = threading.Lock()
_mb_cache: dict[int, list[str]] = {}
_mb_lock = threading.Lock()


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
    with _mb_lock:
        _mb_cache.clear()


def _read_mp4_tags(path: Path) -> dict | None:
    from mutagen.mp4 import MP4

    try:
        return MP4(str(path)).tags or None
    except Exception:  # noqa: BLE001 -- unreadable/non-MP4 file: not a purchase
        return None


def _first_int(value) -> int | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def detect_ids(folder: Path) -> dict | None:
    """{"collection_id", "country"} from the first MP4 file in `folder`
    that carries an iTunes collection ID, else None."""
    folder = Path(folder)
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return None
    for name in names:
        if not name.lower().endswith(MP4_EXTS):
            continue
        tags = _read_mp4_tags(folder / name)
        if not tags:
            continue
        collection_id = _first_int(tags.get("plID"))
        if collection_id:
            storefront = _first_int(tags.get("sfID"))
            return {"collection_id": collection_id, "country": STOREFRONTS.get(storefront)}
    return None


def full_res_url(artwork_url: str) -> str:
    """Rewrite Apple's sized artwork URL (…/100x100bb.jpg) to request the
    original: sizes at or above it return the original upload."""
    return re.sub(r"/\d+x\d+[a-z]*(-\d+)?\.(jpg|png|webp)$", r"/10000x10000bb.\2", artwork_url)


def lookup_album(collection_id: int, country: str | None) -> tuple[dict, bytes | None]:
    with _cache_lock:
        hit = _cache.get(collection_id)
    if hit is not None:
        return hit

    params = {"id": collection_id, "entity": "album"}
    if country:
        params["country"] = country
    info: dict = {"collection_id": collection_id, "error": None}
    data = None
    try:
        resp = requests.get(LOOKUP_URL, params=params, timeout=TIMEOUT, headers=HEADERS)
        resp.raise_for_status()
        results = [r for r in resp.json().get("results", []) if r.get("wrapperType") == "collection"]
        if not results:
            info["error"] = "Album not found in the iTunes Store (it may have been removed)."
        else:
            r = results[0]
            info.update({
                "collection_name": r.get("collectionName"),
                "artist": r.get("artistName"),
                "store_url": (r.get("collectionViewUrl") or "").split("?")[0] or None,
                "track_count": r.get("trackCount"),
            })
            art = r.get("artworkUrl100")
            if not art:
                info["error"] = "The iTunes Store has no artwork for this album."
            else:
                img = requests.get(full_res_url(art), timeout=TIMEOUT, headers=HEADERS)
                img.raise_for_status()
                data = img.content
                info.update({k: v for k, v in image_info(data).items()})
    except Exception as exc:  # noqa: BLE001 -- surfaced to the UI, not cached
        info["error"] = f"iTunes lookup failed: {exc}"
        return info, None

    with _cache_lock:
        _cache[collection_id] = (info, data)
    return info, data


# -- MusicBrainz release by Apple Music link --------------------------------

def apple_links(collection_id: int, extra: tuple[str, ...] = ()) -> list[str]:
    """Every likely shape of the album's store link, in all common stores."""
    countries = list(dict.fromkeys([*STOREFRONTS.values(), *EXTRA_STORE_COUNTRIES]))
    links = [*extra]
    for cc in countries:
        links.append(f"https://music.apple.com/{cc}/album/{collection_id}")
        links.append(f"https://itunes.apple.com/{cc}/album/id{collection_id}")
    links.append(f"https://music.apple.com/album/{collection_id}")
    links.append(f"https://itunes.apple.com/album/id{collection_id}")
    return list(dict.fromkeys(links))


def _slugged_links(store_url: str | None, collection_id: int) -> tuple[str, ...]:
    """The iTunes lookup's own link (with the album-name slug), in its
    music.apple.com and itunes.apple.com/…/id<id> shapes."""
    if not store_url:
        return ()
    m = re.match(r"https://music\.apple\.com/([a-z]{2})/album/([^/]+)/(\d+)$", store_url)
    if not m:
        return (store_url,)
    cc, slug, _ = m.groups()
    return (store_url, f"https://itunes.apple.com/{cc}/album/{slug}/id{collection_id}")


def _mb_lookup(links: list[str]) -> list[str]:
    """Release MBIDs linked from any of `links` (one request). Raises on
    network/server errors so callers don't cache a failure as "none"."""
    params = [("resource", link) for link in links] + [("inc", "release-rels"), ("fmt", "json")]
    resp = mbapi.get("url", params)
    if resp.status_code == 404:
        return []  # none of the links is known to MusicBrainz
    resp.raise_for_status()
    body = resp.json()
    urls = body.get("urls") if "urls" in body else [body]
    release_ids: list[str] = []
    for url in urls or []:
        for rel in url.get("relations", []):
            rid = (rel.get("release") or {}).get("id")
            if rid and rid not in release_ids:
                release_ids.append(rid)
    return release_ids


def musicbrainz_release_ids(collection_id: int, store_url: str | None = None) -> list[str] | None:
    """Releases MusicBrainz links to this iTunes album, or None if
    MusicBrainz couldn't be reached. Cached per album."""
    with _mb_lock:
        if collection_id in _mb_cache:
            return _mb_cache[collection_id]
        try:
            ids = _mb_lookup(apple_links(collection_id, _slugged_links(store_url, collection_id)))
        except Exception:  # noqa: BLE001 -- fall back to a normal search
            log.warning("webimport: MusicBrainz Apple link lookup failed", exc_info=True)
            return None
        _mb_cache[collection_id] = ids
        return ids


def musicbrainz_match_for_dir(folder: Path) -> dict | None:
    """{"source": "apple_music", "collection_id", "release_ids"} for an
    iTunes purchase folder, or None if it isn't one or MusicBrainz
    couldn't be reached. `release_ids` is empty when no release links the
    album."""
    ids = detect_ids(folder)
    if ids is None:
        return None
    info, _ = lookup_album(ids["collection_id"], ids["country"])  # cached; gives the slugged link
    release_ids = musicbrainz_release_ids(ids["collection_id"], info.get("store_url"))
    if release_ids is None:
        return None
    return {"source": "apple_music", "collection_id": ids["collection_id"], "release_ids": release_ids}

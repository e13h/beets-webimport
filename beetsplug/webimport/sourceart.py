"""Album art choice for an inbox import.

beets embeds whatever fetchart finds first. With the homelab config that's
an image in the album's inbox folder (the `filesystem` source), else the
release's Cover Art Archive front. So the review can offer:

- "candidate": the selected release's Cover Art Archive art (fetchart's
  usual result when the folder has no image)
- "embedded":  the art already embedded in the files (purchases and many
               rips carry it)
- "itunes":    the iTunes Store artwork, for iTunes purchases
- "folder":    an image already in the folder, which fetchart would use

Choosing one makes fetchart pick it: "embedded"/"itunes" save the image
as cover.<ext> in the folder; "candidate" sets aside folder images so
fetchart moves on to Cover Art Archive. Set-aside images are renamed with
a `.before-webimport` suffix, never deleted.
"""
from __future__ import annotations

import hashlib
import os
import re
from collections import Counter
from pathlib import Path

from .coverart import image_info

SET_ASIDE_SUFFIX = ".before-webimport"
# fetchart's IMAGE_EXTENSIONS and default cover_names.
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")
DEFAULT_COVER_NAMES = ("cover", "front", "art", "album", "folder")
SAVE_EXT = {"image/png": ".png", "image/webp": ".webp"}

_embedded_cache: dict[tuple, dict | None] = {}


def folder_images(folder: Path, cover_names=DEFAULT_COVER_NAMES, cautious=False) -> list[Path]:
    """Images fetchart's filesystem source would consider, best first.

    Mirrors fetchart: top-level image files (its walk collects names from
    subfolders but only keeps ones that exist at the top level), names
    containing a cover name first, ranked by which cover names they
    contain; other images only when `cautious` is off."""
    folder = Path(folder)
    try:
        names = sorted(n for n in os.listdir(folder)
                       if not n.startswith(".") and n.lower().endswith(IMAGE_EXTS)
                       and (folder / n).is_file())
    except OSError:
        return []
    names_lower = [c.lower() for c in cover_names]
    pattern = re.compile(r"(\b|_)(" + "|".join(map(re.escape, names_lower)) + r")(\b|_)", re.I)

    def priority(name):
        return [i for i, c in enumerate(names_lower) if c in name.lower()]

    names.sort(key=priority)
    named = [n for n in names if pattern.search(os.path.splitext(n)[0])]
    rest = [n for n in names if n not in named]
    return [folder / n for n in named + ([] if cautious else rest)]


def _audio_art(folder: Path) -> list[tuple[str, bytes]]:
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


def embedded_art(folder: Path) -> dict | None:
    """The art embedded in the folder's audio files: the most common image,
    with image_info, `data`, and how many tracks carry it. None if no file
    has art. Cached on the files' names and mtimes."""
    folder = Path(folder)
    try:
        key = (str(folder), tuple(sorted((e.name, e.stat().st_mtime) for e in os.scandir(folder))))
    except OSError:
        return None
    if key in _embedded_cache:
        return _embedded_cache[key]

    tracks = _audio_art(folder)
    images = {hashlib.sha1(a).hexdigest(): a for _, a in tracks if a}
    counts = Counter(hashlib.sha1(a).hexdigest() for _, a in tracks if a)
    result = None
    if counts:
        sha, count = counts.most_common(1)[0]
        data = images[sha]
        result = {**image_info(data), "data": data, "tracks_with_art": sum(counts.values()),
                  "tracks_with_this_art": count, "tracks_total": len(tracks),
                  "distinct_images": len(counts)}
    _embedded_cache.clear()  # one entry is enough: the folder under review
    _embedded_cache[key] = result
    return result


def set_aside(paths) -> list[str]:
    """Rename images so fetchart ignores them; returns the new names."""
    moved = []
    for p in paths:
        target = p.with_name(p.name + SET_ASIDE_SUFFIX)
        os.replace(p, target)
        moved.append(target.name)
    return moved


def save_as_cover(folder: Path, data: bytes, mime: str | None, cover_names=DEFAULT_COVER_NAMES,
                  cautious=False) -> Path:
    """Make `data` the image fetchart picks: set aside the folder's current
    images and write cover.<ext>."""
    folder = Path(folder)
    set_aside(folder_images(folder, cover_names, cautious))
    target = folder / f"cover{SAVE_EXT.get(mime or '', '.jpg')}"
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, target)
    return target

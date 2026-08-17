"""Library browse/search + metadata editing.

Per PRD: any field edit (single field, single track/album, or bulk) that
would change the computed file path automatically triggers the
equivalent of `--move` (since the beets config here runs copy: yes,
move: no -- library-side relocation after edits has to be requested
explicitly, which is what Item.move()/Album.move() do).
"""
from __future__ import annotations


def _album_summary(album) -> dict:
    return {
        "id": album.id,
        "albumartist": album.albumartist,
        "album": album.album,
        "year": album.year,
        "navidrome_library": album.get("navidrome_library", ""),
        "track_count": len(list(album.items())),
        "has_art": bool(album.artpath),
    }


def search_albums(lib, query_str: str = "") -> list[dict]:
    q = query_str.strip() if query_str else ""
    albums = lib.albums(q) if q else lib.albums()
    return [_album_summary(a) for a in albums]


def _jsonable_fields(obj) -> dict:
    """dict(item)/dict(album) includes raw bytes for path-like fields
    (`path`, `artpath`), which Flask's JSON encoder can't serialize.
    Decode those to display strings for the API/UI."""
    out = {}
    for k, v in dict(obj).items():
        if isinstance(v, bytes):
            out[k] = v.decode("utf-8", errors="replace")
        else:
            out[k] = v
    return out


def get_album_detail(lib, album_id: int) -> dict | None:
    album = lib.get_album(album_id)
    if album is None:
        return None
    items = sorted(album.items(), key=lambda i: (i.disc or 1, i.track or 0))
    return {
        "id": album.id,
        "fields": _jsonable_fields(album),
        "tracks": [
            {"id": i.id, "track": i.track, "title": i.title, "length": i.length}
            for i in items
        ],
    }


def get_item_detail(lib, item_id: int) -> dict | None:
    item = lib.get_item(item_id)
    if item is None:
        return None
    return {"id": item.id, "fields": _jsonable_fields(item)}


def _paths_would_change(obj) -> bool:
    """Best-effort check: compute the destination path per config and
    compare to the current path. Avoids an unconditional move() call
    (a no-op move is harmless, but this keeps intent explicit and cheap
    to short-circuit). Both `.destination()` and `.path` are bytes in
    beets' internal representation."""
    try:
        new_path = obj.destination()
    except Exception:
        return True  # unsure -> attempt the move, move() itself is a no-op if unchanged
    return bytes(new_path) != bytes(obj.path)


def set_album_fields(lib, album_id: int, fields: dict, move: bool = True) -> bool:
    album = lib.get_album(album_id)
    if album is None:
        return False
    for k, v in fields.items():
        album[k] = v
    album.store()

    if move and _paths_would_change(album):
        album.move()  # relocates every item per the paths: templates

    return True


def set_item_fields(lib, item_id: int, fields: dict, move: bool = True) -> bool:
    item = lib.get_item(item_id)
    if item is None:
        return False
    for k, v in fields.items():
        item[k] = v
    item.store()

    if move and _paths_would_change(item):
        item.move()

    return True


def bulk_set_field(lib, album_ids: list[int], field: str, value: str, move: bool = True) -> int:
    updated = 0
    for album_id in album_ids:
        if set_album_fields(lib, album_id, {field: value}, move=move):
            updated += 1
    return updated

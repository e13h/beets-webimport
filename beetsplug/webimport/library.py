"""Library browse/search + metadata editing.

Per PRD: any field edit (single field, single track/album, or bulk) that
would change the computed file path automatically triggers the
equivalent of `--move` (since the beets config here runs copy: yes,
move: no -- library-side relocation after edits has to be requested
explicitly, which is what Item.move()/Album.move() do).
"""
from __future__ import annotations


import os
from pathlib import Path
from beets.util import syspath


def get_listening_groups(lib) -> list[str]:
    """Returns distinct navidrome_library values present in the library."""
    groups = set()
    try:
        with lib.transaction() as tx:
            for row in tx.query(
                "SELECT DISTINCT value FROM album_attributes WHERE key = 'navidrome_library' AND value IS NOT NULL AND value != ''"
            ):
                groups.add(row[0])
            for row in tx.query(
                "SELECT DISTINCT value FROM item_attributes WHERE key = 'navidrome_library' AND value IS NOT NULL AND value != ''"
            ):
                groups.add(row[0])
    except Exception:
        for a in lib.albums():
            val = a.get("navidrome_library")
            if val:
                groups.add(val)
        for i in lib.items():
            val = i.get("navidrome_library")
            if val:
                groups.add(val)
    return sorted(groups)


def _album_summary(album, track_count: int) -> dict:
    # No art check here: it meant opening a track file per album (~2.4s
    # for 143 albums). Each tile's thumbnail request reports art (or 404s
    # to the "No Art" placeholder) on its own, in parallel.
    return {
        "id": album.id,
        "albumartist": album.albumartist,
        "album": album.album,
        "year": album.year,
        "navidrome_library": album.get("navidrome_library", ""),
        "track_count": track_count,
    }


def search_albums(lib, query_str: str = "") -> list[dict]:
    q = query_str.strip() if query_str else ""
    albums = lib.albums(q) if q else lib.albums()
    # One grouped query instead of an items() query per album.
    with lib.transaction() as tx:
        counts = dict(tx.query(
            "SELECT album_id, COUNT(*) FROM items WHERE album_id IS NOT NULL GROUP BY album_id"
        ))
    return [_album_summary(a, counts.get(a.id, 0)) for a in albums]




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
    if hasattr(obj, "items"):
        return any(_paths_would_change(i) for i in obj.items())
    try:
        new_path = obj.destination()
    except Exception:
        return True  # unsure -> attempt the move, move() itself is a no-op if unchanged
    return bytes(new_path) != bytes(obj.path)


def _paths_would_change_for_items(items) -> bool:
    for item in items:
        try:
            new_path = item.destination()
        except Exception:
            return True
        if bytes(new_path) != bytes(item.path):
            return True
    return False


def set_album_fields(
    lib,
    album_id: int,
    fields: dict,
    move: bool = True,
    conflict_resolution: str | None = None,
) -> dict:
    """Sets metadata fields on an album (and its items).
    Detects Placement Conflicts when move=True and proposed file paths collide with existing files.
    conflict_resolution can be 'skip', 'overwrite', or 'keep_both'.
    """
    album = lib.get_album(album_id)
    if album is None:
        return {"ok": False, "error": "Album not found"}

    old_album_fields = {k: album.get(k) for k in fields}
    items = list(album.items())
    old_items_fields = [{k: item.get(k) for k in fields} for item in items]

    for k, v in fields.items():
        album[k] = v
        for item in items:
            item[k] = v

    album.store()
    for item in items:
        item.store()

    if move and _paths_would_change_for_items(items):
        conflicts = []
        for item in items:
            try:
                new_dest = item.destination()
            except Exception:
                new_dest = item.path
            dest_str = syspath(new_dest)
            if bytes(new_dest) != bytes(item.path) and os.path.exists(dest_str):
                conflicts.append(dest_str)

        if conflicts:
            if conflict_resolution is None:
                # Conflict detected! Revert in DB before returning
                for k, v in old_album_fields.items():
                    if v is None:
                        del album[k]
                    else:
                        album[k] = v
                album.store()
                for item, old_f in zip(items, old_items_fields):
                    for k, v in old_f.items():
                        if v is None:
                            del item[k]
                        else:
                            item[k] = v
                    item.store()
                return {
                    "ok": False,
                    "conflict": True,
                    "kind": "album",
                    "id": album_id,
                    "destination": conflicts[0],
                    "destinations": conflicts,
                    "message": f"Destination path '{conflicts[0]}' is already occupied.",
                }
            elif conflict_resolution == "skip":
                # Revert changes in DB
                for k, v in old_album_fields.items():
                    if v is None:
                        del album[k]
                    else:
                        album[k] = v
                album.store()
                for item, old_f in zip(items, old_items_fields):
                    for k, v in old_f.items():
                        if v is None:
                            del item[k]
                        else:
                            item[k] = v
                    item.store()
                return {"ok": True, "action": "skip", "reverted": True}
            elif conflict_resolution == "overwrite":
                for c in conflicts:
                    if os.path.exists(c):
                        try:
                            os.remove(c)
                        except OSError:
                            pass
                album.move()
                return {"ok": True, "action": "overwrite"}
            elif conflict_resolution == "keep_both":
                album.move()
                return {"ok": True, "action": "keep_both"}

    if move and _paths_would_change_for_items(items):
        album.move()
    return {"ok": True}


def set_item_fields(
    lib,
    item_id: int,
    fields: dict,
    move: bool = True,
    conflict_resolution: str | None = None,
) -> dict:
    """Sets metadata fields on a single item.
    Detects Placement Conflicts when move=True and proposed file path collides with an existing file.
    conflict_resolution can be 'skip', 'overwrite', or 'keep_both'.
    """
    item = lib.get_item(item_id)
    if item is None:
        return {"ok": False, "error": "Item not found"}

    old_fields = {k: item.get(k) for k in fields}
    for k, v in fields.items():
        item[k] = v

    item.store()

    if move and _paths_would_change(item):
        try:
            new_dest = item.destination()
        except Exception:
            new_dest = item.path

        dest_str = syspath(new_dest)
        if bytes(new_dest) != bytes(item.path) and os.path.exists(dest_str):
            if conflict_resolution is None:
                # Revert in DB
                for k, v in old_fields.items():
                    if v is None:
                        del item[k]
                    else:
                        item[k] = v
                item.store()
                return {
                    "ok": False,
                    "conflict": True,
                    "kind": "item",
                    "id": item_id,
                    "destination": dest_str,
                    "message": f"Destination path '{dest_str}' is already occupied.",
                }
            elif conflict_resolution == "skip":
                for k, v in old_fields.items():
                    if v is None:
                        del item[k]
                    else:
                        item[k] = v
                item.store()
                return {"ok": True, "action": "skip", "reverted": True}
            elif conflict_resolution == "overwrite":
                if os.path.exists(dest_str):
                    try:
                        os.remove(dest_str)
                    except OSError:
                        pass
                item.move()
                return {"ok": True, "action": "overwrite"}
            elif conflict_resolution == "keep_both":
                item.move()
                return {"ok": True, "action": "keep_both"}

    if move and _paths_would_change(item):
        item.move()
    return {"ok": True}


def bulk_set_field(
    lib,
    album_ids: list[int],
    field: str,
    value: str,
    move: bool = True,
    conflict_resolution: str | None = None,
) -> dict:
    if move and conflict_resolution is None:
        for album_id in album_ids:
            res = set_album_fields(
                lib,
                album_id,
                {field: value},
                move=True,
                conflict_resolution=None,
            )
            if res.get("conflict"):
                return res

    updated = 0
    for album_id in album_ids:
        res = set_album_fields(
            lib,
            album_id,
            {field: value},
            move=move,
            conflict_resolution=conflict_resolution,
        )
        if res.get("ok"):
            updated += 1
    return {"ok": True, "updated": updated}

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


# Values read from the audio stream or maintained by beets itself, not
# editable metadata. The explorer shows them in their own read-only group.
READONLY_FIELDS = (
    "id", "album_id", "path", "artpath", "mtime", "added",
    "length", "bitrate", "bitrate_mode", "format", "samplerate",
    "bitdepth", "channels", "encoder_info", "encoder_settings",
)


def get_album_explorer(lib, album_id: int) -> dict | None:
    """Everything beets stores for an album and each of its tracks, for
    the read-only metadata explorer. `item_keys` are the album fields
    that beets also copies onto every track (so the UI can show where a
    track differs from its album); `custom_fields` are flexible
    attributes (not part of beets' fixed schema)."""
    from beets.library import Album, Item

    album = lib.get_album(album_id)
    if album is None:
        return None
    items = sorted(album.items(), key=lambda i: (i.disc or 1, i.track or 0, i.id))

    from . import snapshot

    def node(obj):
        fields = _jsonable_fields(obj)
        # The original-tag snapshot is shown as its own layer, not as a
        # giant JSON string among the custom fields.
        fields.pop(snapshot.SNAPSHOT_FIELD, None)
        fields.pop("original_file", None)
        return {
            "id": obj.id,
            "fields": fields,
            "custom_fields": sorted(set(fields) - set(obj._fields)),
            "original": snapshot.load(obj),
        }

    return {
        "album": node(album),
        "tracks": [node(i) for i in items],
        "item_keys": sorted(Album.item_keys),
        "readonly_fields": list(READONLY_FIELDS),
        # Fields that are file tags (what an original-tag snapshot records).
        "tag_fields": sorted(Item._media_fields - snapshot._NON_TAG_FIELDS - set(READONLY_FIELDS)),
    }


def _empty(value) -> bool:
    return value is None or value == "" or value == [] or value == b""


def _same(db_value, file_value) -> bool:
    if _empty(db_value) and _empty(file_value):
        return True
    if isinstance(db_value, float) or isinstance(file_value, float):
        try:
            import math

            return math.isclose(float(db_value), float(file_value), rel_tol=1e-4, abs_tol=1e-6)
        except (TypeError, ValueError):
            return False
    return db_value == file_value


def _compare_item_file_tags(item) -> dict:
    """Read the item's file through beets' own tag reader (same type
    coercion as an import) and diff every tag field against the DB.
    Fields the file's format has no storage for are reported separately
    as `unsupported` (only when the DB holds a value), since those can
    never match and aren't a sign of anything wrong."""
    from beets.library import Item
    import mediafile

    from .snapshot import media_field_styles

    out = {"id": item.id, "mismatches": [], "unsupported": [], "error": None,
           "modified_outside_beets": False, "art": None}
    path = syspath(item.path)
    try:
        file_item = Item.from_path(path)
        mf = mediafile.MediaFile(path)
    except Exception as exc:  # noqa: BLE001 -- surface any read failure per track
        out["error"] = str(exc) or exc.__class__.__name__
        return out

    try:
        art = mf.art
    except Exception:  # noqa: BLE001 -- unreadable art shouldn't hide the tag diff
        art = None
    if art:
        from .coverart import image_info

        out["art"] = image_info(art)

    try:
        # beets records the file's mtime when it last read/wrote it.
        out["modified_outside_beets"] = os.path.getmtime(path) > (item.mtime or 0) + 1
    except OSError:
        pass

    for field in sorted(Item._media_fields):
        if field in READONLY_FIELDS:
            continue
        db_value = item.get(field)
        file_value = file_item.get(field)
        if _same(db_value, file_value):
            continue
        styles = media_field_styles(field, mf.mgfile)
        if styles is not None and not styles:
            if not _empty(db_value):
                out["unsupported"].append(field)
            continue
        out["mismatches"].append({"field": field, "db": _jsonable(db_value), "file": _jsonable(file_value)})
    return out


def _jsonable(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def compare_album_file_tags(lib, album_id: int) -> dict | None:
    album = lib.get_album(album_id)
    if album is None:
        return None
    return {"tracks": [_compare_item_file_tags(i) for i in album.items()]}


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

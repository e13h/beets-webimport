"""Original-tag snapshots.

beets keeps only the current value of each field, with no record of
what a file said before import. When an inbox import starts (beets has
read the files but changed nothing yet), this captures each track's tags
and stores them on the item as a JSON flexible attribute,
`original_tags`. Flexible attributes are never written to files, and
`--from-scratch` (`Item.clear()`) only clears tag fields, so the snapshot
survives later reimports.

Snapshot shape:
    {"version": 1, "captured_at": <ISO-8601 UTC>, "source_path": <inbox path>,
     "fields": {<beets field>: <value as read from the file>},
     "other":  {<raw tag key>: <value>}}   # tags beets doesn't map to a field

Excluded on purpose: images (size), audio-stream properties (not tags),
and tags that identify the purchaser (iTunes `apID`/`ownr`, ID3 `PRIV`).
"""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

SNAPSHOT_FIELD = "original_tags"
SNAPSHOT_VERSION = 1

# Audio-stream properties and beets bookkeeping: not tags.
_NON_TAG_FIELDS = {
    "length", "bitrate", "bitrate_mode", "format", "samplerate", "bitdepth",
    "channels", "encoder_info", "encoder_settings", "art", "images",
}
# Raw keys (lowercased; ID3 frames matched on the frame id before ":").
_PRIVATE_RAW_KEYS = {"apid", "ownr", "priv"}
_IMAGE_RAW_KEYS = {"covr", "apic", "pic", "metadata_block_picture", "wm/picture", "coverart"}
_MAX_VALUE_CHARS = 4000


def _excluded_raw_key(key: str) -> bool:
    k = key.lower()
    frame = k.split(":", 1)[0]
    return k in _PRIVATE_RAW_KEYS | _IMAGE_RAW_KEYS or frame in _PRIVATE_RAW_KEYS | _IMAGE_RAW_KEYS


def media_field_styles(field: str, mgfile) -> list | None:
    """mediafile storage styles for `field` that apply to this file's
    format, or None if the field has no simple style list (images,
    composite fields). Uses getattr_static: several mediafile descriptor
    types fail when read from the class."""
    import mediafile

    try:
        descriptor = inspect.getattr_static(mediafile.MediaFile, field)
    except AttributeError:
        return None
    descriptor = getattr(descriptor, "date_field", descriptor)
    try:
        return list(descriptor.styles(mgfile))
    except (AttributeError, TypeError):
        return None


def _mapped_raw_keys(mf) -> set[str]:
    """Raw tag keys (lowercased) that mediafile maps to some beets field
    for this file's format."""
    import mediafile

    keys = set()
    for name in mediafile.MediaFile.fields():
        for style in media_field_styles(name, mf.mgfile) or []:
            key = getattr(style, "key", None)
            if not key:
                continue
            keys.add(key.lower())
            desc = getattr(style, "description", None)
            if desc:
                keys.add(f"{key}:{desc}".lower())
    return keys


def _jsonish(value):
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    elif isinstance(value, (list, tuple)):
        return [_jsonish(v) for v in value]
    elif hasattr(value, "text") and not isinstance(value, str):  # ID3 frames
        return _jsonish(list(value.text))
    elif not isinstance(value, (str, int, float, bool)) and value is not None:
        value = str(value)
    if isinstance(value, str) and len(value) > _MAX_VALUE_CHARS:
        value = value[:_MAX_VALUE_CHARS] + "…"
    return value


def _empty(value) -> bool:
    return value is None or value == "" or value == [] or value == b""


def capture(item) -> dict:
    """Snapshot `item`'s tags. `item` must still hold the values beets read
    from the file (i.e. before match metadata is applied)."""
    import mediafile
    from beets.util import displayable_path, syspath

    fields = {}
    for field in sorted(item._media_fields):
        if field in _NON_TAG_FIELDS:
            continue
        value = item.get(field)
        if not _empty(value):
            fields[field] = _jsonish(value)

    other = {}
    try:
        mf = mediafile.MediaFile(syspath(item.path))
        mapped = _mapped_raw_keys(mf)
        raw = mf.mgfile.tags or {}
        for key in sorted(raw.keys()):
            k = str(key)
            if _excluded_raw_key(k) or k.lower() in mapped:
                continue
            other[k] = _jsonish(raw[key])
    except Exception:  # noqa: BLE001 -- a raw-tag read failure shouldn't block import
        pass

    return {
        "version": SNAPSHOT_VERSION,
        "captured_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source_path": displayable_path(item.path),
        "fields": fields,
        "other": other,
    }


def on_import_task_start(task, session):
    """Snapshot each item's original tags at the start of an inbox import.

    Only for webimport's own path-based sessions: a Library-tab reimport
    (query-based) works on already-tagged library items, and a snapshot
    taken there would record beets' tags, not the originals. An existing
    snapshot is never overwritten."""
    from .session import WebImportSession

    if not isinstance(session, WebImportSession) or not session.paths or session.query is not None:
        return
    items = task.items if getattr(task, "is_album", True) else [task.item]
    for item in items:
        if SNAPSHOT_FIELD in item:
            continue
        try:
            item[SNAPSHOT_FIELD] = json.dumps(capture(item), ensure_ascii=False)
        except Exception:  # noqa: BLE001 -- never block an import on this
            pass


def register(register_listener) -> None:
    register_listener("import_task_start", on_import_task_start)


def load(obj) -> dict | None:
    """Parsed snapshot for an item, or None if it has none (or it's unreadable)."""
    raw = obj.get(SNAPSHOT_FIELD) if hasattr(obj, "get") else None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return data if isinstance(data, dict) else None

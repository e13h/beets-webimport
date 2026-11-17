"""Tag preview: what importing with a candidate would do to each file's tags.

Runs beets' own apply step (`AlbumMatch.merged_pairs` → `Item.update`,
with `import.from_scratch` honored) on copies of the review's items, then
compares every tag beets writes (`Item._media_fields`) with what the file
has now. Nothing is written; the task's real items are untouched.

Per field: "same", "added" (file has no value), "changed" (the file's value
is replaced), or "cleared" (the file's value is removed). Changed and
cleared are where the file's current data is lost from the imported copy.

Tags beets doesn't map (store IDs, iTunes atoms, …) aren't written by
beets, so they stay in the file; they're listed as kept. Fields set by
`import.set_fields` are stored in beets only (not written to files) unless
they're also tag fields.
"""
from __future__ import annotations

import json

from beets import config

from .snapshot import _NON_TAG_FIELDS, SNAPSHOT_FIELD, _jsonish

_KEEP_ZERO = {"comp"}  # 0 is a real value here ("not a compilation")


def _norm(field: str, value):
    """Comparable, JSON-safe form; None for "no value". beets stores unset
    ints as 0 and unset strings as ""."""
    value = _jsonish(value)
    if value is None or value == "" or value == [] or value == b"":
        return None
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, (int, float)) and value == 0 and field not in _KEEP_ZERO:
        return None
    if isinstance(value, float):
        value = round(value, 6)
    if isinstance(value, list):
        value = [v for v in value if v not in (None, "")] or None
    return value


def _kind(before, after) -> str:
    if before == after:
        return "same"
    if before is None:
        return "added"
    if after is None:
        return "cleared"
    return "changed"


def tag_fields() -> list[str]:
    from beets.library import Item

    return sorted(f for f in Item._media_fields if f not in _NON_TAG_FIELDS)


def _other_tags(item) -> dict:
    """Raw tags beets doesn't map, from the original-tags snapshot taken
    when the review opened."""
    try:
        return json.loads(item.get(SNAPSHOT_FIELD) or "{}").get("other", {})
    except (TypeError, ValueError):
        return {}


def _set_fields() -> list[dict]:
    """import.set_fields entries (templates shown as configured)."""
    try:
        return [{"field": f, "value": str(v.get())} for f, v in config["import"]["set_fields"].items()]
    except Exception:  # noqa: BLE001
        return []


def _file_name(item) -> str:
    import os

    return os.path.basename(os.fsdecode(item.path))


def preview(task, index: int) -> dict:
    """Tag changes for candidate `index` of a pending album review."""
    match = task.candidates[index]
    from_scratch = bool(config["import"]["from_scratch"].get())
    fields = tag_fields()

    tracks = []
    for item, data in match.merged_pairs:
        after = item.copy()
        if from_scratch:
            after.clear()
        after.update(data)
        rows = []
        for f in fields:
            b, a = _norm(f, item.get(f)), _norm(f, after.get(f))
            if b is None and a is None:
                continue
            rows.append({"field": f, "before": b, "after": a, "kind": _kind(b, a)})
        tracks.append({
            "file": _file_name(item),
            "matched": True,
            "title_before": _norm("title", item.get("title")),
            "title_after": _norm("title", after.get("title")),
            "track_after": after.get("track"),
            "disc_after": after.get("disc"),
            "fields": rows,
            "other_tags": _other_tags(item),
        })
    for item in match.extra_items:
        rows = [{"field": f, "before": v, "after": v, "kind": "same"}
                for f in fields if (v := _norm(f, item.get(f))) is not None]
        tracks.append({"file": _file_name(item), "matched": False,
                       "title_before": _norm("title", item.get("title")), "title_after": None,
                       "fields": rows, "other_tags": _other_tags(item)})

    return {
        "from_scratch": from_scratch,
        "tracks": tracks,
        "summary": _summary(tracks),
        "set_fields": _set_fields(),
    }


def _summary(tracks) -> list[dict]:
    """Per field across tracks: counts by kind, and the before/after value
    when it's the same on every track (else marked as varying)."""
    by_field: dict[str, dict] = {}
    for t in tracks:
        for r in t["fields"]:
            s = by_field.setdefault(r["field"], {"field": r["field"], "counts": {}, "befores": [], "afters": []})
            s["counts"][r["kind"]] = s["counts"].get(r["kind"], 0) + 1
            s["befores"].append(r["before"])
            s["afters"].append(r["after"])
    out = []
    for s in by_field.values():
        befores, afters = s.pop("befores"), s.pop("afters")
        uniform_b = all(b == befores[0] for b in befores)
        uniform_a = all(a == afters[0] for a in afters)
        s["before"] = befores[0] if uniform_b else None
        s["after"] = afters[0] if uniform_a else None
        s["before_varies"], s["after_varies"] = not uniform_b, not uniform_a
        s["tracks"] = sum(s["counts"].values())
        out.append(s)
    return out

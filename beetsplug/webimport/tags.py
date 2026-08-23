"""Tag Vocabulary storage and management.

Per spec (User Story 43-45):
- Tag Vocabulary is an explicitly curated list (e.g. `mood`, multi-valued)
  persisted to JSON (`tags.json`).
- Applying a tag at the album level writes down to every track file in that
  album (`beet write` equivalent).
- Tags on items/albums can be multi-valued, joined with a semicolon delimiter (`;`).
"""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

log = logging.getLogger("beets.webimport.tags")

DELIMITER = ";"


def _split_tags(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [t.strip() for t in raw.split(DELIMITER) if t.strip()]


def _join_tags(tags: list[str]) -> str:
    return f"{DELIMITER} ".join(tags)


class TagStore:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._data: dict[str, list[str]] = {}
        self._load()

    def _load(self):
        with self._lock:
            if self.path.exists():
                try:
                    with open(self.path, "r", encoding="utf-8") as f:
                        self._data = json.load(f)
                except Exception:
                    log.exception("Failed to load tag vocabulary from %s", self.path)
                    self._data = {}
            else:
                self._data = {}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, sort_keys=True)

    def list_fields(self) -> list[str]:
        with self._lock:
            return sorted(self._data.keys())

    def list_values(self, field: str) -> list[str]:
        with self._lock:
            return sorted(self._data.get(field, []))

    def add_field(self, field: str):
        with self._lock:
            if field not in self._data:
                self._data[field] = []
                self._save()

    def remove_field(self, field: str):
        with self._lock:
            if field in self._data:
                del self._data[field]
                self._save()

    def add_value(self, field: str, value: str):
        val = value.strip()
        if not val:
            return
        with self._lock:
            values = self._data.setdefault(field, [])
            if val not in values:
                values.append(val)
                self._save()

    def remove_value(self, field: str, value: str):
        val = value.strip()
        with self._lock:
            values = self._data.get(field, [])
            if val in values:
                values.remove(val)
                self._save()


def apply_tag_to_item(item, field: str, value: str, add: bool = True):
    """Applies or removes a tag value on an individual Item.

    If multi-valued, manages values delimited by `;` and writes tags to file.
    """
    current_raw = item.get(field, "")
    current_list = _split_tags(current_raw)

    if add:
        if value not in current_list:
            current_list.append(value)
    else:
        if value in current_list:
            current_list.remove(value)

    if current_list:
        item[field] = _join_tags(current_list)
    else:
        item[field] = ""
    item.store()
    try:
        item.try_write()
    except Exception:
        log.warning("Could not write tags to file for item %s", getattr(item, "id", None))


def apply_tag_to_album(lib, album, field: str, value: str, add: bool = True):
    """Applies or removes a tag value on an Album and writes down to every track file."""
    current_raw = album.get(field, "")
    current_list = _split_tags(current_raw)

    if add:
        if value not in current_list:
            current_list.append(value)
    else:
        if value in current_list:
            current_list.remove(value)

    if current_list:
        album[field] = _join_tags(current_list)
    else:
        album[field] = ""
    album.store()

    for item in album.items():
        apply_tag_to_item(item, field, value, add=add)

"""Custom tag vocabulary + application.

Per PRD: tags are stored as a multi-valued flexible attribute (default
field: `mood`), values are delimiter-joined in a single beets field
(matching how you'd declare `Tags.PersonalTags.Aliases` + a Split
delimiter in navidrome.toml). Album-level tag assignment writes down to
every track file, since Navidrome smart playlists filter at song level.

The vocabulary itself (the reusable list of known tag values per field)
is stored in a small JSON sidecar file -- beets' db has no concept of "a
list of tags that exist but aren't yet applied to anything", so this
can't live purely in flexible attributes.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

DELIMITER = ";"


class TagStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._data: dict[str, list[str]] = {}
        self._load()

    def _load(self):
        if self.path.exists():
            with self._lock:
                self._data = json.loads(self.path.read_text())

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            self.path.write_text(json.dumps(self._data, indent=2, sort_keys=True))

    def list_fields(self) -> list[str]:
        return sorted(self._data.keys())

    def list_values(self, field: str) -> list[str]:
        return sorted(self._data.get(field, []))

    def add_field(self, field: str):
        with self._lock:
            self._data.setdefault(field, [])
        self._save()

    def add_value(self, field: str, value: str):
        with self._lock:
            self._data.setdefault(field, [])
            if value not in self._data[field]:
                self._data[field].append(value)
        self._save()

    def remove_value(self, field: str, value: str):
        with self._lock:
            if field in self._data and value in self._data[field]:
                self._data[field].remove(value)
        self._save()


def _split(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [v for v in raw.split(DELIMITER) if v]


def _join(values: list[str]) -> str:
    return DELIMITER.join(sorted(set(values)))


def apply_tag_to_item(item, field: str, value: str, add: bool = True):
    current = _split(item.get(field))
    if add and value not in current:
        current.append(value)
    elif not add and value in current:
        current.remove(value)
    item[field] = _join(current)
    item.store()
    item.write()  # writes the actual tag frame to the library file copy


def apply_tag_to_album(lib, album, field: str, value: str, add: bool = True):
    """Sets the tag on the album AND writes it down to every track file,
    per PRD (Navidrome smart playlists filter at the song level)."""
    current = _split(album.get(field))
    if add and value not in current:
        current.append(value)
    elif not add and value in current:
        current.remove(value)
    album[field] = _join(current)
    album.store()

    for item in album.items():
        apply_tag_to_item(item, field, value, add=add)

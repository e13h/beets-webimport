"""Grace-period undo.

Per PRD: undo must be keyed strictly off the exact Album/Item DB IDs
captured at the moment of import (never a re-derived query), and -- since
beets is run in `copy` mode here -- undo is a straight `remove(delete=True)`
(the CLI equivalent of `beet remove -d`). The untouched inbox original is
never touched by import in copy mode, so no restore step is needed.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class UndoRecord:
    record_id: str
    kind: str  # "album" | "item"
    db_id: int
    label: str  # human-readable, for the UI list
    inbox_path: str | None = None
    imported_at: float = field(default_factory=time.time)


class GracePeriodManager:
    def __init__(self, lib, grace_period_seconds: int):
        self.lib = lib
        self.grace_period_seconds = grace_period_seconds
        self._records: dict[str, UndoRecord] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, db_id: int, label: str, inbox_path: str | None = None) -> str:
        import uuid

        record_id = uuid.uuid4().hex
        with self._lock:
            self._records[record_id] = UndoRecord(
                record_id=record_id, kind=kind, db_id=db_id, label=label, inbox_path=inbox_path
            )
        return record_id

    def _prune_expired(self):
        now = time.time()
        with self._lock:
            expired = [
                rid
                for rid, rec in self._records.items()
                if now - rec.imported_at > self.grace_period_seconds
            ]
            for rid in expired:
                del self._records[rid]

    def list_undoable(self) -> list[dict[str, Any]]:
        self._prune_expired()
        now = time.time()
        with self._lock:
            return [
                {
                    "record_id": r.record_id,
                    "kind": r.kind,
                    "label": r.label,
                    "seconds_remaining": max(
                        0,
                        int(self.grace_period_seconds - (now - r.imported_at)),
                    ),
                }
                for r in self._records.values()
            ]

    def undo(self, record_id: str) -> bool:
        """Deletes the library-side files + db entry for this record, by
        ID only. Returns False if the record is unknown or already
        expired (safer to no-op than guess)."""
        self._prune_expired()
        with self._lock:
            rec = self._records.pop(record_id, None)
        if rec is None:
            return False

        if rec.kind == "album":
            obj = self.lib.get_album(rec.db_id)
        else:
            obj = self.lib.get_item(rec.db_id)

        if obj is None:
            return False  # already gone

        obj.remove(delete=True)  # == `beet remove -d`, scoped to this ID

        if rec.inbox_path:
            from pathlib import Path
            marker = Path(rec.inbox_path) / ".webimport_imported"
            if marker.exists():
                try:
                    marker.unlink()
                except OSError:
                    pass

        return True

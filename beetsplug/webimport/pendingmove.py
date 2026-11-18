"""Pending Move: hold back a file move until Navidrome has seen new tags.

Navidrome keeps a track's history (playlists, plays, stars) across a
rename only if it doesn't also see the track's persistent ID change in the
same scan (spike: .scratch/navidrome-safe-lifecycle/issues/01). So when an
operation both writes tags and changes a file's computed path, the tags go
first, and the move waits for a Navidrome scan that started after the write
(ADR-0011).

Rules (`Mover.relocate`):
- No Navidrome configured: move now (plain beets behaviour).
- Tags were written, or the album/item is already pending: pending.
- Otherwise (only beets-only fields such as navidrome_library changed, so
  the files' tags are what Navidrome already has): move now.

A pending move resolves when the poller has seen Navidrome idle *after*
the move was requested, and then sees `lastScan` change: that scan started
after the write. (`lastScan` is a finish time, so comparing it with the
write time is not enough.) Pending state lives in memory only. At startup,
`discover` lists path mismatches as pending but never moves them by itself
(a changed path template would otherwise move the whole library); those
need "Move now".
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

log = logging.getLogger("beets.webimport")

POLL_SECONDS = 2.0


def needs_move(objs) -> bool:
    for obj in objs:
        try:
            if bytes(obj.destination()) != bytes(obj.path):
                return True
        except Exception:  # noqa: BLE001 -- unresolvable template: leave it be
            continue
    return False


@dataclass
class Entry:
    kind: str  # "album" | "item"
    id: int
    since: float = field(default_factory=time.time)
    auto: bool = True  # False: found at startup, waits for "Move now"
    baseline: str | None = None  # lastScan seen while Navidrome was idle
    armed: bool = False
    reason: str = "waiting for Navidrome to scan the new tags"
    scan_requested: bool = False


class Mover:
    def __init__(self, lib, scans=None, lock: threading.Lock | None = None,
                 trigger_scan_after: float = 60.0, thread_init=None):
        self.lib = lib
        self.scans = scans  # NavidromeClient-like, or None
        self.lock = lock or threading.Lock()  # held while moving (Apply Lock)
        self.trigger_scan_after = trigger_scan_after
        self._entries: dict[tuple[str, int], Entry] = {}
        self._guard = threading.Lock()
        self._thread_init = thread_init
        self._stop = threading.Event()

    @property
    def enabled(self) -> bool:
        return self.scans is not None

    # -- requesting moves ------------------------------------------------
    def relocate_album(self, album, wrote_tags: bool) -> str:
        return self._relocate("album", album, list(album.items()), wrote_tags)

    def relocate_item(self, item, wrote_tags: bool) -> str:
        if item.album_id:
            album = self.lib.get_album(item.album_id)
            if album is not None:
                return self._relocate("album", album, list(album.items()), wrote_tags)
        return self._relocate("item", item, [item], wrote_tags)

    def _relocate(self, kind, obj, items, wrote_tags) -> str:
        key = (kind, obj.id)
        with self._guard:
            pending = key in self._entries
            if not needs_move(items):
                self._entries.pop(key, None)
                return "unchanged"
            if self.enabled and (wrote_tags or pending):
                # A new write supersedes the old wait: start over.
                self._entries[key] = Entry(kind, obj.id)
                return "pending"
            self._entries.pop(key, None)
        self._move(kind, obj)
        return "moved"

    def _move(self, kind, obj) -> None:
        obj.move()
        log.info("webimport: moved %s %s to its computed path", kind, obj.id)

    # -- state for the UI ------------------------------------------------
    def is_pending(self, kind: str, id_: int) -> bool:
        with self._guard:
            return (kind, id_) in self._entries

    def pending_album_ids(self) -> set[int]:
        with self._guard:
            return {i for (k, i) in self._entries if k == "album"}

    def pending(self) -> list[dict]:
        with self._guard:
            entries = list(self._entries.values())
        return [
            {"kind": e.kind, "id": e.id, "since": e.since, "auto": e.auto, "reason": e.reason}
            for e in sorted(entries, key=lambda e: e.since)
        ]

    def move_now(self, kind: str, id_: int) -> bool:
        """The user's override: move regardless of Navidrome."""
        with self._guard:
            self._entries.pop((kind, id_), None)
        obj = self.lib.get_album(id_) if kind == "album" else self.lib.get_item(id_)
        if obj is None:
            return False
        with self.lock:
            self._move(kind, obj)
        return True

    def forget(self, kind: str, id_: int) -> None:
        """The album/item left the library (e.g. Undo import)."""
        with self._guard:
            self._entries.pop((kind, id_), None)

    # -- startup -----------------------------------------------------------
    def discover(self) -> int:
        """List albums/singletons whose files aren't at their computed path."""
        found = []
        for album in self.lib.albums():
            if needs_move(album.items()):
                found.append(("album", album.id))
        for item in self.lib.items("singleton:true"):
            if needs_move([item]):
                found.append(("item", item.id))
        with self._guard:
            for key in found:
                self._entries.setdefault(key, Entry(*key, auto=False, reason="files aren't at their computed path"))
        return len(found)

    # -- polling -------------------------------------------------------------
    def tick(self) -> None:
        """One poll of Navidrome; moves whatever became safe."""
        with self._guard:
            entries = [e for e in self._entries.values() if e.auto]
        if not entries or not self.enabled:
            return
        try:
            st = self.scans.scan_status()  # fetched after every entry above was created
        except Exception as exc:  # noqa: BLE001
            for e in entries:
                e.reason = f"can't reach Navidrome ({exc})"
            return
        ready = []
        for e in entries:
            if not e.armed:
                e.reason = "waiting for Navidrome to scan the new tags"
                if not st["scanning"]:
                    e.baseline, e.armed = st["last_scan"], True
            elif not st["scanning"] and st["last_scan"] != e.baseline:
                ready.append(e)
            elif not e.scan_requested and time.time() - e.since > self.trigger_scan_after:
                e.scan_requested = True
                try:
                    self.scans.start_scan()
                    log.info("webimport: no Navidrome scan yet; requested one")
                except Exception as exc:  # noqa: BLE001 -- non-admin user: just keep waiting
                    log.info("webimport: couldn't start a Navidrome scan (%s); still waiting", exc)
        for e in ready:
            self._resolve(e)

    def _resolve(self, e: Entry) -> None:
        if not self.lock.acquire(timeout=0.5):
            return  # an import apply is running; next tick
        try:
            with self._guard:
                if self._entries.get((e.kind, e.id)) is not e:
                    return  # superseded or cancelled meanwhile
                del self._entries[(e.kind, e.id)]
            obj = self.lib.get_album(e.id) if e.kind == "album" else self.lib.get_item(e.id)
            if obj is not None:
                self._move(e.kind, obj)
        except Exception:  # noqa: BLE001
            log.exception("webimport: pending move of %s %s failed", e.kind, e.id)
            with self._guard:
                e.reason, e.auto = "the move failed; see the log", False
                self._entries.setdefault((e.kind, e.id), e)
        finally:
            self.lock.release()

    def start(self) -> None:
        def run():
            if self._thread_init:
                self._thread_init()
            try:
                n = self.discover()
                if n:
                    log.info("webimport: %d album(s)/track(s) aren't at their computed path", n)
            except Exception:  # noqa: BLE001
                log.exception("webimport: pending-move discovery failed")
            while not self._stop.wait(POLL_SECONDS):
                try:
                    self.tick()
                except Exception:  # noqa: BLE001
                    log.exception("webimport: pending-move poll failed")

        threading.Thread(target=run, name="webimport-pending-moves", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

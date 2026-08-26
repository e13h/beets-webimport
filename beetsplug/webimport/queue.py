"""Coordinates parallel import review with a serial apply step.

Design (see PRD "Concurrency model"):
  - Each inbox album/task runs its own ImportSession in its own worker
    thread (bounded pool) -> candidate search happens in parallel.
  - Each task blocks in `choose_match`/`choose_item` waiting for a
    decision submitted from the web UI (ReviewManager).
  - Once a decision is submitted, the task's thread acquires a single
    global `apply_lock` before letting the pipeline proceed to apply,
    and releases it once that task's apply is confirmed done (via the
    `album_imported`/`item_imported` plugin events). This serializes the
    actual db-write/move step across concurrently-reviewed tasks without
    serializing the review/search phase.
  - In-flight review state is intentionally NOT persisted across a
    process restart (see PRD) -- it's all in-memory here.
"""
from __future__ import annotations

import queue
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Optional

from beets.plugins import send


@dataclass
class PendingReview:
    task_id: str
    kind: str  # "match" | "item" | "duplicate"
    path: str
    payload: dict  # serialized candidates / duplicate info for the UI
    decision_queue: "queue.Queue" = field(default_factory=lambda: queue.Queue(maxsize=1))


class ApplyCoordinator:
    """Serializes the apply phase across concurrently-reviewed tasks."""

    def __init__(self):
        self._lock = threading.Lock()
        self._apply_done = threading.Event()
        # Listen for the events beets fires once a task's files are
        # actually written/moved, so we know when it's safe to let the
        # next queued apply proceed.
        send  # (import kept for clarity; listeners registered by caller)

    def acquire(self):
        self._lock.acquire()
        self._apply_done.clear()

    def release(self):
        if self._lock.locked():
            self._lock.release()


class ReviewManager:
    """Holds pending review items and bridges them to/from the web UI."""

    def __init__(self):
        self._pending: dict[str, PendingReview] = {}
        self._lock = threading.Lock()

    def register(self, kind: str, path: str, payload: dict) -> PendingReview:
        task_id = uuid.uuid4().hex
        pr = PendingReview(task_id=task_id, kind=kind, path=path, payload=payload)
        with self._lock:
            self._pending[task_id] = pr
        return pr

    def list_pending(self) -> list[dict]:
        with self._lock:
            return [
                {
                    "task_id": pr.task_id,
                    "kind": pr.kind,
                    "path": pr.path,
                    "payload": pr.payload,
                }
                for pr in self._pending.values()
            ]

    def get(self, task_id: str) -> Optional[PendingReview]:
        with self._lock:
            return self._pending.get(task_id)

    def submit_decision(self, task_id: str, decision: dict) -> bool:
        pr = self.get(task_id)
        if pr is None:
            return False
        try:
            pr.decision_queue.put_nowait(decision)
        except queue.Full:
            return False
        return True

    def wait_for_decision(self, task_id: str) -> dict:
        """Blocks the calling (import pipeline) thread until the web UI
        submits a decision for this task."""
        pr = self.get(task_id)
        decision = pr.decision_queue.get()  # blocks
        with self._lock:
            self._pending.pop(task_id, None)
        return decision


class InboxWorkerPool:
    """Runs one ImportSession per album path, bounded by max_workers."""

    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._futures: dict[str, Any] = {}

    def submit(self, path: str, run_fn):
        """run_fn: callable(path) -> None, executed in the pool."""
        fut = self._executor.submit(run_fn, path)
        self._futures[path] = fut
        return fut

    def is_running(self, path: str) -> bool:
        fut = self._futures.get(path)
        if fut is None:
            return False
        return fut.running() or not fut.done()

    def running_paths(self) -> set[str]:
        return {p for p, fut in self._futures.items() if fut.running() or not fut.done()}

    def shutdown(self):
        self._executor.shutdown(wait=False)

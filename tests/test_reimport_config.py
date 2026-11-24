"""Reimport and the Apply Lock (ADR-0005, revised): the session takes the
lock only to apply, and run_reimport releases it however the session ends."""
from __future__ import annotations

import threading
from unittest.mock import MagicMock

import beets
import pytest

from beetsplug.webimport.reimport import run_reimport
from beetsplug.webimport.session import WebImportSession


def _reimport(apply_lock, **kw):
    run_reimport(lib=MagicMock(), review_manager=MagicMock(), loghandler=MagicMock(), album_ids=[123],
                 apply_lock=apply_lock, from_scratch=True, set_fields={"reimport_field": "custom"}, **kw)


def test_run_reimport_doesnt_hold_the_apply_lock_or_touch_global_config(monkeypatch):
    before = (beets.config["import"]["from_scratch"].get(bool), beets.config["import"]["set_fields"].get(dict))
    apply_lock = threading.Lock()
    seen = {}

    def run(session):
        seen["locked"] = apply_lock.locked()
        seen["config"] = (beets.config["import"]["from_scratch"].get(bool),
                          beets.config["import"]["set_fields"].get(dict))
        seen["session"] = (session.reimport_from_scratch, session.reimport_set_fields)
        session._acquire_apply_lock()  # as when a choice is applied

    monkeypatch.setattr(WebImportSession, "run", run)
    _reimport(apply_lock)
    assert seen == {"locked": False, "config": before, "session": (True, {"reimport_field": "custom"})}
    assert not apply_lock.locked()  # released after the apply


def test_run_reimport_releases_the_apply_lock_on_exception(monkeypatch):
    apply_lock = threading.Lock()

    def run(session):
        session._acquire_apply_lock()
        raise RuntimeError("boom during apply")

    monkeypatch.setattr(WebImportSession, "run", run)
    with pytest.raises(RuntimeError, match="boom during apply"):
        _reimport(apply_lock)
    assert not apply_lock.locked()

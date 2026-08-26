from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import beets
import pytest

from beetsplug.webimport.reimport import _temporary_import_config, run_reimport
from beetsplug.webimport.session import WebImportSession


@pytest.fixture(autouse=True)
def _reset_beets_config():
    """Ensure beets.config has clean import settings before and after each test."""
    orig_from_scratch = beets.config["import"]["from_scratch"].get(bool)
    orig_set_fields = beets.config["import"]["set_fields"].get(dict)
    yield
    beets.config["import"]["from_scratch"].set(orig_from_scratch)
    beets.config["import"]["set_fields"].set(orig_set_fields)


def test_temporary_config_mutation_and_clean_exit_restore():
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"initial": "value"})

    with _temporary_import_config(from_scratch=True, set_fields={"navidrome_library": "kids"}):
        assert beets.config["import"]["from_scratch"].get(bool) is True
        current_fields = beets.config["import"]["set_fields"].get(dict)
        assert current_fields == {"initial": "value", "navidrome_library": "kids"}

    assert beets.config["import"]["from_scratch"].get(bool) is False
    assert beets.config["import"]["set_fields"].get(dict) == {"initial": "value"}


def test_temporary_config_restores_on_exception():
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"initial": "value"})

    with pytest.raises(RuntimeError, match="simulated failure"):
        with _temporary_import_config(from_scratch=True, set_fields={"navidrome_library": "kids"}):
            assert beets.config["import"]["from_scratch"].get(bool) is True
            raise RuntimeError("simulated failure")

    assert beets.config["import"]["from_scratch"].get(bool) is False
    assert beets.config["import"]["set_fields"].get(dict) == {"initial": "value"}


def test_set_fields_merges_without_replacing_and_undoes_merge():
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"a": "1", "b": "2"})

    with _temporary_import_config(from_scratch=False, set_fields={"b": "overridden", "c": "3"}):
        merged = beets.config["import"]["set_fields"].get(dict)
        assert merged == {"a": "1", "b": "overridden", "c": "3"}

    restored = beets.config["import"]["set_fields"].get(dict)
    assert restored == {"a": "1", "b": "2"}
    assert "c" not in restored


def test_temporary_config_with_none_or_empty_set_fields():
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"keep": "me"})

    with _temporary_import_config(from_scratch=True, set_fields=None):
        assert beets.config["import"]["from_scratch"].get(bool) is True
        assert beets.config["import"]["set_fields"].get(dict) == {"keep": "me"}

    assert beets.config["import"]["from_scratch"].get(bool) is False
    assert beets.config["import"]["set_fields"].get(dict) == {"keep": "me"}


def test_run_reimport_holds_apply_lock_and_guards_concurrent_threads(monkeypatch):
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"orig": "1"})

    apply_lock = threading.Lock()
    reimport_running = threading.Event()
    can_finish_reimport = threading.Event()
    inside_reimport_observed = {}
    concurrent_observed = {}

    def mock_run(session_self):
        # Inside reimport: lock must be acquired and session marked accordingly
        inside_reimport_observed["lock_locked"] = apply_lock.locked()
        inside_reimport_observed["session_lock_acquired"] = session_self._lock_acquired
        inside_reimport_observed["from_scratch"] = beets.config["import"]["from_scratch"].get(bool)
        inside_reimport_observed["set_fields"] = beets.config["import"]["set_fields"].get(dict)

        # Calling _acquire_apply_lock() inside session should be a safe no-op (no re-acquire / deadlock)
        session_self._acquire_apply_lock()

        reimport_running.set()
        can_finish_reimport.wait(timeout=5.0)

    monkeypatch.setattr(WebImportSession, "run", mock_run)

    def target_reimport():
        run_reimport(
            lib=MagicMock(),
            review_manager=MagicMock(),
            loghandler=MagicMock(),
            album_ids=[123],
            apply_lock=apply_lock,
            from_scratch=True,
            set_fields={"reimport_field": "custom"},
        )

    def target_concurrent():
        reimport_running.wait(timeout=5.0)
        # Concurrent thread simulates a fresh-import review apply step that needs apply_lock
        with apply_lock:
            concurrent_observed["from_scratch"] = beets.config["import"]["from_scratch"].get(bool)
            concurrent_observed["set_fields"] = beets.config["import"]["set_fields"].get(dict)

    t_reimport = threading.Thread(target=target_reimport)
    t_concurrent = threading.Thread(target=target_concurrent)

    t_reimport.start()
    t_concurrent.start()

    assert reimport_running.wait(timeout=5.0)
    # At this point, t_reimport is running and holds the lock; t_concurrent is blocked waiting for apply_lock
    assert apply_lock.locked() is True

    # Allow reimport to complete and release lock
    can_finish_reimport.set()
    t_reimport.join(timeout=5.0)
    t_concurrent.join(timeout=5.0)

    assert not t_reimport.is_alive()
    assert not t_concurrent.is_alive()

    # Reimport saw mutated config while holding lock
    assert inside_reimport_observed["lock_locked"] is True
    assert inside_reimport_observed["session_lock_acquired"] is True
    assert inside_reimport_observed["from_scratch"] is True
    assert inside_reimport_observed["set_fields"] == {"orig": "1", "reimport_field": "custom"}

    # Concurrent thread only acquired lock after reimport finished and saw restored config
    assert concurrent_observed["from_scratch"] is False
    assert concurrent_observed["set_fields"] == {"orig": "1"}

    # Global lock is released after all complete
    assert apply_lock.locked() is False


def test_run_reimport_releases_apply_lock_on_exception(monkeypatch):
    beets.config["import"]["from_scratch"].set(False)
    beets.config["import"]["set_fields"].set({"orig": "1"})

    apply_lock = threading.Lock()

    def mock_run_fail(session_self):
        assert apply_lock.locked() is True
        assert session_self._lock_acquired is True
        assert beets.config["import"]["from_scratch"].get(bool) is True
        raise RuntimeError("boom during session.run")

    monkeypatch.setattr(WebImportSession, "run", mock_run_fail)

    with pytest.raises(RuntimeError, match="boom during session.run"):
        run_reimport(
            lib=MagicMock(),
            review_manager=MagicMock(),
            loghandler=MagicMock(),
            album_ids=[123],
            apply_lock=apply_lock,
            from_scratch=True,
            set_fields={"reimport_field": "custom"},
        )

    # Lock is cleanly released and config is restored even after exception
    assert apply_lock.locked() is False
    assert beets.config["import"]["from_scratch"].get(bool) is False
    assert beets.config["import"]["set_fields"].get(dict) == {"orig": "1"}

from __future__ import annotations

import beets
import pytest

from beetsplug.webimport.reimport import _temporary_import_config


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

from __future__ import annotations

from beets.library import Library


def test_disposable_library_fixture(lib: Library):
    assert lib is not None
    assert list(lib.items()) == []
    assert list(lib.albums()) == []

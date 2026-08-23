from __future__ import annotations

import tempfile
import wave
from pathlib import Path

import pytest
from beets.library import Library


def make_wav_file(path: Path) -> Path:
    """Helper to create a minimal valid WAVE audio file that mutagen/mediafile

    can parse and write metadata tags to.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(44100)
        w.writeframes(b"\x00" * 100)
    return path


@pytest.fixture
def create_wav_file():
    return make_wav_file


@pytest.fixture
def lib(tmp_path: Path) -> Library:
    """Yields a disposable beets Library backed by an isolated SQLite database

    and music directory within tmp_path. No network access or running server required.
    Torn down automatically after each test with tmp_path cleanup.
    """
    db_path = str(tmp_path / "test_library.db")
    music_dir = str(tmp_path / "music")
    (tmp_path / "music").mkdir(parents=True, exist_ok=True)
    library = Library(db_path, music_dir)
    return library

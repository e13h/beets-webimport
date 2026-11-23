"""Which build is running (version.py)."""
from beetsplug.webimport import version


def test_tags_from_git_archive_refs():
    assert version._tags("HEAD -> main, tag: v0.1.0, origin/main") == ["v0.1.0"]
    assert version._tags("") == []


def test_archive_placeholders_win(monkeypatch):
    monkeypatch.setattr(version, "_ARCHIVE", {"commit": "a" * 40, "date": "2026-11-23T10:00:00-08:00",
                                              "refs": "HEAD -> main, tag: v0.1.0"})
    version.info.cache_clear()
    try:
        v = version.info()
        assert (v["commit"], v["tags"], v["source"], v["dirty"]) == ("a" * 40, ["v0.1.0"], "archive", False)
        assert v["label"] == f"{v['version']} (aaaaaaa)"
    finally:
        version.info.cache_clear()


def test_git_checkout(monkeypatch):
    version.info.cache_clear()
    try:
        v = version.info()
        assert v["source"] == "git" and len(v["commit"]) == 40 and v["label"].startswith(v["version"])
    finally:
        version.info.cache_clear()

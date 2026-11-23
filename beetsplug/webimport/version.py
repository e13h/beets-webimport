"""Which build of the plugin is running.

The homelab installs GitHub's tarball of `main`, which has no git
metadata. `git archive` (and so GitHub's archive downloads) fills in the
`$Format:...$` placeholders below for files marked `export-subst` in
.gitattributes, so the tarball knows its commit. A git checkout (dev,
editable install) asks git instead.
"""
from __future__ import annotations

import subprocess
from functools import lru_cache
from importlib import metadata
from pathlib import Path

_ARCHIVE = {"commit": "$Format:%H$", "date": "$Format:%cI$", "refs": "$Format:%D$"}


def _tags(refs: str) -> list[str]:
    return [r.strip()[5:] for r in refs.split(",") if r.strip().startswith("tag: ")]


def _git(*args: str) -> str:
    here = Path(__file__).resolve().parent
    return subprocess.run(["git", "-C", str(here), *args], capture_output=True, text=True,
                          timeout=5, check=True).stdout.strip()


def _from_git() -> dict | None:
    try:
        commit = _git("rev-parse", "HEAD")
        date = _git("log", "-1", "--format=%cI")
        tags = _git("tag", "--points-at", "HEAD").split()
        dirty = bool(_git("status", "--porcelain", "--untracked-files=no"))
    except (OSError, subprocess.SubprocessError):
        return None
    return {"commit": commit, "date": date, "tags": tags, "dirty": dirty, "source": "git"}


@lru_cache(maxsize=1)
def info() -> dict:
    try:
        version = metadata.version("beets-webimport")
    except metadata.PackageNotFoundError:
        version = "unknown"
    if not _ARCHIVE["commit"].startswith("$"):
        build = {"commit": _ARCHIVE["commit"], "date": _ARCHIVE["date"], "tags": _tags(_ARCHIVE["refs"]),
                 "dirty": False, "source": "archive"}
    else:
        build = _from_git() or {"commit": None, "date": None, "tags": [], "dirty": False, "source": None}
    short = (build["commit"] or "")[:7]
    label = version
    if short:
        label += f" ({short}{'-dirty' if build['dirty'] else ''})"
    return {"version": version, **build, "label": label}

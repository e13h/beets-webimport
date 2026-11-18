"""Guards against developing under assumptions that differ from deployment.

The dev config (.config/config.yaml) is the homelab config (.config/homelab.yaml,
a verbatim copy) plus path-only overrides (.config/local.yaml). These tests
fail when the copy drifts from the selfhosted repo, when local.yaml starts
overriding behavior instead of paths, or when the local environment can't load
every plugin the homelab runs.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
CONFIG_DIR = REPO / ".config"
HOMELAB_COPY = CONFIG_DIR / "homelab.yaml"
LOCAL_OVERRIDES = CONFIG_DIR / "local.yaml"

# Override with HOMELAB_BEETS_CONFIG if the selfhosted repo lives elsewhere.
SELFHOSTED_CONFIG = Path(
    os.environ.get(
        "HOMELAB_BEETS_CONFIG",
        REPO.parent / "selfhosted/services/reptile/beets/config-beets/config.yaml",
    )
)

# Container mount points and the Navidrome endpoint (a local test container
# in dev), which legitimately differ on a dev machine.
ALLOWED_LOCAL_KEYS = {
    ("directory",),
    ("library",),
    ("import", "log"),
    ("webimport", "inbox_dir"),
    ("webimport", "navidrome", "url"),
    ("webimport", "navidrome", "user"),
    ("webimport", "navidrome", "password"),
}


def _leaf_keys(d, prefix=()):
    for k, v in d.items():
        if isinstance(v, dict):
            yield from _leaf_keys(v, prefix + (k,))
        else:
            yield prefix + (k,)


def test_homelab_copy_matches_selfhosted_repo():
    if not SELFHOSTED_CONFIG.exists():
        pytest.skip(f"selfhosted config not found at {SELFHOSTED_CONFIG}")
    assert HOMELAB_COPY.read_text() == SELFHOSTED_CONFIG.read_text(), (
        f"{HOMELAB_COPY} has drifted from {SELFHOSTED_CONFIG}. Copy whichever "
        "side has the intended change over the other."
    )


def test_local_overrides_are_paths_only():
    local = yaml.safe_load(LOCAL_OVERRIDES.read_text()) or {}
    extra = set(_leaf_keys(local)) - ALLOWED_LOCAL_KEYS
    assert not extra, (
        f"local.yaml overrides non-path settings {sorted(extra)}; put behavior "
        "changes in homelab.yaml so they ship to the homelab too."
    )


def test_dev_config_includes_homelab_then_local():
    main = yaml.safe_load((CONFIG_DIR / "config.yaml").read_text())
    assert main == {"include": ["homelab.yaml", "local.yaml"]}


def test_all_homelab_plugins_load_locally():
    wanted = yaml.safe_load(HOMELAB_COPY.read_text())["plugins"]
    beet = Path(sys.executable).parent / "beet"
    proc = subprocess.run(
        [str(beet), "version"],
        env={**os.environ, "BEETSDIR": str(CONFIG_DIR)},
        capture_output=True,
        text=True,
        cwd=REPO,
    )
    match = re.search(r"^plugins: (.*)$", proc.stdout, re.M)
    loaded = set(match.group(1).split(", ")) if match else set()
    missing = sorted(set(wanted) - loaded)
    assert not missing, (
        f"homelab plugins not loading locally: {missing}. Usually a missing "
        "dependency (chroma: `brew install chromaprint` + pyacoustid; "
        "replaygain: `brew install mp3gain`).\n" + proc.stderr[-2000:]
    )

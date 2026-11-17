#!/usr/bin/env bash
# Run the webimport dev server against the repo-local config (.config/,
# which mirrors the homelab config). Extra args go to `beet webimport`.
set -euo pipefail
cd "$(dirname "$0")/.."
export BEETSDIR=./.config
exec .venv/bin/beet webimport "$@"

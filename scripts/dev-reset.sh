#!/usr/bin/env bash
# Reset the disposable dev library to a clean slate so the inbox can be
# imported again from scratch.
#
#   scripts/dev-reset.sh           reset (stops a running dev server first)
#   scripts/dev-reset.sh --start   reset, then start the dev server
#
# Removes only repo-local, git-ignored state: the library DB and its
# migration backups, imported files (.library/), beets' import state,
# plugin data (thumbnails, tags), the import log, and the
# .webimport_imported markers that make inbox folders look imported.
# Never touches inbox audio files or staging bins (.inbox/_grouped/).
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${DEV_PORT:-8338}"
start=false
for arg in "$@"; do
  case "$arg" in
    --start) start=true ;;
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

# Deleting the DB under a running server leaves it serving stale state.
for pid in $(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true); do
  if ps -o command= -p "$pid" | grep -q "beet.*webimport"; then
    echo "Stopping dev server (pid $pid, port $PORT)"
    kill "$pid"
    for _ in $(seq 1 50); do kill -0 "$pid" 2>/dev/null || break; sleep 0.1; done
  else
    echo "Port $PORT is used by something other than beet webimport; leaving it alone." >&2
  fi
done

echo "Resetting dev library state"
rm -f .config/library.db .config/library.db-*.bak .config/state.pickle .config/beet.log
rm -rf .library .config/webimport
markers=$(find .inbox -name .webimport_imported -print -delete 2>/dev/null | wc -l | tr -d ' ')
echo "Removed $markers import marker(s) from .inbox"

if $start; then
  echo "Starting dev server on port $PORT"
  exec scripts/dev-server.sh
fi
echo "Done. Start the server with: scripts/dev-server.sh"

#!/usr/bin/env bash
# Reset the disposable dev library to a clean slate so the inbox can be
# imported again from scratch.
#
#   scripts/dev-reset.sh           reset (stops a running dev server first)
#   scripts/dev-reset.sh --start   reset, then start the dev server
#   scripts/dev-reset.sh --force   reset even if some imports can't be undone
#                                  (e.g. copy-mode imports, whose inbox copies
#                                  are still there)
#
# Imports move files out of .inbox (move mode), so first every album is
# undone: the original files go back to .inbox byte for byte. If any
# can't be restored, the reset stops and nothing is deleted.
#
# Then removes only repo-local, git-ignored state: the library DB and its
# migration backups, imported files (.library/), stored originals, beets'
# import state, plugin data (thumbnails, tags), the import log, and any
# .webimport_imported markers left from copy-mode imports.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${DEV_PORT:-8338}"
start=false
force=false
for arg in "$@"; do
  case "$arg" in
    --start) start=true ;;
    --force) force=true ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
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

if [ -f .config/library.db ]; then
  echo "Putting imported files back in .inbox"
  if ! BEETSDIR=./.config .venv/bin/python scripts/dev-undo-all.py; then
    if $force; then
      echo "Some imports couldn't be undone (above); --force: deleting anyway." >&2
    else
      echo "Some imports couldn't be undone (above); not deleting anything. Use --force if their files are safe elsewhere." >&2
      exit 1
    fi
  fi
fi

echo "Resetting dev library state"
rm -f .config/library.db .config/library.db-*.bak .config/state.pickle .config/beet.log
rm -rf .library .config/webimport .config/webimport-originals
markers=$(find .inbox -name .webimport_imported -print -delete 2>/dev/null | wc -l | tr -d ' ')
echo "Removed $markers import marker(s) from .inbox"

if $start; then
  echo "Starting dev server on port $PORT"
  exec scripts/dev-server.sh
fi
echo "Done. Start the server with: scripts/dev-server.sh"

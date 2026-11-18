#!/usr/bin/env bash
# Reset the dev environment: empty library, and .inbox back to its
# saved initial state (.inbox-pristine/).
#
#   scripts/dev-reset.sh               reset (stops a running dev server first)
#   scripts/dev-reset.sh --start       reset, then start the dev server
#   scripts/dev-reset.sh --save-inbox  make the current .inbox the saved state
#                                      (after adding test files), then reset
#   scripts/dev-reset.sh --force       reset even if .inbox has files the saved
#                                      state doesn't (they're deleted)
#
# Imports move files out of .inbox, so the reset doesn't try to put them
# back: it deletes all dev state (library DB, .library/, stored originals,
# import state, plugin data, log, .inbox) and recreates .inbox from
# .inbox-pristine/. On macOS the copy is an APFS clone: instant, and no
# extra disk space until a file changes. The first run saves the current
# .inbox as .inbox-pristine/.
#
# .inbox-pristine/ holds real purchased music: it's git-ignored.
set -euo pipefail
cd "$(dirname "$0")/.."

PORT="${DEV_PORT:-8338}"
PRISTINE=.inbox-pristine
start=false force=false save=false
for arg in "$@"; do
  case "$arg" in
    --start) start=true ;;
    --force) force=true ;;
    --save-inbox) save=true ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

clone() {  # clone dir $1 to $2 (copy-on-write where the filesystem allows)
  cp -cR "$1" "$2" 2>/dev/null || cp -R --reflink=auto "$1" "$2" 2>/dev/null || cp -R "$1" "$2"
}

# Files in a folder (relative paths), ignoring webimport's own hidden files.
files() { (cd "$1" && find . -type f ! -name '.*' ! -path '*/.*' | sort); }

if $save || [ ! -d "$PRISTINE" ]; then
  [ -d .inbox ] || { echo "No .inbox to save." >&2; exit 1; }
  echo "Saving the current .inbox as the initial state ($PRISTINE/)"
  rm -rf "$PRISTINE.tmp"
  clone .inbox "$PRISTINE.tmp"
  find "$PRISTINE.tmp" \( -name '.webimport*' -o -name '.DS_Store' \) -prune -exec rm -rf {} + 2>/dev/null || true
  rm -rf "$PRISTINE"
  mv "$PRISTINE.tmp" "$PRISTINE"
elif [ -d .inbox ] && ! $force; then
  extra=$(comm -23 <(files .inbox) <(files "$PRISTINE"))
  if [ -n "$extra" ]; then
    echo "These .inbox files aren't in the saved initial state and would be deleted:" >&2
    echo "$extra" | sed 's/^/  /' >&2
    echo "Run with --save-inbox to keep them (saves .inbox as the new initial state), or --force to delete them." >&2
    exit 1
  fi
fi

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

echo "Resetting dev state"
rm -f .config/library.db .config/library.db-*.bak .config/state.pickle .config/beet.log
rm -rf .library .config/webimport .config/webimport-originals .inbox
clone "$PRISTINE" .inbox
echo "Restored .inbox: $(files .inbox | wc -l | tr -d ' ') files"

if $start; then
  echo "Starting dev server on port $PORT"
  exec scripts/dev-server.sh
fi
echo "Done. Start the server with: scripts/dev-server.sh"

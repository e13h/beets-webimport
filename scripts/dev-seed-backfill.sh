#!/usr/bin/env bash
# Dev setup for Backfill (ADR-0016): a library like the homelab's (tracks
# imported before originals were kept) plus store downloads in the inbox.
#
#   scripts/dev-seed-backfill.sh [--start]
#
# Needs .backfill-fixture/server/ (git-ignored), copied read-only from the
# server:
#   music/<navidrome_library>/<artist>/<album>/...   library files
#   downloads/<artist>/...                            the store downloads
# The library files are imported as-is with plain `beet import` (no
# webimport session, so no originals are saved, as on the homelab), and
# .inbox is replaced by the downloads. `scripts/dev-reset.sh --force`
# goes back to the normal dev state.
set -euo pipefail
cd "$(dirname "$0")/.."
FIX=.backfill-fixture/server
[ -d "$FIX/music" ] && [ -d "$FIX/downloads" ] || { echo "Missing $FIX/{music,downloads}" >&2; exit 1; }

scripts/dev-reset.sh --force >/dev/null
export BEETSDIR=./.config
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
for group in "$FIX"/music/*/; do
  name=$(basename "$group")
  for album in "$group"*/*/; do
    dest="$tmp/$name/$(basename "$(dirname "$album")")/$(basename "$album")"
    mkdir -p "$(dirname "$dest")"
    cp -cR "$album" "$dest" 2>/dev/null || cp -R "$album" "$dest"
    .venv/bin/beet import -q -A --set navidrome_library="$name" "$dest" >/dev/null 2>&1 || {
      echo "import failed: $album" >&2; exit 1; }
  done
done
rm -rf .inbox
cp -cR "$FIX/downloads" .inbox 2>/dev/null || cp -R "$FIX/downloads" .inbox
echo "Library: $(.venv/bin/beet ls | wc -l | tr -d ' ') tracks in $(.venv/bin/beet ls -a | wc -l | tr -d ' ') albums"
echo "Inbox: $(find .inbox -type f ! -name '.*' | wc -l | tr -d ' ') files"
if [ "${1:-}" = "--start" ]; then exec scripts/dev-server.sh; fi

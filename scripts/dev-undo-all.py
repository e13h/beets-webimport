"""Undo every import in the dev library, putting the original files back in
.inbox (byte for byte). Run by dev-reset.sh before it deletes anything:
in move mode the imported files are the only copies.

Exit status 1 if any album (or a track not in an album) couldn't be
restored; dev-reset.sh then stops without deleting the library.
"""
from __future__ import annotations

import sys

from beets import config
from beets.library import Library


def main() -> int:
    config.read()
    lib = Library(config["library"].as_filename(), config["directory"].as_filename())
    inbox = config["webimport"]["inbox_dir"].get(str)

    from beetsplug.webimport import restore

    failed = 0
    for album in list(lib.albums()):
        try:
            r = restore.undo(lib, album, inbox)
            other = f", {r['other_files']} other file(s)" if r["other_files"] else ""
            print(f"restored {album.albumartist} - {album.album}: {r['audio_files']} track(s){other}")
        except restore.UndoRefused as exc:
            failed += 1
            print(f"CAN'T RESTORE {album.albumartist} - {album.album}: {exc}", file=sys.stderr)
            for p in exc.plan.problems:
                print(f"  - {p}", file=sys.stderr)
    singles = list(lib.items("singleton:true"))
    if singles:
        failed += len(singles)
        print(f"CAN'T RESTORE {len(singles)} track(s) imported as singletons (no album to undo).", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

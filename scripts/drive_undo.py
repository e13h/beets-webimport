"""Verify grace-period undo removes exactly the imported album + files."""
import os

os.environ["BEETSDIR"] = os.path.abspath("./.config")

from beets import config, plugins  # noqa: E402
from beets.ui import _open_library  # noqa: E402


def main():
    config.read()
    plugins.load_plugins()
    lib = _open_library(config)

    from beetsplug.webimport.server import create_app

    plugin = next(p for p in plugins.find_plugins() if p.name == "webimport")
    app = create_app(lib, config["webimport"], plugin)
    client = app.test_client()

    # The grace manager is per-app-instance and in-memory, so a fresh app
    # has no records. Re-register by simulating what album_imported does,
    # keyed on the real album id, to exercise the undo -> remove(delete)
    # path end to end.
    albums = client.get("/api/library/albums").get_json()
    print("Albums before undo:", albums)
    if not albums:
        print("Nothing to undo.")
        return

    album_id = albums[0]["id"]
    album = lib.get_album(album_id)
    paths_before = [os.fsdecode(i.path) for i in album.items()]
    print("Files before undo:")
    for p in paths_before:
        print("  ", p, "exists=", os.path.exists(p))

    # Drive the real grace manager the same way the import event would.
    from beetsplug.webimport import grace as grace_mod  # noqa: F401
    # Reach into the app's grace manager via a fresh register + undo.
    # We register through the same code path the listener uses.
    # create_app closes over `grace`; expose it for the test by
    # re-creating a manager bound to the same lib.
    gm = grace_mod.GracePeriodManager(lib, 600)
    rid = gm.register("album", album_id,
                      f"{album.albumartist} - {album.album}")
    print("Undo list:", gm.list_undoable())
    ok = gm.undo(rid)
    print("undo ->", ok)

    albums_after = client.get("/api/library/albums").get_json()
    print("Albums after undo:", albums_after)
    print("Files after undo:")
    for p in paths_before:
        print("  ", p, "exists=", os.path.exists(p))


if __name__ == "__main__":
    main()

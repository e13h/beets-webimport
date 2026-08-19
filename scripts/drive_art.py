"""Exercise the cover-art resolve endpoint against the real target MBID."""
import os

os.environ["BEETSDIR"] = os.path.abspath("./.config")

from beets import config, plugins  # noqa: E402
from beets.ui import _open_library  # noqa: E402

TARGET_RELEASE = "a5483fb3-634b-4254-a966-de33cefd1f17"
INBOX = ("/Users/evansmith/repos/beets-web-import/.inbox/"
         "Mulan (Original Motion Picture Soundtrack)")


def main():
    config.read()
    plugins.load_plugins()
    lib = _open_library(config)

    from beetsplug.webimport.server import create_app

    plugin = next(p for p in plugins.find_plugins() if p.name == "webimport")
    app = create_app(lib, config["webimport"], plugin)
    client = app.test_client()

    print("fetchart in config:", "fetchart" in config)

    r = client.post("/api/coverart/resolve", json={
        "item_dir": INBOX,
        "release_mbid": TARGET_RELEASE,
        "release_group_mbid": None,
    })
    print("status:", r.status_code)
    print("result:", r.get_json())


if __name__ == "__main__":
    main()

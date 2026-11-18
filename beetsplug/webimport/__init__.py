"""beets-webimport: native beets plugin serving a web UI for import review,
library browsing/editing, tagging, and multi-library routing.

See ../../README.md and the PRD for full context. This module only wires
the plugin into beets (config defaults + CLI command); the actual logic
lives in the sibling modules.
"""
from __future__ import annotations

import logging

from beets.plugins import BeetsPlugin
from beets.ui import Subcommand

log = logging.getLogger("beets.webimport")


class WebImportPlugin(BeetsPlugin):
    def __init__(self):
        super().__init__("webimport")

        # Defaults. Anything here can be overridden in config.yaml under
        # a top-level `webimport:` key.
        self.config.add(
            {
                "host": "0.0.0.0",
                "port": 8338,
                "inbox_dir": "",  # falls back to import.paths / user-set
                "tag_fields": ["mood"],
                "candidate_search_workers": 4,
                "thumbnail_cache_dir": "",  # falls back to beets config dir
                "debug": False,  # enables Flask debug mode + the reloader
                # iTunes purchases: look up the MusicBrainz release linked
                # to the album's Apple Music listing and use it as the
                # Direct ID when no ID was given.
                "apple_music_match": True,
                # Navidrome integration (Pending Move, ADR-0011): moves
                # that follow a tag write wait for Navidrome to scan the
                # new tags, so tracks keep their play history, stars and
                # playlist entries. Off unless url and user are set. Keep
                # the password out of config files: set it in the
                # WEBIMPORT_NAVIDROME_PASSWORD environment variable.
                "navidrome": {
                    "url": "",
                    "user": "",
                    "password": "",
                    # Ask Navidrome for a scan if none came this many
                    # seconds after a write (needs an admin user; a
                    # regular user just keeps waiting for the watcher).
                    "scan_request_after": 60,
                },
            }
        )

    def commands(self):
        cmd = Subcommand(
            "webimport",
            help="run the beets-webimport web server",
        )
        cmd.func = self._run

        cmd.parser.add_option(
            "--host",
            dest="host",
            help="host to bind (default from config)",
        )
        cmd.parser.add_option(
            "--port",
            dest="port",
            type="int",
            help="port to bind (default from config)",
        )
        cmd.parser.add_option(
            "--debug",
            dest="debug",
            action="store_true",
            default=None,
            help="enable Flask debug mode + auto-reload (default from config)",
        )
        return [cmd]

    def _run(self, lib, opts, args):
        # Imported lazily so `beet` itself stays fast to invoke for
        # unrelated commands (Flask etc. aren't imported unless this
        # subcommand actually runs).
        from .server import create_app

        host = opts.host or self.config["host"].get(str)
        port = opts.port or self.config["port"].get(int)
        debug = opts.debug if opts.debug is not None else self.config["debug"].get(bool)

        app = create_app(lib, self.config, self)
        log.info(
            "beets-webimport serving on http://%s:%s%s",
            host,
            port,
            " (debug/reload enabled)" if debug else "",
        )
        # threaded=True is needed regardless of debug mode: the UI polls
        # several endpoints concurrently while background worker threads
        # (InboxWorkerPool, etc.) are also running.
        app.run(host=host, port=port, debug=debug, use_reloader=debug, threaded=True)

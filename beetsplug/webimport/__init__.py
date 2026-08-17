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
                "grace_period_seconds": 600,
                "inbox_dir": "",  # falls back to import.paths / user-set
                "tag_fields": ["mood"],
                "candidate_search_workers": 4,
                "thumbnail_cache_dir": "",  # falls back to beets config dir
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
        return [cmd]

    def _run(self, lib, opts, args):
        # Imported lazily so `beet` itself stays fast to invoke for
        # unrelated commands (Flask etc. aren't imported unless this
        # subcommand actually runs).
        from .server import create_app

        host = opts.host or self.config["host"].get(str)
        port = opts.port or self.config["port"].get(int)

        app = create_app(lib, self.config, self)
        log.info("beets-webimport serving on http://%s:%s", host, port)
        app.run(host=host, port=port, threaded=True)

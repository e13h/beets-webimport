# beets-webimport

A native beets plugin (not a separate app) that serves a mobile-friendly
web UI for:

- Reviewing inbox imports (parallel candidate review, serial apply queue)
- MusicBrainz ID / URL paste-to-match
- Dual cover-art preview (source vs. resolved-by-fetchart)
- Grace-period undo (ID-scoped `remove -d`, safe for `copy: yes` configs)
- Library browsing/search, per-track and per-album metadata editing,
  bulk edit, with automatic `--move` on any path-affecting field change
- Custom tag vocabulary (e.g. `mood`) with track/album drag-drop assignment
- `navidrome_library` assignment feeding your `$navidrome_library` path
  variable
- Reimport UI (`-L -S <mbid> --from-scratch --set field=value` equivalent)

See `.scratch/webimport/spec.md` for the full requirements this
implements, `CONTEXT.md` for domain vocabulary, and `docs/adr/` for the
hard-to-reverse design decisions behind it.

## Install

```bash
pip install -e /path/to/beets-webimport
```

Add to your beets `config.yaml`:

```yaml
plugins: [..., webimport]

webimport:
  host: 0.0.0.0
  port: 8338
  grace_period_seconds: 600
  inbox_dir: /inbox/preview
  tag_fields:
    - mood
  debug: false  # set true for Flask debug mode + auto-reload on code changes
```

Run it:

```bash
beet webimport
```

For development, enable debug mode (Flask's debugger + the Werkzeug
auto-reloader, which restarts the server whenever plugin source files
change) either via config (`webimport.debug: true`) or a one-off flag:

```bash
beet webimport --debug
```

## Status / known simplifications

This is a working first implementation of the architecture, not a
polished final product. Notably:

- Frontend is vanilla JS/HTML (no build step) rather than a compiled
  React app — functional on desktop and mobile via CSS, but touch
  drag-and-drop is implemented with a simple long-press + "move to" menu
  rather than fully custom gesture handling. Treat as a base to refine.
- Cover-art "resolved" preview mirrors fetchart's source-priority order
  and queries the Cover Art Archive via the same JSON API fetchart uses
  (picking the first Front image), so the preview matches what an import
  would embed. It previews the `filesystem` and `coverart` (CAA) sources
  only; other remote sources (itunes, amazon, ...) are honored in the
  ordering but not fetched for preview, and embedart's actual file write
  isn't executed during preview.
- Duplicate resolution (`resolve_duplicate`) is implemented but the UI
  for it is intentionally minimal (keep / remove-old / skip) — extend as
  needed.

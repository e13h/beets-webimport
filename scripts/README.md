# End-to-end test drivers

Reproducible harnesses that exercise the `webimport` plugin against the
real import pipeline (MusicBrainz + Cover Art Archive) by driving the
Flask app through its HTTP API with `test_client()` — i.e. acting as the
browser, no manual clicking required.

Run them from the **repo root** (they resolve `./.config` and `./.inbox`
relative to the current directory):

```bash
# Full inbox import: candidate review -> force target MBID -> apply.
# Verifies copy-mode file placement, set_fields, art embedding, and that
# the album_imported event registers a grace-period undo record.
.venv/bin/python scripts/drive_import.py

# Grace-period undo: ID-scoped remove(delete=True) wipes the album's DB
# row + files, leaving the inbox originals untouched.
.venv/bin/python scripts/drive_undo.py

# Cover-art preview endpoint against a real release MBID (CAA JSON API).
.venv/bin/python scripts/drive_art.py

# Concurrency + duplicates: submits two albums at once to confirm
# parallel review, serial apply (no stuck apply_lock), and the duplicate
# resolution prompt.
.venv/bin/python scripts/drive_concurrency.py
```

These use a disposable library (`.config/library.db`) and music dir
(`.library/`) configured in `.config/config.yaml`. To reset between runs:

```bash
rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
```

The target release used by the drivers is the Mulan soundtrack:
`a5483fb3-634b-4254-a966-de33cefd1f17`.

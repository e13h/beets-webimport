# CONTEXT.md — glossary

A native, pip-installable **beets plugin** (`beetsplug/webimport/`) that
serves a Flask web UI for import review, library browsing, tagging, and
multi-library routing. Frontend is deliberately vanilla JS/HTML in
`beetsplug/webimport/static/` — no build step, no npm.

## Language

**Listening Group**:
User-facing concept for the category (kids, worship, holiday, talk radio,
regular, or any future value) that routes an album to a distinct Navidrome
library root. Implemented as the freeform beets flexible attribute
`navidrome_library` — not a fixed enum; any string typed or selected by the
user is a valid, new group. Autocomplete suggestions are derived live from
the distinct values already present in the library (not a separately
maintained vocabulary list, unlike Tag Vocabulary below) — a group only
appears as a suggestion once something has actually been routed to it, and
the user can always type a new value instead of picking a suggested one.
"Unassigned" is the reserved default value (`import.set_fields.
navidrome_library: unassigned`) applied to anything imported without an
explicit group choice; the library browse view must surface it as a
filterable state so nothing gets lost in it silently.
_Avoid_: navidrome_library (when referring to the user-facing concept —
reserve that name for the underlying field)

**Direct ID Import**:
Supplying a known release identifier (a bare MBID/UUID or any ID-bearing
URL the matching backend can parse, e.g. MusicBrainz or Discogs release
URLs) at the moment an import is started, so the initial broad candidate
search is skipped entirely in favor of a single targeted lookup. Distinct
from the search-by-ID override, which happens mid-review against an
already-completed candidate search. The targeted result still passes
through the normal review step before apply; a failed or empty lookup is
surfaced for correction rather than silently falling back to a heuristic
match. On a folder already imported, a Direct ID Import routes through
the Reimport flow (query-driven against the library record), not a fresh
path-driven session — avoiding the silent-duplicate trap.

**Grace Period**:
The configurable window (default ~10 minutes) after an import or reimport
apply during which the resulting Album/Item can be undone. Tracked
server-side as wall-clock time from the real `album_imported`/`item_imported`
event, independent of whether a browser client is currently connected. Lost
(not restored) if the plugin process restarts before it elapses — an
accepted, low-priority gap (see ADR-0004). Expiry has two effects: the
import becomes permanent (undo no longer available), and the originating
Staging Bin (if any) becomes eligible for inbox cleanup.

**Source Art**:
The cover image associated with the currently-selected import candidate
(from MusicBrainz/Spotify/etc.), one of the two thumbnails shown in
candidate review. Shows a "No Cover Art Available" placeholder when the
candidate has none — never substitutes Resolved Art in its place, so the
match/mismatch indicator stays meaningful.

**Resolved Art**:
The image fetchart/embedart will actually write to the file for the
currently-selected candidate, computed by running fetchart's real
resolution logic (source priority, minimum resolution, aspect ratio, local
`cover.jpg` precedence, overwrite rules) rather than a reimplementation of
those rules. Computed lazily, only for the highlighted candidate.

**Apply Lock**:
The single global mutual-exclusion lock serializing the db-write/move
("apply") step across concurrently-reviewed Import Tasks. Guarantees
applies never overlap; does not guarantee ordering between tasks.
_Avoid_: apply queue (implies a FIFO ordering guarantee that doesn't exist)

**Import Task**:
Beets' own `ImportTask`/`SingletonImportTask` — the unit of review,
identified by `task_id` in the review API (`/api/review/<task_id>/decide`).
One inbox submission normally yields one task; manual grouping can split
it into several, reviewed one after another.
_Avoid_: review unit, session (see Import Session — a session may contain
several tasks)

**Import Session** (`WebImportSession`):
One instance per inbox submission, occupying one slot in the
`InboxWorkerPool` and running beets' `ImportSession` pipeline. Parallel
review happens *across* sessions; the Import Task(s) within a single
session are still visited one at a time by the beets pipeline.

**Move-on-Field-Change**:
The general rule that any metadata edit — single field, single track/album,
or bulk — which changes an item's computed path (per `paths:` templates)
triggers an automatic move of the underlying file(s), since the config runs
`copy: yes`/`move: no` by default. Applies uniformly to every field; not a
special case limited to `navidrome_library`. Relies on beets'
`%aunique{}` template disambiguation for the common case; a genuine
destination collision beyond that is a Placement Conflict (below), deferred
past MVP.

**Placement Conflict**:
The umbrella concept for "two things want the same library slot," resolved
through the same skip/overwrite/keep-both decision shape regardless of what
triggered it. Two distinct triggers, both resolved this way:
- a beets-detected duplicate during import (via `duplicate_action: ask` /
  `get_duplicate_action`), or
- a destination collision from Move-on-Field-Change that `%aunique{}`
  doesn't resolve (deferred past MVP — see carry-forward list).

Naming this once, and reusing the same decision UI for both triggers, is
intentional — avoids inventing a fourth resolution shape later.

**Tag Vocabulary**:
The reusable, GUI-managed set of custom tag names/values (e.g. `mood`) that
the user can apply to tracks/albums via drag-and-drop, distinct from
Listening Group's live-derived autocomplete: Tag Vocabulary is an
explicitly curated list maintained ahead of use, not just "whatever's
already in the library." A new tag *value* is usable immediately; a new
tag *name* additionally requires a `navidrome.toml` edit + full Navidrome
rescan before Navidrome will index it.

**Staging Bin**:
An ad-hoc subdirectory under the inbox that manual grouping moves files
into, so the resulting directory matches one intended real album/single
before beets' own directory-based grouping runs a canonical import on it.
Chosen over constructing `ImportTask`/`SingletonImportTask` objects
directly from an arbitrary in-memory file list, so every import — split or
not — is an ordinary beets import (see ADR-0003). Survives past that
import, through the Grace Period, since splitting a ripped playlist into
bins is tedious and shouldn't have to be redone if the import is undone;
only cleared from the inbox once its Grace Period expires.
_Avoid_: bin (alone), in-memory grouping

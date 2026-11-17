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
the Reimport flow in the Library tab (query-driven against the library
record, per ADR-0005), not a fresh path-driven session — avoiding the
silent-duplicate trap. Two-Phase Edit applies to the Library-tab Reimport
apply, since those files already exist in Navidrome.

**Grace Period**:
The configurable, **destructive** auto-delete of inbox originals after an
import apply. On expiry the plugin performs the same action as Confirm
Import: inbox files and the marker are removed, making the import
permanent. Default **30 days**, configurable, and disable-able (then only
manual confirm removes originals). It does *not* bound undo of the library
record — undoability is scoped purely by the marker file (see Approve
Tab). Tracked server-side as wall-clock time from the real
`album_imported`/`item_imported` event; lost (not enforced) if the plugin
process restarts before expiry — an accepted, low-priority gap (see
ADR-0004). Staging Bins share this lifecycle.
_Avoid_: undo window (the grace period deletes originals; it no longer
bounds undo)

**Approve Tab**:
The inbox view (renamed from Undo) listing every folder bearing a
`.webimport_imported` marker — i.e. originals whose import is live in the
library. Shown as "imported N days ago" from the marker. Folders here
never appear in the Import tab. Two actions: **Undo import** (delete the
marked album from the library, remove the marker → folder returns to the
Import tab as unimported) and **Confirm Import**. No reimport here; redo
is undo-then-reimport.
_Avoid_: Undo tab (old name), Imported list

**Confirm Import**:
The Approve Tab action that permanently accepts an import: deletes the
inbox originals and the marker, leaving the library album untouched.
Equivalent to Grace Period expiry.
_Avoid_: delete from inbox (that described the old explicit folder
deletion, not the accept semantics)

**Pending Move**:
The advisory state of a library item whose metadata was written (phase 1
of ADR-0011) but whose file still sits at its old path, awaiting the
user's confirmation that Navidrome has picked up the change before the
move (phase 2) runs. Detected, never persisted: an actual-path vs.
computed-path mismatch means a move is owed (holds across restarts,
per ADR-0004). Superseded by any later move-producing operation; undone
away with the item.
_Avoid_: move queue, deferred move

**Art Choice**:
The album art the user picks in candidate review for after import: keep the
files' current embedded art, the selected release's Cover Art Archive art,
iTunes Store art (iTunes purchases), or an image file in the inbox folder.
webimport applies it as the album's art; embedart embeds it (ADR-0013).
_Avoid_: source art, resolved art (the retired dual preview)

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

**Two-Phase Edit**:
The rule (ADR-0011) that any library operation changing a file's computed
path — field edit, bulk edit, or Library-tab reimport apply — writes
metadata first and defers the move behind Pending Move confirmation, so
Navidrome can remap PIDs while paths stay stable. Skipped entirely when
the computed path doesn't change, and for Import-tab applies (those files
never existed in Navidrome). Supersedes Move-on-Field-Change.
_Avoid_: modify-then-move (loose description, not the term)

**Move-on-Field-Change** *(superseded)*:
The former rule that any metadata edit changing the computed path
immediately moved the file(s) in the same operation. Replaced by
Two-Phase Edit (ADR-0011) because the atomic modify+move breaks
Navidrome PID remapping. Retained here so old references resolve.

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
not — is an ordinary beets import (see ADR-0003). Survives the import and
shares the Approve Tab lifecycle: a Staging Bin's originals are removed
only by Confirm Import or Grace Period expiry, same as any album.
_Avoid_: bin (alone), in-memory grouping

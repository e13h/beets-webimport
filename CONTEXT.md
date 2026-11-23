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

**Undo Import**:
The library album action that puts an import back: every original file
returns to its inbox path byte-identical (tags, art, checksum, mtime,
permissions), along with the folder's other files, and the album is
removed from the library. All-or-nothing, checked by SHA-256 before
anything changes (restore.py, ADR-0014/0015). Redo is undo, then import.
_Avoid_: Approve tab, Confirm Import, Grace Period (the copy-mode
lifecycle it replaced: the inbox held a second copy until confirmed or
auto-deleted)

**Companion Files**:
A folder's non-audio files (cover.jpg, .cue, .log, scans). beets moves
only audio, so webimport keeps companions whole with the album
(`original_folder`) and removes them from the inbox after a checked
import; Undo Import puts them back (lifecycle.py).

**Backfill**:
Attaching store downloads in the inbox to library tracks imported before
originals were kept, matched by audio checksum or fingerprint (never by
title). Identical audio is saved as the track's Original File; the same
recording at equal or better quality is **swapped in** (the library's
tags and art written onto the download, the old file kept in
`webimport-replaced/`); worse or unmatched downloads stay in the inbox
(`backfill.py`, ADR-0016).
_Avoid_: re-importing to get originals (loses edits and can drop
Navidrome history)

**Inbox Copy (copy-mode leftover)**:
A folder imported before move mode, still holding its files and the
`.webimport_imported` marker. Shown in the Inbox as Imported with
"Remove inbox copy", which first checks every file can be restored
exactly from the library (ADR-0015).

**Pending Move**:
The state of an album (or singleton) whose new tags were written (phase 1
of ADR-0011) but whose files still sit at their old path, until a
Navidrome scan that started after the write has seen them. webimport
watches Navidrome's scan status and then runs the move (phase 2) by
itself. "Move now" is the manual override. Held in memory only
(ADR-0004): after a restart, albums not at their computed path are listed
as pending ("Not at expected path" in the Library tab, versus "Waiting for
Navidrome" for a move that follows a scan) but wait for "Move now" or
"Move all", which moves every such album at once. A later write restarts
the wait; Undo import drops it.
_Avoid_: move queue, deferred move

**Art Choice**:
The album art the user picks in candidate review for after import: keep the
files' current embedded art, the selected release's Cover Art Archive art,
iTunes Store art (iTunes purchases), or an image file in the inbox folder.
webimport applies it as the album's art; embedart embeds it (ADR-0013).
_Avoid_: source art, resolved art (the retired dual preview)

**Original File**:
An inbox file's exact pre-import bytes, rebuildable from the library copy:
webimport keeps everything except the audio (tags, art, container) and
puts it back around the imported file's audio, checked by SHA-256
(`originals.py`, ADR-0014). Distinct from the original-tags snapshot
(`original_tags`), which is the readable view of the same tags.

**Tag Preview**:
In candidate review, each file's tags now vs. after importing with the
focused candidate, computed by running beets' apply step on copies
(`tagpreview.py`). Fields are added, replaced, removed, or unchanged;
replaced and removed are where the imported file loses its current value.
Tags beets doesn't write (store IDs, iTunes atoms) are listed as kept.

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
The rule (ADR-0011) that a library operation which both writes tags and
changes a file's computed path (a Library-tab reimport apply, or an edit
of a real tag field) writes the tags first and leaves the move as a
Pending Move. Navidrome then sees only one change per scan and keeps the
track's history. Edits of beets-only fields (e.g. `navidrome_library`)
move at once, since the files' tags don't change. Skipped when the
computed path doesn't change, for Import-tab applies (those files never
existed in Navidrome), and when the Navidrome integration is off.
Supersedes Move-on-Field-Change.
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
not — is an ordinary beets import (see ADR-0003). Emptied and
pruned by the import like any inbox folder; Undo Import recreates it.
_Avoid_: bin (alone), in-memory grouping

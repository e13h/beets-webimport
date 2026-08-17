# Beets Web Plugin — Product Requirements

## Background

Replacing beets-flask, which is too slow (per-view re-computation with no
session/candidate reuse, confirmed via direct SQLite inspection of its
`beets-flask-sqlite.db`) and doesn't work with the chroma plugin. Raw
`beet import -t` on a representative album took ~9s; beets-flask took ~60s
for the same album with no caching benefit on repeat views.

## Architecture

- **Native beets plugin** (`beets.plugins.BeetsPlugin`), hooking
  `ImportSession` and plugin events directly — not a separate app that
  shells out to the `beet` CLI.
- **Web UI served by the plugin itself**, responsive and fully functional
  on both desktop and mobile (touch-friendly equivalents for every
  drag-and-drop interaction: long-press drag, dedicated grab handle, or a
  3-dot "move to" menu).
- **No app-level auth** — network access is gated by Tailscale.
- Lightweight and fast — must not get in the way of plain `beet` CLI usage.

## Import Flow

- Drag-and-drop inbox directory for new album dirs (from ARM or manual
  drop).
- Tolerant of files being moved/renamed mid-process — importer should not
  choke on missing/renamed files.
- Uses beets under the hood for all matching/tagging — existing plugins
  (chroma, musicbrainz, spotify, etc.) work unmodified.
- Candidates shown as a browsable list, built by overriding
  `choose_match`/`choose_item`.
- **Concurrency model**: parallel candidate review across multiple albums
  (independently browsable/reorderable), funneling into a single **serial
  apply queue** for the actual db write/move step. No persistence of
  in-flight review state across a plugin restart — acceptable to lose and
  re-trigger candidate search on restart (simpler implementation,
  underlying files are never at risk).
- Manual override: paste a MusicBrainz ID/URL directly to preview and
  accept, bypassing search.
- **Manual grouping**: drag individual files from the inbox into ad-hoc
  bins to split a single rip (e.g., a burned playlist disc) into separate
  albums/singles before import. Maps to constructing `ImportTask`
  (albums) / `SingletonImportTask` (singles) directly from arbitrary file
  lists, rather than relying on beets' default directory-based grouping.
- Drag-and-drop custom artwork onto an album dir; picked up by
  fetchart/embedart as the preferred art source.
- **Duplicate handling**: config runs `duplicate_action: ask`, so beets
  will flag suspected duplicates against the existing library during
  import. Plugin overrides `resolve_duplicate` (alongside
  `choose_match`/`choose_item`) to surface this as an explicit decision
  point in the GUI (keep existing, replace, keep both, merge) rather than
  auto-resolving silently.

### Dual cover-art preview

- Two thumbnails shown per candidate:
  1. **Source art** — image associated with the selected MB/Spotify
     candidate.
  2. **Resolved art** — what fetchart/embedart will actually write to the
     file, computed by running the real fetchart resolution logic
     (source priority, minimum resolution, aspect-ratio requirements,
     local `cover.jpg` precedence, overwrite rules) — not a
     reimplementation of those rules.
- A match/mismatch indicator so identical results need no manual visual
  comparison.
- **Computed lazily**: resolved art is only generated for the
  currently-selected/highlighted candidate, refreshing as focus moves
  through the list — not upfront for every candidate, to keep the list
  fast to load.

## Undo / Grace Period

- ~10 minute grace period after import apply during which the import can
  be undone.
- Beets is run in **`copy` mode** (source files in inbox are never moved,
  only copied into the library).
- Undo = `beet remove -d`, i.e. delete the library-side copy and the db
  entry in one step. The untouched inbox original is immediately
  available to re-enter the review queue with no restore step needed.
- **Safety requirement**: the undo call must be keyed strictly off the
  exact `Album`/`Item` DB IDs captured at the moment of that import (from
  the `ImportSession` result), never a re-derived query string — avoids
  any risk of an overly broad match deleting unrelated library items.

## Post-Import: Reimport

- From the library view, select an album (or multi-select several) and
  reimport to reassign metadata — GUI equivalent of:
  ```
  beet import -L -S <mbid> --from-scratch --set navidrome_library=kids album:aladdin
  ```
- Flags exposed as checkboxes/inputs in the UI:
  - `-L` — implied always in this context (reimporting from library, not
    disk).
  - `-S <id>` — restrict matching to a specific MusicBrainz ID, or run a
    normal search via existing chroma/musicbrainz plugins.
  - `--from-scratch` — erase existing metadata before applying new
    metadata. Shown **bold/highlighted** when checked to draw attention
    to its destructive nature (no modal confirmation needed).
  - `--set field=value` — set/restore fields (e.g., `navidrome_library`)
    that would otherwise be wiped by `--from-scratch`.
- Diff view shows the new candidate's resulting metadata (old → new); no
  separate "erased fields" pass needed beyond that diff.
- Goes through the **same grace-period undo mechanism** as a fresh
  import.

## Library Browse & Metadata Editing

- Browse library by artist or album list (~800 songs currently), with
  **text search as a first-class feature**.
- Album art thumbnails sourced from beets' `art_path` field (fast, no
  per-file I/O), resized/cached (e.g. 200x200) for grid display. Fall
  back to extracting embedded art from the file only when `art_path` is
  null.
- Album view: full metadata + track list. Track view (on selecting a
  track): full metadata for that track.
- Metadata editing, per-track or applied to an entire album, including
  custom fields:
  - **Type-aware inputs** preferred (date picker, multi-value chip input
    for fields like `genres`); plain text box as fallback for complex/
    unusual fields.
  - **Custom fields are extensible** — not hardcoded to just
    `navidrome_library`/`mood`; the plugin should support registering new
    field names as needs arise.
  - **Bulk edit**: multi-select across several albums and apply a field
    change (e.g., set `navidrome_library=kids`) across all of them in one
    action.
- **Unified move-on-field-change behavior**: any metadata edit — single
  field, single track/album, or bulk — that would change the computed
  file path (per the `paths:` template config) automatically triggers the
  equivalent of `--move`, since the config runs `copy: yes` / `move: no`
  by default. This is a general mechanism, not a special case limited to
  `navidrome_library`.
- No concurrency/conflict handling needed for simultaneous
  view/edit (solo-user assumption).

## Custom Tags (Navidrome Integration)

- Navidrome only indexes tags explicitly declared in `navidrome.toml`
  (`Tags.<Name>.Aliases`); new tag *values* work immediately, new tag
  *names* require a config edit + full library rescan (acceptable,
  expected to be rare).
- Initial custom field: **`mood`**, multi-valued.
- Reusable/managed tag vocabulary maintained in the GUI; tags applied via
  drag-and-drop (or touch equivalent) onto individual tracks or whole
  albums.
- **Album-level tag assignment writes down to every track file** (`beet
  write`) — Navidrome smart playlists filter at the song level, so
  album-only writes wouldn't be picked up by per-song filtering.

## Multi-Library Routing (Navidrome)

- Navidrome libraries are distinct, non-overlapping root folders (no
  per-file/per-tag library assignment in Navidrome itself).
- GUI-selectable "listening group" (kids / worship / holiday / talk radio
  / regular / any future value) is written as a beets flexible attribute
  (`navidrome_library`) at import time or via metadata edit. Values are
  **not** a fixed, pre-keyed set — the plugin should let the user type or
  select any string, including new ones not seen before.
- Actual routing is via `$navidrome_library` used directly as a path
  variable in the existing templates (`paths.default`, `paths.singleton`,
  `paths.comp`), not per-value conditional templates:
  ```yaml
  paths:
    default: $navidrome_library/$albumartist/$album%aunique{}/$track $title
    singleton: $navidrome_library/Non-Album/$artist/$title
    comp: $navidrome_library/Compilations/$album%aunique{}/$track $title
  ```
- `import.set_fields.navidrome_library: unassigned` is the current
  default, so anything imported without an explicit library selection in
  the GUI lands in `/music/unassigned/...` rather than failing or being
  blocked. The GUI should surface "unassigned" as a visible, filterable
  state in the library browse view (e.g., a way to quickly find and
  triage everything still sitting in `unassigned`), and should let the
  user assign/change `navidrome_library` freely — any string becomes a
  new top-level folder the next time something is routed to it.
- Each resulting top-level folder (`/music/kids`, `/music/worship`,
  `/music/unassigned`, etc.) is registered as a separate library root in
  Navidrome as they're created/populated — this is a manual one-time step
  per new library value, done in Navidrome's settings, not something the
  plugin needs to automate.
- Changing `navidrome_library` on an already-imported item/album
  automatically triggers a move (see "Unified move-on-field-change
  behavior" above) to physically relocate files to match the updated
  path — editing the field alone must never leave files stranded in the
  wrong folder.

## Explicitly Out of Scope / Deferred

- Persistent/durable in-flight review state across plugin restarts.
- Concurrent multi-user editing conflict handling.
- Automatic Navidrome rescan triggering (manual/periodic auto-scan
  assumed sufficient for now — revisit if needed).

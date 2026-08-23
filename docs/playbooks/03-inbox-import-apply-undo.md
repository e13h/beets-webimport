# Playbook 03: Inbox Import → Apply → Grace-Period Undo

## Purpose & Scope

This playbook verifies the standard **Inbox Import**, **Search-by-ID Override**, **Apply**, and **Grace-Period Undo** workflows as specified in `.scratch/webimport/spec.md` (User Stories 1–8, 21–25), **ADR-0001** (Copy-mode import with ID-scoped undo), and **ADR-0009** (Playwright against a real running server over in-process `test_client()` scripts).

This playbook supersedes and replaces the deprecated `test_client()` scripts `scripts/drive_import.py` and `scripts/drive_undo.py`.

### Scenario
1. An album folder (`Mulan (Original Motion Picture Soundtrack)`) exists in `.inbox/`.
2. The user initiates import via the web UI and inspects initial match candidates in the review modal.
3. The user overrides automatic matching by providing a specific MusicBrainz Release ID (`a5483fb3-634b-4254-a966-de33cefd1f17`) through the UI's search-by-ID input (`[data-mbid]`, `[data-use-id]`).
4. The candidate list updates with the target release, and the user selects and applies the match (`[data-select]`).
5. Beets imports the files in copy mode (`copy: yes`), writes metadata tags, sets `navidrome_library: unassigned` (`set_fields`), fetches/embeds `cover.jpg`, and registers a Grace Period undo entry.
6. The user views the undo record in the UI's Undo tab (`#tabs button[data-tab="undo"]`).
7. The user triggers undo from the UI (`[data-undo]`), confirming library database rows and copied files in `.library/` are deleted while the original inbox files in `.inbox/` remain completely intact (ADR-0001).

### Verifications
1. **Inbox Review Initiation**: Clicking "Start import" (`[data-start]`) queues the inbox folder and produces an "Awaiting candidate review" card with a "Review" button (`[data-review]`) under `#pending-reviews`.
2. **Search-by-ID Override**: Entering target MBID `a5483fb3-634b-4254-a966-de33cefd1f17` into `[data-mbid]` and clicking `[data-use-id]` queries MusicBrainz and refreshes the candidate list with the forced release.
3. **Apply & File Placement**: Selecting the forced candidate (`[data-select]`) imports audio files under `.library/` according to beets' directory structure templates, assigns `navidrome_library=unassigned`, and fetches/embeds cover art (`cover.jpg`).
4. **Grace Period Registration**: The applied import is registered in the in-memory `GracePeriodManager` and visible in the web UI under `#undo-list` with an active countdown timer.
5. **ID-Scoped Undo**: Clicking `[data-undo]` executes `remove(delete=True)` on the exact captured IDs, deleting the library files and SQLite DB entries while leaving the original files in `.inbox/` untouched.

---

## Network Host Allowlist

Executing this playbook against live MusicBrainz and Cover Art Archive services requires outbound network access to:

- `musicbrainz.org`, `*.musicbrainz.org`
- `coverartarchive.org`, `*.coverartarchive.org`
- `archive.org`, `*.archive.org`
- `itunes.apple.com`, `*.mzstatic.com`

---

## Prerequisites & Environment Setup

### 1. Reset Disposable Library and State
Before starting the server, wipe existing library databases, temporary cache state, and library media files:

```bash
rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
rm -f .config/state.pickle && rm -rf .config/webimport
```

Ensure the test inbox folder `.inbox/Mulan (Original Motion Picture Soundtrack)` is present with its 4 audio tracks:
```bash
ls -la ".inbox/Mulan (Original Motion Picture Soundtrack)"
```

### 2. Start the Webimport Server
Start the real server with configuration pointing to `./.config`:

```bash
BEETSDIR=./.config .venv/bin/beet webimport
```
The server serves at `http://localhost:8338` (bound to `0.0.0.0:8338`).

---

## Step-by-Step Playwright Verification Procedure

### Step 1: Open the Web UI and Verify Inbox Content
Navigate to `http://localhost:8338` and inspect the initial Inbox view.

```json
// Tool Call: browser_navigate
{
  "url": "http://localhost:8338"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Page title is `beets-webimport`.
- The "Inbox" navigation button (`#tabs button[data-tab="inbox"]`) has class `active`.
- Section `#tab-inbox` has class `active`.
- `#inbox-dirs` contains a `.card` displaying the path to `.inbox/Mulan (Original Motion Picture Soundtrack)` and an enabled "Start import" button (`button[data-start]`).
- `#pending-reviews` is empty.

---

### Step 2: Start Import for the Inbox Directory
Click the "Start import" button on the Mulan inbox card to submit the directory to the worker pool.

```json
// Tool Call: browser_click
{
  "element": "Start import button for Mulan directory",
  "target": "#inbox-dirs .card button[data-start]"
}
```

Wait for the worker pool to discover candidate matches from MusicBrainz and render a pending review task:

```json
// Tool Call: browser_wait_for
{
  "text": "Awaiting candidate review",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Under `#pending-reviews`, a `.card` appears showing:
  - Path: `.../.inbox/Mulan (Original Motion Picture Soundtrack)`
  - Status text: `Awaiting candidate review`
  - A "Review" button (`button[data-review]`).

---

### Step 3: Open Candidate Review Modal
Click the "Review" button to open the candidate decision modal.

```json
// Tool Call: browser_click
{
  "element": "Review button",
  "target": "#pending-reviews .card button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- A modal dialog appears inside `#modal-root .modal-backdrop .modal`.
- Header `<h3>` displays the album directory path.
- Candidate list contains one or more `.candidate` cards showing match distance, artist, and album title.
- The bottom action row contains:
  - Input field `input[data-mbid]` with placeholder `Paste MusicBrainz ID or URL`.
  - Button `button[data-use-id]` labeled "Use ID".
  - Button `button[data-asis]` labeled "Use as-is".
  - Button `button[data-skip]` labeled "Skip".

---

### Step 4: Force Target Release via Search-by-ID Override
Type the target MusicBrainz release ID (`a5483fb3-634b-4254-a966-de33cefd1f17`) into `input[data-mbid]` and click "Use ID" (`button[data-use-id]`).

```json
// Tool Call: browser_type
{
  "element": "MusicBrainz ID input field",
  "target": ".modal input[data-mbid]",
  "text": "a5483fb3-634b-4254-a966-de33cefd1f17"
}
```

```json
// Tool Call: browser_click
{
  "element": "Use ID button",
  "target": ".modal button[data-use-id]"
}
```

Wait for the worker thread to query MusicBrainz for the specific MBID and re-populate the pending review card:

```json
// Tool Call: browser_wait_for
{
  "text": "Awaiting candidate review",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- The previous review modal closes (`.modal-backdrop` is removed).
- The task is re-queued with the new candidate list for release `a5483fb3-634b-4254-a966-de33cefd1f17`.
- A `.card` with "Awaiting candidate review" and `button[data-review]` is visible under `#pending-reviews`.

---

### Step 5: Open Updated Review and Apply Match
Click "Review" on the updated task card to view the forced candidates.

```json
// Tool Call: browser_click
{
  "element": "Review button for updated task",
  "target": "#pending-reviews .card button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Modal opens displaying the candidate match for the target release:
  `Jerry Goldsmith, Matthew Wilder & David Zippel – Mulan (Original Motion Picture Soundtrack) (1998)`.
- Match distance is `0.00` (or near zero).
- Dual cover-art preview container (`.art-compare[data-art]`) displays Front cover art thumbnails.
- The candidate card contains an enabled "Select" button (`.candidate button[data-select]`).

Click "Select" on the candidate to apply the import:

```json
// Tool Call: browser_click
{
  "element": "Select candidate button",
  "target": ".modal .candidate:nth-child(1) button[data-select]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Review modal closes.
- The card disappears from `#pending-reviews`.
- Server acquires the Apply Lock, copies audio files into `.library/`, embeds cover art, sets flexible fields, writes DB records, and fires `album_imported`.

---

### Step 6: Verify Filesystem and Library Database State
Verify externally observable filesystem and library outcomes:

```bash
# 1. Verify files copied under .library/ (copy-mode placement)
ls -la ".library/Jerry Goldsmith, Matthew Wilder & David Zippel/Mulan (Original Motion Picture Soundtrack)"

# 2. Verify cover art was fetched and placed as cover.jpg
test -f ".library/Jerry Goldsmith, Matthew Wilder & David Zippel/Mulan (Original Motion Picture Soundtrack)/cover.jpg" && echo "cover.jpg exists"

# 3. Verify original files in .inbox/ remain intact (ADR-0001)
ls -la ".inbox/Mulan (Original Motion Picture Soundtrack)"

# 4. Verify beets library entry and set_fields (navidrome_library=unassigned)
BEETSDIR=./.config .venv/bin/beet info -a "Mulan"
```

**Expected Observable Outcome:**
- Files copied to `.library/Jerry Goldsmith, Matthew Wilder & David Zippel/Mulan (Original Motion Picture Soundtrack)/`.
- `cover.jpg` exists in the album library directory.
- `navidrome_library: unassigned` is set on the album and items.
- All 4 original audio files in `.inbox/Mulan (Original Motion Picture Soundtrack)/` remain present and unmodified.

---

### Step 7: Verify Grace-Period Undo Entry in Web UI
Navigate to the "Undo" tab in the web UI.

```json
// Tool Call: browser_click
{
  "element": "Undo tab button",
  "target": "#tabs button[data-tab='undo']"
}
```

Wait for the undo record to render (finalized after `album_imported` event):

```json
// Tool Call: browser_wait_for
{
  "text": "Undoable for",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Active tab is `#tab-undo`.
- `#undo-list` contains a `.card` showing:
  - Album label: `Jerry Goldsmith, Matthew Wilder & David Zippel - Mulan (Original Motion Picture Soundtrack)`
  - Countdown timer: `Undoable for ...s` (e.g. ~590–600 seconds remaining)
  - A danger-styled "Undo" button (`button.danger[data-undo]`).

---

### Step 8: Trigger Undo through Web UI
Click the "Undo" button on the recent import record to trigger ID-scoped deletion.

```json
// Tool Call: browser_click
{
  "element": "Undo button",
  "target": "#undo-list .card button[data-undo]"
}
```

Wait for the undo list to clear:

```json
// Tool Call: browser_wait_for
{
  "text": "Nothing pending undo.",
  "time": 10
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- The import card is removed from `#undo-list`.
- `#undo-list` displays `<p class="timer">Nothing pending undo.</p>`.

---

### Step 9: Confirm Library and Filesystem Cleanup (ADR-0001)
Verify that the library files and database entry were removed, while the inbox original was left completely untouched.

```bash
# 1. Verify album is removed from beets database
BEETSDIR=./.config .venv/bin/beet ls -a "Mulan"

# 2. Verify library destination directory is removed / empty
ls ".library/Jerry Goldsmith, Matthew Wilder & David Zippel" 2>/dev/null || echo "Library directory removed"

# 3. Verify inbox originals are untouched and ready for re-import
ls -la ".inbox/Mulan (Original Motion Picture Soundtrack)"
```

Navigate to the Library tab in the UI:

```json
// Tool Call: browser_click
{
  "element": "Library tab button",
  "target": "#tabs button[data-tab='library']"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- `beet ls -a "Mulan"` outputs nothing (0 albums, 0 items).
- The library destination directory under `.library/` is deleted.
- All original audio files in `.inbox/Mulan (Original Motion Picture Soundtrack)/` remain present on disk.
- `#album-grid` in the Library tab is empty.

---

## Teardown

Stop the `beet webimport` server process when testing completes:

```bash
pkill -f "beet webimport" || true
```

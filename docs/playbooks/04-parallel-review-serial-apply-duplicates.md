# Playbook 04: Parallel Review + Serial Apply + Duplicates

**Purpose:** Verify parallel candidate review across concurrent inbox submissions, serialized import application via the Apply Lock (ADR-0006), and duplicate conflict resolution (`get_duplicate_action`) in the web UI.

**Context & References:**
- Validates concurrency and mutual exclusion guarantees documented in `CONTEXT.md` (Apply Lock, Import Session, Import Task, Placement Conflict) and ADR-0006 (`docs/adr/0006-serial-apply-lock-over-parallel-apply.md`).
- Implements User Story 15 and duplicate handling specifications in `.scratch/webimport/spec.md`.

---

## Prerequisites & Environment Setup

### 1. Reset Disposable Test Library and Prepare Duplicate Inbox Folder

Before running the server, wipe any previous library database / files and create a duplicate copy of the inbox album:

```bash
rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
rm -f .config/state.pickle && rm -rf .config/webimport
cp -r .inbox/Mulan .inbox/Mulan_dup
```

*(Note: If `.inbox` contains `Mulan (Original Motion Picture Soundtrack)`, copy that directory to `.inbox/Mulan_dup`.)*

### 2. Start the Server

Start the `beet webimport` daemon with the local configuration:

```bash
BEETSDIR=./.config .venv/bin/beet webimport
```

The server serves the web frontend at `http://localhost:8338`.

### 3. Required Network Hosts (Sandbox Allowlist)

The playbook queries live MusicBrainz and Cover Art Archive endpoints for metadata and cover art resolution. Ensure the following network hosts are allowed:
- `musicbrainz.org`, `*.musicbrainz.org`
- `coverartarchive.org`, `*.coverartarchive.org`
- `archive.org`, `*.archive.org`
- `itunes.apple.com`, `*.mzstatic.com`

**Target Release MBID:** `a5483fb3-634b-4254-a966-de33cefd1f17`

---

## Verification Steps

### Step 1: Open the Web Import Inbox

1. **User Action:** Navigate to the Web Import application.
2. **Playwright MCP Calls:**
   ```json
   // 1. Navigate to the web application
   browser_navigate(url="http://localhost:8338")
   // 2. Capture initial snapshot
   browser_snapshot()
   ```
3. **Expected Observable Outcome:**
   - Active navigation tab is "Inbox" (`nav#tabs button[data-tab="inbox"].active`).
   - `#tab-inbox` is visible and active.
   - `#inbox-dirs` renders two folder cards: the original `Mulan` album and the duplicate `Mulan_dup`.
   - Each card has a `.path` label and a `button[data-start]` ("Start import").
   - `#pending-reviews` is initially empty.

---

### Step 2: Concurrently Submit Both Inbox Albums

1. **User Action:** Click "Start import" on both inbox folders in immediate succession to initiate concurrent `WebImportSession` pipelines in the worker pool.
2. **Playwright MCP Calls:**
   ```json
   // Click "Start import" for the first album
   browser_click(target="#inbox-dirs .card:first-child button[data-start]")
   // Click "Start import" for the second (duplicate) album
   browser_click(target="#inbox-dirs .card:last-child button[data-start]")
   ```
3. **Expected Observable Outcome:**
   - POST requests are issued to `/api/inbox/start` with `{ "paths": [...] }`.
   - Both import tasks are dispatched to the background `InboxWorkerPool`.
   - Worker threads begin fetching MusicBrainz candidates in parallel without blocking one another.

---

### Step 3: Verify Parallel Candidate Review

1. **User Action:** Observe the "Pending review" section to confirm both albums are simultaneously available for review.
2. **Playwright MCP Calls:**
   ```json
   // Wait for pending review tasks to be registered
   browser_wait_for(text="Awaiting candidate review")
   // Capture snapshot of pending review queue
   browser_snapshot()
   ```
3. **Expected Observable Outcome:**
   - `#pending-reviews` contains **two separate cards** simultaneously:
     - One card for the original album (e.g. path ending in `Mulan`).
     - One card for the duplicate album (`Mulan_dup`).
   - Both cards display status text `"Awaiting candidate review"` and have an enabled `button[data-review]` ("Review").
   - Confirms parallel candidate review across sessions per `CONTEXT.md`.

---

### Step 4: Review and Apply Album 1 to Target Release

1. **User Action:** Open candidate review for the first album, override candidate lookup with the target release MBID (`a5483fb3-634b-4254-a966-de33cefd1f17`), and apply the match.
2. **Playwright MCP Calls:**
   ```json
   // Open candidate review modal for the first album
   browser_click(target="#pending-reviews .card:first-child button[data-review]")

   // In the review modal, enter the target MBID
   browser_type(target=".modal input[data-mbid]", text="a5483fb3-634b-4254-a966-de33cefd1f17")
   browser_click(target=".modal button[data-use-id]")

   // Wait for the re-review task to appear with resolved candidates
   browser_wait_for(text="Awaiting candidate review")

   // Open the re-reviewed task
   browser_click(target="#pending-reviews .card:first-child button[data-review]")

   // Select the top candidate to trigger apply
   browser_click(target=".modal .candidate:first-child button[data-select]")
   ```
3. **Expected Observable Outcome:**
   - The review modal closes.
   - The worker thread acquires the global Apply Lock (ADR-0006).
   - Beets writes tags, copies files to `.library/Jerry Goldsmith, Matthew Wilder & David Zippel/Mulan (Original Motion Picture Soundtrack)/`, adds the album to `.config/library.db`, embeds cover art, and releases the Apply Lock.
   - The first album is removed from `#pending-reviews`.
   - Only the second album (`Mulan_dup`) remains under `#pending-reviews`.

---

### Step 5: Verify First Album Landed in the Library

1. **User Action:** Verify that the first album completed import and is tracked in the Undo list and filesystem.
2. **Playwright MCP Calls:**
   ```json
   // Switch to Undo tab to verify import completion
   browser_click(target="nav#tabs button[data-tab='undo']")
   browser_snapshot()
   // Return to Inbox tab
   browser_click(target="nav#tabs button[data-tab='inbox']")
   ```
3. **Expected Observable Outcome:**
   - `#undo-list` contains an undo entry for `"Jerry Goldsmith, Matthew Wilder & David Zippel - Mulan (Original Motion Picture Soundtrack)"`.
   - Files exist on disk under `.library/`.
   - The library database contains exactly 1 album.

---

### Step 6: Review and Resolve Album 2 (Trigger Duplicate Prompt)

1. **User Action:** Review the second album (`Mulan_dup`), set the same target release MBID (`a5483fb3-634b-4254-a966-de33cefd1f17`), and select the candidate to trigger beets' duplicate detection pipeline.
2. **Playwright MCP Calls:**
   ```json
   // Open review for the remaining Mulan_dup card
   browser_click(target="#pending-reviews .card button[data-review]")

   // Set the target MBID
   browser_type(target=".modal input[data-mbid]", text="a5483fb3-634b-4254-a966-de33cefd1f17")
   browser_click(target=".modal button[data-use-id]")

   // Wait for re-review task to appear
   browser_wait_for(text="Awaiting candidate review")

   // Open the re-reviewed candidate modal
   browser_click(target="#pending-reviews .card button[data-review]")

   // Select the target candidate
   browser_click(target=".modal .candidate:first-child button[data-select]")
   ```
3. **Expected Observable Outcome:**
   - When the worker applies album 2, beets detects that an album with the same artist and title already exists in the library (`duplicate_action: ask`).
   - The session hook `get_duplicate_action(task, found_duplicates)` triggers and registers a `duplicate` task in `ReviewManager`.
   - The review card in `#pending-reviews` updates its status to `"Possible duplicate"`.

---

### Step 7: Inspect Duplicate Review Modal and Options

1. **User Action:** Click "Review" on the "Possible duplicate" card to open the duplicate decision modal.
2. **Playwright MCP Calls:**
   ```json
   // Open duplicate decision dialog
   browser_click(target="#pending-reviews .card button[data-review]")
   // Snapshot modal DOM
   browser_snapshot()
   ```
3. **Expected Observable Outcome:**
   - `openDuplicateReview` renders the duplicate modal inside `#modal-root`.
   - Modal header: `<h3>Possible duplicate — .../.inbox/Mulan_dup</h3>`.
   - Existing duplicate album title is listed under `<ul><li>...</li></ul>`.
   - The three valid `DuplicateAction` choices are present in the DOM:
     - `button[data-keep-both]` ("Keep both" → `DuplicateAction.KEEP`)
     - `button.secondary[data-remove-old]` ("Replace existing" → `DuplicateAction.REMOVE`)
     - `button.danger[data-skip]` ("Skip new" → `DuplicateAction.SKIP`)

---

### Step 8: Choose "Skip New" and Confirm Single Library Copy

1. **User Action:** Click "Skip new" to reject the duplicate import.
2. **Playwright MCP Calls:**
   ```json
   // Choose Skip New
   browser_click(target=".modal button[data-skip]")
   // Snapshot pending reviews
   browser_snapshot()
   ```
3. **Expected Observable Outcome:**
   - Modal closes.
   - POST `/api/review/<task_id>/decide` with `{ "action": "skip" }` resolves `get_duplicate_action` to `DuplicateAction.SKIP`.
   - `#pending-reviews` becomes completely empty (`dirsEl.innerHTML` contains no pending items).
   - **Filesystem & Database Check:**
     - `.library/` contains only the files from the first import (no second album directory or duplicate files).
     - Database `.config/library.db` contains exactly 1 album.

---

### Step 9: Verify Apply Lock Health via Library Tab

1. **User Action:** Switch to the Library tab to confirm that the Apply Lock was properly released and the UI remains fully responsive.
2. **Playwright MCP Calls:**
   ```json
   // Switch to Library tab
   browser_click(target="nav#tabs button[data-tab='library']")
   // Wait for library grid to load
   browser_wait_for(text="Search albums")
   browser_snapshot()
   ```
3. **Expected Observable Outcome:**
   - Navigation button `button[data-tab="library"]` becomes `.active`.
   - `#tab-library` is active and visible.
   - `loadLibrary()` successfully completes `GET /api/library/albums` without hanging or timing out.
   - `#album-grid` renders a single album tile for "Mulan (Original Motion Picture Soundtrack)".
   - Confirms the global Apply Lock was safely released and is not stuck.

---

### Step 10: Teardown & Clean Up

After completing verification:

1. Remove the temporary duplicate directory from the inbox:
   ```bash
   rm -rf .inbox/Mulan_dup
   ```
2. Stop the `beet webimport` server process.

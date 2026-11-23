# Playbook 03: Inbox Import → Apply → Undo Import

## Purpose & Scope

This playbook verifies the standard **Inbox Import**, **Search-by-ID Override**, **Apply**, and **Undo Import** workflows as specified in `.scratch/webimport/spec.md` (User Stories 1–8, 21–25), **ADR-0014/0015** (move mode; byte-exact originals; Undo Import), and **ADR-0009** (Playwright against a real running server over in-process `test_client()` scripts).

### Scenario
1. An album folder (`Mulan (Original Motion Picture Soundtrack)`) exists in `.inbox/`.
2. The user initiates import via the web UI and inspects initial match candidates in the review modal.
3. The user overrides automatic matching (for these iTunes test files, the release found through the album's Apple Music link) by providing a specific MusicBrainz Release ID (`4e929666-952f-473c-baf2-97c9ca6bfbbe`) through the UI's search-by-ID input (`[data-mbid]`, `[data-use-id]`).
4. The candidate list updates with the target release, and the user selects and applies the match (`[data-select]`).
5. Beets **moves** the files into `.library/` (`move: yes`), writes metadata tags, sets `navidrome_library: unassigned` (`set_fields`), and embeds the chosen album art. webimport stores each file's original non-audio bytes and removes the emptied folder from the inbox.
6. The user opens the album in the Library tab and runs **Undo import…** (`[data-undo-import]`, then `[data-undo-confirm]`).
7. The four original files are back in `.inbox/` byte-identical to before the import, and the album is gone from the library.

### Verifications
1. **Inbox Review Initiation**: Clicking "Start import" (`[data-start]`) queues the inbox folder and produces an "Candidates ready for review" card with a "Review" button (`[data-review]`) on the folder's card in `#inbox-dirs` (the Inbox tab is one list; a card's review appears on it).
2. **Search-by-ID Override**: Entering target MBID `4e929666-952f-473c-baf2-97c9ca6bfbbe` into `[data-mbid]` and clicking `[data-use-id]` queries MusicBrainz and refreshes the candidate list with the forced release.
3. **Apply & File Placement**: Selecting the forced candidate (`[data-select]`) moves the audio files under `.library/` according to beets' path templates, assigns `navidrome_library=unassigned`, embeds album art, and removes the folder from `.inbox/`.
4. **Undo Import**: The undo panel lists the folder it will restore; confirming puts every file back byte-identical (SHA-256 match), removes the album, its library files and its stored originals, and the folder reappears in the Inbox tab.

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
scripts/dev-reset.sh
```

Ensure the test inbox folder `.inbox/Mulan (Original Motion Picture Soundtrack)` is present with its 4 audio tracks, and record their checksums for the undo check in Step 9:
```bash
ls -la ".inbox/Mulan (Original Motion Picture Soundtrack)"
(cd ".inbox/Mulan (Original Motion Picture Soundtrack)" && shasum -a 256 *.m4a) > "${TMPDIR:-/tmp}/mulan-before.sha"
```

### 2. Start the Webimport Server
Start the real server with configuration pointing to `./.config`:

```bash
scripts/dev-server.sh
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
- `#inbox-dirs` contains a `.card` for each inbox folder (B.o.B, Coldplay, Mulan); the Mulan card shows the path to `.inbox/Mulan (Original Motion Picture Soundtrack)` and an enabled "Start import" button (`button[data-start]`).
- no card in `#inbox-dirs` shows a `[data-review]` button.

---

### Step 2: Start Import for the Inbox Directory
Click the "Start import" button on the Mulan inbox card to submit the directory to the worker pool.

```json
// Tool Call: browser_click
{
  "element": "Start import button for Mulan directory",
  "target": "#inbox-dirs .card:has-text('Mulan') button[data-start]"
}
```

Wait for the worker pool to discover candidate matches from MusicBrainz and render a pending review task:

```json
// Tool Call: browser_wait_for
{
  "text": "Candidates ready for review",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- On the folder's card in `#inbox-dirs`:
  - Path: `.../.inbox/Mulan (Original Motion Picture Soundtrack)`
  - Status text: `Candidates ready for review`
  - A "Review" button (`button[data-review]`).

---

### Step 3: Open Candidate Review Modal
Click the "Review" button to open the candidate decision modal.

```json
// Tool Call: browser_click
{
  "element": "Review button",
  "target": "#inbox-dirs .card button[data-review]"
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
Type the target MusicBrainz release ID (`4e929666-952f-473c-baf2-97c9ca6bfbbe`) into `input[data-mbid]` and click "Use ID" (`button[data-use-id]`).

```json
// Tool Call: browser_type
{
  "element": "MusicBrainz ID input field",
  "target": ".modal input[data-mbid]",
  "text": "4e929666-952f-473c-baf2-97c9ca6bfbbe"
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
  "text": "Candidates ready for review",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- The previous review modal closes (`.modal-backdrop` is removed).
- The task is re-queued with the new candidate list for release `4e929666-952f-473c-baf2-97c9ca6bfbbe`.
- A `.card` with "Candidates ready for review" and `button[data-review]` is visible on the folder's card in `#inbox-dirs` (the Inbox tab is one list; a card's review appears on it).

---

### Step 5: Open Updated Review and Apply Match
Click "Review" on the updated task card to view the forced candidates.

```json
// Tool Call: browser_click
{
  "element": "Review button for updated task",
  "target": "#inbox-dirs .card button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Modal opens displaying the candidate match for the target release:
  `Jerry Goldsmith, Matthew Wilder & David Zippel – Mulan: An Original Walt Disney Records Soundtrack (2020)`.
- Match distance is moderate (about `0.34`: the files' album title, album artist and year differ from the release's, and 8 of its 12 tracks are missing).
- The "Tags after import" section shows replaced fields (album, album artist, year) highlighted.
- The "Album art after import" section (`.art-choice`) shows the art options with thumbnails; the selected release's Cover Art Archive option shows its size.
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
- The card's Review button and "Ready for review" badge go away (move mode: the card leaves the list once imported).
- Server acquires the Apply Lock, moves the audio files into `.library/`, writes tags, embeds the chosen art, checks each file's stored original, then removes the emptied folder from `.inbox/`.

---

### Step 6: Verify Filesystem and Library Database State
Wait for the import to finish: the folder leaves the Inbox list as the last step (not when the album first appears in the Library; see the timing facts in `docs/agents/dev-environment.md`).

```json
// Tool Call: browser_wait_for
{
  "textGone": "Mulan (Original Motion Picture Soundtrack)",
  "time": 60
}
```

```bash
# 1. Files moved into .library/
ls -la .library/unassigned/Jerry*/Mulan*/

# 2. The inbox folder is gone (move mode)
ls ".inbox/Mulan (Original Motion Picture Soundtrack)" 2>/dev/null || echo "inbox folder gone"

# 3. Art embedded (embedart.remove_art_file: yes, so no art file on disk)
.venv/bin/python -c "import glob,mediafile,sys; f=sorted(glob.glob('.library/unassigned/Jerry*/Mulan*/*.m4a'))[0]; sys.exit(0 if mediafile.MediaFile(f).art else 1)" && echo "art embedded"

# 4. Library entry and set_fields
BEETSDIR=./.config .venv/bin/beet info -a "Mulan" | grep -i "navidrome_library"

# 5. One stored original per track (non-audio bytes only)
ls .config/webimport-originals | wc -l
```

**Expected Observable Outcome:**
- 4 `.m4a` files under `.library/unassigned/Jerry Goldsmith, Matthew Wilder & David Zippel/Mulan_ An Original Walt Disney Records Soundtrack/`.
- `inbox folder gone`; no `.webimport_imported` marker or `.webimport-safety` folder is left in `.inbox/`.
- `art embedded`; `navidrome_library: unassigned`.
- `4` stored originals.

---

### Step 7: Open Undo Import for the Album
Open the album in the Library tab and start Undo import.

```json
// Tool Call: browser_click
{
  "element": "Library tab button",
  "target": "#tabs button[data-tab='library']"
}
```

```json
// Tool Call: browser_click
{
  "element": "Mulan album tile",
  "target": ".album-tile:has-text('Mulan')"
}
```

```json
// Tool Call: browser_click
{
  "element": "Undo import button",
  "target": "[data-undo-import]"
}
```

```json
// Tool Call: browser_wait_for
{
  "text": "Undo import of",
  "time": 30
}
```

**Expected Observable Outcome:**
- The panel (`[data-undo-panel]`) reads "Undo import of Mulan: An Original Walt Disney Records Soundtrack?", says the 4 original tracks go back exactly as before import, and lists the folder `.../.inbox/Mulan (Original Motion Picture Soundtrack)`.
- No problems list; an enabled "Undo import" button (`[data-undo-confirm]`).

---

### Step 8: Confirm Undo

```json
// Tool Call: browser_click
{
  "element": "Confirm undo import",
  "target": "[data-undo-confirm]"
}
```

```json
// Tool Call: browser_wait_for
{
  "text": "back in the inbox",
  "time": 30
}
```

**Expected Observable Outcome:**
- Toast "Undone: 4 tracks back in the inbox."; the modal closes.
- The Library tab no longer shows the Mulan tile.

---

### Step 9: Verify Byte-Identical Restore

```bash
# 1. Every file matches its pre-import checksum (recorded in Prerequisites)
(cd ".inbox/Mulan (Original Motion Picture Soundtrack)" && shasum -a 256 -c "${TMPDIR:-/tmp}/mulan-before.sha")

# 2. Album, library files and stored originals are gone
BEETSDIR=./.config .venv/bin/beet ls -a "Mulan"
ls .library/unassigned/Jerry* 2>/dev/null || echo "library folder removed"
ls .config/webimport-originals | wc -l
```

```json
// Tool Call: browser_click
{
  "element": "Inbox tab button",
  "target": "#tabs button[data-tab='inbox']"
}
```

**Expected Observable Outcome:**
- `shasum -c` prints `OK` for all 4 files.
- `beet ls -a "Mulan"` prints nothing; `library folder removed`; `0` stored originals.
- The Inbox tab shows the Mulan card again with "Start import".

---

### Step 10 (optional): Copy-Mode Leftovers
A folder imported before move mode still holds its files and a `.webimport_imported` marker. It shows in the Inbox as **Imported** with **Remove inbox copy** (`[data-release]`). Clicking it removes the folder only if every file can be rebuilt exactly from the library; otherwise the toast lists why and nothing changes. (Covered by `tests/test_lifecycle.py`; the dev inbox has no such folders after a reset.)

---

## Teardown

```bash
scripts/dev-reset.sh   # stops the server; .inbox back to its initial state
```

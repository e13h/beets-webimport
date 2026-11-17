# Playbook 06: Manual Grouping via Staging Bins

## Purpose & Scope

This playbook verifies the **Manual Grouping** workflow via ad-hoc **Staging Bins**, as specified in `.scratch/webimport/spec.md` (User Stories 9–12), **ADR-0003** (Staging-directory manual grouping over in-memory task construction), and **ADR-0009** (Playwright against a real running server).

### Scenario
An inbox directory contains a synthetic "burned playlist" rip—audio tracks originating from more than one distinct release (e.g., several tracks from the *Mulan* soundtrack mixed with a standalone single track). Importing this folder directly would cause beets to mistakenly attempt matching it as a single release. 

Instead, the user splits the mixed directory into two or more ad-hoc **Staging Bins** (e.g., `bin_0` for the multi-track album and `bin_1` for the singleton track). Each bin is staged into its own directory under `.inbox/_grouped/<group_id>/bin_N/`, triggering standard directory-based beets imports per ADR-0003.

### Verifications
1. **Physical Staging**: Splitting creates discrete subdirectories under `.inbox/_grouped/<group_id>/` and moves the audio files into their respective bins.
2. **Independent Import Tasks**: Each bin produces its own independent review card in the UI's "Pending review" section (not a single merged import).
3. **Candidate Review & Apply**: Both the multi-track album bin and the singleton bin can be independently reviewed, matched (or forced via MBID / as-is), and applied.
4. **Library Placement**: Each bin is imported into the library as its own separate canonical entity under `.library/` with default metadata (`navidrome_library: unassigned`).
5. **Grace Period Persistence**: Staging bins under `.inbox/_grouped/` persist on disk through the Grace Period after apply (per ADR-0003 and Spec Story 11), ensuring that undo does not discard manual splitting work.

---

## Network Host Allowlist

Running this playbook against live MusicBrainz and Cover Art Archive lookups requires outbound access to:

- `musicbrainz.org`, `*.musicbrainz.org`
- `coverartarchive.org`, `*.coverartarchive.org`
- `archive.org`, `*.archive.org`
- `itunes.apple.com`, `*.mzstatic.com`

---

## Prerequisites & Environment Setup

### 1. Reset Disposable Library and State
Before running the server, wipe existing library databases, temporary state, and previous inbox grouping directories:

```bash
scripts/dev-reset.sh
rm -rf .inbox
mkdir -p .inbox
```

### 2. Create Mixed Playlist Test Fixture
Generate a mixed inbox directory `.inbox/Burned_Playlist/` containing tracks from multiple distinct releases:
- 2 tracks from *Mulan* (e.g., "Honor to Us All", "Reflection")
- 1 track from a standalone single (e.g., Carly Rae Jepsen - "Call Me Maybe")

```bash
mkdir -p .inbox/Burned_Playlist

# Generate synthetic audio fixtures (or copy test mp3/flac files if present)
# Note: In a test environment, ffmpeg or touch/sample audio files can be used:
cat << 'EOF' > /tmp/make_mixed_fixture.py
import os
from pathlib import Path

base = Path(".inbox/Burned_Playlist")
base.mkdir(parents=True, exist_ok=True)

# Create minimal valid MP3 silent frames or sample test files
# Track 1 & 2: Mulan (Matthew Wilder & David Zippel / Jerry Goldsmith)
(base / "01 - Honor to Us All.mp3").write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 1024)
(base / "02 - Reflection.mp3").write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 1024)

# Track 3: Standalone single
(base / "03 - Call Me Maybe.mp3").write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 1024)
EOF
python3 /tmp/make_mixed_fixture.py && rm /tmp/make_mixed_fixture.py
```

### 3. Start the Webimport Server
Start the real server in the background:

```bash
scripts/dev-server.sh
```
The server will bind to `http://localhost:8338`.

---

## Step-by-Step Playwright Verification Procedure

### Step 1: Open the Web UI and Verify Mixed Inbox Directory
Navigate to the root URL and verify the `Burned_Playlist` folder is listed in the Inbox.

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

**Expected Outcome:**
- Active tab is "Inbox" (`#tab-inbox`).
- Under `#inbox-dirs`, a card is present showing the path to `.inbox/Burned_Playlist`.

---

### Step 2: Split Mixed Directory into Staging Bins
Split the files in `.inbox/Burned_Playlist` into two distinct staging bins:
- **Bin 0** (Multi-track album): `01 - Honor to Us All.mp3`, `02 - Reflection.mp3`
- **Bin 1** (Singleton track): `03 - Call Me Maybe.mp3`

Execute the grouping action via UI interaction or by posting the grouping structure to `/api/inbox/group`:

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const inboxData = await (await fetch('/api/inbox')).json();\n  const mixedDir = inboxData.inbox_dirs.find(d => d.includes('Burned_Playlist'));\n  if (!mixedDir) throw new Error('Burned_Playlist not found in inbox');\n  \n  const res = await fetch('/api/inbox/group', {\n    method: 'POST',\n    headers: { 'Content-Type': 'application/json' },\n    body: JSON.stringify({\n      bins: [\n        {\n          files: [\n            `${mixedDir}/01 - Honor to Us All.mp3`,\n            `${mixedDir}/02 - Reflection.mp3`\n          ]\n        },\n        {\n          files: [\n            `${mixedDir}/03 - Call Me Maybe.mp3`\n          ],\n          singleton: true\n        }\n      ]\n    })\n  });\n  return await res.json();\n}"
}
```

**Expected Outcome:**
- The response returns `{"submitted": ["<abs_path>/.inbox/_grouped/<id>/bin_0", "<abs_path>/.inbox/_grouped/<id>/bin_1"]}`.
- Files have been physically moved into separate directories under `.inbox/_grouped/<id>/`.

---

### Step 3: Verify Separate Import Tasks Appear in Pending Review
Wait for both staging bins to be processed by the worker pool and appear in the review queue.

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

**Expected Outcome:**
- Two distinct cards appear under `#pending-reviews`:
  - One for `.../_grouped/<id>/bin_0`
  - One for `.../_grouped/<id>/bin_1`
- Confirms each staging bin is processed as an independent `ImportTask` rather than a single mixed task.

---

### Step 4: Candidate Review and Apply for Bin 0 (Multi-track Album)
Open review for `bin_0`, inspect candidates (or override with target MBID `a5483fb3-634b-4254-a966-de33cefd1f17`), and apply.

```json
// Tool Call: browser_click
{
  "element": "Review button for bin_0",
  "target": "#pending-reviews .card:has(.path:text('bin_0')) button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

Apply match (either by selecting candidate 0 or using search ID override):

```json
// Tool Call: browser_click
{
  "element": "Select first candidate",
  "target": ".modal .candidate:nth-child(1) button[data-select]"
}
```

**Expected Outcome:**
- Review modal closes.
- The `bin_0` card disappears from `#pending-reviews`.
- Server acquires Apply Lock, executes copy-mode import for `bin_0`, and emits `album_imported`.

---

### Step 5: Candidate Review and Apply for Bin 1 (Singleton Track)
Open review for `bin_1`, select the appropriate match (or click "Use as-is"), and apply.

```json
// Tool Call: browser_click
{
  "element": "Review button for bin_1",
  "target": "#pending-reviews .card:has(.path:text('bin_1')) button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

```json
// Tool Call: browser_click
{
  "element": "Select candidate or Use as-is",
  "target": ".modal button[data-select], .modal button[data-asis]"
}
```

**Expected Outcome:**
- Review modal closes.
- All pending reviews are cleared.

---

### Step 6: Verify Separate Library Albums and Placement
Navigate to the "Library" tab to confirm both entities were imported into the library independently.

```json
// Tool Call: browser_click
{
  "element": "Library Tab Button",
  "target": "#tabs button[data-tab='library']"
}
```

```json
// Tool Call: browser_wait_for
{
  "time": 2
}
```

```json
// Tool Call: browser_snapshot
{}
```

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const albums = await (await fetch('/api/library/albums')).json();\n  return albums.map(a => ({ id: a.id, artist: a.artist, album: a.album, group: a.navidrome_library }));\n}"
}
```

**Expected Outcome:**
- Two distinct album records exist in the library.
- Both albums have `navidrome_library` attribute set to `unassigned`.
- Files exist under `.library/` structured according to beets path templates (e.g. `.library/unassigned/Disney/Mulan/...` and `.library/unassigned/Carly Rae Jepsen/...`).

---

### Step 7: Verify Staging Bins Persist Through Grace Period
Confirm that Staging Bins under `.inbox/_grouped/<id>/` have **not** been immediately deleted upon apply, ensuring undo safety per ADR-0003 and Spec Story 11.

```json
// Tool Call: browser_click
{
  "element": "Undo Tab Button",
  "target": "#tabs button[data-tab='undo']"
}
```

```json
// Tool Call: browser_snapshot
{}
```

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const undoList = await (await fetch('/api/undo')).json();\n  return undoList;\n}"
}
```

Verify the filesystem via bash / python:
```bash
# Verify directories and files still exist under .inbox/_grouped/
ls -la .inbox/_grouped/*/*
```

**Expected Outcome:**
- Undo tab lists the recent imports with active countdown timers.
- The `.inbox/_grouped/<id>/bin_0` and `.inbox/_grouped/<id>/bin_1` folders and audio files still exist on disk throughout the Grace Period duration.

---

### Step 8: Verify Staging Bins Cleaned Up on Grace Period Expiry
After the Grace Period expires (or after expiry pruning is triggered), verify that the staging bins under `.inbox/_grouped/` are automatically removed from disk without leaving empty directories behind, while regular library albums remain intact.

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  // Fetch undo list to trigger pruning or wait for expiry\n  const undoList = await (await fetch('/api/undo')).json();\n  const inboxData = await (await fetch('/api/inbox')).json();\n  return { undoList, inboxData };\n}"
}
```

Verify the filesystem via bash / python:
```bash
# Verify staging bins are gone once grace period has elapsed
ls -la .inbox/_grouped 2>/dev/null || echo "Cleaned up"
```

**Expected Outcome:**
- Staging bins under `.inbox/_grouped/<id>/` are deleted once the Grace Period elapses.
- Library files and database entries for the imported albums remain in place.

---

## Teardown

Stop the `beet webimport` process:
```bash
pkill -f "beet webimport" || true
```

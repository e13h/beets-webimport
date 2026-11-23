# Playbook 06: Manual Grouping via Staging Bins


## Purpose & Scope

This playbook verifies the **Manual Grouping** workflow via ad-hoc **Staging Bins**, as specified in `.scratch/webimport/spec.md` (User Stories 9–12), **ADR-0003** (Staging-directory manual grouping over in-memory task construction), and **ADR-0009** (Playwright against a real running server).

### Scenario
An inbox directory contains a "burned playlist"—audio tracks originating from more than one distinct release (two tracks from the *Mulan* soundtrack mixed with a B.o.B track). Importing this folder directly would cause beets to mistakenly attempt matching it as a single release. 

Instead, the user splits the mixed directory into two or more ad-hoc **Staging Bins** (e.g., `bin_0` for the multi-track album and `bin_1` for the singleton track). Each bin is staged into its own directory under `.inbox/_grouped/<group_id>/bin_N/`, triggering standard directory-based beets imports per ADR-0003.

### Verifications
1. **Physical Staging**: Splitting creates discrete subdirectories under `.inbox/_grouped/<group_id>/` and moves the audio files into their respective bins.
2. **Independent Import Tasks**: Each bin produces its own independent review card in the UI's "Pending review" section (not a single merged import).
3. **Candidate Review & Apply**: Both the multi-track album bin and the singleton bin can be independently reviewed, matched (or forced via MBID / as-is), and applied.
4. **Library Placement**: Each bin is imported into the library as its own separate canonical entity under `.library/` with default metadata (`navidrome_library: unassigned`).
5. **Bins Emptied on Import** (ADR-0015, move mode): each bin's files move into the library and the emptied bin folders are pruned from `.inbox/_grouped/`.
6. **Undo Recreates the Bin**: Undo import on the album bin puts its files back in `.inbox/_grouped/<id>/bin_0/` byte-identical, so the manual split isn't lost. (The singleton bin can't be undone: singletons have no album, a known gap.)

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

```bash
scripts/dev-reset.sh
```

### 2. Create the Mixed Playlist Fixture
Clone three real inbox tracks into one folder (`cp -c`: APFS clones, instant). Two are from *Mulan*, one is a B.o.B single; record their checksums for Step 8.

```bash
M=".inbox/Mulan (Original Motion Picture Soundtrack)"
mkdir .inbox/Burned_Playlist
cp -c "$M/01 Honor To Us All.m4a" "$M/02 Reflection.m4a" ".inbox/B.o.B/08 Magic [Feat. Rivers Cuomo].mp3" .inbox/Burned_Playlist/
(cd .inbox/Burned_Playlist && shasum -a 256 *.m4a) > "${TMPDIR:-/tmp}/bin0-before.sha"
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
- **Bin 0** (Multi-track album): `01 Honor To Us All.m4a`, `02 Reflection.m4a`
- **Bin 1** (Singleton track): `08 Magic [Feat. Rivers Cuomo].mp3`

Execute the grouping action via UI interaction or by posting the grouping structure to `/api/inbox/group`:

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const inboxData = await (await fetch('/api/inbox')).json();\n  const mixedDir = inboxData.inbox_dirs.map(d => d.path).find(p => p.includes('Burned_Playlist'));\n  if (!mixedDir) throw new Error('Burned_Playlist not found in inbox');\n  \n  const res = await fetch('/api/inbox/group', {\n    method: 'POST',\n    headers: { 'Content-Type': 'application/json' },\n    body: JSON.stringify({\n      bins: [\n        {\n          files: [\n            `${mixedDir}/01 Honor To Us All.m4a`,\n            `${mixedDir}/02 Reflection.m4a`\n          ]\n        },\n        {\n          files: [\n            `${mixedDir}/08 Magic [Feat. Rivers Cuomo].mp3`\n          ],\n          singleton: true\n        }\n      ]\n    })\n  });\n  return await res.json();\n}"
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
  "text": "Candidates ready for review",
  "time": 30
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Outcome:**
- Two distinct cards appear in `#inbox-dirs` (the Inbox tab is one list):
  - One for `.../_grouped/<id>/bin_0`
  - One for `.../_grouped/<id>/bin_1`
- Confirms each staging bin is processed as an independent `ImportTask` rather than a single mixed task.

---

### Step 4: Candidate Review and Apply for Bin 0 (Multi-track Album)
Open review for `bin_0`, inspect candidates (or override with target MBID `4e929666-952f-473c-baf2-97c9ca6bfbbe`), and apply.

```json
// Tool Call: browser_click
{
  "element": "Review button for bin_0",
  "target": "#inbox-dirs .card:has(.path:text('bin_0')) button[data-review]"
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
- The `bin_0` card loses its Review button.
- Server acquires Apply Lock and moves `bin_0`'s files into the library (2 of the release's tracks: a partial album, kept together as the album).

---

### Step 5: Candidate Review and Apply for Bin 1 (Singleton Track)
Open review for `bin_1`, select the appropriate match (or click "Use as-is"), and apply.

```json
// Tool Call: browser_click
{
  "element": "Review button for bin_1",
  "target": "#inbox-dirs .card:has(.path:text('bin_1')) button[data-review]"
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
- Files exist under `.library/` structured according to beets path templates (e.g. `.library/unassigned/Jerry Goldsmith, …/Mulan_ …/` and `.library/unassigned/Non-Album/B.o.B/`).

---

### Step 7: Verify the Bins Were Emptied

```bash
ls -R .inbox/_grouped 2>/dev/null || echo "no staging bins left"
```

**Expected Outcome:**
- `no staging bins left` (or an empty `_grouped/`): both bins' files moved into the library and the emptied bin folders were pruned.
- The Inbox tab shows neither bin.

---

### Step 8: Undo Import of the Album Bin Recreates It
Library tab → the Mulan album → **Undo import…** → confirm.

```json
// Tool Call: browser_click
{ "element": "Library tab", "target": "#tabs button[data-tab='library']" }
```

```json
// Tool Call: browser_click
{ "element": "Mulan album tile", "target": ".album-tile:has-text('Mulan')" }
```

```json
// Tool Call: browser_click
{ "element": "Undo import", "target": "[data-undo-import]" }
```

```json
// Tool Call: browser_click
{ "element": "Confirm undo", "target": "[data-undo-confirm]" }
```

```json
// Tool Call: browser_wait_for
{ "text": "back in the inbox", "time": 30 }
```

```bash
(cd .inbox/_grouped/*/bin_0 && shasum -a 256 -c "${TMPDIR:-/tmp}/bin0-before.sha")
```

**Expected Outcome:**
- The undo panel lists `.../.inbox/_grouped/<id>/bin_0` as the folder to restore.
- `shasum -c` prints `OK` for both tracks: the bin is back exactly as split.
- The Inbox tab shows `bin_0` again, ready to re-import; the B.o.B singleton stays in the library (singletons have no Undo import).

---

## Teardown

`Burned_Playlist` and the bins aren't in the saved initial inbox, so the reset needs `--force` to delete them:
```bash
scripts/dev-reset.sh --force
```

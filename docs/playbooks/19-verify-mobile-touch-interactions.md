# Playbook 19: Verify Mobile / Touch Interactions via Playwright Touch Emulation

## Purpose & Scope

This playbook verifies the mobile touch equivalents of desktop drag-and-drop and context actions in `beets-webimport` (`attachLongPress` and `showLongPressMenu` in `static/app.js`), per `.scratch/webimport/spec.md` (Testing Decisions & Further Notes), **ADR-0007**, and **ADR-0009**.

On desktop, user interactions rely on mouse clicks, context menus, and drag-and-drop. On mobile and touch devices, long-press gestures (holding touch contact for ≥450ms without moving) serve as the touch equivalent, opening contextual floating action menus (`.long-press-menu`) to:
1. **Assign Listening Group / Library Routing**: Long-press on an album tile in the **Library** grid to trigger "Set navidrome_library…" or "Reimport / reassign MBID…".
2. **Per-Track Tagging**: Long-press on individual track rows within the Album Detail modal to apply track-level tags (`item` scope).
3. **Tag Vocabulary Application**: Long-press on tag chips in the **Tags** tab to apply existing tags across albums or tracks.
4. **Gesture Cancellation**: Cancel the long-press timer if touch contact moves (`touchmove`) or ends prematurely (`touchend` < 450ms) before the threshold fires.

> **Important Proxy Note (per Spec Further Notes):**
> Playwright touch and viewport emulation is an automatable continuous-integration proxy, **not a replacement for a manual verification pass on a real physical touch device** (e.g. iOS Safari and Android Chrome). Physical testing is still needed to verify hardware touch-rejection quirks, native OS callout/selection conflicts, virtual keyboard viewport reflow, and fluid scrolling physics.

---

## Network Host Allowlist

When importing or looking up live MusicBrainz / Cover Art Archive metadata during preparation:

- `musicbrainz.org`, `*.musicbrainz.org`
- `coverartarchive.org`, `*.coverartarchive.org`
- `archive.org`, `*.archive.org`
- `itunes.apple.com`, `*.mzstatic.com`

---

## Prerequisites & Environment Setup

### 1. Reset Disposable Test Library and Prepare Test Fixture
Wipe existing database and library state, and ensure a test album is imported into the library:

```bash
scripts/dev-reset.sh
```

Create and import a minimal test fixture if the library is empty:
```bash
cat << 'EOF' > /tmp/setup_touch_fixture.py
import os
import sqlite3
from pathlib import Path
import beets.library

config_dir = Path(".config")
config_dir.mkdir(parents=True, exist_ok=True)
lib_dir = Path(".library")
lib_dir.mkdir(parents=True, exist_ok=True)

lib = beets.library.Library(str(config_dir / "library.db"), str(lib_dir))

# Create test audio file
track_path = lib_dir / "test_track.mp3"
track_path.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 1024)

item = beets.library.Item(
    title="Touch Test Track",
    artist="Touch Artist",
    album="Touch Album",
    albumartist="Touch Artist",
    track=1,
    path=str(track_path).encode("utf-8"),
    navidrome_library="unassigned"
)
lib.add(item)
album = lib.add_album([item])
album.album = "Touch Album"
album.albumartist = "Touch Artist"
album.navidrome_library = "unassigned"
album.store()
lib._connection().commit()
print(f"Created Album ID: {album.id}, Item ID: {item.id}")
EOF
python3 /tmp/setup_touch_fixture.py && rm /tmp/setup_touch_fixture.py
```

### 2. Start the Server
Start the real `beet webimport` server:

```bash
scripts/dev-server.sh
```
The server serves at `http://localhost:8338`.

---

## Step-by-Step Playwright Verification Procedure

### Step 1: Emulate Mobile Viewport & Navigate to Web UI
Configure the browser viewport to a mobile device dimension (e.g. iPhone / Android viewport: 390 × 844 px) and load the web UI.

```json
// Tool Call: browser_resize
{
  "width": 390,
  "height": 844
}
```

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
- Web UI renders responsively within the mobile viewport.
- Tab navigation buttons (`#tabs button`) fit cleanly across the top navigation bar.

---

### Step 2: Navigate to Library Tab & Inspect Album Tile
Switch to the Library tab to display the imported test album tile.

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
  "text": "Touch Album",
  "time": 5
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Outcome:**
- Section `#tab-library` is active.
- An `.album-tile` is visible displaying `Touch Artist`, `Touch Album`, and `.lib-badge` with text `"unassigned"`.

---

### Step 3: Exercise Long-Press Menu on Album Tile (Touch Emulation)
Simulate a touch contact on the album tile holding for 500ms (exceeding the 450ms `attachLongPress` threshold) to summon the `.long-press-menu`.

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const tile = document.querySelector('#album-grid .album-tile');\n  if (!tile) throw new Error('Album tile not found');\n  const rect = tile.getBoundingClientRect();\n  const x = rect.left + rect.width / 2;\n  const y = rect.top + rect.height / 2;\n  \n  // Dispatch touchstart\n  const touchObj = new Touch({\n    identifier: Date.now(),\n    target: tile,\n    clientX: x,\n    clientY: y,\n    pageX: x,\n    pageY: y,\n    screenX: x,\n    screenY: y\n  });\n  const touchEvent = new TouchEvent('touchstart', {\n    bubbles: true,\n    cancelable: true,\n    touches: [touchObj],\n    targetTouches: [touchObj],\n    changedTouches: [touchObj]\n  });\n  tile.dispatchEvent(touchEvent);\n  \n  // Wait > 450ms for long-press timer\n  await new Promise(r => setTimeout(r, 500));\n  return document.querySelector('.long-press-menu') !== null;\n}"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Outcome:**
- A `.long-press-menu` element is rendered in the DOM positioned near the touch point.
- The menu presents options:
  - `"Set navidrome_library…"`
  - `"Reimport / reassign MBID…"`

---

### Step 4: Execute "Set navidrome_library…" Touch Action
Handle the browser prompt and select `"Set navidrome_library…"` to change the listening group routing.

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  window.prompt = () => 'kids';\n  const btn = Array.from(document.querySelectorAll('.long-press-menu button'))\n    .find(b => b.textContent.includes('Set navidrome_library'));\n  if (!btn) throw new Error('Set navidrome_library button not found in menu');\n  btn.click();\n}"
}
```

```json
// Tool Call: browser_wait_for
{
  "text": "kids",
  "time": 5
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Outcome:**
- Long-press menu dismisses after selection.
- Toast notification reports success: `Updated navidrome_library on 1 album(s).`
- The album tile's `.lib-badge` updates from `unassigned` to `kids`.
- Confirms the touch long-press menu successfully routes the album to a new library group.

---

### Step 5: Open Album Details & Long-Press Track to Apply Tag
Open the album detail modal and use long-press on a track row to apply a per-track tag (`item` scope).

1. Click the album tile to open details:
```json
// Tool Call: browser_click
{
  "element": "Album tile",
  "target": "#album-grid .album-tile"
}
```

```json
// Tool Call: browser_wait_for
{
  "text": "Tracks",
  "time": 5
}
```

```json
// Tool Call: browser_snapshot
{}
```

2. Trigger long-press on the track row (`.card.grabbable`):
```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  const trackRow = document.querySelector('#modal-root [data-tracks] .card.grabbable');\n  if (!trackRow) throw new Error('Track row not found');\n  const rect = trackRow.getBoundingClientRect();\n  const x = rect.left + rect.width / 2;\n  const y = rect.top + rect.height / 2;\n  \n  const touchObj = new Touch({\n    identifier: Date.now(),\n    target: trackRow,\n    clientX: x,\n    clientY: y,\n    pageX: x,\n    pageY: y\n  });\n  trackRow.dispatchEvent(new TouchEvent('touchstart', { touches: [touchObj], bubbles: true }));\n  await new Promise(r => setTimeout(r, 500));\n  return document.querySelector('.long-press-menu') !== null;\n}"
}
```

```json
// Tool Call: browser_snapshot
{}
```

3. Execute the `"Apply tag…"` action:
```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  let callCount = 0;\n  window.prompt = (msg) => {\n    callCount++;\n    if (callCount === 1) return 'mood'; // Tag field\n    if (callCount === 2) return 'energetic'; // Tag value\n    return null;\n  };\n  const btn = Array.from(document.querySelectorAll('.long-press-menu button'))\n    .find(b => b.textContent.includes('Apply tag'));\n  if (!btn) throw new Error('Apply tag button not found');\n  btn.click();\n}"
}
```

```json
// Tool Call: browser_wait_for
{
  "text": "Applied mood=\"energetic\"",
  "time": 5
}
```

**Expected Outcome:**
- Floating action menu closes.
- Success toast confirms: `Applied mood="energetic" to item #...`.
- Track item in beets library has `mood` field set to `energetic`.

---

### Step 6: Verify Long-Press Cancellation on Touch Move / End
Verify that scrolling or tapping (touch lasting <450ms or moving before timer) cancels the long-press menu without triggering false activations.

```json
// Tool Call: browser_evaluate
{
  "function": "async () => {\n  // Close modal if open\n  const backdrop = document.querySelector('#modal-root .modal-backdrop');\n  if (backdrop && backdrop.close) backdrop.close();\n  \n  const tile = document.querySelector('#album-grid .album-tile');\n  const touchObj = new Touch({ identifier: 1, target: tile, clientX: 100, clientY: 100 });\n  \n  // 1. Test touchmove cancellation\n  tile.dispatchEvent(new TouchEvent('touchstart', { touches: [touchObj], bubbles: true }));\n  await new Promise(r => setTimeout(r, 100));\n  tile.dispatchEvent(new TouchEvent('touchmove', { touches: [touchObj], bubbles: true }));\n  await new Promise(r => setTimeout(r, 400));\n  \n  const menuAfterMove = document.querySelector('.long-press-menu');\n  \n  // 2. Test touchend before threshold\n  tile.dispatchEvent(new TouchEvent('touchstart', { touches: [touchObj], bubbles: true }));\n  await new Promise(r => setTimeout(r, 150));\n  tile.dispatchEvent(new TouchEvent('touchend', { touches: [], bubbles: true }));\n  await new Promise(r => setTimeout(r, 400));\n  \n  const menuAfterEnd = document.querySelector('.long-press-menu');\n  \n  return { moveCancelled: menuAfterMove === null, endCancelled: menuAfterEnd === null };\n}"
}
```

**Expected Outcome:**
- Returns `{ "moveCancelled": true, "endCancelled": true }`.
- No `.long-press-menu` appears when touch interaction is interrupted by movement (scrolling) or early release (tapping).

---

## Teardown

Stop the `beet webimport` process:
```bash
pkill -f "beet webimport" || true
```

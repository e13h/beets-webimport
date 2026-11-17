# Playbook 05 — Cover-Art Preview

This playbook provides an end-to-end procedure for verifying the **Dual Cover-Art Preview** feature in `beets-webimport` using Playwright MCP browser tools against a live running server.

It provides end-to-end verification for cover art previews per **ADR-0009** and **.scratch/webimport/spec.md** (Testing Decisions & Dual cover-art preview sections).

---

## Prerequisites & Environment Setup

### 1. Reset Disposable Test Library & State

Ensure a clean test environment before starting the server:

```bash
scripts/dev-reset.sh
```

Ensure an inbox directory exists under `.inbox/` (for instance `.inbox/Mulan (Original Motion Picture Soundtrack)` or an audio file directory).

### 2. Start the Server

Start the real `beet webimport` plugin server in the background:

```bash
scripts/dev-server.sh
```

The web server serves the web UI at `http://localhost:8338`.

### 3. Required Network Hosts Allowlist

This playbook performs real network lookups against MusicBrainz and the Cover Art Archive (CAA). Outbound network access must be granted for:

- `musicbrainz.org`, `*.musicbrainz.org`
- `coverartarchive.org`, `*.coverartarchive.org`
- `archive.org`, `*.archive.org`
- `itunes.apple.com`, `*.mzstatic.com`

---

## Target Release Under Test

- **Target Release MBID:** `4e929666-952f-473c-baf2-97c9ca6bfbbe` (*Mulan: An Original Walt Disney Records Soundtrack*, the 2020 Digital Media release linked to the test files' iTunes album)
- **Expected Outcome:** Both Source Art and Resolved Art resolve successfully to the CAA Front image, resulting in `match: true` and rendering a green `.art-badge.match` badge with text `"match"`.

---

## Step-by-Step Playwright Verification Flow

### Step 1: Open the Web UI

Navigate to the web interface in the browser.

- **Playwright MCP Call:**
  ```json
  {
    "tool": "browser_navigate",
    "parameters": {
      "url": "http://localhost:8338"
    }
  }
  ```
- **Verification Call:**
  ```json
  {
    "tool": "browser_snapshot",
    "parameters": {}
  }
  ```
- **Expected Observable UI State:**
  - The page loads with navigation tabs `#tabs`.
  - The **Inbox** tab is active (`#tabs button[data-tab="inbox"].active`, `#tab-inbox.tab.active`).
  - `#inbox-dirs` lists available inbox directory cards (`.card`), each containing `.path` and a start button `button[data-start]`.

---

### Step 2: Start Import for the Inbox Directory

Initiate the candidate search pipeline for the inbox album.

- **Playwright MCP Call:**
  ```json
  {
    "tool": "browser_click",
    "parameters": {
      "element": "Start import button on inbox directory card",
      "target": "#inbox-dirs .card:first-child button[data-start]"
    }
  }
  ```
- **Wait Call:**
  ```json
  {
    "tool": "browser_wait_for",
    "parameters": {
      "text": "Review"
    }
  }
  ```
- **Expected Observable UI State:**
  - A card appears under `#pending-reviews` with status text `"Awaiting candidate review"` and a `"Review"` button (`button[data-review]`).

---

### Step 3: Open Candidate Review & Confirm Lazy Art Loading

Open the candidate review modal to inspect candidate items and verify that cover art resolution is computed **lazily** (only for the focused candidate, not upfront for the entire list).

- **Playwright MCP Call:**
  ```json
  {
    "tool": "browser_click",
    "parameters": {
      "element": "Review button on pending review card",
      "target": "#pending-reviews .card button[data-review]"
    }
  }
  ```
- **Verification Call:**
  ```json
  {
    "tool": "browser_snapshot",
    "parameters": {}
  }
  ```
- **Expected Observable UI State:**
  - Modal backdrop and dialog open (`#modal-root .modal-backdrop .modal`).
  - A list of candidates is displayed (`div.candidate`).
  - **Candidate 0 (First candidate):**
    - Automatically receives focus: `div.candidate:first-child.focused`.
    - Initiates art resolution in its preview container `.candidate.focused .art-compare[data-art]` (initially showing `<span class="timer">Resolving art…</span>` before populating).
  - **Candidate 1+ (Unfocused candidates):**
    - Do **not** have the `.focused` class (`div.candidate:not(.focused)`).
    - Their `.art-compare[data-art]` container is completely empty (no images, no pending timers), confirming art resolution is **not** performed upfront for unfocused candidates.

---

### Step 4: Confirm Lazy Loading on Focus Switch

Click an unfocused candidate to verify that art resolution triggers on-demand when focus moves.

- **Playwright MCP Call:**
  ```json
  {
    "tool": "browser_click",
    "parameters": {
      "element": "Second candidate card to change focus",
      "target": ".modal .candidate:nth-child(2)"
    }
  }
  ```
- **Verification Call:**
  ```json
  {
    "tool": "browser_snapshot",
    "parameters": {}
  }
  ```
- **Expected Observable UI State:**
  - The second candidate now has the `.focused` class (`.modal .candidate:nth-child(2).focused`).
  - The first candidate loses the `.focused` class.
  - The second candidate's `.art-compare[data-art]` container now initiates resolution and displays its art comparison / placeholders.

---

### Step 5: Force the Target MusicBrainz Release ID

Use the MBID override input in the review modal to target known release `4e929666-952f-473c-baf2-97c9ca6bfbbe`.

- **Playwright MCP Calls:**
  ```json
  {
    "tool": "browser_type",
    "parameters": {
      "element": "MusicBrainz ID input field",
      "target": ".modal input[data-mbid]",
      "text": "4e929666-952f-473c-baf2-97c9ca6bfbbe"
    }
  }
  ```
  ```json
  {
    "tool": "browser_click",
    "parameters": {
      "element": "Use ID button",
      "target": ".modal button[data-use-id]"
    }
  }
  ```
- **Expected Observable UI State:**
  - The review modal closes.
  - An updated import task is queued in the worker pool with `action: search_id`.
  - The Inbox tab updates as the re-lookup against MusicBrainz completes.

---

### Step 6: Open Target Release Review Modal

Wait for the re-lookup to complete and reopen the candidate review modal.

- **Wait Call:**
  ```json
  {
    "tool": "browser_wait_for",
    "parameters": {
      "text": "Review"
    }
  }
  ```
- **Playwright MCP Call:**
  ```json
  {
    "tool": "browser_click",
    "parameters": {
      "element": "Review button for target release",
      "target": "#pending-reviews .card button[data-review]"
    }
  }
  ```
- **Wait Call for Art Resolution:**
  ```json
  {
    "tool": "browser_wait_for",
    "parameters": {
      "text": "match"
    }
  }
  ```
- **Verification Call:**
  ```json
  {
    "tool": "browser_snapshot",
    "parameters": {}
  }
  ```
- **Expected Observable UI State:**
  - The candidate review modal is open for the target release (`4e929666-952f-473c-baf2-97c9ca6bfbbe`).
  - Candidate 0 is focused (`div.candidate.focused`).

---

### Step 7: Verify Dual Cover-Art Thumbnails and Match Badge

Verify the exact DOM structure and visual feedback of the dual cover-art preview container for the target release.

- **Verification Inspection Points:**
  1. **Container:** `.modal .candidate.focused .art-compare[data-art]` exists.
  2. **Source Art Thumbnail:**
     - Element: `.modal .candidate.focused .art-compare img[alt="source"]`
     - Expected source: Remote CAA front image URL (e.g. `https://coverartarchive.org/...` or `https://ia...archive.org/...`).
  3. **Resolved Art Thumbnail:**
     - Element: `.modal .candidate.focused .art-compare img[alt="resolved"]`
     - Expected resolved URL: Matches the CAA front image selected by fetchart source priority rules.
  4. **Match Indicator Badge:**
     - Element: `.modal .candidate.focused .art-compare .art-badge.match`
     - Expected text: `"match"`
     - Confirms `result.match === true` (source and resolved art match identically).

---

### Step 8: Teardown

Stop the server process when testing concludes and clean up disposable files if desired.

```bash
# Clean up temporary test files
scripts/dev-reset.sh
```

---

## References

- **ADR-0009:** Playwright against a real running server, over in-process `test_client()` scripts (`docs/adr/0009-playwright-against-real-server-over-test-client-scripts.md`)
- **Spec:** `.scratch/webimport/spec.md` (Dual cover-art preview & Testing Decisions)
- **Domain & Glossary:** `CONTEXT.md` (*Source Art*, *Resolved Art*)

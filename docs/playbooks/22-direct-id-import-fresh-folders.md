# Playbook 22: Direct ID Import on Fresh Inbox Folders


## Purpose & Scope

Verifies the **Direct ID Import** workflow on a fresh (unimported) inbox
folder card, per ticket 38 and the Direct ID Import entry in `CONTEXT.md`:
the user supplies a known release identifier at import-start time, the
broad multi-second candidate search is skipped, and the review modal opens
directly on the single targeted candidate for final approval (never
auto-applied). Also verifies the retry error state when the lookup yields
zero candidates.

Depends on the API behavior from ticket 37: `/api/inbox/start` accepts
`{"paths": [...], "search_ids": {"<path>": "<raw ID>"}}`, and a zero-result
targeted lookup registers a review task with an empty candidate list and
`attempted_search_id` in the payload.

## References

- `docs/adr/0009-playwright-against-real-server-over-test-client-scripts.md`
- `docs/playbooks/03-inbox-import-apply-undo.md` (baseline import flow)
- Target test release (Mulan) MBID: `4e929666-952f-473c-baf2-97c9ca6bfbbe`

---

## Network Host Allowlist

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

Ensure the test inbox folder is present:

```bash
ls -la ".inbox/Mulan (Original Motion Picture Soundtrack)"
```

### 2. Start the Webimport Server

```bash
scripts/dev-server.sh
```

---

## Deterministic Execution Steps

### Step 1: Open the Web UI and Verify the Fresh Card Toggle

```json
// Tool Call: browser_navigate
{ "url": "http://localhost:8338" }
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- `#inbox-dirs` shows the Mulan card with an enabled "Start import"
  button (`button[data-start]`) **and** a secondary "Import with ID…"
  button (`button[data-id-toggle]`).
- The ID form (`[data-id-form]`) is hidden (display: none).

Click the toggle:

```json
// Tool Call: browser_click
{
  "element": "Import with ID… toggle on Mulan card",
  "target": "#inbox-dirs .card button[data-id-toggle]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- The ID form expands: input `input[data-id-input]` (placeholder
  "Paste MusicBrainz ID or URL") and button `button[data-id-go]`
  ("Start import with ID"). The default "Start import" button is
  unchanged.

### Step 2: Submit with a Valid MBID (Known-Good)

```json
// Tool Call: browser_type
{
  "element": "Direct ID input on Mulan card",
  "target": "#inbox-dirs .card input[data-id-input]",
  "text": "4e929666-952f-473c-baf2-97c9ca6bfbbe"
}
```

```json
// Tool Call: browser_click
{
  "element": "Start import with ID button",
  "target": "#inbox-dirs .card button[data-id-go]"
}
```

Wait for the review task (single targeted lookup — should appear within
a few seconds, well under the broad-search wait):

```json
// Tool Call: browser_wait_for
{ "text": "Candidates ready for review", "time": 30 }
```

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
- Review modal shows **exactly one** candidate: `Jerry Goldsmith,
  Matthew Wilder & David Zippel – Mulan: An Original Walt Disney
  Records Soundtrack (2020)` (distance around `0.5`: the test files'
  iTunes tags differ from MusicBrainz's titles and artists).
- No error banner is shown.
- The modal's standard actions remain: "Use ID", "Use as-is", "Skip",
  and the candidate's "Select" — approval still goes through the
  standard apply path (no auto-apply happened).

### Step 3: Approve and Verify Apply

```json
// Tool Call: browser_click
{
  "element": "Select candidate button",
  "target": ".modal .candidate:nth-child(1) button[data-select]"
}
```

Wait for full finalization: the folder leaving the Inbox list, not the
album appearing in the Library (see the timing facts in
`docs/agents/dev-environment.md`):

```json
// Tool Call: browser_wait_for
{ "textGone": "Mulan (Original Motion Picture Soundtrack)", "time": 60 }
```

Verify filesystem state:

```bash
.venv/bin/python -c "import glob,mediafile,sys; f=sorted(glob.glob('.library/unassigned/Jerry*/Mulan*/*.mp3'))[0]; sys.exit(0 if mediafile.MediaFile(f).art else 1)" && echo "applied"
BEETSDIR=./.config .venv/bin/beet ls -a | wc -l   # 1 album
```

**Expected Observable Outcome:**
- Album applied under `.library/unassigned/` with embedded cover art; 1 album in library;
  `.inbox/Mulan (Original Motion Picture Soundtrack)` no longer exists.

### Step 4: Reset, then Submit a Bogus ID (Retry Error State)

Reset the library (Step 0 commands), restart the server, reopen the UI,
expand the toggle, and submit a bogus ID:

```json
// Tool Call: browser_type
{
  "element": "Direct ID input on Mulan card",
  "target": "#inbox-dirs .card input[data-id-input]",
  "text": "00000000-0000-0000-0000-000000000000"
}
```

```json
// Tool Call: browser_click
{
  "element": "Start import with ID button",
  "target": "#inbox-dirs .card button[data-id-go]"
}
```

```json
// Tool Call: browser_wait_for
{ "text": "Candidates ready for review", "time": 30 }
```

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
- Review modal opens in the **error state**: banner (`.id-error-banner`)
  reading "⚠ No candidate found for ID
  **00000000-0000-0000-0000-000000000000**.", with a replacement input
  (`input[data-retry-id]`), a "Try ID" button
  (`button[data-retry-go]`), and an "Auto-search instead" button
  (`button[data-auto-search]`). The session was not abandoned.

### Step 5: Retry with a Good ID via the Error-State Input

```json
// Tool Call: browser_type
{
  "element": "Retry ID input in error banner",
  "target": ".modal input[data-retry-id]",
  "text": "4e929666-952f-473c-baf2-97c9ca6bfbbe"
}
```

```json
// Tool Call: browser_click
{
  "element": "Try ID button",
  "target": ".modal button[data-retry-go]"
}
```

```json
// Tool Call: browser_wait_for
{ "text": "Candidates ready for review", "time": 30 }
```

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
- Modal now shows the single Mulan candidate (recovered via correction,
  no session restart). Approving it applies normally (Step 3 checks).

### Step 6 (Alternative Fallback): Auto-Search from the Error State

Repeat Step 4 to reach the error state, then instead click
"Auto-search instead":

```json
// Tool Call: browser_click
{
  "element": "Auto-search instead button",
  "target": ".modal button[data-auto-search]"
}
```

```json
// Tool Call: browser_wait_for
{ "text": "Candidates ready for review", "time": 60 }
```

**Expected Observable Outcome:**
- The task re-registers with the normal broad-search candidate list
  (multiple candidates), proving the fallback ran the unrestricted
  search rather than re-probing the blank ID.

---

## Teardown

```bash
scripts/dev-reset.sh   # stops the server; .inbox back to its initial state
```

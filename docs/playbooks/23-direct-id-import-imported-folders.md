# Playbook 23: Direct ID Import on Already-Imported Folders (Reimport Path)

## Purpose & Scope

Verifies Direct ID Import on an already-imported inbox folder card
(marker-file detection, ADR-0010), per ticket 39: submitting the card's
"Import with ID…" input fires the **Reimport** endpoint
(`/api/reimport`) with just the supplied ID — `from_scratch` off, no
`set_fields` — so the targeted lookup runs query-driven against the
existing library record rather than re-importing the inbox files. The
critical assertion is that **no duplicate album is created** (avoiding
the silent-duplicate trap of ticket 22 / ADR-0010's motivation), and
that the targeted candidate still passes through review-modal approval.

## References

- `docs/adr/0010-inbox-already-imported-detection-via-marker-file.md`
- `docs/adr/0005-reimport-via-temporary-config-mutation.md`
- `docs/playbooks/07-reimport-end-to-end.md` (full Re-import modal)
- Target test release (Mulan) MBID: `a5483fb3-634b-4254-a966-de33cefd1f17`

---

## Network Host Allowlist

Same as playbook 22: `musicbrainz.org`/`*.musicbrainz.org`,
`coverartarchive.org`/`*.coverartarchive.org`, `archive.org`/`*.archive.org`,
`itunes.apple.com`/`*.mzstatic.com`.

---

## Prerequisites & Environment Setup

```bash
rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
rm -f .config/state.pickle && rm -rf .config/webimport
BEETSDIR=./.config .venv/bin/beet webimport
```

---

## Deterministic Execution Steps

### Step 1: Seed — Import Mulan Normally (Direct ID via Fresh Card)

1. Navigate to `http://localhost:8338`.
2. On the Mulan card, click "Import with ID…" (`button[data-id-toggle]`),
   paste `a5483fb3-634b-4254-a966-de33cefd1f17` into
   `input[data-id-input]`, click `button[data-id-go]`.
3. Wait for "Awaiting candidate review", click Review
   (`#pending-reviews .card button[data-review]`), click Select
   (`.modal .candidate:nth-child(1) button[data-select]`).
4. Switch to the Undo tab and wait for "Undoable for".

**Expected Observable Outcome:**
- Mulan imported; Undo tab shows the record; the inbox Mulan card now
  carries the **Imported** badge and shows "Re-import" + "Import with
  ID…" + "Delete from inbox" buttons.

### Step 2: Direct-ID-Import the Same Folder with the Same MBID

```json
// Tool Call: browser_click
{
  "element": "Import with ID… toggle on imported Mulan card",
  "target": "#inbox-dirs .card.imported button[data-id-toggle]"
}
```

```json
// Tool Call: browser_type
{
  "element": "Direct ID input on imported Mulan card",
  "target": "#inbox-dirs .card.imported input[data-id-input]",
  "text": "a5483fb3-634b-4254-a966-de33cefd1f17"
}
```

```json
// Tool Call: browser_click
{
  "element": "Start import with ID button on imported card",
  "target": "#inbox-dirs .card.imported button[data-id-go]"
}
```

```json
// Tool Call: browser_wait_for
{ "text": "Awaiting candidate review", "time": 30 }
```

```json
// Tool Call: browser_click
{
  "element": "Review button for reimport task",
  "target": "#pending-reviews .card button[data-review]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- Review modal shows the single targeted Mulan candidate for approval.
- From-scratch is **not** offered in this modal — it remains exclusive
  to the full Re-import modal (`openReimport`'s `input[data-fromscratch]`).

### Step 3: Approve and Verify No Duplicate

```json
// Tool Call: browser_click
{
  "element": "Select candidate button",
  "target": ".modal .candidate:nth-child(1) button[data-select]"
}
```

```json
// Tool Call: browser_wait_for
{ "textGone": "Awaiting candidate review", "time": 30 }
```

Verify library state after finalization (poll the Undo tab per the
timing facts in `docs/agents/dev-environment.md`):

```bash
BEETSDIR=./.config .venv/bin/beet ls -a | wc -l   # must still be 1
ls ".inbox/Mulan (Original Motion Picture Soundtrack)/.webimport_imported" && echo "marker intact"
```

**Expected Observable Outcome:**
- **Exactly 1 album** in the library — no duplicate was created, and no
  duplicate-decision prompt was needed during apply.
- The marker file remains; the card stays "Imported".
- A fresh undo record appears for the reimport (it goes through the
  same grace mechanism).

### Step 4: Marker Without Album ID Fails Cleanly

Simulate a corrupt marker (no `album_id`) to verify the guard:

```bash
# Stop server, then:
python3 - <<'EOF'
import json, pathlib
p = pathlib.Path(".inbox/Mulan (Original Motion Picture Soundtrack)/.webimport_imported")
d = json.loads(p.read_text()); d.pop("album_id", None)
p.write_text(json.dumps(d))
EOF
# Restart server, reload UI
```

```json
// Tool Call: browser_click
{
  "element": "Import with ID… toggle on imported Mulan card",
  "target": "#inbox-dirs .card.imported button[data-id-toggle]"
}
```

```json
// Tool Call: browser_type
{
  "element": "Direct ID input on imported Mulan card",
  "target": "#inbox-dirs .card.imported input[data-id-input]",
  "text": "a5483fb3-634b-4254-a966-de33cefd1f17"
}
```

```json
// Tool Call: browser_click
{
  "element": "Start import with ID button on imported card",
  "target": "#inbox-dirs .card.imported button[data-id-go]"
}
```

```json
// Tool Call: browser_snapshot
{}
```

**Expected Observable Outcome:**
- An error toast appears: "Cannot Direct-ID-import: library album ID
  unavailable from marker data. Use Re-import instead." The button
  re-enables; **no** fresh import of the inbox files is started
  (`#pending-reviews` stays empty of new tasks).

---

## Teardown

```bash
pkill -f "beet webimport" || true
```

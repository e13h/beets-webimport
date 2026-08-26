# Playbook 15: Placement Conflict UI for Move-on-Field-Change Collisions

## Purpose & Scope

This playbook exercises and verifies the **Placement Conflict** workflow as defined in `.scratch/webimport/spec.md` (User Story 40), `CONTEXT.md` (Placement Conflict glossary entry), and local issue `.scratch/webimport/issues/15-placement-conflict-ui.md`.

When a metadata edit's resulting Move-on-Field-Change would relocate a file to a destination path that is already occupied by an existing file (beyond `%aunique{}` template disambiguation), the system must intercept the move, surface a **Placement Conflict** modal in the UI offering three resolution options (**Keep both**, **Overwrite existing**, **Skip edit / revert**), and execute the chosen resolution.

---

## Scenario Overview

1. An existing album (e.g. `Mulan`) is imported into the library with `navidrome_library=unassigned`.
2. An unrelated file is placed at the destination where moving the album to `navidrome_library=kids` would place it (e.g. `.library/kids/Disney/Mulan/01 Honor to Us All.mp3`).
3. The user opens the Album Detail modal in the Library tab and edits `navidrome_library` to `kids`, then clicks **Save**.
4. The server detects the destination collision, prevents silent overwriting or corrupted moves, and returns a `409 Conflict` response with collision details.
5. The frontend displays the **Placement Conflict** modal with collision path and actions: `Keep both`, `Overwrite existing`, `Skip edit (revert)`.
6. **Scenario A (Skip)**: User clicks **Skip edit (revert)**. The database fields revert to `unassigned`, files remain untouched, and an info toast notifies the user.
7. **Scenario B (Keep both)**: User re-attempts the edit and selects **Keep both**. The files are moved and disambiguated (e.g. appending `.1`), preserving both existing and new files.
8. **Scenario C (Overwrite)**: User re-attempts the edit with an occupied path and selects **Overwrite existing**. The colliding file is replaced with the newly relocated file.

---

## Step-by-Step Execution Procedure

### Step 1: Open Library & Select Album
1. Open `http://localhost:8338` in browser.
2. Click the **Library** tab (`#tabs button[data-tab="library"]`).
3. Click an album tile to open the Album Detail modal.

### Step 2: Edit Field to Colliding Value
1. In the Album Detail modal, locate the `navidrome_library` input (`[data-field="navidrome_library"]`).
2. Type `kids` (or the colliding value).
3. Click **Save (auto-move if path changes)** (`[data-save-album]`).

### Step 3: Verify Conflict Modal
1. Observe the Placement Conflict modal appears over the view.
2. Verify modal text contains `Placement Conflict` and displays the conflicting destination path in a `<pre class="path">` block.
3. Verify the three action buttons are visible:
   - `[data-keep-both]` ("Keep both")
   - `[data-overwrite]` ("Overwrite existing")
   - `[data-skip]` ("Skip edit (revert)")

### Step 4: Resolve via Skip
1. Click `[data-skip]`.
2. Confirm the modal closes and an info toast appears ("Edit skipped (reverted).").
3. Re-open the album detail: confirm `navidrome_library` remains `unassigned` (or prior value) and files did not move.

### Step 5: Resolve via Overwrite or Keep Both
1. Edit `navidrome_library` to `kids` again and click **Save**.
2. When the conflict modal appears, click `[data-keep-both]` (or `[data-overwrite]`).
3. Confirm the modal closes, a success toast appears ("Album saved."), and the library badge updates to `kids`.

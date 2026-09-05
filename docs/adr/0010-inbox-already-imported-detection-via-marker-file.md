# 0010: Inbox Already-Imported Detection via Directory Marker File

> **Superseded by ADR-0012** for the UI behavior: imported folders now
> live in the Approve tab (renamed from Undo), with "Undo import" /
> "Confirm import and delete inbox files" actions, a 30-day destructive
> Grace Period, and no in-tab reimport button. The marker file mechanism
> defined below carries over unchanged.

## Context

Because beets is configured in `copy: yes` mode (`move: no`), source audio
files remain in `.inbox/` after a successful import. Currently, `/api/inbox`
scans directory listings with no cross-reference to library state.
Re-clicking "Start import" on an already-imported directory re-runs full
candidate review and can silently create duplicate library entries if
candidate metadata tags differ from raw tags.

## Decision

When an import is successfully applied, the backend writes a hidden marker
file (`.webimport_imported`) directly inside the imported inbox folder.

The marker file contains:
- `album_id`: Beets library database ID of the imported album
- `imported_at`: ISO timestamp of the apply event
- `staging_bin`: Boolean indicating if this is an ad-hoc Staging Bin

### Lifecycle & Invariants

1. **Scan & Detection:** `/api/inbox` checks for the presence of
   `.webimport_imported`. Folders containing this marker are reported as
   `imported: true` with their associated `album_id`.
2. **Undo integration:** If an import is undone during its Grace Period,
   the undo handler removes the `.webimport_imported` marker file,
   instantly returning the folder to unimported status.
3. **Staging Bins compatibility:** For Staging Bins (`_grouped/<id>/bin_N/`),
   the marker marks that bin as imported. When the bin's Grace Period
   expires, the Staging Bin directory (and its marker) is pruned per ADR-0003
   and ticket #13.
4. **UI Behavior (superseded by ADR-0012):** ~~Already-imported folders
   display an `[Imported]` badge with "Start import" replaced by a
   "Re-import" button and a "Delete from inbox" action.~~ Imported folders
   now appear in the Approve tab instead.

## Consequences

- **Pros:** Zero-overhead scans (simple file existence check), persists
  reliably across plugin restarts without requiring an external tracking
  database, stays attached if folders are moved within the inbox, and
  integrates cleanly with Grace Period undo.
- **Cons:** Writes a hidden file into the user's inbox folder.

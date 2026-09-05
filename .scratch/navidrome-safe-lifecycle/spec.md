# navidrome-safe-lifecycle — spec

Outcome of a grilling session (2026-09-05). Full shared-understanding
summary was confirmed by the user; ADRs 0011/0012 written, ADR-0001 and
ADR-0010 updated, CONTEXT.md reworded.

## Goal

Rework the inbox-original lifecycle around the `.webimport_imported`
marker, and make all path-changing metadata edits two-phase so Navidrome
can remap PIDs without losing playlists/play counts.

## Decisions

1. **Approve Tab** (renamed from Undo): folders with a marker appear only
   there, as "imported N days ago". Actions: "Undo import" (delete marked
   album, remove marker → back to Import tab) and "Confirm import and
   delete inbox files" (delete originals + marker). No reimport button in
   this tab; redo = undo then re-import from scratch. Marker schema
   unchanged (`album_id`, `imported_at`, `staging_bin`); `album_id` must be
   updated on every apply (fixes a live staleness bug).
2. **Grace Period redefined**: destructive auto-delete of inbox originals,
   default **30 days**, configurable, disable-able (manual confirm only).
   Staging Bins share the lifecycle. It no longer bounds library undo.
3. **Two-Phase Edit** (supersedes Move-on-Field-Change): any library
   operation changing computed paths (field edits, bulk edits, Library-tab
   reimport apply) writes metadata, defers move to Pending Move state,
   resolved by manual user confirmation (Navidrome API integration =
   backlog). No phasing when path doesn't change; Import-tab applies are
   single-phase. Pending moves detected via actual-path vs computed-path
   mismatch (no persistence), advisory not locks, superseded by later
   operations. UI: badge + inline confirm, bulk confirm all.
4. **Copy mode is the supported mode.** Under `move: yes` the plugin
   degrades to a plain import GUI (no Approve tab, no undo). No move-mode
   support is built.
5. Undo after reimport deletes the currently-marked album and resets the
   folder to unimported; prior library metadata is not resurrected.

## ADRs

- `docs/adr/0011-two-phase-metadata-edits.md` (new)
- `docs/adr/0012-approve-tab-inbox-original-lifecycle.md` (new; supersedes
  UI clauses of ADR-0010)
- ADR-0001, ADR-0010 updated in place.

## Fog

- The Navidrome PID/remap premise behind two-phase is **unverified**
  (docs-derived only). Spike 01 must run first; if falsified, two-phase is
  unnecessary and Move-on-Field-Change is restored.

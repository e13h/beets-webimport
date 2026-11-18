# 0012: Approve Tab — Marker-Driven Inbox Original Lifecycle

> **Superseded by ADR-0015** (move mode; Undo Import restores originals from the library).

Under copy mode, inbox originals are the undo mechanism, so their lifecycle
is user-visible state, not a background timer's business. The Undo tab is
renamed **Approve** and redefined: a folder containing the
`.webimport_imported` marker (ADR-0010's schema, unchanged) appears *only*
there — never in the Import tab — shown as "imported N days ago" from
`imported_at`. Two actions: **Undo import** (delete the marked album from
the library, remove the marker → folder returns to the Import tab as
unimported) and **Confirm import and delete inbox files** (delete inbox
originals + marker → album is permanent). The Grace Period becomes a
destructive auto-delete of inbox originals performing the same action as
Confirm: default **30 days**, configurable, disable-able (manual confirm
only). Staging Bins share this single lifecycle. There is no reimport
button in the Approve tab; redo = undo, then re-import from scratch.
Undo after a reimport targets the marker's `album_id`, which every
successful apply updates — so undo always removes the currently-live
album and resets the folder to unimported; prior library metadata is not
resurrected.

Supersedes ADR-0010's UI clauses (its "Re-import" button and
`[Imported]`-badge-in-Inbox behavior); the marker file mechanism itself
carries over.

## Consequences

- Under `move: yes`, no marker can exist and there is nothing to approve;
  the plugin degrades to a plain import GUI (no Approve tab, no undo).
- Grace expiry now deletes inbox files, so the window to catch a bad match
  is the whole 30 days — undo of the *library record* itself is bounded by
  the marker's presence, not the timer.
- The marker's `album_id` going stale after reimport is a live bug to fix
  as part of this work.

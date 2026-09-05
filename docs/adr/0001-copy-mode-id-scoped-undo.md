# Copy-mode import with ID-scoped undo

Beets runs in `copy` mode (`copy: yes` / `move: no`): inbox originals are
never moved, only copied into the library. This is the plugin's supported
mode: the whole Approve/undo lifecycle (ADR-0012) exists because the inbox
original survives the import, making undo a cheap `remove(delete=True)` on
the exact `Album`/`Item` DB IDs captured from the real
`album_imported`/`item_imported` events at the moment of that import —
never a re-derived query (e.g. by artist/album name) that could risk
matching unrelated library items. Under `move: yes` no original survives,
no marker is written, and the plugin degrades to a plain import GUI: no
Approve tab, no undo.

Undo semantics under ADR-0012: an inbox folder with a
`.webimport_imported` marker can be undone at any time ("Undo import" in
the Approve tab), removing exactly the marked album and returning the
folder to unimported state. Inbox originals are themselves deleted only by
"Confirm import" or Grace Period expiry (30-day default, disable-able).

## Consequences

- Re-submitting the same inbox original for import is not a normal flow
  anymore: imported folders are hidden from the Import tab (ADR-0012), and
  redo means undoing first. If a duplicate does reach beets anyway,
  `duplicate_action: ask` flags it and prompts
  (skip/overwrite/keep both) before a second copy is created. Undo always
  targets the marker's `album_id` (updated on every apply), so it removes
  exactly one copy.
- This decision is effectively permanent as long as the library is meant
  to be safely rebuildable from originals: `move` mode is out of scope
  beyond degrading the UI; a real restore-on-undo path would be its own
  ADR.

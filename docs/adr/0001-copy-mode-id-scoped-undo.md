# Copy-mode import with ID-scoped undo

Beets runs in `copy` mode (`copy: yes` / `move: no`): inbox originals are
never moved, only copied into the library. This makes "undo" cheap and safe
to implement as `remove(delete=True)` on the exact `Album`/`Item` DB IDs
captured from the real `album_imported`/`item_imported` events at the moment
of that import — never a re-derived query (e.g. by artist/album name) that
could risk matching unrelated library items. Because the inbox original is
untouched, undo needs no restore step: the file is immediately available to
re-enter the review queue.

## Consequences

- Re-submitting the same inbox original for import while an earlier import
  of it is still within its grace period is not ambiguous: beets'
  `duplicate_action: ask` flags it as a duplicate and prompts the user
  (skip/overwrite/keep both) before a second copy is created. Undo always
  targets the specific captured IDs, so it removes exactly one copy
  regardless of how many similar copies exist in the library.
- This decision is effectively permanent as long as the library is
  meant to be safely rebuildable from originals: switching to `move` mode
  would require a real restore-on-undo path instead.

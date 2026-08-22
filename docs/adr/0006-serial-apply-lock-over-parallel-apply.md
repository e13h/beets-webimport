# Serial Apply Lock over parallel apply

The db-write/move ("apply") step is serialized across concurrently-reviewed
Import Tasks via a single global Apply Lock, while candidate search/review
itself remains parallel (one Import Session per inbox submission in a
bounded worker pool). Only one task's apply step runs at a time.

This is **not** protecting against unsafe concurrent SQLite writes — beets'
own `Database` already serializes those internally (a per-`Database`
`threading.Lock` plus one connection per thread, `check_same_thread=False`).
The real motivation, discovered while grilling this decision: **path
disambiguation correctness**. Beets computes each item's destination path
(via `%aunique{}` and friends) by reading current library state; if two
applies ran concurrently, both could read the same pre-write state, both
conclude they're not colliding, and then both write — producing a real
collision or a corrupted disambiguation suffix. The lock closes that window
by ensuring one task's full apply (path computation through the
`album_imported`/`item_imported` event confirming it's done) completes
before the next one starts.

Apply order across tasks is not required to be fair or FIFO — only mutual
exclusion matters. See "Apply Lock" in `CONTEXT.md` (not "apply queue": no
ordering guarantee is implied or provided).

## Considered options

- **Parallel apply**: would only matter if apply itself (copy + tag write +
  art embed) is slow enough, and reviewers finish concurrently often enough,
  for serialization to be a real bottleneck. Given solo usage today, this is
  deprioritized to a spike (carry-forward list), not built.

## Consequences

- The lock's acquire/release window (right before returning a final
  decision from `choose_match`/`choose_item`, released only once
  `album_imported`/`item_imported` confirms that task's apply is done)
  already brackets the full path-computation-to-write window, so the
  current implementation already satisfies this reasoning — no code change
  required as a result of clarifying it.

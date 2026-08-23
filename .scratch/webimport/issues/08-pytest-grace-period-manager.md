# 08: pytest unit tests — GracePeriodManager

**What to build:** Fast, no-network pytest coverage for
`beetsplug/webimport/grace.py`'s `GracePeriodManager`: registration,
expiry pruning, and ID-scoped undo, using the fixture from ticket 02.

**Blocked by:** 02

**Status:** done

- [x] Test: registering a record makes it appear in `list_undoable()` with a decreasing `seconds_remaining`.
- [x] Test: a record older than `grace_period_seconds` is pruned from `list_undoable()` and can no longer be undone (`undo()` returns `False`).
- [x] Test: `undo()` on a real registered album/item ID removes exactly that DB entry and its files (`remove(delete=True)`), scoped strictly to the given ID (per ADR-0001) — verified against the disposable library fixture, not real MusicBrainz data.
- [x] Test: `undo()` on an unknown or already-consumed record ID returns `False` rather than raising or silently matching something else.
- [x] No network access required.

# 10: pytest unit tests — library.py's _jsonable_fields

**What to build:** Fast, no-network pytest coverage for
`beetsplug/webimport/library.py`'s `_jsonable_fields` helper, which
decodes beets' raw-bytes fields for JSON serialization, using the fixture
from ticket 02.

**Blocked by:** 02

**Status:** done

- [x] Test: a real `Item`/`Album` with bytes-valued fields (`path`, `artpath`, `destination()`) round-trips through `_jsonable_fields` into a dict that's actually JSON-serializable (e.g. `json.dumps` doesn't raise).
- [x] Test: the decoded values match the original paths (accounting for `os.fsencode`/`os.fsdecode`).
- [x] Test: a field that is `None` (e.g. no `artpath` set) decodes to `None`/absent rather than raising.
- [x] No network access required.

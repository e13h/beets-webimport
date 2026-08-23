# 11: pytest unit tests — tag vocabulary store

**What to build:** Fast, no-network pytest coverage for
`beetsplug/webimport/tags.py`'s Tag Vocabulary storage/management logic
(distinct from Listening Group's live-derived autocomplete — see
`CONTEXT.md`), using the fixture from ticket 02.

**Blocked by:** 02

**Status:** done

- [x] Test: adding a new tag name/value to the vocabulary persists it and it's retrievable afterward.
- [x] Test: applying a tag at the album level writes it down to every track file in that album (`beet write` equivalent), per the spec's "album-level tag assignment writes down to every track file" requirement — verified against the disposable library fixture.
- [x] Test: applying a tag to an individual track only affects that track, not the whole album.
- [x] No network access required.

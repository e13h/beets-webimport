# 17: Thumbnail caching layer for the library grid

**What to build:** The library browse grid currently serves `artpath`
directly with no resizing/caching layer. Add resized (e.g. 200x200),
cached thumbnails for grid display, falling back to extracting embedded
art from the file only when `artpath` is null, per the spec's Library
Browse & Metadata Editing user stories.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] Library grid thumbnails are served from a resized, cached representation rather than the full-size `artpath` file directly.
- [x] Cache is invalidated/regenerated when an album's art changes (e.g. after a reimport or a manual art replacement).
- [x] Albums with a null `artpath` still show art by falling back to extracting embedded art from the file, cached the same way.
- [x] Verified to keep the library grid responsive at the current ~800-album scale (informal timing check acceptable — no formal perf budget specified).

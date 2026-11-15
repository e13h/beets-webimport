# 41: Replace album art on an album already in the library

**Status:** needs-triage

**Blocked by:** None

**Problem:** Some library albums have the wrong cover art. The only fix
today is a full reimport. That rewrites all metadata and can move files,
which risks Navidrome losing playlists and play counts (see
navidrome-safe-lifecycle ticket 03). Fixing art alone shouldn't need any
of that.

**What to build:** From the album detail view in the Library tab, the user
chooses a replacement image, previews it next to the current art, and
applies it. Applying embeds the image into every track of the album. Image
sources:
- other images on the Cover Art Archive for the album's `mb_albumid`
  (release first, then release group), shown as a pick list;
- an uploaded image file, for art from an iTunes/Amazon purchase or
  elsewhere.

Art follows the configured `embedart`/`fetchart` behavior rather than
hardcoding the homelab's. Under the homelab config
(`embedart.remove_art_file: yes`, `art_filename: albumart`) the image is
embedded and no art file is kept, so `artpath` stays null. If
`remove_art_file` is off, the album's art file and `artpath` are
replaced too.

**Why this is single-phase:** embedding art doesn't change any computed
path, so per ADR-0011 no Pending Move applies. File paths stay the same,
so Navidrome keeps its IDs and picks up the new art on its next scan.

**Acceptance criteria:**
- [ ] An API endpoint embeds a given image (a CAA image URL for the
      album's release/release group, or an uploaded file) into all of an
      album's items, using beets' own embed logic (`beets.art` /
      `embedart` helpers) rather than writing tags directly.
- [ ] Respects `embedart.remove_art_file`, `embedart.maxwidth` /
      `compare_threshold` where set, and `art_filename`.
- [ ] File paths are unchanged after apply. A unit test asserts every
      item's `path` is identical before and after.
- [ ] The library grid thumbnail updates without a manual cache clear.
      `coverart.py` keys the cache on the first item's `st_mtime_ns` when
      `artpath` is null, so this should already work. Verify it.
- [ ] UI: album detail view has a "Change art" action showing current art
      and candidate art side by side, with explicit apply. Works with
      touch on mobile.
- [ ] Uploads are restricted to image types, and the server checks that
      the file decodes as an image before embedding.
- [ ] A playbook covers: import Mulan → replace art with a different CAA
      image → embedded art in the tracks changed → paths unchanged →
      thumbnail updated.

**Out of scope:** changing metadata or switching to a different release.
That's a reimport, and safe handling of the path changes it causes is
navidrome-safe-lifecycle ticket 03.

## Comments

# 0017: Reimport Suggests What a Fresh Import Would

A Library-tab Reimport now offers the same suggestions as a fresh inbox
import of the store download:

- **iTunes purchases** start from the MusicBrainz release(s) linked to the
  album's Apple Music listing (`apple_music_match`), with the same fallback
  to a normal search when none is linked or it can't be fetched. "Search
  again" afterwards is the user's: the Apple match runs once per album.
- **Store purchases** (iTunes, Amazon) get the likeliest digital releases
  added and marked "likely your purchase" (`purchase.py`).
- **iTunes Store art** is an Art Choice (ADR-0013), and the default as for a
  fresh import. The album folder's image file isn't offered: in the library
  that's beets' own copy of the current art, which "Keep" already covers.

The store IDs (`plID`, `sfID`) are read from the library files or, when an
earlier import rewrote their tags and dropped them, from the stored
originals (ADR-0014, rebuilt in memory; nothing is written). On the
homelab, 33 of 46 iTunes albums had the IDs only in their originals.

The inbox finds its Apple match before the session starts (one folder, one
task). A reimport can cover several albums in one query session, so the
session finds each album's match in `choose_match`, after beets' own first
search; that search's candidates are replaced. One extra search per album
was preferred over one session per album.

Art options are fetched per review (`/api/review/<id>/art_options`), so the
server knows whether the review is an inbox folder or a library album.

## Consequences

- beets 2.x expands an item's relative DB path when the value is first
  read, with the reading thread's music dir. A reimport's items are read
  in the pipeline's first stage, where it can be unbound, and reached the
  review with relative paths: their files couldn't be read, and beets'
  duplicate check (task paths vs. the library album's paths) flagged the
  album as a duplicate of itself. The session makes them absolute before
  the review (`_resolve_item_paths`).
- A reimport to the suggested release changes the track's Navidrome IDs;
  it goes through Two-Phase Edit as before (ADR-0011).
- The config's `import.set_fields` are defaults for new imports (homelab:
  `navidrome_library: unassigned`). beets applied them to reimports too,
  after copying the replaced album's fields, so every reimport reset the
  album's Listening Group and moved its files. A reimport now applies only
  the fields set in the Reimport dialog; other `set_fields` keys keep the
  album's and tracks' values (`reimport.keep_library_fields`), and apply
  only where the album had none.

## Starting from the original download's tags

A reimport of an album whose tracks all have a stored original starts from
the originals' tags, not the current ones: at `import_task_created`, before
beets' first search, each track's tag fields are replaced in memory by its
original's (`reimport.restore_original_tags`, read from the rebuilt bytes,
nothing written). The chosen release is applied on top, so fields the
release doesn't set (genre, copyright, comments from the store) come from
the purchase, as for a fresh import of the download; a skipped review
changes nothing. All tracks or none: an album half from originals would
match as neither.

`--from-scratch` (clear every tag field, then apply the release) is only
offered for albums without stored originals. With originals it would
discard the purchase's tags this is meant to keep.

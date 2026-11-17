# 30: Track detail modal & full track metadata view

**What to build:** In the Library album detail modal, clicking a track in the track list should open a Track Detail modal displaying full track metadata (title, artist, track number, disc, length, bitrate, format, mbid, and flexible attributes), backed by `GET /api/library/items/<item_id>` per User Story 35.

**Blocked by:** None (can start immediately)

**Status:** resolved

- [ ] Clicking a track row in the album detail view opens a dedicated Track Detail modal.
- [ ] Fetches and renders full track metadata from `GET /api/library/items/<item_id>`.
- [ ] Displays core audio metadata (track title, artist, track/disc numbers, duration, bitrate, audio format, MusicBrainz track/recording ID).
- [ ] Displays custom/flexible attributes attached to the item.
- [ ] Includes close button and Escape key dismissal matching standard modal behavior (per #28).

## Comments

**2026-11-17 — resolved by the metadata explorer** (`static/explorer.js`,
`GET /api/library/albums/<id>/explore`). Track details are shown in the
album modal's explorer (tree of tracks, field list on the right) rather
than in a separate modal. All beets fields are shown, grouped, including
flexible attributes. The explorer also compares each track's beets DB
values with the tags written in its file
(`GET /api/library/albums/<id>/filetags`). Read-only; editing is 31/32.


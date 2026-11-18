# 01 — Spike: verify Navidrome PID remap behavior

Status: resolved
Type: research
Blocked by: —

**Prerequisite for 03 (two-phase implementation).**

Verify (or falsify) the premise from Navidrome docs, untested by us:
Navidrome remaps its PIDs when a file's *metadata* changes while its *path*
stays stable — but loses the mapping (playlists, play counts) when metadata
and path change atomically in one step.

Method: local Navidrome instance, one album with a playlist and play count;
(1) metadata-only edit, (2) metadata+rename in one go; observe PID/playlist
survival via Navidrome's API or DB.

**If falsified**: two-phase is unnecessary — restore Move-on-Field-Change,
retire ADR-0011, drop 03.

## Notes (2026-11-17)

Target: Navidrome **0.64.2** (homelab runs `deluan/navidrome:latest`, no
`ND_*` env vars and no navidrome.toml; music is mounted `:ro`). Reproduce
with the image pinned to `0.64.2`. The effective config exported from the
running server (2026-11-18) confirms the defaults below. Other settings that
matter:
- `MusicFolder = "/music"`: a single folder in the config. Additional
  libraries would be configured in the database, not in the config, so that
  question is still open.
- `AutoImportPlaylists = true`, `PlaylistsPath = ""`: `.m3u` files anywhere
  under `/music` get imported as playlists. Those reference tracks by *path*,
  so a rename may break them whatever the PID matching does. Check whether
  any of the homelab playlists are file-based.
- `Scanner.IgnoreDotFolders = true`: the test library root must not sit
  inside a dot-folder within the mount. The dev `.library/` is fine only if
  it is the mount root itself.
- `Scanner.Extractor = "taglib"`, `DevSelectiveWatcher = true`, `Schedule = ""`
  (no periodic scans; the watcher plus scan-on-startup do all the scanning).

Relevant defaults (navidrome.org configuration options):
- `PID.Track` = `musicbrainz_trackid|albumid,discnumber,tracknumber,title`
- `PID.Album` = `musicbrainz_albumid|albumartistid,album,albumversion,releasedate`
- Watcher on (`Scanner.WatcherWait` 5s), `ScanOnStartup` true,
  `Scanner.Schedule` 0, `PurgeMissing` never (missing rows are kept).

Navidrome's docs (persistent-ids, "Handling File Moves and Retagging") say
a missing file is matched to a new file by exact tags, then PID, then path
without extension. They also say "Retagging and moving files cannot be done
in the same scan". Their recommended order is move, scan, then retag. That's
the reverse of ADR-0011's order; either order should work if only one thing
changes per scan.

Open questions the docs don't answer (cover them in the repro):
- Does an edit that changes the path but keeps `musicbrainz_trackid` (and so
  the PID) get matched even if tags change in the same scan?
- Files with no MBIDs (as-is / iTunes imports): the PID falls back to album
  and title fields, so retagging changes it.
- A move across Navidrome library roots (changing `navidrome_library`, see
  ADR-0002): is a missing file ever matched to one in a different library?
- `navidrome missing fix "old" "new"` is a manual repair tool, so it's a
  possible remedy as well as the two-phase approach.

Homelab library layout (from the user, 2026-11-17): all playlists were made
in Navidrome itself; there are no `.m3u` files. Library 1 is `/music` (the
original root), which Navidrome won't let you remove. Listening Groups were
later added as subdirectories, and those are registered as further
libraries. So the libraries **overlap**: every track is indexed once in the
root library and once in its group library. A `navidrome_library` change is
therefore a move *within* the root library but *between* the group
libraries, and a playlist can hold either copy. The repro must mirror this
layout. Possible side fix, outside this ticket: rebuild without the root
library.

## Results (2026-11-17, Navidrome 0.64.2)

Harness: `repro/repro.py`. Run it with `.venv/bin/python
.scratch/navidrome-safe-lifecycle/repro/repro.py [--keep]`. Output goes to
`repro/results-*.md`; the latest runs are `repro/results-explicit-scans.md` and `repro/results-watcher.md`. It uses mp3 fixtures written by beets, the homelab path
templates, and overlapping libraries `/music`, `/music/main` and
`/music/kids`. Every track gets a playlist entry, a star and 2 plays in both
of its libraries. Scans are explicit (the watcher is off).

| edit | with MBIDs | without MBIDs |
|---|---|---|
| tag-only, path unchanged | kept | kept |
| retitle / rename album: write tags + rename, one scan | kept | **lost** |
| same, rename only, tags untouched (webimport today) | kept | kept |
| Listening Group move (path-only, crosses libraries) | kept | kept |
| rename album + group move, one scan | kept | **lost** |
| new release MBIDs + rename, one scan (reimport to a different release) | **lost** | **lost** |
| every two-phase variant (tags first *or* move first) | kept | kept |

What we learned:
- **The premise holds, with conditions.** History is lost only when the PID
  and the path change in the same scan. Changing one at a time, in either
  order, always kept it. ADR-0011's order (tags first) works, and so does
  the order Navidrome's docs recommend (move first).
- **PID.Track `musicbrainz_trackid` is the release-track ID** (beets
  `mb_releasetrackid`), not the recording ID (`mb_trackid`). For
  MusicBrainz-matched files the PID doesn't change on ordinary edits, so a
  one-scan edit is safe. It changes when you reimport to a *different
  release*, which loses history even with MBIDs.
- **Without MBIDs** the PID is built from albumid, disc, track and title, so
  any title or album edit that also renames the file loses history.
- **Moves across libraries work, matched by PID only.** Navidrome
  re-parents the existing row into the new library ("Found cross-library
  moved track"). The overlapping root library also matches within itself.
  The overlap wasn't the cause in any case tested.
- **webimport's field edits never write tags** (`set_album_fields` /
  `set_item_fields` only `store()` + `move()`). That's why they're harmless
  to Navidrome, but it's a separate bug: the file tags (and what Navidrome
  shows) stay stale until something writes them. Once tag writing is added,
  edits to files without MBIDs will start losing history.
- Harness pitfall: beets' as-is import (`-A`) doesn't write tags, so the
  fixtures need `beet write -f` first. Otherwise the first edit changes
  tags the edit itself didn't touch.

Follow-up cases:
- **D0: a group move on files beets never wrote (as-is imports) lost
  history** when the files had no MBIDs. `beet modify` writes tags by
  default, so the move was also the files' first beets write, which changed
  their PID. This is the likely cause of the user's past `navidrome_library`
  losses. The homelab has 36 tracks without `mb_releasetrackid`.
- **U: a move into a group folder that isn't a Navidrome library yet**, then
  registering it and scanning again, **kept history**. Missing rows are
  matched to the new library on the later scan.
- The user's past release changes were done with `beet modify` on the
  command line, which matches case R. As of 2026-11-17 the homelab has no
  missing files; the earlier losses were cleaned up by hand.

Auth (Subsonic API, 0.64.2): every call needs credentials. Without them:
error 10 "missing parameter: 'u'". A non-admin user can call
`getScanStatus` but gets error 50 on `startScan`. An admin can do both.

Repair tool: `navidrome missing list|fix` runs inside the Navidrome
container and works there (the image sets `ND_DATAFOLDER=/data`).

Watcher mode (`--watch`: homelab `WatcherWait` 5s, every scan triggered by
the watcher): **same results for every case.** Two-phase works when the
pause between phases is "wait for the watcher's scan". `getScanStatus`
reports the scan type `quick-selective` for those scans.

A non-admin user can't have zero libraries ("at least one library must be
assigned"). With access to only one unrelated library it still gets the
server-wide scan status. The user created a `webimport` Navidrome user
(2026-11-17).

Not covered yet: m4a (iTunes) files and album-level history.

Direction agreed with the user (2026-11-17): webimport talks to Navidrome
itself. A path-changing edit becomes: write tags, wait for Navidrome's scan
(via the Subsonic API), then move. This replaces ADR-0011's manual
confirmation. The Navidrome URL and credentials go in the webimport config.

## Answer

The premise holds, narrowed down: history is lost when a track's PID and
path change in the same scan. Two-phase (either order) always kept it. 03
was implemented with automatic confirmation via Navidrome's scan status
(ADR-0011, rewritten).

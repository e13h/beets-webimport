# 0011: Two-Phase Metadata Edits (tags first, move after Navidrome's scan)

Navidrome keeps a track's history (playlists, play counts, stars) across a
rename by matching the missing file to the new one by tags, then by
persistent ID (PID), then by path. It can't follow a track whose PID *and*
path change in the same scan: the old row goes missing and a new row starts
with no history. Spike 01 (`.scratch/navidrome-safe-lifecycle/`, Navidrome
0.64.2) confirmed this and narrowed it down. `PID.Track` is
`musicbrainz_trackid` (beets' `mb_releasetrackid`) or, without it, a hash
of album, disc, track number and title. So the edits that lose history are:

- a reimport to a different release, which changes the MBIDs;
- a title or album edit on a file without MBIDs;
- the first tag write on a file beets never wrote (an as-is import) when
  it is combined with a move.

Changing one thing per scan, in either order, always kept history. That
includes moves between Navidrome libraries, which are matched by PID.

Therefore every library operation that **writes tags and changes a file's
computed path** is two-phase. Phase 1 writes the tags and leaves the files
where they are. Phase 2, the move, runs once Navidrome has scanned the new
tags. Confirmation is automatic: webimport polls Navidrome's Subsonic
`getScanStatus` (`webimport.navidrome`: `url`, `user`, and the password in
`WEBIMPORT_NAVIDROME_PASSWORD`). A regular Navidrome user is enough: scan
status is server-wide.

## Rules

- **Tags written + path changed** (Library-tab reimport, API field edits of
  tag fields): Pending Move.
- **Only beets-only fields changed** (e.g. `navidrome_library`): move at
  once. The files' tags are untouched and are what Navidrome already has,
  so it matches them by tags or PID. If the album already has a Pending
  Move, it stays pending instead.
- **Navidrome integration off**: move at once (plain beets behaviour).
- **Import-tab applies**: single-phase. Those files never existed in
  Navidrome.

## When a pending move is safe

`lastScan` is when a scan *finished*. A scan that was already running when
the tags were written can finish after the write without having seen it.
So a pending move resolves only after the poller has seen Navidrome idle
(`scanning: false`) after the write, and then sees `lastScan` change. That
scan started after the write. If no scan comes within
`scan_request_after` seconds, webimport asks for one (`startScan`). That
needs an admin user; with a regular user it just keeps waiting, since
Navidrome's file watcher normally scans about 5 seconds after the write.

## Consequences

- Pending state is in memory only (ADR-0004). At startup, albums whose
  files aren't at their computed path are listed as pending but are
  **never moved automatically**: a changed path template would otherwise
  move the whole library. They wait for "Move now".
- "Move now" is the user's override, with a warning. It also covers
  Navidrome being unreachable.
- A later write supersedes a pending move (the wait starts over), and
  Undo import drops it.
- The reimport's own session gets `move`/`copy` off in its private config
  (`WebImportSession.hold_files`). The global import config isn't touched:
  parallel inbox reviews read it outside the Apply Lock.
- Not covered: edits made outside webimport (`beet modify`, `mbsync`).
  Nothing waits for Navidrome there.
- Rejected: manual per-album confirmation as the only mechanism (the
  original version of this ADR), and comparing `lastScan` with file mtimes
  (unsound, see above).

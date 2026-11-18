# 06 — Path-changing edits outside webimport aren't phased

Status: needs-triage
Type: task
Blocked by: —

Pending Move (ADR-0011) protects only edits made through webimport. The
user's past history losses came from `beet modify` on the command line
(changing the release, then the tags and paths changed together), which
nothing makes wait for Navidrome. Also, 36 homelab tracks have no
`mb_releasetrackid`, probably as-is imports beets never wrote. Their first
write combined with a move loses history (spike case D0).

Options: document "change releases with the Library-tab Reimport"; a
`beet` subcommand from the plugin that phases a modify; a one-time
`beet write` (and a scan) for the unwritten tracks before any further moves.

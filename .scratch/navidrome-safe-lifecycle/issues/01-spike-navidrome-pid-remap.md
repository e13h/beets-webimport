# 01 — Spike: verify Navidrome PID remap behavior

Status: needs-triage
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

# 06: Playbook — manual grouping via Staging Bins

**What to build:** A new Playwright playbook (previously untested per
`.scratch/webimport/spec.md`'s Testing Decisions section) covering manual
grouping: splitting one inbox directory containing multiple real
albums/singles (e.g. a burned playlist rip) into separate Staging Bins
through the UI, and confirming each bin imports as its own canonical
album.

**Blocked by:** 01

**Status:** done

- [x] Test fixture: an inbox directory containing tracks from more than one real album/single (a synthetic "burned playlist" rip), added to the disposable test inbox.
- [x] Playbook drags/assigns files from that directory into two or more ad-hoc Staging Bins through the real UI.
- [x] Confirms each bin goes through an ordinary beets import (directory-based grouping) once populated, per ADR-0003 — i.e. each ends up as its own correctly-matched album, not a single merged import.
- [x] Confirms this works for both a multi-track album bin and a singleton bin, if the UI distinguishes them.

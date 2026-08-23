# 03: Playbook — inbox import → apply → grace-period undo

**What to build:** A Playwright playbook (per the convention from ticket
01) that replaces `scripts/drive_import.py` and `scripts/drive_undo.py`.
Against a real running `beet webimport` server and the disposable test
library/inbox, drives the actual web UI to: review a real inbox album,
force a target MusicBrainz release via the search-by-ID override, apply
it, and confirm the result — then undo it and confirm the undo's effect.

**Blocked by:** 01

**Status:** done

- [x] Playbook reviews the Mulan test album from the inbox through the real UI (not by POSTing directly to `/api/*`).
- [x] Forces the target release (`a5483fb3-634b-4254-a966-de33cefd1f17`) via the search-by-ID override and confirms the resulting candidate list reflects it.
- [x] Applies the import and confirms: copy-mode file placement under the configured path template, `set_fields` (`navidrome_library=unassigned`) applied, and `cover.jpg` fetched/embedded.
- [x] Confirms the applied import appears in the Grace Period / undo list in the UI.
- [x] Triggers undo through the UI and confirms the library-side files and DB entry are gone, while original inbox files remain untouched (per ADR-0001).
- [x] Playbook file is added under the location documented in ticket 01, and the disposable library reset step is called out at the top.

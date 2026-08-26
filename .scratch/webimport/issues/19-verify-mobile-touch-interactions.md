# 19: Verify mobile/touch drag-and-drop equivalents via Playwright touch emulation

**What to build:** `app.js`'s `attachLongPress` (the touch equivalent of
desktop drag-and-drop interactions) has only been reviewed for logical
correctness, never exercised under any form of touch input. Add a
Playwright playbook using touch/mobile emulation to exercise it as the
closest automatable proxy for a real-device pass.

**Blocked by:** 01

**Status:** done

- [x] Playbook runs under Playwright's mobile/touch emulation (viewport + touch event support) against the real running server.
- [x] Exercises long-press-to-menu as the touch equivalent of at least one desktop drag-and-drop interaction named in the spec (e.g. manual grouping into a Staging Bin, or the "move to" menu).
- [x] Confirms the resulting action (e.g. a file moved into a bin) matches what the equivalent desktop drag-and-drop would produce.
- [x] Playbook explicitly notes it is a proxy for, not a replacement of, a real-device manual verification pass (per the spec's Further Notes).

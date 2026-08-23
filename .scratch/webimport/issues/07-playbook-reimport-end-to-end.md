# 07: Playbook — reimport end-to-end

**What to build:** A new Playwright playbook (previously untested — big risk area) covering
reimport: driving `--from-scratch` + `--set` against an already-applied
album through the UI, confirming the diff view, and confirming grace-
period undo behaves the same as a fresh import.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Test fixture: an already-applied, real album in the disposable library (e.g. import the Mulan test album first, then reimport it).
- [ ] Playbook selects that album from the library view and triggers reimport through the UI.
- [ ] Confirms the `--from-scratch` toggle renders bold/highlighted when checked (per the spec's UI requirement) and that toggling it does not require a modal confirmation.
- [ ] Sets a `--set field=value` override (e.g. `navidrome_library=kids`) and confirms it survives `--from-scratch`'s metadata clearing.
- [ ] Confirms the diff view shows old → new metadata correctly.
- [ ] Applies the reimport and confirms it goes through the same Grace Period / undo mechanism as a fresh import (appears in the undo list, undo removes exactly this reimport's result).
- [ ] Confirms reimport's temporary config mutation (ADR-0005) is fully restored afterward — a subsequent unrelated fresh import in the same session behaves normally (not still `from_scratch` or carrying stale `set_fields`).

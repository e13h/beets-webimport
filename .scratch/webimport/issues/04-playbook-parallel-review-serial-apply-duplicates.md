# 04: Playbook — parallel review + serial apply + duplicates

**What to build:** A Playwright playbook that replaces
`scripts/drive_concurrency.py`. Submits two albums (one a duplicate copy
of the other) to the inbox at once through the real UI, and confirms
parallel review, serialized apply via the Apply Lock, and the duplicate
decision prompt all behave correctly.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Playbook submits two inbox albums (the test album plus a duplicate copy of it) together and confirms both are independently browsable/reviewable in the UI at the same time (parallel review, per `CONTEXT.md`'s Import Session/Import Task glossary entries).
- [ ] Resolves and applies the first album to the target release; confirms it lands in the library.
- [ ] Resolves the second (duplicate) album to the same release and confirms the duplicate decision prompt appears in the UI (per `get_duplicate_action`, not the stale `resolve_duplicate` name) with the real `DuplicateAction` options (skip new / merge all / remove old / keep all).
- [ ] Chooses "skip new" and confirms exactly one album remains in the library afterward.
- [ ] Confirms the Apply Lock is not left stuck: a subsequent ordinary UI action (e.g. loading the library view) still responds normally.

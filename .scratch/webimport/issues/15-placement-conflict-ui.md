# 15: Placement Conflict UI for Move-on-Field-Change collisions

**What to build:** When a metadata edit's resulting Move-on-Field-Change
would relocate a file to a destination that's already occupied beyond
what beets' own `%aunique{}` disambiguation resolves, surface this as an
explicit Placement Conflict decision in the UI — skip / overwrite / keep
both — reusing the same decision shape as duplicate handling
(`get_duplicate_action`), per `CONTEXT.md`'s Placement Conflict glossary
entry and the spec's Out of Scope note calling for this to not invent a
fourth resolution shape.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] A metadata edit (single field, single track/album, or bulk) that would trigger Move-on-Field-Change to a destination already occupied by an unrelated file (not resolved by `%aunique{}`) surfaces a decision prompt in the UI before any file is moved.
- [ ] The prompt offers skip / overwrite / keep-both, matching the decision shape already used for duplicate handling during import.
- [ ] Choosing "skip" leaves both the edit and the file in place unchanged (or reverts the edit — clarify with the user which is expected before finalizing behavior).
- [ ] Choosing "overwrite" or "keep both" produces the expected filesystem result, verified end-to-end.
- [ ] Covered by a Playwright playbook exercising a real collision scenario.

# 09: pytest unit tests — reimport config-mutation context manager

**What to build:** Fast, no-network pytest coverage for
`beetsplug/webimport/reimport.py`'s `_temporary_import_config` context
manager: restore-on-exit behavior (including on exception) and
`set_fields` merge semantics, using the fixture from ticket 02.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Test: entering the context manager sets `import.from_scratch`/`import.set_fields` as requested; exiting it restores the exact prior values.
- [ ] Test: if an exception is raised inside the `with` block, the prior config values are still restored (the `finally` path).
- [ ] Test: `set_fields` passed to the context manager is merged with (not replacing) any pre-existing `set_fields`, and the merge is undone on exit.
- [ ] No network access required — this only touches `beets.config` and doesn't need a real session run.

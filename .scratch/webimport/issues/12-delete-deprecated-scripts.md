# 12: Delete scripts/*.py and scripts/README.md

**What to build:** Remove the deprecated in-process `test_client()`
harnesses now that every scenario they covered (plus the two previously-
untested scenarios) has Playwright playbook coverage, per ADR-0009.

**Blocked by:** 03, 04, 05, 06, 07

**Status:** ready-for-agent

- [ ] `scripts/drive_import.py`, `scripts/drive_undo.py`, `scripts/drive_art.py`, `scripts/drive_concurrency.py`, and `scripts/README.md` are deleted.
- [ ] The `scripts/` directory itself is removed if nothing remains in it.
- [ ] No remaining references to `scripts/drive_*.py` or `scripts/README.md` in `CONTEXT.md`, `README.md`, `.scratch/webimport/spec.md`, or `docs/adr/*.md` — update any that mention them to point at the new playbooks instead.

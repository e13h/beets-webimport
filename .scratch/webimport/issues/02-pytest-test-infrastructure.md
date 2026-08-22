# 02: Set up pytest test infrastructure

**What to build:** A `tests/` directory, pytest configuration (added to
`pyproject.toml`'s `[project.optional-dependencies].dev`, already lists
`pytest` — confirm/extend as needed), and a fixture providing a
disposable, in-memory or temp-directory beets library with no network
access and no running server. This is a prefactor: it produces no test
coverage itself, but every unit-test ticket below depends on it existing.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `tests/` directory exists with a `conftest.py` (or equivalent) providing a fixture that yields a disposable beets `Library` backed by a temp directory/SQLite file, torn down after each test.
- [ ] Running `pytest` from the repo root (with no other changes) passes with zero collected tests (or a trivial smoke test), proving the harness itself works.
- [ ] Documented in `CONTEXT.md` alongside the Playwright playbook conventions, distinguishing "fast pytest unit tests, no network/server" from "Playwright playbooks, real network/server" as the two testing layers per ADR-0009 and `.scratch/webimport/spec.md`'s Testing Decisions section.
- [ ] No network access required to run this suite.

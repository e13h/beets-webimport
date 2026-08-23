# Testing Workflows & Conventions

Per ADR-0009 and `.scratch/webimport/spec.md`'s Testing Decisions section, testing in this repo is structured into two distinct, complementary layers:

## 1. Fast pytest unit tests (no network, no running server)

- **Location:** `tests/` (`tests/test_*.py`).
- **Execution:** `pytest` (or `.venv/bin/pytest`) from the repo root.
- **Harness & Fixtures:**
  - `lib` fixture in `tests/conftest.py` provides an isolated, disposable in-memory/temp-directory SQLite beets `Library` with clean music and database directories for each test.
  - `create_wav_file` fixture in `tests/conftest.py` creates valid minimal audio files for tag writing/reading tests.
- **Scope:** Fast unit tests verifying component logic in isolation (`grace.py`, `reimport.py`, `library.py`, `tags.py`, etc.).
- **Constraints:** Completely offline and hermetic — no network access required or allowed, no running server process required.

## 2. Playwright playbooks (end-to-end against real running server)

- **Location:** `docs/playbooks/` (`docs/playbooks/*.md`).
- **Execution:** Driven by an agent using Playwright MCP browser tools against a live `beet webimport` server instance.
- **Workflow:**
  1. **Reset disposable test library:**
     ```bash
     rm -f .config/library.db .config/library.db-*.bak && rm -rf .library
     rm -f .config/state.pickle && rm -rf .config/webimport
     ```
  2. **Start the server:**
     ```bash
     BEETSDIR=./.config .venv/bin/beet webimport
     ```
     (Serves on `http://localhost:8338`).
  3. **Execute playbook steps:** Agent drives the browser via Playwright MCP tools (`browser_navigate`, `browser_click`, `browser_type`, `browser_snapshot`, `browser_wait_for`, etc.) to execute user flows through the real web UI (`static/app.js`).
  4. **Teardown server:** Stop the server process when verification finishes.
- **Playbook Shape:**
  - Standard markdown document under `docs/playbooks/`.
  - Header with purpose and prerequisites (including resetting disposable library state).
  - Numbered, deterministic steps describing the UI action, the corresponding Playwright MCP tool calls, and the expected observable UI/filesystem/library outcomes.
  - Verifies externally observable behavior (rendered UI elements, match indicators, copy-mode file placement in `.library/`, undo removals, DB state) rather than internal implementation calls.
- **Network-Host Allowlist:** Playbooks interacting with real MusicBrainz / Cover Art Archive metadata require network access to:
  - `musicbrainz.org`, `*.musicbrainz.org`
  - `coverartarchive.org`, `*.coverartarchive.org`
  - `archive.org`, `*.archive.org`
  - `itunes.apple.com`, `*.mzstatic.com`
- **Deprecation Note:** Direct in-process Flask `test_client()` driver scripts (`scripts/drive_*.py`) are superseded by these Playwright playbooks (ADR-0009).

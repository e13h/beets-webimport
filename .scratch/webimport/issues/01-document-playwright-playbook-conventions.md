# 01: Document Playwright playbook conventions

**What to build:** Update `CONTEXT.md`'s testing section (currently
documents the deprecated `test_client()` bootstrap) to instead document
how an agent runs a Playwright-driven end-to-end check against this
plugin: starting a real `beet webimport` server against the disposable
`.config`/`.inbox` test setup, resetting the library between runs,
where playbook files live, and the network-host allowlist
(`musicbrainz.org`, `coverartarchive.org`, `archive.org`,
`itunes.apple.com`, and their subdomains) needed for real MusicBrainz/CAA
lookups. This is a prefactor: it produces no test coverage itself, but
every playbook ticket below depends on the convention it establishes.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] `CONTEXT.md` no longer describes the `test_client()` bootstrap as the way to close the loop; it describes starting/stopping a real `beet webimport` server instead.
- [x] Documents the disposable-library reset steps (already partially present) in terms of the new workflow.
- [x] Documents a conventional location for playbook files (e.g. `docs/playbooks/` or similar) and the shape a playbook takes (numbered steps, expected observable outcomes, Playwright MCP tool calls).
- [x] Documents the network-host allowlist needed for playbooks that hit MusicBrainz/CAA for real.
- [x] References `.scratch/webimport/spec.md`'s Testing Decisions section and ADR-0009 rather than re-deriving the rationale for the seam.

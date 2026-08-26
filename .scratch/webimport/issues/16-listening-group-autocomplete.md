# 16: Listening Group autocomplete

**What to build:** Wire a live `SELECT DISTINCT navidrome_library`
query against the current library into the Listening Group input
wherever it's editable (import-time assignment and metadata-edit),
surfaced as autocomplete suggestions without forcing selection from that
list — per `CONTEXT.md`'s Listening Group glossary entry and ADR-0002.

**Blocked by:** None (can start immediately)

**Status:** done

- [x] The Listening Group input (at import time and in metadata editing) offers autocomplete suggestions drawn from the distinct `navidrome_library` values currently present in the library.
- [x] Typing a value not in that list is still accepted as a valid, new Listening Group — the suggestion list never blocks free-text entry.
- [x] A brand-new Listening Group only appears as a future suggestion once something has actually been routed to it (no separate pre-staging mechanism, per the user's stated preference).
- [x] The `unassigned` default value appears in the suggestion list once anything exists with it (which is the common case, given `import.set_fields.navidrome_library: unassigned`).
- [x] Query performance is acceptable at the current library size (~800 albums) — no noticeable input lag.

# 33: Type-aware metadata inputs (date picker, multi-value chip inputs)

**What to build:** In album and track metadata editing forms, replace raw plain-text inputs with type-aware input controls where appropriate: date pickers for date fields (year, original_year), multi-value chip inputs for delimiter-separated fields (like `genres` / `genre`), falling back to plain text inputs for unspecialized or custom fields, per User Story 37.

**Blocked by:** 31, 32

**Status:** ready-for-agent

- [ ] Date fields (e.g. `year`, `original_year`, release dates) render with type-aware date/year input controls.
- [ ] Multi-value fields (e.g. `genre`/`genres`, `mood`) render with chip/tag-style multi-value inputs that allow adding and removing individual values joined by delimiters.
- [ ] Unspecialized and custom flexible fields fall back gracefully to standard plain text boxes.
- [ ] Preserves keyboard accessibility and mobile touch support across all custom input widgets.

# `$navidrome_library` as a free-form path variable

Multi-library routing to Navidrome is implemented by writing a user-chosen
string into the `navidrome_library` beets flexible attribute and referencing
it directly as `$navidrome_library` in `paths.default`/`paths.singleton`/
`paths.comp` — not via a fixed enum matched by per-value conditional `paths:`
entries. Any string the user types or selects becomes a valid new top-level
library folder the next time something is routed to it; registering that
folder as a Navidrome library root is a manual, out-of-band step in
Navidrome's own settings, not something the plugin automates.

An earlier PRD draft modeled listening groups as a fixed, pre-keyed set; that
was corrected specifically because it doesn't match how the path templates
actually work.

## Consequences

- Typos/casing variants (`kids` vs `Kids` vs `kidz`) silently become distinct
  top-level folders with no built-in warning. The plugin should offer
  autocomplete against existing values to reduce this risk, without forcing
  the user to pick only from that list (freeform input must remain
  possible).
- Because routing is driven by Move-on-Field-Change, changing this value on
  an already-imported item always triggers a physical relocation — the field
  and the file location can never be edited independently of each other.

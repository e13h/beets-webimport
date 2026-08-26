# 36: Tag vocabulary GUI: field creation, deletion, and vocabulary curation

**What to build:** In the Tag Vocabulary tab (`#tab-tags`), provide complete GUI management for the tag vocabulary, including creating new tag fields (e.g. `occasion`, `energy`), deleting tag fields, and removing individual tag values from vocabulary lists, backed by backend REST endpoints, closing User Story 43.

**Blocked by:** None

**Status:** ready-for-agent

- [ ] Backend API exposes endpoints for tag vocabulary management: `POST /api/tags` (or `POST /api/tags/<field>` for field creation), `DELETE /api/tags/<field>` (remove field), and `DELETE /api/tags/<field>/<value>` (remove value), delegating to `TagStore`.
- [ ] Tag Vocabulary tab in the web UI includes a form to create a new tag field name.
- [ ] Each tag field card provides an action/button to remove the tag field from the vocabulary.
- [ ] Each `.tag-chip` provides a removal affordance (e.g. a "×" button or context action) to delete that value from the field's vocabulary.
- [ ] Updated vocabulary changes persist immediately to `tags.json` and refresh the UI.

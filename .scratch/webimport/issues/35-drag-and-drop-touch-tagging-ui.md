# 35: Custom tags: drag-and-drop & touch-first UI for applying tags to albums and tracks

**What to build:** Provide an intuitive HTML5 drag-and-drop and touch-first UI for applying custom tags (from the Tag Vocabulary) to whole albums and individual tracks during library browsing, closing User Story 44.

**Blocked by:** None

**Status:** ready-for-agent

- [ ] Tag chips in the Tag Vocabulary tab and album/track detail views are draggable (`draggable="true"`) with drag visual feedback.
- [ ] Album tiles in `#album-grid` and track rows in album detail views accept dropped tag chips (`dragover`/`drop` handlers) to apply the tag to the target album or track via `POST /api/tags/<field>/apply`.
- [ ] For touch devices and mobile interactions, provide a direct, modal/picker touch workflow that allows selecting a tag from the vocabulary and applying it directly to an album or track without asking the user to manually type database IDs into `window.prompt()`.
- [ ] Album tile long-press / context menu includes an "Apply tag…" action that opens a tag picker from the vocabulary.
- [ ] Track row long-press / context menu in album detail views provides a tag picker allowing selection from the Tag Vocabulary rather than free-form text prompts.
- [ ] Shows clear visual confirmation (toast notifications and UI updates) when a tag is applied.

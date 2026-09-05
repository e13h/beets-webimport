# 02 — Fix stale marker album_id after reimport

Status: needs-triage
Type: task
Blocked by: —

Every successful import/reimport apply must update the
`.webimport_imported` marker in the originating inbox folder so its
`album_id` points at the currently-live library album and `imported_at`
reflects the last apply. Today `run_reimport` never touches the marker
(`beetsplug/webimport/reimport.py`), so undo-by-marker can target a deleted
album.

Scope: update marker on apply in the reimport path; unit test asserting
"marker intact *and* album_id current" after reimport (playbook 23
currently asserts only intactness — update it too).

Unblocks 04 (Approve tab), which relies on marker-truthful undo.

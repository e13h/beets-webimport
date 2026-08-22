# Staging-directory manual grouping over in-memory task construction

Manual grouping (splitting one inbox directory — e.g. a burned playlist
CD rip — into several real albums/singles before import) is implemented by
moving files into ad-hoc Staging Bin subdirectories and letting beets' own
directory-based grouping run a normal import against each resulting
directory, rather than constructing `ImportTask`/`SingletonImportTask`
objects directly from an arbitrary in-memory file list.

This was initially flagged as a possible scope-reduction against the PRD's
originally-stated design (in-memory task construction), but is in fact the
intended end state: physically regrouping tracks into real album folders on
disk keeps every subsequent import — split or not — a canonical, ordinary
beets import, rather than requiring the importer to special-case
groupings that never touched disk.

## Consequences

- `.scratch/webimport/spec.md` describes staging-directory regrouping
  rather than direct in-memory `ImportTask` construction, per this ADR.
- Manual grouping is necessarily an extra, visible filesystem move step
  before the beets import pipeline ever sees the split files — there is no
  "undo the grouping" without also moving files back.

# 43: `import.incremental: yes` silently skips re-importing a folder after undo

**Status:** resolved (workaround) — revisit

**Problem:** With beets' `incremental: yes` (the homelab config), beets
records every imported folder in its state file and skips it on later
imports ("Skipping previously-imported path"). After an undo, re-importing
the same inbox folder does nothing and the UI never gets a review. The
plugin's `.webimport_imported` marker (ADR-0010/0012) already tracks
import state per folder, so incremental adds no protection here.

**Workaround (2026-11-17):** `incremental: no` in the homelab config
(`.config/homelab.yaml`; still needs copying to the selfhosted repo).

**Revisit:** the user would like incremental-style behavior back,
done in a way that works with undo. Options:
- On undo, remove the folder from beets' incremental state
  (`beets.importer.state`), so the next import isn't skipped.
- Let the marker be the only source of truth, and turn incremental off
  for webimport sessions while the CLI keeps it.
- Surface "skipped: previously imported" in the UI instead of failing
  silently, whatever else is chosen.

## Comments

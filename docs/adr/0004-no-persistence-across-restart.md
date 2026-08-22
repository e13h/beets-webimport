# No persistence of in-process review or grace-period state across restart

Neither in-flight import review state (`ReviewManager`/`InboxWorkerPool`)
nor pending grace-period undo records (`GracePeriodManager`) survive a
plugin process restart; both are plain in-memory state, by design. A
restart mid-review simply means the affected inbox albums re-enter search
from scratch on the next pass; a restart mid-grace-period means that
import's undo option is silently forfeited (the library copy stands as
final).

This is accepted because the plugin models a single long-running server
process for a single user, and because the underlying files are never at
risk either way: inbox originals are untouched (copy mode, see ADR-0001)
and a forfeited grace period just means one less opportunity to undo, not
data loss.

## Consequences

- Restarting the plugin (e.g. to deploy a code change) has a real, if minor,
  user-facing cost: any grace-period-eligible import from the last ~10
  minutes becomes permanent, and any in-progress review must be re-started.
- Making either of these durable (e.g. persisting to disk) is a valid future
  enhancement but explicitly deprioritized against implementation
  simplicity for now.

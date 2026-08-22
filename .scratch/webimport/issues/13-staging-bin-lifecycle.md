# 13: Staging Bin lifecycle — persist through grace period, clean up on expiry

**What to build:** Currently, Staging Bins created by manual grouping
(`_grouped/<id>/bin_N/` under the inbox) are never cleaned up at all.
Implement the intended lifecycle from `CONTEXT.md`'s Staging Bin and
Grace Period glossary entries: a bin survives untouched through its
import's Grace Period (so an undo doesn't require redoing the splitting
work), and is removed from the inbox once that Grace Period expires.

**Blocked by:** 06

**Status:** ready-for-agent

- [ ] A Staging Bin's files are not deleted or moved immediately after its import applies.
- [ ] If the import is undone within the Grace Period, the Staging Bin's original files are still present and re-enter the review queue without the user having to re-split them.
- [ ] Once the Grace Period for that bin's import expires (without an undo), the Staging Bin is removed from the inbox automatically.
- [ ] Covered by the manual-grouping playbook (ticket 06) or a follow-up extension of it: verify a bin persists immediately after apply, and is gone after the grace period elapses.

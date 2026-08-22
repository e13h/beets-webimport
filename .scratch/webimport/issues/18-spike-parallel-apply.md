# 18: Spike — is parallel apply a needed workflow?

**What to build:** An investigation-only spike, not a feature
implementation. Determine whether the Apply Lock's serialization of the
db-write/move step (ADR-0006) is ever a real bottleneck for solo usage —
i.e. whether the apply step (copy + tag write + art embed) is slow enough,
and reviews finish concurrently often enough, that relaxing it to allow
parallel applies would be a meaningful workflow improvement.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Measures real apply-step latency (copy + tag write + art embed) for a representative album against the actual environment/library size.
- [ ] Assesses how often, in practice, multiple reviews are likely to finish close enough together for serialization to matter for a single user.
- [ ] Produces a written recommendation: build parallel apply, or leave the Apply Lock as-is (with reasoning) — this ticket's deliverable is the recommendation, not a code change.
- [ ] If the recommendation is to proceed, file a new follow-up ticket for the actual implementation (do not implement it as part of this spike).

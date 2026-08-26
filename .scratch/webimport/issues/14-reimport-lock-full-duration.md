# 14: Reimport — hold the Apply Lock for the full config-mutated duration

**What to build:** Close the known gap from ADR-0005: reimport's
temporary mutation of the global `beets.config["import"]["from_scratch"]`/
`["set_fields"]` is currently only guarded by the Apply Lock at apply
time, not for the whole duration the config is mutated. A concurrent
fresh-import review on another thread could transiently observe the
mutated global config. Acquire the lock for the entire
config-mutated window instead.

**Blocked by:** 07

**Status:** done

- [x] `run_reimport` (or its caller) acquires the Apply Lock before mutating `import.from_scratch`/`import.set_fields`, and releases it only after the config is restored — not just around the apply step.
- [x] A concurrent fresh-import review submitted while a reimport is in flight is not able to observe the reimport's mutated config values (verified via a targeted test — pytest with two threads/config mutation timing, or a concurrency playbook extension).
- [x] Existing reimport behavior (diff view, grace/undo, `--from-scratch` + `--set`) is unaffected — ticket 07's playbook still passes.
- [x] ADR-0005 is updated to note the gap has been closed (or a new ADR entry/amendment records the change, if the fix itself involves a design choice worth recording).

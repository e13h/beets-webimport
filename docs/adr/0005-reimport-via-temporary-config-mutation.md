# Reimport via temporary global config mutation

Reimport (`-L`/`-S`/`--from-scratch`/`--set` equivalent) is implemented by
temporarily flipping `beets.config["import"]["from_scratch"]` and
`["set_fields"]` for the duration of a library-query session, then
restoring the prior values in a `finally` block — reusing beets' own
apply-time metadata-clearing logic rather than reimplementing it.

## Consequences

- Because `beets.config` is process-global and import review is otherwise
  parallel across sessions, `run_reimport` acquires the global Apply Lock
  *before* mutating `import.from_scratch` / `import.set_fields`, and releases
  it only after the configuration is restored in a `finally` block (rather
  than acquiring it only at apply time). This prevents concurrent fresh-import
  review/apply operations on other worker threads from transiently observing
  the reimport's mutated global configuration.

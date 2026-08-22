# Reimport via temporary global config mutation

Reimport (`-L`/`-S`/`--from-scratch`/`--set` equivalent) is implemented by
temporarily flipping `beets.config["import"]["from_scratch"]` and
`["set_fields"]` for the duration of a library-query session, then
restoring the prior values in a `finally` block — reusing beets' own
apply-time metadata-clearing logic rather than reimplementing it.

## Consequences

- Because `beets.config` is process-global and import review is otherwise
  parallel across sessions, a reimport in flight on one thread can
  transiently be observed by another thread's concurrent fresh-import
  review while the override is active. This is a known, currently-unguarded
  race; low priority to fix given single-user usage, but the fix (reimport
  should hold a lock for its entire config-mutated duration, not only at
  apply time) is understood and tracked as follow-up work rather than left
  as a silent gap.

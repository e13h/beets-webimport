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

## Revised (0.1.8): per-task settings, Apply Lock only to apply

Holding the Apply Lock for the whole reimport session meant one reimport
at a time: a second one couldn't even search until the first had been
reviewed and applied ("Waiting for another import to finish applying"
while the other sat in review).

beets reads `from_scratch` and `set_fields` only while applying
(`match.apply_metadata`, `_apply_choice`/`task.set_fields`), so the
reimport now gives them to its own tasks instead of the global config
(`reimport.apply_reimport_settings`): `apply_metadata` is called with the
session's `from_scratch`, and the fields are set right after `task.add`
(beets' own `set_fields` is switched off for the task). The global config
is never changed, so the session takes the Apply Lock only when a choice is
applied, like an inbox import, and several reimports can be ready for
review at once. The "Tags after import" preview reads the same per-task
settings.

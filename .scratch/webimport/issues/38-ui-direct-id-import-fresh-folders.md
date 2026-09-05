# 38: UI — Direct ID Import toggle on fresh inbox folders (with retry on failed lookup)

**What to build:** A fresh (unimported) inbox folder card offers an
inline expandable "Import with ID…" input. The user pastes a release
identifier (bare UUID, MusicBrainz URL, or Discogs URL) and submits;
the broad candidate search is skipped and the review modal opens
showing the single targeted candidate for final approval or deny —
the same approval opportunity `beet import -S <mbid>` gives, never
auto-applied. If the lookup found nothing (bad ID, 404, network
failure), the review modal instead shows an error banner naming the
failed ID, with an input to supply a different ID or fall back to a
normal auto-search, without abandoning the session. This ticket makes
the Direct ID Import workflow (see CONTEXT.md) user-visible end to end.

**Blocked by:** 37 (API — accept a pre-specified search ID on inbox
import start)

**Status:** resolved

- [x] Each fresh inbox folder card has an inline toggle ("Import with
      ID…") that expands a free-text input; the default "Start import"
      flow is unchanged when the toggle is unused.
- [x] The input is sent as a raw string (no client-side parsing or URL
      extraction) and starting an import with an ID skips the visible
      multi-second candidate-search wait.
- [x] Submitting with a valid ID opens the normal review modal showing
      the single targeted candidate; approval still goes through the
      standard apply path (no auto-apply).
- [x] Submitting with an invalid/unresolvable ID opens the review modal
      in an error state: banner naming the failed ID, an input to supply
      a replacement ID, and a way to trigger a normal auto-search.
- [x] Playbook or manual verification against the disposable test setup:
      fresh Mulan inbox folder imported via a known-good MBID resolves
      to the expected release and applies correctly after approval; a
      bogus ID shows the retry error state.

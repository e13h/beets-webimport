# 05: Playbook — cover-art preview

**What to build:** A Playwright playbook that replaces
`scripts/drive_art.py`. Against a real running server, drives the UI to
show the dual cover-art preview (Source Art vs. Resolved Art) for a known
release and confirms the match/mismatch indicator.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] Playbook navigates the real UI to a candidate review showing the target release (`a5483fb3-634b-4254-a966-de33cefd1f17`).
- [ ] Confirms both the Source Art and Resolved Art thumbnails render (per `CONTEXT.md`'s glossary entries for each).
- [ ] Confirms the match/mismatch indicator reflects the real result (`match: true` against this known release, consistent with what `drive_art.py` previously verified at the API layer).
- [ ] Confirms Resolved Art is computed lazily — only for the highlighted candidate, not upfront for the whole list — by observing it does not appear for unfocused candidates.

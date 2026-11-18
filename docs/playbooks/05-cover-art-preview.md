# Playbook 05 — Album Art Choice

End-to-end check of the **Art Choice** (ADR-0013) in candidate review,
using Playwright MCP browser tools against a live server (ADR-0009).

The review's "Album art after import" section offers: **Keep current art**
(the files' embedded art), **Cover Art Archive** (the focused candidate's
front cover, release-group fallback), **iTunes Store** (iTunes purchases),
and **Image in the folder** (if any). The chosen image is embedded on
import; the inbox folder is never modified.

---

## Prerequisites

```bash
scripts/dev-reset.sh --start
```

Inbox fixtures: `.inbox/Mulan (Original Motion Picture Soundtrack)` (iTunes
purchase, **no** embedded art) and, if present, an Amazon MP3 album such as
`.inbox/Coldplay` (600 × 600 embedded art).

Network hosts: `musicbrainz.org`, `coverartarchive.org`, `archive.org`,
`*.archive.org`, `itunes.apple.com`, `*.mzstatic.com`.

---

## Step 1: Start the Mulan import and open review

```
browser_navigate(url="http://localhost:8338")
browser_click(target="text=Start import")          # on the Mulan row
browser_wait_for(text="Candidates ready")
browser_click(target="[data-review]")
browser_wait_for(text="Album art after import")
browser_snapshot()
```

**Expected:**
- "✓ Matched via Apple Music link" banner; one candidate, *Mulan: An
  Original Walt Disney Records Soundtrack (2020)* (`4e929666-…`).
- Art options (`.art-choice [data-art-choice]`):
  - **Keep current art** — "Your files have no embedded art".
  - **Cover Art Archive** — "1500 × 1500 px · 4.0 MB" with a thumbnail.
  - **iTunes Store** — "1500 × 1500 px · 1.2 MB", **selected** (default).
- No `.candidate` contains images; there are no broken-image icons.
- All `<img>` sources are `/api/art/<sha1>` (nothing loads from
  `coverartarchive.org` or `archive.org` in the browser).

## Step 2: Choose the Cover Art Archive image and apply

```
browser_click(target='[data-art-choice][value="candidate"]')
browser_click(target=".candidate [data-select]")
browser_wait_for(text="Import applied successfully")
```

**Expected:**
- `BEETSDIR=./.config .venv/bin/beet ls -a -f '$album $artpath' Mulan`
  shows an empty `artpath` (`embedart.remove_art_file`).
- Library tab → Mulan → explorer art block: embedded 1500 × 1500, 4.0 MB
  (the Cover Art Archive image, not iTunes' 1.2 MB one).
- The Mulan folder is gone from `.inbox/` (move mode, ADR-0015); no
  `cover.jpg` was ever written there. Library → Mulan → **Undo import…**
  puts the four `.m4a` files back byte-identical.

## Step 3 (optional): Files with their own art — Amazon purchase

Start and review `.inbox/Coldplay`.

**Expected:**
- **Keep current art** shows the files' 600 × 600 image.
- **Cover Art Archive** shows 1772 × 1772 for the 2006 digital release and
  is selected (larger than the files' art).
- Choosing **Keep current art** and applying leaves the imported file's
  embedded art byte-identical to the inbox original.

## Step 4: Focus switching makes no repeat downloads

In a review with several candidates, click each candidate, then click back
to the first.

**Expected:** the Cover Art Archive option updates per candidate ("loading…"
→ size). Revisiting a candidate is instant: no new requests in the network
log (images are served `Cache-Control: immutable`, and the server caches
each release's art).

## Teardown

```bash
scripts/dev-reset.sh   # undoes every import first: files return to .inbox/
```

## References

- ADR-0013 (webimport owns import-time album art), `artchoice.py`
- `tests/test_artchoice.py`

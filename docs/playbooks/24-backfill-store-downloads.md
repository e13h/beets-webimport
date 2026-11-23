# Playbook 24 — Backfill: attach store downloads to the library

Checks **Backfill** (ADR-0016) end to end in the Inbox tab against a dev
library seeded like the homelab's: identical audio is saved as originals,
same-recording downloads are swapped in, new tracks stay, and Undo import
afterwards returns the downloads byte-identical.

## Prerequisites

`.backfill-fixture/server/` from the homelab (see `dev-environment.md`,
"Backfill test data"), and `fpcalc` (`brew install chromaprint`).

```bash
scripts/dev-seed-backfill.sh            # 20 tracks in 4 albums; 22 inbox files
(cd .inbox && find . -type f ! -name '.*' -exec shasum -a 256 {} +) > "${TMPDIR:-/tmp}/bf-before.sha"
BEETSDIR=./.config .venv/bin/beet ls -f '$id|$title|$album|$mb_trackid|$navidrome_library' > "${TMPDIR:-/tmp}/bf-tags.txt"
scripts/dev-server.sh
```

## Step 1: Check the inbox against the library

```
browser_navigate(url="http://localhost:8338")
browser_click(target="[data-backfill-scan]")
browser_wait_for(text="Attach all")
browser_snapshot()
```

**Expected:**
- Bar: "Last check: 5 identical · 15 to swap in · 2 new."
- Cards: *B.o.B* (1 identical · 1 new), *Lea Salonga* (Mulan, 4 identical),
  *Oliver Wallace* (Cinderella, 4 to swap in), *Train* (Save Me, San
  Francisco, 11 to swap in); *Avalon* has no "In library" line.

## Step 2: Review one folder

```
browser_click(target="#inbox-dirs .card:has-text('Train') [data-backfill]")
browser_snapshot()
browser_click(target="[data-bf-cancel]")
```

**Expected:** 11 rows "OGG 112 kbps → MP3 2xx kbps", **Swap in**, "better
quality", each paired with the right library title (including "If It’s
Love" and "This Ain’t Goodbye" with curly apostrophes).

## Step 3: Attach all

```
browser_click(target="[data-backfill-all]")
browser_click(target="[data-bf-confirm]")
browser_wait_for(text="Attached:", time=120)
```

**Expected:**
- Toast: "Attached: 5 identical tracks, 15 tracks swapped for the download."
- Inbox shows only *Avalon* and *B.o.B* (with no "In library" line).
- Shell:
  ```bash
  export BEETSDIR=./.config
  .venv/bin/beet ls -f '$id|$title|$album|$mb_trackid|$navidrome_library' | diff "${TMPDIR:-/tmp}/bf-tags.txt" - && echo same tags
  .venv/bin/beet write -p        # prints nothing: file tags match the DB
  .venv/bin/beet move -p         # "Moving 0 items"
  .venv/bin/beet ls -f '$format $bitrate' Train | sort | uniq -c   # MP3 ~250kbps
  ls .config/webimport-replaced/*/main/Train/*/   # the 11 old .ogg files
  ```

## Step 4: Undo import gives back the downloads

Library tab → each album → **Undo import…** → confirm (or loop over the
four albums). Then:

```bash
(cd .inbox && shasum -a 256 -c "${TMPDIR:-/tmp}/bf-before.sha")
```

**Expected:** all 22 `OK`, including the 15 swapped tracks.

## Teardown

```bash
scripts/dev-reset.sh --force
```

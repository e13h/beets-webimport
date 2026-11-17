# 0013: webimport Owns Import-Time Album Art

The review shows the art the files have now and the options for after
import: **keep** the files' embedded art, the selected release's **Cover Art
Archive** front (release-group fallback), **iTunes Store** art for iTunes
purchases, or an **image file in the inbox folder**. The server downloads
each option once, holds the bytes in a content-addressed in-memory store,
and serves previews from it, so what the user sees, its size, and what
gets embedded are the same image. On apply, webimport sets the chosen
image as the album's art (`Album.set_art` in the `import_task_files`
stage); `art_set` makes embedart embed it. "Keep" sets nothing, and with
`scrub: auto: no` the files' own art survives. fetchart's automatic step is
off (`fetchart: auto: no`); the plugin stays loaded for manual
`beet fetchart`.

Replaces the dual "Source Art / Resolved Art" preview, which re-implemented
fetchart's source rules to predict its result and steered fetchart by
writing `cover.jpg` into (and renaming images in) the inbox folder.

## Consequences

- The inbox folder is never modified for art; a later re-import doesn't
  silently reuse an earlier choice.
- A decision without an `art_choice` gets the server-side default
  (`artchoice.default_choice`, mirrored in the UI): folder image, else
  iTunes art, else the larger of the files' art and the CAA art.
- CLI `beet import` gets no art (fetchart's auto step is off). Imports go
  through webimport.
- New art sources (a pasted image URL, a Spotify link) only need to supply
  image bytes.

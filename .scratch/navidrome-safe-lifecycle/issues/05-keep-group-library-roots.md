# 05 — Keep Listening Group folders when their last album leaves

Status: needs-triage
Type: task
Blocked by: —

When the last album moves out of a Listening Group folder (e.g.
`/music/christmas`), beets prunes the now-empty folder. That folder is a
Navidrome library root, and with its root gone Navidrome skips the library
in its scan: its rows are never marked missing, never matched to the
moved files, and keep showing as present. The moved album's copy in the
destination library starts with no history. Seen in the e2e run
(`repro/e2e_webimport.py`) before `.keep` files were added. The homelab is
unaffected while every group holds several albums.

Options: a `.keep` file in each group root (Navidrome ignores dotfiles,
and beets won't prune a non-empty folder), created when a group is first
used; or have webimport stop pruning at the group root.

# Repro results 20261117-204337 (deluan/navidrome:0.64.2)

| case | edit | with MBIDs | without MBIDs |
|---|---|---|---|
| A | tag-only edit (genre), path unchanged | kept | kept |
| B | retitle track 1: write tags + rename, one scan (beet modify) | kept | LOST root#1, main#1 |
| Bw | retitle track 1: rename only, tags untouched (webimport today) | kept | kept |
| C | rename album: write tags + rename, one scan | kept | LOST root#1, main#1, root#2, main#2 |
| Cw | rename album: rename only, tags untouched (webimport today) | kept | kept |
| D | Listening Group main->kids (path-only; flex field, no tag change) | kept (row moved library) | kept (row moved library) |
| G | rename album + group main->kids: write tags + rename, one scan | kept (row moved library) | LOST root#1, main#1, root#2, main#2 |
| E | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | kept | kept |
| F | retitle, two-phase move first: rename, scan, write, scan (ND docs) | kept | kept |
| H | rename album, two-phase tags first | kept | kept |
| I | rename album + group main->kids, two-phase tags first | kept (row moved library) | kept (row moved library) |
| D0 | group move main->kids on files beets never wrote (as-is import) | kept (row moved library) | LOST main#1, main#2 |
| U | group move main->talk (unregistered), scan, register talk, scan | kept (row moved library) | kept (row moved library) |
| R | reimport-like: new MBIDs + rename album, one scan | LOST root#1, main#1, root#2, main#2 | LOST root#1, main#1, root#2, main#2 |
| R2 | reimport-like, two-phase tags first | kept | kept |

## Per row

| case | edit | trk | row's library | original row | history on live row | new history-less row(s) |
|---|---|---|---|---|---|---|
| A-mb | tag-only edit (genre), path unchanged | 1 | root | kept | plays=2 starred=True playlist=True |  |
| A-mb | tag-only edit (genre), path unchanged | 1 | main | kept | plays=2 starred=True playlist=True |  |
| A-mb | tag-only edit (genre), path unchanged | 2 | root | kept | plays=2 starred=True playlist=True |  |
| A-mb | tag-only edit (genre), path unchanged | 2 | main | kept | plays=2 starred=True playlist=True |  |
| A-nomb | tag-only edit (genre), path unchanged | 1 | root | kept | plays=2 starred=True playlist=True |  |
| A-nomb | tag-only edit (genre), path unchanged | 1 | main | kept | plays=2 starred=True playlist=True |  |
| A-nomb | tag-only edit (genre), path unchanged | 2 | root | kept | plays=2 starred=True playlist=True |  |
| A-nomb | tag-only edit (genre), path unchanged | 2 | main | kept | plays=2 starred=True playlist=True |  |
| B-mb | retitle track 1: write tags + rename, one scan (beet modify) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| B-mb | retitle track 1: write tags + rename, one scan (beet modify) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| B-mb | retitle track 1: write tags + rename, one scan (beet modify) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| B-mb | retitle track 1: write tags + rename, one scan (beet modify) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| B-nomb | retitle track 1: write tags + rename, one scan (beet modify) | 1 | root | MISSING | lost (row missing) | root:6zMcuB, main:5cIQje |
| B-nomb | retitle track 1: write tags + rename, one scan (beet modify) | 1 | main | MISSING | lost (row missing) | root:6zMcuB, main:5cIQje |
| B-nomb | retitle track 1: write tags + rename, one scan (beet modify) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| B-nomb | retitle track 1: write tags + rename, one scan (beet modify) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| Bw-mb | retitle track 1: rename only, tags untouched (webimport today) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| Bw-mb | retitle track 1: rename only, tags untouched (webimport today) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| Bw-mb | retitle track 1: rename only, tags untouched (webimport today) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| Bw-mb | retitle track 1: rename only, tags untouched (webimport today) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| Bw-nomb | retitle track 1: rename only, tags untouched (webimport today) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| Bw-nomb | retitle track 1: rename only, tags untouched (webimport today) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| Bw-nomb | retitle track 1: rename only, tags untouched (webimport today) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| Bw-nomb | retitle track 1: rename only, tags untouched (webimport today) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| C-mb | rename album: write tags + rename, one scan | 1 | root | kept | plays=2 starred=True playlist=True |  |
| C-mb | rename album: write tags + rename, one scan | 1 | main | kept | plays=2 starred=True playlist=True |  |
| C-mb | rename album: write tags + rename, one scan | 2 | root | kept | plays=2 starred=True playlist=True |  |
| C-mb | rename album: write tags + rename, one scan | 2 | main | kept | plays=2 starred=True playlist=True |  |
| C-nomb | rename album: write tags + rename, one scan | 1 | root | MISSING | lost (row missing) | root:2koA04, main:0wfG2p |
| C-nomb | rename album: write tags + rename, one scan | 1 | main | MISSING | lost (row missing) | root:2koA04, main:0wfG2p |
| C-nomb | rename album: write tags + rename, one scan | 2 | root | MISSING | lost (row missing) | root:7o6U88, main:2fBzSm |
| C-nomb | rename album: write tags + rename, one scan | 2 | main | MISSING | lost (row missing) | root:7o6U88, main:2fBzSm |
| Cw-mb | rename album: rename only, tags untouched (webimport today) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| Cw-mb | rename album: rename only, tags untouched (webimport today) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| Cw-mb | rename album: rename only, tags untouched (webimport today) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| Cw-mb | rename album: rename only, tags untouched (webimport today) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| Cw-nomb | rename album: rename only, tags untouched (webimport today) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| Cw-nomb | rename album: rename only, tags untouched (webimport today) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| Cw-nomb | rename album: rename only, tags untouched (webimport today) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| Cw-nomb | rename album: rename only, tags untouched (webimport today) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| D-mb | Listening Group main->kids (path-only; flex field, no tag change) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| D-mb | Listening Group main->kids (path-only; flex field, no tag change) | 1 | main | kept (moved to kids) | lost (row missing) |  |
| D-mb | Listening Group main->kids (path-only; flex field, no tag change) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| D-mb | Listening Group main->kids (path-only; flex field, no tag change) | 2 | main | kept (moved to kids) | lost (row missing) |  |
| D-nomb | Listening Group main->kids (path-only; flex field, no tag change) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| D-nomb | Listening Group main->kids (path-only; flex field, no tag change) | 1 | main | kept (moved to kids) | lost (row missing) |  |
| D-nomb | Listening Group main->kids (path-only; flex field, no tag change) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| D-nomb | Listening Group main->kids (path-only; flex field, no tag change) | 2 | main | kept (moved to kids) | lost (row missing) |  |
| G-mb | rename album + group main->kids: write tags + rename, one scan | 1 | root | kept | plays=2 starred=True playlist=True |  |
| G-mb | rename album + group main->kids: write tags + rename, one scan | 1 | main | kept (moved to kids) | lost (row missing) |  |
| G-mb | rename album + group main->kids: write tags + rename, one scan | 2 | root | kept | plays=2 starred=True playlist=True |  |
| G-mb | rename album + group main->kids: write tags + rename, one scan | 2 | main | kept (moved to kids) | lost (row missing) |  |
| G-nomb | rename album + group main->kids: write tags + rename, one scan | 1 | root | MISSING | lost (row missing) | root:0apSfj, kids:5LAgqn |
| G-nomb | rename album + group main->kids: write tags + rename, one scan | 1 | main | MISSING | lost (row missing) | root:0apSfj, kids:5LAgqn |
| G-nomb | rename album + group main->kids: write tags + rename, one scan | 2 | root | MISSING | lost (row missing) | root:762KCq, kids:5XKzmf |
| G-nomb | rename album + group main->kids: write tags + rename, one scan | 2 | main | MISSING | lost (row missing) | root:762KCq, kids:5XKzmf |
| E-mb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| E-mb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| E-mb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| E-mb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| E-nomb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| E-nomb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| E-nomb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| E-nomb | retitle, two-phase tags first: write, scan, move, scan (ADR-0011) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| F-mb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| F-mb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| F-mb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| F-mb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| F-nomb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| F-nomb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 1 | main | kept | plays=2 starred=True playlist=True |  |
| F-nomb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| F-nomb | retitle, two-phase move first: rename, scan, write, scan (ND docs) | 2 | main | kept | plays=2 starred=True playlist=True |  |
| H-mb | rename album, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| H-mb | rename album, two-phase tags first | 1 | main | kept | plays=2 starred=True playlist=True |  |
| H-mb | rename album, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| H-mb | rename album, two-phase tags first | 2 | main | kept | plays=2 starred=True playlist=True |  |
| H-nomb | rename album, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| H-nomb | rename album, two-phase tags first | 1 | main | kept | plays=2 starred=True playlist=True |  |
| H-nomb | rename album, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| H-nomb | rename album, two-phase tags first | 2 | main | kept | plays=2 starred=True playlist=True |  |
| I-mb | rename album + group main->kids, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| I-mb | rename album + group main->kids, two-phase tags first | 1 | main | kept (moved to kids) | lost (row missing) |  |
| I-mb | rename album + group main->kids, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| I-mb | rename album + group main->kids, two-phase tags first | 2 | main | kept (moved to kids) | lost (row missing) |  |
| I-nomb | rename album + group main->kids, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| I-nomb | rename album + group main->kids, two-phase tags first | 1 | main | kept (moved to kids) | lost (row missing) |  |
| I-nomb | rename album + group main->kids, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| I-nomb | rename album + group main->kids, two-phase tags first | 2 | main | kept (moved to kids) | lost (row missing) |  |
| D0-mb | group move main->kids on files beets never wrote (as-is import) | 1 | root | kept | plays=2 starred=True playlist=True |  |
| D0-mb | group move main->kids on files beets never wrote (as-is import) | 1 | main | kept (moved to kids) | lost (row missing) |  |
| D0-mb | group move main->kids on files beets never wrote (as-is import) | 2 | root | kept | plays=2 starred=True playlist=True |  |
| D0-mb | group move main->kids on files beets never wrote (as-is import) | 2 | main | kept (moved to kids) | lost (row missing) |  |
| D0-nomb | group move main->kids on files beets never wrote (as-is import) | 1 | root | kept | plays=2 starred=True playlist=True | kids:1eie0m |
| D0-nomb | group move main->kids on files beets never wrote (as-is import) | 1 | main | MISSING | lost (row missing) | kids:1eie0m |
| D0-nomb | group move main->kids on files beets never wrote (as-is import) | 2 | root | kept | plays=2 starred=True playlist=True | kids:3xo76E |
| D0-nomb | group move main->kids on files beets never wrote (as-is import) | 2 | main | MISSING | lost (row missing) | kids:3xo76E |
| U-mb | group move main->talk (unregistered), scan, register talk, scan | 1 | root | kept | plays=2 starred=True playlist=True |  |
| U-mb | group move main->talk (unregistered), scan, register talk, scan | 1 | main | kept (moved to talk-mb) | lost (row missing) |  |
| U-mb | group move main->talk (unregistered), scan, register talk, scan | 2 | root | kept | plays=2 starred=True playlist=True |  |
| U-mb | group move main->talk (unregistered), scan, register talk, scan | 2 | main | kept (moved to talk-mb) | lost (row missing) |  |
| U-nomb | group move main->talk (unregistered), scan, register talk, scan | 1 | root | kept | plays=2 starred=True playlist=True |  |
| U-nomb | group move main->talk (unregistered), scan, register talk, scan | 1 | main | kept (moved to talk-nomb) | lost (row missing) |  |
| U-nomb | group move main->talk (unregistered), scan, register talk, scan | 2 | root | kept | plays=2 starred=True playlist=True |  |
| U-nomb | group move main->talk (unregistered), scan, register talk, scan | 2 | main | kept (moved to talk-nomb) | lost (row missing) |  |
| R-mb | reimport-like: new MBIDs + rename album, one scan | 1 | root | MISSING | lost (row missing) | root:0E5nNW, main:6ZPrXc |
| R-mb | reimport-like: new MBIDs + rename album, one scan | 1 | main | MISSING | lost (row missing) | root:0E5nNW, main:6ZPrXc |
| R-mb | reimport-like: new MBIDs + rename album, one scan | 2 | root | MISSING | lost (row missing) | root:4UeBmX, main:6LzjEp |
| R-mb | reimport-like: new MBIDs + rename album, one scan | 2 | main | MISSING | lost (row missing) | root:4UeBmX, main:6LzjEp |
| R-nomb | reimport-like: new MBIDs + rename album, one scan | 1 | root | MISSING | lost (row missing) | root:0voyWE, main:5ZxnkM |
| R-nomb | reimport-like: new MBIDs + rename album, one scan | 1 | main | MISSING | lost (row missing) | root:0voyWE, main:5ZxnkM |
| R-nomb | reimport-like: new MBIDs + rename album, one scan | 2 | root | MISSING | lost (row missing) | root:2yYEZB, main:1yicyq |
| R-nomb | reimport-like: new MBIDs + rename album, one scan | 2 | main | MISSING | lost (row missing) | root:2yYEZB, main:1yicyq |
| R2-mb | reimport-like, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| R2-mb | reimport-like, two-phase tags first | 1 | main | kept | plays=2 starred=True playlist=True |  |
| R2-mb | reimport-like, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| R2-mb | reimport-like, two-phase tags first | 2 | main | kept | plays=2 starred=True playlist=True |  |
| R2-nomb | reimport-like, two-phase tags first | 1 | root | kept | plays=2 starred=True playlist=True |  |
| R2-nomb | reimport-like, two-phase tags first | 1 | main | kept | plays=2 starred=True playlist=True |  |
| R2-nomb | reimport-like, two-phase tags first | 2 | root | kept | plays=2 starred=True playlist=True |  |
| R2-nomb | reimport-like, two-phase tags first | 2 | main | kept | plays=2 starred=True playlist=True |  |

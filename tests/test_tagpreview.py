"""Tag preview: beets' apply step run on copies, compared field by field."""
from types import SimpleNamespace

import pytest
from beets import config
from beets.autotag.distance import Distance
from beets.autotag.hooks import AlbumInfo, TrackInfo
from beets.autotag.match import AlbumMatch
from beets.library import Item

from beetsplug.webimport import tagpreview


def _item(**fields):
    return Item(path=b"/inbox/Album/01 Song.m4a", **fields)


def _task(items, extra=()):
    tracks = [TrackInfo(title="Song (Remastered)", track_id="rec-1", index=1, length=200)]
    info = AlbumInfo(tracks=tracks, album="The Album", album_id="rel-1", artist="Band",
                     artist_id="art-1", year=2020, label="Label Co")
    match = AlbumMatch(Distance(), info, dict(zip(items, tracks)), list(extra), [])
    return SimpleNamespace(candidates=[match])


@pytest.fixture(autouse=True)
def _scratch_off():
    config["import"]["from_scratch"] = False
    yield
    config["import"]["from_scratch"] = False


def _row(track, field):
    return next((r for r in track["fields"] if r["field"] == field), None)


def test_classifies_changed_added_same():
    item = _item(title="Song", album="The Album", year=1998, genres=["Rock"])
    pv = tagpreview.preview(_task([item]), 0)
    t = pv["tracks"][0]
    assert _row(t, "title") == {"field": "title", "before": "Song", "after": "Song (Remastered)", "kind": "changed"}
    assert _row(t, "year")["kind"] == "changed"
    assert _row(t, "album")["kind"] == "same"
    assert _row(t, "label") == {"field": "label", "before": None, "after": "Label Co", "kind": "added"}
    assert _row(t, "mb_albumid")["kind"] == "added"
    # Not touched by the match: kept.
    assert _row(t, "genres")["kind"] == "same"
    assert _row(t, "composers") is None  # empty before and after: not listed


def test_nothing_is_modified():
    item = _item(title="Song", year=1998)
    tagpreview.preview(_task([item]), 0)
    assert item.title == "Song" and item.year == 1998 and not item.get("mb_albumid")


def test_from_scratch_clears_fields_the_match_doesnt_set():
    config["import"]["from_scratch"] = True
    item = _item(title="Song", genres=["Rock"], comments="ripped by me")
    pv = tagpreview.preview(_task([item]), 0)
    t = pv["tracks"][0]
    assert pv["from_scratch"] is True
    assert _row(t, "genres")["kind"] == "cleared"
    assert _row(t, "comments") == {"field": "comments", "before": "ripped by me", "after": None, "kind": "cleared"}


def test_unmatched_files_listed_unchanged():
    item = _item(title="Song")
    extra = _item(title="Bonus")
    pv = tagpreview.preview(_task([item], extra=[extra]), 0)
    bonus = pv["tracks"][1]
    assert bonus["matched"] is False
    assert all(r["kind"] == "same" for r in bonus["fields"])


def test_summary_marks_varying_values():
    a, b = _item(title="One", year=1998), _item(title="Two", year=1998)
    tracks = [TrackInfo(title="One", track_id="r1", index=1), TrackInfo(title="2", track_id="r2", index=2)]
    info = AlbumInfo(tracks=tracks, album="X", album_id="rel", artist="Y", artist_id="a", year=2020)
    task = SimpleNamespace(candidates=[AlbumMatch(Distance(), info, {a: tracks[0], b: tracks[1]}, [], [])])
    summary = {s["field"]: s for s in tagpreview.preview(task, 0)["summary"]}
    assert summary["year"]["counts"] == {"changed": 2}
    assert summary["year"]["before"] == 1998 and summary["year"]["after"] == 2020
    assert summary["title"]["counts"] == {"same": 1, "changed": 1}
    assert summary["title"]["before_varies"] and summary["title"]["after_varies"]


def test_norm_treats_beets_unset_values_as_empty():
    assert tagpreview._norm("year", 0) is None
    assert tagpreview._norm("comp", 0) == 0
    assert tagpreview._norm("comp", True) == 1
    assert tagpreview._norm("genres", ["", None]) is None
    assert tagpreview._norm("title", "") is None

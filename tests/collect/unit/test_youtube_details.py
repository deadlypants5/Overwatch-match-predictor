"""Video descriptions: reading match dates and map timestamps, fetching, and using them to link."""

from __future__ import annotations

import datetime as dt
import json

import pytest

from owstudy.collect.catalog.link import LINKED, _check_map_lists, choose_by_description, parse_title
from owstudy.collect.errors import RetrievalBlocked
from owstudy.collect.refs.youtube_details import fetch_details, load_details, parse_description

# Shaped like ObsSojourn's descriptions (links and supporter names left out).
DESC = """Heroes played: Tracer, Pharah, Echo
ZETA Division vs Team Falcons | OWCS Korea Stage 1 Playoffs
Match Date: April 25, 2026

**SPOILERS AHEAD**
Timestamps:
Lijiang Tower: 0:00
Runasapi: 9:50
Numbani: 19:00
Watchpoint: Gibraltar: 1:02:40

CHECK OUT OUR SECOND CHANNEL
"""


def test_parse_description():
    d = parse_description(DESC)
    assert d.match_date == dt.date(2026, 4, 25)
    assert d.maps == (("Lijiang Tower", 0), ("Runasapi", 590), ("Numbani", 1140), ("Watchpoint: Gibraltar", 3760))
    assert d.heroes == ("Tracer", "Pharah", "Echo")


@pytest.mark.parametrize("text", ["", None, "no date here", "Match Date: someday\n"])
def test_parse_description_missing_parts(text):
    d = parse_description(text)
    assert d.match_date is None and d.maps == ()
    if text and "someday" in text:
        assert d.notes  # an unreadable date is reported, not guessed


def test_date_variants():
    assert parse_description("Match Date: May 3rd, 2026").match_date == dt.date(2026, 5, 3)
    assert parse_description("match date: 2026-05-03").match_date == dt.date(2026, 5, 3)


# --- linking ---------------------------------------------------------------------------------

RR = {"series_id": "rr", "playoff": False, "round": "Round Robin", "day": dt.date(2026, 3, 22)}
SD = {"series_id": "sd", "playoff": True, "round": "Seeding Decider", "day": dt.date(2026, 4, 25)}
GF = {"series_id": "gf", "playoff": True, "round": "Grand Finals", "day": dt.date(2026, 5, 3)}
MAPS = {"sd": ["map:lijiang_tower", "map:runasapi", "map:numbani", "map:watchpoint_gibraltar"],
        "gf": ["map:lijiang_tower", "map:watchpoint_gibraltar", "map:blizzard_world", "map:esperanca", "map:rialto"]}
TITLE = parse_title("[ Proper ] Versus his Old Team | ZETA Division vs Team Falcons | OWCS Korea Stage 1 Playoffs")


def _m(*refs):
    return [(r, r, 0) for r in refs]


def test_match_date_picks_the_series():
    pick, conf, note = choose_by_description([GF, SD, RR], TITLE, dt.date(2026, 4, 25), [], MAPS)
    assert (pick, conf) == (SD, "high") and "2026-04-25" in note
    # one day off (time zones) still counts when nothing matches exactly
    assert choose_by_description([GF, SD, RR], TITLE, dt.date(2026, 4, 24), [], MAPS)[:2] == (SD, "high")


def test_no_series_on_that_date_is_low():
    pick, conf, note = choose_by_description([GF, SD], TITLE, dt.date(2026, 1, 1), [], MAPS)
    assert conf == "low" and "no series on the description's match date" in note


def test_maps_break_a_same_day_tie():
    other = dict(SD, series_id="sd2")
    pick, conf, _ = choose_by_description([SD, other], TITLE, dt.date(2026, 4, 25),
                                          _m("map:lijiang_tower", "map:runasapi"), MAPS)  # fmt: skip
    assert (pick, conf) == (SD, "high")


def _row(sid, conf, desc_maps):
    return {"series_id": sid, "status": LINKED, "link_confidence": conf, "note": "", "_desc_maps": desc_maps}


def test_short_map_list_marks_replay_incomplete():
    rows = [_row("sd", "high", _m("map:lijiang_tower", "map:runasapi", "map:numbani")),
            _row("sd", "high", _m(*MAPS["sd"]))]
    _check_map_lists(rows, MAPS)
    assert rows[0].get("_incomplete") and "3 of 4 maps" in rows[0]["note"]
    assert not rows[1].get("_incomplete") and rows[1]["link_confidence"] == "high"


def test_different_maps_lower_the_link():
    rows = [_row("sd", "high", _m("map:oasis", "map:busan"))]
    _check_map_lists(rows, MAPS)
    assert rows[0]["link_confidence"] == "low" and "differ" in rows[0]["note"]


# --- fetching (fake yt-dlp, no network) ------------------------------------------------------


class FakeYdl:
    def __init__(self, fail=()):
        self.fail, self.asked = set(fail), []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def extract_info(self, url, download):
        assert download is False  # never downloads
        vid = url.split("=")[1]
        self.asked.append(vid)
        if vid in self.fail:
            raise RuntimeError("Video unavailable")
        return {"id": vid, "title": f"t {vid}", "description": DESC, "upload_date": "20260427", "duration": 100,
                "formats": ["big", "list"]}


def test_fetch_saves_details_and_skips_saved_videos(tmp_path):
    ydl, sleeps = FakeYdl(fail={"bad"}), []
    folder, failed = fetch_details(["a", "b", "bad"], root=tmp_path, date="2026-11-17",
                                   ydl_factory=lambda o: ydl, sleep=sleeps.append)  # fmt: skip
    assert failed == ["bad"] and len(sleeps) == 2
    saved = json.loads((folder / "details.json").read_text(encoding="utf-8"))["videos"]
    assert [v["id"] for v in saved] == ["a", "b"] and "formats" not in saved[0]
    assert (folder / "snapshot.json").exists()
    assert set(load_details(tmp_path)) == {"a", "b"}

    ydl2 = FakeYdl()
    folder2, _ = fetch_details(["a", "b", "c"], root=tmp_path, date="2026-11-18",
                               ydl_factory=lambda o: ydl2, sleep=lambda s: None)  # fmt: skip
    assert ydl2.asked == ["c"]  # a and b were saved already
    assert set(load_details(tmp_path)) == {"a", "b", "c"}


def test_fetch_stops_when_youtube_refuses(tmp_path):
    ydl = FakeYdl(fail={"a", "b", "c", "d"})
    with pytest.raises(RetrievalBlocked):
        fetch_details(["a", "b", "c", "d"], root=tmp_path, ydl_factory=lambda o: ydl, sleep=lambda s: None)
    assert not (tmp_path / "youtube_details").exists()


def test_highlight_upload_with_some_maps_is_incomplete_not_wrong():
    # "Gibraltar/Blizzard World" uploads list maps 2 and 3 only
    rows = [_row("gf", "high", _m("map:watchpoint_gibraltar", "map:blizzard_world"))]
    _check_map_lists(rows, MAPS)
    assert rows[0]["link_confidence"] == "high" and rows[0].get("_incomplete")
    assert "2 of 5 maps" in rows[0]["note"]
    rows = [_row("gf", "high", _m("map:blizzard_world", "map:watchpoint_gibraltar"))]  # wrong order
    _check_map_lists(rows, MAPS)
    assert rows[0]["link_confidence"] == "low"

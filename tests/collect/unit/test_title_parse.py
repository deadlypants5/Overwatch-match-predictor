"""T021: reading ObsSojourn video titles and matching them to series."""

from __future__ import annotations

import datetime as dt

import pytest

from owstudy.collect.catalog.entities import Alias, AliasTable
from owstudy.collect.catalog.link import (
    AMBIGUOUS,
    BOOTCAMP,
    MATCHED,
    NO_SERIES,
    NO_TEAMS,
    NOT_OWCS,
    PRE_2026,
    UNKNOWN_TEAM,
    TeamMatcher,
    event_hint,
    match_videos,
    parse_date,
    parse_title,
    raw_key,
)


def test_standard_title():
    t = parse_title("[ Proper ] Tracer Diff | ZETA Division vs Crazy Raccoon | OWCS Korea Stage 1 Week 2")
    assert (t.player, t.team_a, t.team_b) == ("Proper", "ZETA Division", "Crazy Raccoon")
    assert t.event_text == "OWCS Korea Stage 1 Week 2"


def test_extra_separators_and_vs_dot():
    t = parse_title("[Kevster]  Clutch | Upper Final | T1 vs. Team Falcons | OWCS Asia Stage 1 Playoffs")
    assert (t.player, t.team_a, t.team_b) == ("Kevster", "T1", "Team Falcons")
    assert t.event_text == "OWCS Asia Stage 1 Playoffs"
    assert "playoff" in t.phase and "upper" in t.phase


def test_title_without_teams():
    t = parse_title("[ Someone ] Highlights | OWCS Korea Stage 1")
    assert not t.has_pair


@pytest.mark.parametrize(
    "event,expected",
    [
        ("OWCS Korea Stage 1", ("korea", "1")),
        ("OWCS KOR S2 Week 3", ("korea", "2")),
        ("OWCS Asia Stage 1 Main Event", ("asia", "1")),
        ("OWCS North America Stage 3", ("na", "3")),
        ("OWCS Midseason Championship", ("midseason", None)),
        ("Champions Clash Tokyo", ("clash", None)),
        ("Something else", (None, None)),
    ],
)
def test_event_hint(event, expected):
    assert event_hint(event) == expected


def test_parse_date():
    assert parse_date("2026-04-24 - 18:50") == dt.date(2026, 4, 24)
    assert parse_date("April 24th, 2026") == dt.date(2026, 4, 24)
    assert parse_date("") is None


def test_raw_key_drops_filler_words():
    assert raw_key("Team Falcons") == raw_key("FALCONS") == "falcons"
    assert raw_key("ONSIDE Gaming") == "onside"


# --- matching -----------------------------------------------------------------------

SERIES = [
    {"series_key": "Asia/Stage 1/Korea|Regular Season|1", "event": "Asia/Stage 1/Korea", "part": "Regular Season",
     "date": "2026-03-20 - 18:00", "team1": "ZETA DIVISION", "team2": "Poker Face"},
    {"series_key": "Asia/Stage 1/Korea|Main/Playoffs|2", "event": "Asia/Stage 1/Korea", "part": "Main/Playoffs",
     "date": "2026-04-25 - 18:00", "team1": "Poker Face", "team2": "ZETA DIVISION"},
    {"series_key": "Asia/Stage 1/Korea|Regular Season|3", "event": "Asia/Stage 1/Korea", "part": "Regular Season",
     "date": "2026-03-22 - 18:00", "team1": "Crazy Raccoon", "team2": "Team Falcons"},
    {"series_key": "Asia/Stage 1/Korea|Regular Season|4", "event": "Asia/Stage 1/Korea", "part": "Regular Season",
     "date": "2026-03-29 - 18:00", "team1": "Crazy Raccoon", "team2": "Team Falcons"},
]  # fmt: skip


def _ts(day: dt.date) -> int:
    return int(dt.datetime(day.year, day.month, day.day, 12, tzinfo=dt.timezone.utc).timestamp())


def _video(vid, title, day=dt.date(2026, 4, 1)):
    return {"id": vid, "title": title, "timestamp": _ts(day), "duration": 3600}


@pytest.fixture
def matcher():
    aliases = AliasTable([Alias("team", "zeta", "team:zeta_division", None, None, "manual")])
    names = [s["team1"] for s in SERIES] + [s["team2"] for s in SERIES]
    return TeamMatcher(names, aliases, sheet_abbrs=[("PF", "Poker Face"), ("CR", "Crazy Raccoon")])


def _match(matcher, videos):
    return {r["video_id"]: r for r in match_videos(videos, SERIES, matcher)}


def test_alias_abbreviation_and_typo_resolve(matcher):
    assert matcher.resolve("ZETA") == raw_key("ZETA DIVISION")  # hand-curated alias
    assert matcher.resolve("PF") == raw_key("Poker Face")  # spreadsheet abbreviation
    assert matcher.resolve("Poker Fcae") == raw_key("Poker Face")  # typo, close enough
    assert matcher.resolve("Totally Different") is None


def test_statuses(matcher):
    out = _match(matcher, [
        _video("a", "[ P ] x | ZETA vs PF | OWCS Korea Stage 1 Regular Season", dt.date(2026, 3, 21)),
        _video("b", "[ P ] x | Telacy vs VanirQuick | FaceIt Masters EMEA S10 Grand Finals"),
        _video("c", "[ P ] x | Team Liquid vs Virtus Pro | OWCS Preseason Bootcamp"),
        _video("d", "[ P ] x | ZETA vs PF | OWCS Korea Stage 1", dt.date(2025, 6, 1)),
        _video("e", "[ P ] Highlights | OWCS Korea Stage 1"),
        _video("f", "[ P ] x | ZETA vs Nobody Known | OWCS Korea Stage 1"),
        _video("g", "[ P ] x | ZETA vs Crazy Raccoon | OWCS Korea Stage 1"),
        _video("h", "[ P ] x | ZETA vs PF | OWCS Korea Stage 1 Open Qualifier"),
    ])  # fmt: skip
    assert out["a"]["status"] == MATCHED and out["a"]["series_key"].endswith("|1")
    assert out["b"]["status"] == NOT_OWCS
    assert out["c"]["status"] == BOOTCAMP and out["c"]["series_key"] == ""
    assert out["d"]["status"] == PRE_2026
    assert out["e"]["status"] == NO_TEAMS
    assert out["f"]["status"] == UNKNOWN_TEAM
    assert out["g"]["status"] == NO_SERIES
    assert out["h"]["status"] == NOT_OWCS


def test_phase_words_pick_playoff_series(matcher):
    out = _match(matcher, [_video("p", "[ P ] x | PF vs ZETA | OWCS Korea Stage 1 Upper Final", dt.date(2026, 4, 26))])
    assert out["p"]["status"] == MATCHED and out["p"]["series_key"].endswith("|2")


def test_repeated_pairing_is_ambiguous_and_takes_latest_before_upload(matcher):
    out = _match(matcher, [_video("r", "[ P ] x | CR vs Falcons | OWCS Korea Stage 1", dt.date(2026, 3, 30))])
    assert out["r"]["status"] == AMBIGUOUS
    assert out["r"]["series_key"].endswith("|4") and out["r"]["note"] == "2 candidates"

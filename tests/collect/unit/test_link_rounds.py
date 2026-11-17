"""Telling repeat matchups apart: round words, player uniqueness, video length, upload neighbours."""

from __future__ import annotations

from owstudy.collect.catalog.link import LINKED, choose_series, parse_title, phase_filter, settle_by_length

RR = {"series_id": "rr", "playoff": False, "round": "Round Robin", "score_a": 3, "score_b": 1}
SD = {"series_id": "sd", "playoff": True, "round": "Seeding Decider", "score_a": 3, "score_b": 1}
GF = {"series_id": "gf", "playoff": True, "round": "Grand Finals", "score_a": 4, "score_b": 1}
ALL = [GF, SD, RR]  # nearest date first, as link_candidates returns them


def _t(event: str):
    return parse_title(f"[ Proper ] Nickname | ZETA Division vs Team Falcons | {event}")


def test_round_words_pick_the_round():
    assert choose_series(ALL, _t("OWCS Korea Stage 1 Grand Finals"))[:2] == (GF, "medium")
    assert choose_series(ALL, _t("OWCS Korea Stage 1 Seeding Decider"))[:2] == (SD, "medium")


def test_no_phase_words_means_regular_season():
    pick, conf, note = choose_series(ALL, _t("OWCS Korea Stage 1"))
    assert (pick, conf) == (RR, "medium") and "regular season" in note


def test_playoffs_word_keeps_seeding_decider_open():
    # ObsSojourn often labels seeding deciders "Playoffs": both stay candidates, decided later
    kept, _ = phase_filter(ALL, _t("OWCS Korea Stage 1 Playoffs"))
    assert kept == [GF, SD]
    assert choose_series(ALL, _t("OWCS Korea Stage 1 Playoffs"))[1] == "low"


def _row(vid, sid, conf, player, dur):
    return {"video_id": vid, "series_id": sid, "status": LINKED, "link_confidence": conf, "pov_player_id": player,
            "player_norm": player, "duration_s": dur, "_n_maps": 5 if sid == "gf" else 4, "note": ""}


def test_same_player_rules_out_a_series_and_length_decides():
    # Grand final POVs (titled "Grand Finals") are confident; Proper's "Playoffs" video of a
    # different length can't be a second Proper POV of the grand final -> seeding decider.
    rows = [_row(f"g{i}", "gf", "medium", p, 4315) for i, p in enumerate(["proper", "knife", "shu"])]
    rows.append(_row("x", "gf", "low", "proper", 3445))
    settle_by_length(rows, {"x": [GF, SD]})
    assert (rows[-1]["series_id"], rows[-1]["link_confidence"]) == ("sd", "medium")
    assert "ruled out" in rows[-1]["note"]


def test_map_count_guess_needs_three_agreeing_povs():
    one = [_row("a", "gf", "low", "p1", 3600)]
    settle_by_length(one, {"a": [GF, SD]})
    assert one[0]["link_confidence"] == "low"  # one video could be a 5-map replay with holes
    three = [_row(v, "gf", "low", p, 3600) for v, p in (("a", "p1"), ("b", "p2"), ("c", "p3"))]
    settle_by_length(three, {v: [GF, SD] for v in "abc"})
    assert {r["series_id"] for r in three} == {"gf"} and {r["link_confidence"] for r in three} == {"medium"}


def test_short_pov_follows_its_upload_neighbours():
    # A POV with holes (900 s) looks like a short series, but it was uploaded in the middle of
    # the grand final's confident videos.
    rows = [_row("n1", "gf", "medium", "p1", 4315), _row("n2", "gf", "medium", "p2", 4315),
            _row("x", "sd", "low", "p3", 900), _row("n3", "gf", "medium", "p4", 4315)]
    settle_by_length(rows, {"x": [GF, SD]})
    assert (rows[2]["series_id"], rows[2]["link_confidence"]) == ("gf", "medium")
    assert "uploaded alongside 3" in rows[2]["note"]


# --- researcher's video notes (configs/collect/video_overrides.yaml) ---------------------

import pytest  # noqa: E402

from owstudy.collect.catalog.link import _apply_overrides, _set_roles  # noqa: E402
from owstudy.collect.config import VideoOverride, load_video_overrides  # noqa: E402
from owstudy.collect.errors import ConfigError  # noqa: E402


def test_incomplete_replay_is_never_primary():
    rows = [_row("full", "gf", "high", "p1", 4000), _row("holes", "gf", "high", "p2", 4300)]
    for r in rows:
        r["pov_team_id"] = "team:a"
    _apply_overrides(rows, {"holes": VideoOverride("holes", incomplete=True, note="missing map 5")}, {"gf": GF})
    _set_roles(rows, {"gf": {"team_a_id": "team:a", "team_b_id": "team:b"}}, 1)
    roles = {r["video_id"]: r["role"] for r in rows}
    assert roles == {"full": "primary", "holes": "unused"}  # though it is the longest
    assert "missing map 5" in rows[1]["note"]


def test_hand_set_series_wins():
    rows = [_row("x", "gf", "low", "p1", 3445)]
    _apply_overrides(rows, {"x": VideoOverride("x", series_id="sd")}, {"gf": GF, "sd": SD})
    assert (rows[0]["series_id"], rows[0]["link_confidence"]) == ("sd", "manual")
    with pytest.raises(ConfigError):
        _apply_overrides(rows, {"x": VideoOverride("x", series_id="nope")}, {"gf": GF})
    _apply_overrides(rows, {"gone": VideoOverride("gone", incomplete=True)}, {"gf": GF})  # deleted video: ignored


def test_load_video_overrides(tmp_path):
    assert load_video_overrides(tmp_path / "missing.yaml") == {}
    f = tmp_path / "v.yaml"
    f.write_text("videos:\n  - {video_id: abc, incomplete: true, note: holes}\n", encoding="utf-8")
    assert load_video_overrides(f)["abc"] == VideoOverride("abc", "", True, "holes")
    for bad in ("videos:\n  - {video_id: abc}\n",  # says nothing
                "videos:\n  - {video_id: abc, incomplete: yes please}\n",
                "videos:\n  - {video_id: abc, incomplete: true, colour: red}\n",
                "videos:\n  - {video_id: a, incomplete: true}\n  - {video_id: a, incomplete: true}\n"):
        f.write_text(bad, encoding="utf-8")
        with pytest.raises(ConfigError):
            load_video_overrides(f)


def test_repo_video_overrides_load():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[3]
    assert len(load_video_overrides(repo / "configs" / "collect" / "video_overrides.yaml")) == 3

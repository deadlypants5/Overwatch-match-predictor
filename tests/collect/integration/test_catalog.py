"""T027: building the catalog and linking videos, on the small fake references (T026).

The fixture (tests/collect/fixtures/references/, see its README) is one Korea Stage 1 event with
four series, one NA series on the same patch day, one Preseason Bootcamp series, a spreadsheet
with one series Liquipedia doesn't have, and a short video list.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import shutil
from pathlib import Path

import pandas as pd
import pytest

from owstudy.collect.catalog.build import (
    assign_patch,
    build_catalog,
    region_stage,
    series_id_of,
    split_event,
    start_utc,
)
from owstudy.collect.catalog.entities import Alias, AliasTable
from owstudy.collect.catalog.link import in_scope_links, link_videos
from owstudy.collect.cli import main
from owstudy.collect.config import PatchOverrides, load_config, load_patch_overrides, load_patches
from owstudy.collect.io.tables import read_table
from owstudy.collect.refs.youtube_list import load_videos

REPO = Path(__file__).resolve().parents[3]
CONF = REPO / "configs" / "collect"
FIX = Path(__file__).parents[1] / "fixtures" / "references"
LP, SHEET, YT = FIX / "liquipedia" / "2026-11-20", FIX / "spreadsheet" / "2026-11-20", FIX / "youtube" / "2026-11-20"
KOREA = "Asia/Stage 1/Korea"
BOTH = "liquipedia:2026-11-20;spreadsheet:2026-11-20"

S1 = series_id_of("Asia/Stage 1/Korea|Regular Season|1")  # Alpha-Bravo, patch day, Clash map
S2 = series_id_of("Asia/Stage 1/Korea|Regular Season|2")  # forfeit
S4 = series_id_of("Asia/Stage 1/Korea|Regular Season|3")  # Charlie-Alpha, 08:00 KST
S3 = series_id_of("Asia/Stage 1/Korea|Main/Playoffs|1")  # Alpha-Bravo again, playoffs
NA = series_id_of("NA/Stage 1|Regular Season|1")
SHEET_ONLY = "sheet_korea_stage_1_85"


@pytest.fixture(scope="module")
def cfg(tmp_path_factory):
    return load_config(CONF / "default.yaml", local_path=tmp_path_factory.mktemp("cfg") / "none.yaml")


def _build(aliases=None, overrides=None):
    patches = load_patches(CONF / "patches.yaml")
    return build_catalog(
        LP, SHEET, aliases or AliasTable(), read_table(REPO / "data" / "interim" / "entities" / "maps.csv"), patches,
        overrides or load_patch_overrides(CONF / "patch_overrides.yaml", patches), KOREA,
    )  # fmt: skip


@pytest.fixture(scope="module")
def cat():
    return _build()


@pytest.fixture(scope="module")
def links(cat, cfg):
    return link_videos(cat, load_videos(YT), AliasTable(), cfg).set_index("video_id")


def _series(cat, sid):
    rows = cat.series[cat.series.series_id == sid]
    assert len(rows) == 1, sid
    return rows.iloc[0]


def _map(cat, mid):
    return cat.maps.set_index("map_id").loc[mid]


# --- series (US1 scenario 1) ----------------------------------------------------------


def test_each_series_appears_once_with_both_sources(cat):
    korea = cat.scoped([KOREA]).series
    assert sorted(korea.series_id) == sorted([S1, S2, S4, S3, SHEET_ONLY])
    assert not cat.series.series_id.duplicated().any()
    for sid in (S1, S2, S4, S3):
        assert _series(cat, sid).sources == BOTH, sid


def test_series_fields(cat):
    s = _series(cat, S1)
    assert (s.region, s.stage, s.phase, s.best_of) == ("Korea", "Stage 1", "Regular Season", "5")
    assert (s.team_a_id, s.team_b_id, s.score_a, s.score_b, s.status) == (
        "team:team_alpha", "team:bravo_esports", 3, 1, "played")  # fmt: skip
    assert bool(s.in_pilot) and not bool(_series(cat, NA).in_pilot)
    s3 = _series(cat, S3)  # Liquipedia order kept: Bravo is team a here
    assert (s3.team_a_id, s3.team_b_id, s3.phase, s3.best_of) == ("team:bravo_esports", "team:team_alpha", "Playoffs", "7")
    assert _series(cat, S4).best_of == "5"  # not on Liquipedia: from the sheet's "[Bo5]"


def test_sheet_only_series_is_flagged_and_keeps_its_maps(cat):
    s = _series(cat, SHEET_ONLY)
    assert s.sources == "spreadsheet:2026-11-20"
    assert (s.team_a_id, s.team_b_id, s.start_utc, s.patch_id) == ("team:delta_gaming", "team:team_alpha", "", "")
    maps = cat.maps[cat.maps.series_id == SHEET_ONLY]
    assert list(maps.winner) == ["a", "b", "a", "b", "a"]


def test_unplayed_and_bootcamp_series_left_out(cat):
    assert series_id_of("Asia/Stage 1/Korea|Regular Season|4") not in set(cat.series.series_id)
    assert not cat.series.series_id.str.contains("bootcamp").any()  # FR-023a
    assert not cat.maps.series_id.str.contains("bootcamp").any()


# --- maps ------------------------------------------------------------------------------


def test_twelve_korea_liquipedia_maps_with_clash_and_forfeit(cat):
    lp_korea = cat.maps[cat.maps.series_id.isin([S1, S2, S4, S3])]
    assert len(lp_korea) == 12
    clash = _map(cat, f"{S1}-m2")
    assert (clash.map_ref, clash.mode_id, clash.status) == ("map:hanaoka", "clash", "clash_excluded")
    assert _map(cat, f"{S2}-m1").status == "forfeit"
    s2 = _series(cat, S2)
    assert (s2.status, s2.score_a, s2.score_b) == ("forfeit", "", "")
    assert set(lp_korea.status) == {"played", "clash_excluded", "forfeit"}
    m = _map(cat, f"{S4}-m2")
    assert (m.map_ref, m.mode_id, m.winner) == ("map:runasapi", "push", "b")


def test_start_time_converted_to_utc(cat):
    assert _series(cat, S1).start_utc == "2026-04-14T10:00:00Z"
    s4 = _series(cat, S4)  # 08:00 KST is the previous day in UTC
    assert (s4.local_date, s4.start_utc, s4.tz) == ("2026-04-16", "2026-04-15T23:00:00Z", "KST")
    assert _series(cat, NA).start_utc == "2026-04-14T20:00:00Z"  # 15:00 CDT


def test_start_utc_unknown_time_zone_or_time():
    import datetime as dt

    assert start_utc(dt.date(2026, 4, 1), dt.time(19, 0), "TBA", "Korea") == ""
    assert start_utc(dt.date(2026, 4, 1), None, "KST", "Korea") == ""
    assert start_utc(dt.date(2026, 4, 1), dt.time(19, 0), "CST", "China") == "2026-04-01T11:00:00Z"
    assert start_utc(dt.date(2026, 4, 1), dt.time(19, 0), "CST", "NA") == "2026-04-02T01:00:00Z"


# --- patches ---------------------------------------------------------------------------


def test_patch_rules(cat):
    # p2026.12 went live 2026-04-14: Korea plays before the release -> previous patch.
    assert set(cat.maps[cat.maps.series_id == S1].patch_id) == {"p2026.11"}
    assert set(cat.maps[cat.maps.series_id == NA].patch_id) == {"p2026.12"}  # NA plays after it
    assert set(cat.maps[cat.maps.series_id == S4].patch_id) == {"p2026.12"}  # 2026-04-16
    assert set(cat.maps[cat.maps.series_id == S3].patch_id) == {"p2026.14"}  # 2026-04-25
    pd_rows = cat.patch_day.set_index("series_id")
    assert sorted(pd_rows.index) == sorted([S1, NA])
    assert pd_rows.loc[S1].rule == "pre_patch_region" and pd_rows.loc[NA].rule == "new_patch"
    assert pd_rows.loc[S1].local_date == "2026-04-14"


def test_asia_playoffs_follow_korea_rule():
    patches = load_patches(CONF / "patches.yaml")
    overrides = PatchOverrides(("Korea", "Asia"), {})
    day = dt.date(2026, 4, 14)  # p2026.12 went live this day
    assert assign_patch(day, "Asia/Stage 1", ("x",), patches, overrides) == ("p2026.11", "pre_patch_region")
    assert assign_patch(day, "Asia/Stage 1/Korea", ("x",), patches, overrides)[1] == "pre_patch_region"
    assert assign_patch(day, "Asia/Stage 1/Japan", ("x",), patches, overrides) == ("p2026.12", "new_patch")
    assert assign_patch(day, "NA/Stage 1", ("x",), patches, overrides) == ("p2026.12", "new_patch")


def test_hand_set_patch_wins():
    patches = load_patches(CONF / "patches.yaml")
    cat = _build(overrides=PatchOverrides(("Korea",), {"Asia/Stage 1/Korea|Main/Playoffs|1": "p2026.13"}))
    assert set(cat.maps[cat.maps.series_id == S3].patch_id) == {"p2026.13"}
    assert cat.patch_day.set_index("series_id").loc[S3].rule == "hand_set"
    assert assign_patch(None, KOREA, ("x",), patches, PatchOverrides()) == ("", None)


# --- lineups and aliases --------------------------------------------------------------


def test_lineups_from_event_roster(cat):
    lu = cat.lineups[cat.lineups.series_id == S4]
    charlie = sorted(lu[lu.team_id == "team:charlie"].player_id)  # "Charlie" matches roster "CHARLIE"
    assert charlie == ["player:cobra", "player:comet", "player:crane", "player:cub_korean_player", "player:cy"]
    assert len(lu[lu.team_id == "team:team_alpha"]) == 5
    assert set(cat.lineups.source) == {"event_roster"}
    assert not cat.lineups.player_id.str.contains("coach").any()  # staff left out


def test_alias_proposals(cat):
    p = cat.proposals
    rows = set(zip(p.entity_type, p.alias, p.candidate_stable_id))
    assert ("team", "ALP", "team:team_alpha") in rows and ("team", "BRV", "team:bravo_esports") in rows
    assert ("player", "Cub", "player:cub_korean_player") in rows
    assert not any(a == "Team Alpha" for _, a, _ in rows)  # a team's own name isn't proposed
    known = AliasTable([Alias("team", "alp", "team:team_alpha", None, None, "manual")])
    assert "ALP" not in set(_build(aliases=known).proposals.alias)  # already in aliases.csv


def test_region_stage_round_trip():
    for key in ["Asia/Stage 1/Korea", "Asia/Stage 2", "NA/Stage 3", "EMEA/Stage 1", "Champions Clash", "World Finals"]:
        assert region_stage(*split_event(key)) == key


# --- video links (US1 scenarios 2, 4, 5) ------------------------------------------------


def test_single_candidate_is_high_confidence(links):
    r = links.loc["vidS4Cy0000"]
    assert (r.series_id, r.status, r.link_confidence, r.role) == (S4, "linked", "high", "primary")
    assert (r.pov_player_id, r.pov_team_id) == ("player:cy", "team:charlie")


def test_repeated_pairing_resolved_by_phase_words(links):
    rs, gf = links.loc["vidS1Ace000"], links.loc["vidS3Bolt00"]  # both uploaded after both series
    assert (rs.series_id, rs.link_confidence) == (S1, "medium")
    assert (gf.series_id, gf.link_confidence) == (S3, "medium")
    assert "phase words" in rs.note


def test_abbreviations_in_titles_resolve(links):
    r = links.loc["vidS1Bolt00"]  # "ALP vs BRV"
    assert (r.series_id, r.pov_team_id) == (S1, "team:bravo_esports")


def test_duplicate_upload(links):
    r = links.loc["vidS1AceDup"]
    assert (r.series_id, r.status, r.role) == (S1, "duplicate", "duplicate")
    assert "vidS1Ace000" in r.note


def test_unmatched_titles_are_not_guessed(links):
    for vid, why in (("vidUnknown0", "unknown team"), ("vidNoSeries", "no played 2026 series")):
        r = links.loc[vid]
        assert (r.status, r.series_id, r.link_confidence, r.role) == ("unmatched", "", "", "")
        assert why in r.note


def test_out_of_scope_videos(links):
    assert links.loc["vidBootcamp"].status == "not_owcs_2026"
    assert "FR-023a" in links.loc["vidBootcamp"].note
    assert links.loc["vidFaceit00"].status == "not_owcs_2026"
    assert links.loc["vidOld20250"].status == "not_owcs_2026"


def test_roles_and_cross_check(cat, cfg, links):
    assert links.loc["vidS1Ace000"].role == "primary"  # longest video of the series
    assert links.loc["vidS1Bolt00"].role == "unused"
    two = dataclasses.replace(cfg, video=dataclasses.replace(cfg.video, povs_per_series=2))
    l2 = link_videos(cat, load_videos(YT), AliasTable(), two).set_index("video_id")
    assert l2.loc["vidS1Ace000"].role == "primary" and l2.loc["vidS1Bolt00"].role == "cross_check"
    assert not links.confirmed.any()


def test_series_without_video_keep_their_maps(cat, links):
    linked = set(links[links.status == "linked"].series_id)
    for sid in (S2, NA, SHEET_ONLY):
        assert sid not in linked
        assert len(cat.maps[cat.maps.series_id == sid]) > 0


def test_scope_filter(cat, links):
    scoped = cat.scoped([KOREA])
    kept = set(in_scope_links(links.reset_index(), set(scoped.series.series_id), [KOREA]).video_id)
    assert {"vidS1Ace000", "vidS4Cy0000", "vidUnknown0", "vidNoSeries", "vidBootcamp", "vidS1AceDup"} <= kept
    assert not {"vidFaceit00", "vidOld20250"} & kept  # other region-stages


# --- commands: catalog build, status, refs fetch ----------------------------------------


@pytest.fixture
def data_dir(tmp_data_dir):
    shutil.copytree(FIX, tmp_data_dir / "raw" / "reference", dirs_exist_ok=True)
    ent = tmp_data_dir / "interim" / "entities"
    ent.mkdir(parents=True)
    shutil.copy(REPO / "data" / "interim" / "entities" / "maps.csv", ent)
    (ent / "aliases.csv").write_text("entity_type,alias,stable_id,valid_from,valid_to,source\n", encoding="utf-8")
    return tmp_data_dir


def _run(data_dir, *args):
    config = data_dir.parent / "configs" / "collect" / "default.yaml"
    return main(["--config", str(config), "--data-dir", str(data_dir), *args])


def test_catalog_build_command_is_repeatable(data_dir, capsys):
    assert _run(data_dir, "catalog", "build") == 0
    out = data_dir / "interim" / "catalog"
    names = ["series.csv", "maps.csv", "lineups.csv", "patch_day_series.csv", "video_links.csv"]
    first = {n: (out / n).read_bytes() for n in names}
    assert all(b"\r" not in v for v in first.values())
    assert _run(data_dir, "catalog", "build") == 0
    assert first == {n: (out / n).read_bytes() for n in names}  # same inputs, same bytes
    series = pd.read_csv(out / "series.csv", dtype=str)
    assert sorted(series.series_id) == sorted([S1, S2, S4, S3, SHEET_ONLY])  # pilot scope only
    assert (data_dir / "interim" / "entities" / "aliases.csv").read_text(encoding="utf-8").count("\n") == 1
    assert "ALP" in (data_dir / "interim" / "entities" / "aliases_proposed.csv").read_text(encoding="utf-8")
    assert "series: 5" in capsys.readouterr().out


def test_status_command(data_dir, capsys):
    assert _run(data_dir, "status") == 2  # no catalog yet
    assert _run(data_dir, "catalog", "build") == 0
    capsys.readouterr()
    assert _run(data_dir, "status") == 0
    out = capsys.readouterr().out
    assert KOREA in out
    from owstudy.collect.catalog.inventory import coverage_status

    row = coverage_status(data_dir / "interim" / "catalog").set_index("region_stage").loc[KOREA]
    assert (row.series, row.one_source_series, row.maps, row.excluded_maps) == (5, 1, 15, 2)
    assert (row.maps_with_replay, row.maps_no_replay, row.series_no_replay) == (10, 5, 1)
    assert (row.links_to_review, row.patch_day_series) == (0, 1)


def test_fetch_liquipedia_refuses_without_key(data_dir, capsys):
    assert _run(data_dir, "refs", "fetch", "liquipedia") == 3
    err = capsys.readouterr().err
    assert "liquipedia_api_key" in err and "local.yaml" in err
    assert not (data_dir / "raw" / "reference" / "liquipedia" / "2026-11-15").exists()


def test_fetch_with_key_never_prints_it(data_dir, capsys):
    local = data_dir.parent / "configs" / "collect" / "local.yaml"
    local.write_text('user_agent_contact: "tests"\nliquipedia_api_key: "SECRET-KEY-123"\n', encoding="utf-8")
    code = _run(data_dir, "refs", "fetch", "liquipedia")
    out = capsys.readouterr()
    assert code == 2 and "T028" in out.err
    assert "SECRET-KEY-123" not in out.err + out.out


def test_fetch_owtv_not_built(data_dir, capsys):
    assert _run(data_dir, "refs", "fetch", "owtv") == 2
    assert "T066" in capsys.readouterr().err


def test_import_sheet_missing_file(data_dir, capsys):
    assert _run(data_dir, "refs", "import-sheet", str(data_dir / "nope.xlsx")) == 2
    assert "not found" in capsys.readouterr().err

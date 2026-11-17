"""T020: the inventory command reproduces the exploratory 2026-11-15 numbers."""

from __future__ import annotations

import glob
import shutil
from pathlib import Path

import pandas as pd
import pytest

from owstudy.collect.cli import main
from owstudy.collect.refs.liquipedia import parse_batch
from owstudy.collect.refs.spreadsheet import parse_workbook

REPO = Path(__file__).resolve().parents[3]
REF = REPO / "data" / "raw" / "reference"
OLD_SUMMARY = Path(__file__).parents[1] / "fixtures" / "references" / "inventory_summary_2026-11-15.csv"
XLSX = REPO / "OWCS 2026 Hero Bans _ Metas(1).xlsx"  # not committed; tests using it skip without it
OUTPUTS = ["inventory_summary.csv", "series_inventory.csv", "series_missing_video.csv",
           "pilot_korea_stage1_series.csv", "gap_coverage.csv", "sheet_vs_liquipedia.csv", "video_matches.csv"]  # fmt: skip


@pytest.fixture(scope="module")
def run_dir(tmp_path_factory) -> Path:
    """Run `owstudy-collect inventory --scope all` on a copy of the committed snapshots."""
    root = tmp_path_factory.mktemp("inv")
    data = root / "data"
    shutil.copytree(REF, data / "raw" / "reference")
    (data / "interim" / "entities").mkdir(parents=True)
    shutil.copy(REPO / "data" / "interim" / "entities" / "aliases.csv", data / "interim" / "entities")
    code = main(["--config", str(REPO / "configs" / "collect" / "default.yaml"), "--data-dir", str(data),
                 "--scope", "all", "inventory"])  # fmt: skip
    assert code == 0
    return data / "interim" / "inventory"


def test_writes_every_output_with_unix_line_endings(run_dir):
    for name in OUTPUTS:
        data = (run_dir / name).read_bytes()
        assert data and b"\r" not in data, name


def test_summary_reproduces_exploratory_numbers(run_dir):
    old = pd.read_csv(OLD_SUMMARY).replace({"scope": {"PILOT Korea Stage 1": "PILOT Asia/Stage 1/Korea"}})
    new = pd.read_csv(run_dir / "inventory_summary.csv")
    assert list(new.columns) == list(old.columns)
    merged = old.merge(new, on="scope", how="outer", suffixes=("_old", "_new"), indicator=True)
    assert (merged._merge == "both").all(), merged[merged._merge != "both"].scope.tolist()
    for c in ["series", "maps", "series_with_video", "series_missing_video", "maps_with_video",
              "maps_missing_video", "pov_videos"]:  # fmt: skip
        assert (merged[f"{c}_old"] == merged[f"{c}_new"]).all(), c
    for c in ["hours_all_pov", "hours_one_pov", "hours_one_pov_per_team"]:
        assert ((merged[f"{c}_old"] - merged[f"{c}_new"]).abs() <= 0.1 + 1e-9).all(), c


def test_pilot_row(run_dir):
    s = pd.read_csv(run_dir / "inventory_summary.csv").set_index("scope").loc["PILOT Asia/Stage 1/Korea"]
    assert (s.series, s.maps, s.series_with_video) == (51, 186, 25)
    assert s.hours_one_pov == pytest.approx(18.4, abs=0.05)
    pilot = pd.read_csv(run_dir / "pilot_korea_stage1_series.csv")
    assert len(pilot) == 51 and set(pilot.event) == {"Asia/Stage 1/Korea"}


def test_bootcamp_videos_are_out_of_scope(run_dir):
    v = pd.read_csv(run_dir / "video_matches.csv", keep_default_na=False)
    boot = v[v.title.str.contains("Preseason Bootcamp")]
    assert len(boot) > 0
    assert set(boot.status) == {"out_of_scope_bootcamp"} and (boot.series_key == "").all()


def test_two_runs_are_byte_identical(run_dir, tmp_path):
    data = tmp_path / "data"
    shutil.copytree(run_dir.parents[1], data)
    main(["--config", str(REPO / "configs" / "collect" / "default.yaml"), "--data-dir", str(data), "inventory"])
    for name in OUTPUTS:
        assert (data / "interim" / "inventory" / name).read_bytes() == (run_dir / name).read_bytes(), name


# --- the readers moved into the package reproduce the committed snapshot tables -------


def _same(old_csv: Path, rows: list[dict]) -> None:
    old = pd.read_csv(old_csv, dtype=str, keep_default_na=False)
    new = pd.DataFrame(rows).drop(columns="locator").astype(object).where(lambda d: d.notna(), "").astype(str)
    assert len(new) == len(old)
    pd.testing.assert_frame_equal(old, new[list(old.columns)], check_dtype=False)


def test_liquipedia_reader_reproduces_snapshot():
    series, maps = parse_batch(sorted(glob.glob(str(REF / "liquipedia" / "2026-11-15" / "batch*.json"))))
    _same(REF / "liquipedia" / "2026-11-15" / "lp_series.csv", series)
    _same(REF / "liquipedia" / "2026-11-15" / "lp_maps.csv", maps)
    assert len({s["series_key"] for s in series}) == len(series)
    assert all("@" in s["locator"] and "#match" in s["locator"] for s in series)


@pytest.mark.skipif(not XLSX.exists(), reason="spreadsheet file not present (it isn't committed)")
def test_spreadsheet_reader_reproduces_snapshot_and_reads_bans():
    series, maps, bans = parse_workbook(XLSX)
    _same(REF / "spreadsheet" / "2026-11-15" / "sheet_series.csv", series)
    _same(REF / "spreadsheet" / "2026-11-15" / "sheet_maps.csv", maps)
    assert all(r["locator"].count("!") == 1 for r in series + maps + bans)
    by_map = pd.DataFrame(bans).groupby(["series_key", "map_number"]).size()
    assert (by_map == 2).all()  # one ban per team wherever a map has bans
    assert len(by_map) >= 0.99 * len(maps)

"""Footage inventory (User Story 0, FR-007a): how many series and maps each 2026 event has,
how many have an ObsSojourn POV video, and how many hours of footage that is.

Reads the latest reference snapshots and writes `data/interim/inventory/`. Covers every 2026
event regardless of `--scope`: it's a survey, not processing.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from owstudy.collect.catalog.entities import AliasTable
from owstudy.collect.catalog.link import MATCHED, TeamMatcher, match_videos
from owstudy.collect.io.tables import read_table, write_table
from owstudy.collect.refs.snapshot import latest_snapshot

SERIES_INV_COLUMNS = ["series_key", "event", "part", "date", "team1", "team2", "maps_played", "vod",
                      "n_pov", "pov_hours", "one_pov_h", "two_pov_h", "has_video"]  # fmt: skip
SUMMARY_COLUMNS = ["scope", "series", "maps", "series_with_video", "series_missing_video", "maps_with_video",
                   "maps_missing_video", "pov_videos", "hours_all_pov", "hours_one_pov", "hours_one_pov_per_team"]  # fmt: skip
GAP_COLUMNS = ["scope", "series", "obs_video", "missing_obs", "missing_obs_but_official_vod",
               "no_video_at_all", "maps_no_video_at_all"]  # fmt: skip
SHEET_VS_LP_COLUMNS = ["event", "lp_series", "lp_maps", "sheet_series", "sheet_maps", "series_diff", "maps_diff"]
VIDEO_COLUMNS = ["video_id", "title", "player", "event_text", "duration_s", "upload_date", "team_a", "team_b",
                 "series_key", "status", "note"]  # fmt: skip

HOURS = {"pov_hours": 4, "one_pov_h": 4, "two_pov_h": 4}
SUMMARY_HOURS = {"hours_all_pov": 1, "hours_one_pov": 1, "hours_one_pov_per_team": 1}
ALL_LABEL = "ALL 2026"


def pilot_label(pilot: str) -> str:
    return f"PILOT {pilot}"


def sheet_tab_event(tab: str) -> str:
    """Spreadsheet tab name -> Liquipedia event ('Korea - Stage 1' -> 'Asia/Stage 1/Korea')."""
    m = re.match(r"(.+?) - Stage (\d)$", tab)
    if m:
        region, stage = m.group(1), m.group(2)
        if region in ("Japan", "Korea", "Pacific"):
            return f"Asia/Stage {stage}/{region}"
        return f"{ {'North America': 'NA'}.get(region, region)}/Stage {stage}"
    for prefix in ("Champions Clash", "Midseason Championship", "World Finals"):
        if tab.startswith(prefix):
            return prefix
    return tab


@dataclass
class Inventory:
    videos: pd.DataFrame
    series: pd.DataFrame
    summary: pd.DataFrame
    gap: pd.DataFrame
    sheet_vs_lp: pd.DataFrame
    pilot: str

    @property
    def pilot_series(self) -> pd.DataFrame:
        return self.series[self.series.event == self.pilot]

    @property
    def missing(self) -> pd.DataFrame:
        return self.series[~self.series.has_video]


def _summary(df: pd.DataFrame, name: str) -> dict:
    return {
        "scope": name, "series": len(df), "maps": int(df.maps_played.sum()),
        "series_with_video": int(df.has_video.sum()), "series_missing_video": int((~df.has_video).sum()),
        "maps_with_video": int(df[df.has_video].maps_played.sum()),
        "maps_missing_video": int(df[~df.has_video].maps_played.sum()),
        "pov_videos": int(df.n_pov.fillna(0).sum()), "hours_all_pov": round(df.pov_hours.fillna(0).sum(), 1),
        "hours_one_pov": round(df.one_pov_h.sum(), 1), "hours_one_pov_per_team": round(df.two_pov_h.sum(), 1),
    }  # fmt: skip


def _gap(df: pd.DataFrame, name: str) -> dict:
    missing = df[~df.has_video]
    no_vod = missing[missing.vod.fillna("").astype(str).str.strip() == ""]
    return {
        "scope": name, "series": len(df), "obs_video": int(df.has_video.sum()), "missing_obs": len(missing),
        "missing_obs_but_official_vod": len(missing) - len(no_vod), "no_video_at_all": len(no_vod),
        "maps_no_video_at_all": int(no_vod.maps_played.sum()),
    }  # fmt: skip


def _scopes(S: pd.DataFrame, pilot: str, fn) -> pd.DataFrame:
    rows = [fn(S[S.event == pilot], pilot_label(pilot))]
    rows += [fn(g, ev) for ev, g in S.groupby("event")]
    rows.append(fn(S, ALL_LABEL))
    return pd.DataFrame(rows)


def build_inventory(
    lp_series: pd.DataFrame,
    sheet_series: pd.DataFrame,
    sheet_maps: pd.DataFrame,
    videos: list[dict],
    aliases: AliasTable,
    pilot: str,
) -> Inventory:
    lp = lp_series.copy()
    lp["maps_played"] = pd.to_numeric(lp.maps_played).astype(int)
    lp = lp[lp.maps_played > 0].copy()

    matcher = TeamMatcher(
        list(lp.team1) + list(lp.team2), aliases, list(zip(sheet_series.abbr1, sheet_series.team1))
        + list(zip(sheet_series.abbr2, sheet_series.team2)),
    )  # fmt: skip
    V = pd.DataFrame(match_videos(videos, lp.to_dict(orient="records"), matcher), columns=VIDEO_COLUMNS)

    mv = V[V.status.str.startswith(MATCHED)]
    per = mv.groupby("series_key").agg(
        n_pov=("video_id", "count"),
        pov_hours=("duration_s", lambda s: s.sum() / 3600),
        median_len_h=("duration_s", lambda s: s.median() / 3600),
    ).reset_index()
    S = lp.merge(per, on="series_key", how="left")
    S["has_video"] = S.n_pov.fillna(0) > 0
    # One POV per series = the median POV length (POVs of one series are about the same length).
    S["one_pov_h"] = S.median_len_h.fillna(0)
    # One POV per team: 2 x median when there are >= 2 POVs (titles don't say the POV's team).
    S["two_pov_h"] = S.median_len_h.fillna(0) * S.n_pov.fillna(0).clip(upper=2)
    S["n_pov"] = S.n_pov.astype("Int64")

    sh_maps = sheet_maps.groupby("series_key").size()
    sh = sheet_series.assign(event=sheet_series.sheet.map(sheet_tab_event))
    sh["map_rows"] = sh.series_key.map(sh_maps).fillna(0).astype(int)
    lp_ev = S.groupby("event").agg(lp_series=("series_key", "count"), lp_maps=("maps_played", "sum"))
    sh_ev = sh.groupby("event").agg(sheet_series=("series_key", "count"), sheet_maps=("map_rows", "sum"))
    cmp = lp_ev.join(sh_ev, how="outer").fillna(0).astype(int).reset_index()
    cmp["series_diff"] = cmp.lp_series - cmp.sheet_series
    cmp["maps_diff"] = cmp.lp_maps - cmp.sheet_maps

    return Inventory(
        videos=V, series=S[SERIES_INV_COLUMNS], summary=_scopes(S, pilot, _summary),
        gap=_scopes(S, pilot, _gap), sheet_vs_lp=cmp[SHEET_VS_LP_COLUMNS], pilot=pilot,
    )  # fmt: skip


def write_inventory(inv: Inventory, out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    return [
        write_table(inv.videos, out / "video_matches.csv", VIDEO_COLUMNS, key=["video_id"]),
        write_table(inv.series, out / "series_inventory.csv", SERIES_INV_COLUMNS, key=["series_key"], decimals=HOURS),
        write_table(inv.missing, out / "series_missing_video.csv", SERIES_INV_COLUMNS, key=["series_key"], decimals=HOURS),
        write_table(inv.pilot_series, out / "pilot_korea_stage1_series.csv", SERIES_INV_COLUMNS, key=["series_key"],
                    decimals=HOURS),
        write_table(inv.summary, out / "inventory_summary.csv", SUMMARY_COLUMNS, key=["scope"], decimals=SUMMARY_HOURS),
        write_table(inv.gap, out / "gap_coverage.csv", GAP_COLUMNS, key=["scope"]),
        write_table(inv.sheet_vs_lp, out / "sheet_vs_liquipedia.csv", SHEET_VS_LP_COLUMNS, key=["event"]),
    ]  # fmt: skip


STATUS_COLUMNS = ["region_stage", "series", "one_source_series", "maps", "maps_with_replay", "maps_no_replay",
                  "series_no_replay", "links_to_review", "patch_day_series", "excluded_maps"]  # fmt: skip


def coverage_status(catalog_dir: str | Path) -> pd.DataFrame:
    """Coverage per region-stage from the written catalog (`owstudy-collect status`, task T034).

    - `maps`: played maps in scope (Clash and forfeit maps are counted in `excluded_maps`)
    - `maps_with_replay` / `maps_no_replay`: played maps whose series has / has no primary POV video
    - `links_to_review`: low-confidence video links not yet confirmed
    - `patch_day_series`: series played on a patch day (catalog/patch_day_series.csv)
    """
    from owstudy.collect.catalog.build import region_stage

    d = Path(catalog_dir)
    series = read_table(d / "series.csv", required=["series_id", "region", "stage", "sources", "status"])
    maps = read_table(d / "maps.csv", required=["map_id", "series_id", "status"])
    links = read_table(d / "video_links.csv", required=["video_id", "series_id", "status", "link_confidence",
                                                         "role", "confirmed"])  # fmt: skip
    patch_day = read_table(d / "patch_day_series.csv", required=["series_id"])

    series = series.assign(region_stage=[region_stage(r, s) for r, s in zip(series.region, series.stage)])
    rs_of = dict(zip(series.series_id, series.region_stage))
    with_replay = set(links[(links.role == "primary") & (links.status == "linked")].series_id)
    review = links[(links.status == "linked") & (links.link_confidence == "low") & (links.confirmed != "true")]
    maps = maps.assign(region_stage=maps.series_id.map(rs_of), replay=maps.series_id.isin(with_replay))
    rows = []
    for rs, g in series.groupby("region_stage"):
        m = maps[maps.region_stage == rs]
        played = m[m.status == "played"]
        ids = set(g.series_id)
        rows.append({
            "region_stage": rs, "series": len(g), "one_source_series": int((~g.sources.str.contains(";")).sum()),
            "maps": len(played), "maps_with_replay": int(played.replay.sum()),
            "maps_no_replay": int((~played.replay).sum()),
            "series_no_replay": int(sum(1 for s in g.series_id[g.status == "played"] if s not in with_replay)),
            "links_to_review": int(review.series_id.isin(ids).sum()),
            "patch_day_series": int(patch_day.series_id.isin(ids).sum()), "excluded_maps": len(m) - len(played),
        })  # fmt: skip
    return pd.DataFrame(rows, columns=STATUS_COLUMNS)


def run_inventory(reference_root: str | Path, aliases_path: str | Path, pilot: str) -> Inventory:
    """Build the inventory from the latest liquipedia, spreadsheet and youtube snapshots."""
    lp_dir = latest_snapshot("liquipedia", root=reference_root)
    sheet_dir = latest_snapshot("spreadsheet", root=reference_root)
    yt_dir = latest_snapshot("youtube", root=reference_root)
    with open(yt_dir / "obssojourn_videos.json", encoding="utf-8") as f:
        videos = json.load(f)["entries"]
    return build_inventory(
        read_table(lp_dir / "lp_series.csv", required=["series_key", "event", "part", "date", "team1", "team2",
                                                        "maps_played", "vod"]),
        read_table(sheet_dir / "sheet_series.csv", required=["series_key", "sheet", "team1", "team2", "abbr1", "abbr2"]),
        read_table(sheet_dir / "sheet_maps.csv", required=["series_key", "map_number"]),
        videos,
        AliasTable.load(aliases_path),
        pilot,
    )  # fmt: skip

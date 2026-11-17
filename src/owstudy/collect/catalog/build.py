"""The catalog: every series, map and lineup in scope, with stable IDs (task T031, FR-008).

Built from the latest Liquipedia and spreadsheet snapshots (no network). Writes
`data/interim/catalog/`:

- `series.csv`: one row per series. `series_id` is the slug of the Liquipedia match key, so it
  stays the same across snapshots. A series only the spreadsheet lists gets `sheet_<slug>` and
  `sources` names only the spreadsheet: that's the flag for "appears in one source".
- `maps.csv`: one row per map (`map_id = <series_id>-m<n>`), with the patch it was played on.
- `lineups.csv`: who was on each team for the series (Liquipedia; event roster when the match
  lists no players).
- `patch_day_series.csv`: series played on a patch day, for the researcher to check.

Also writes `data/interim/entities/teams.csv`, `players.csv` and `aliases_proposed.csv`
(name variants for the researcher to accept into the hand-curated `aliases.csv`, which this
module never writes). The OWCS Preseason Bootcamp is left out everywhere (FR-023a).

Patch rule (configs/collect/patches.yaml, patch_overrides.yaml): each map gets the latest patch
whose `live_date` is on or before the series' local date. On a patch day, series in a
`pre_patch_regions` region get the previous patch instead. Series listed under `series:` take
the patch given there.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from owstudy.collect.catalog.entities import (
    PROPOSAL_COLUMNS,
    AliasTable,
    map_id,
    normalize_alias,
    player_id,
    slug,
    team_id,
)
from owstudy.collect.catalog.inventory import sheet_tab_event
from owstudy.collect.catalog.link import BOOTCAMP_RE, TeamMatcher, parse_date, raw_key
from owstudy.collect.config import Patch, PatchOverrides
from owstudy.collect.io.tables import read_table, write_table
from owstudy.collect.refs.liquipedia import parse_batch, parse_lineups, response_files

SERIES_COLUMNS = ["series_id", "region", "stage", "phase", "round", "best_of", "start_utc", "local_date", "tz",
                  "team_a_id", "team_b_id", "score_a", "score_b", "status", "sources", "in_pilot"]  # fmt: skip
MAP_COLUMNS = ["map_id", "series_id", "map_number", "map_ref", "mode_id", "winner", "patch_id", "status"]
LINEUP_COLUMNS = ["series_id", "team_id", "player_id", "source"]
PATCH_DAY_COLUMNS = ["series_id", "local_date", "patch_id", "rule"]
TEAM_COLUMNS = ["team_id", "name"]
PLAYER_COLUMNS = ["player_id", "name", "liquipedia_page"]

SERIES_STATUS = ("played", "forfeit", "walkover")
MAP_STATUS = ("played", "clash_excluded", "forfeit")
FORFEIT_MARKS = {"FF", "W", "L", "DQ", "-"}

# Liquipedia time-zone abbreviations -> hours from UTC. "CST" on 2026 OWCS pages is China
# Standard Time; for NA events it would be US Central Standard Time (see utc_offset).
TZ_OFFSETS = {"KST": 9, "JST": 9, "CST": 8, "SGT": 8, "PHT": 8, "ICT": 7, "AEST": 10, "AEDT": 11,
              "CEST": 2, "CET": 1, "BST": 1, "GMT": 0, "UTC": 0, "EDT": -4, "EST": -5, "CDT": -5,
              "MDT": -6, "PDT": -7, "PST": -8}  # fmt: skip
ASIA_REGIONS = {"Korea", "Japan", "Pacific"}
INTERNATIONAL = "International"


# --- small helpers ---------------------------------------------------------------------


def split_event(event: str) -> tuple[str, str]:
    """Region-stage key -> (region, stage).

    'Asia/Stage 1/Korea' -> ('Korea', 'Stage 1'); 'NA/Stage 2' -> ('NA', 'Stage 2');
    'Asia/Stage 1' (the Asia playoffs) -> ('Asia', 'Stage 1'); 'Champions Clash' -> ('International', 'Champions Clash').
    """
    parts = event.split("/")
    if len(parts) == 3:
        return parts[2], parts[1]
    if len(parts) == 2 and parts[1].startswith("Stage"):
        return parts[0], parts[1]
    return INTERNATIONAL, event


def region_stage(region: str, stage: str) -> str:
    """(region, stage) -> region-stage key: the inverse of split_event."""
    if region == INTERNATIONAL:
        return stage
    if region in ASIA_REGIONS:
        return f"Asia/{stage}/{region}"
    return f"{region}/{stage}"


def is_bootcamp(text: str) -> bool:
    return bool(BOOTCAMP_RE.search(text))


def utc_offset(tz: str, region: str) -> int | None:
    if tz == "CST" and region == "NA":
        return -6
    return TZ_OFFSETS.get(tz)


def local_datetime(text: str) -> tuple[dt.date | None, dt.time | None]:
    """'2026-04-14 - 19:00' or 'March 21, 2026 - 15:10' -> (date, time). Time is None if absent."""
    day = parse_date(text)
    m = re.search(r" - (\d{1,2}):(\d{2})", str(text))
    return day, (dt.time(int(m.group(1)), int(m.group(2))) if m and day else None)


def start_utc(day: dt.date | None, time: dt.time | None, tz: str, region: str) -> str:
    """Local start time -> 'YYYY-MM-DDTHH:MM:SSZ', or '' when the time or time zone is unknown."""
    offset = utc_offset(tz, region)
    if day is None or time is None or offset is None:
        return ""
    local = dt.datetime.combine(day, time)
    return (local - dt.timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M:%SZ")


def round_name(sheet_phase: str) -> str:
    """Spreadsheet phase -> round name: 'Seeding Decider [Bo5]' -> 'Seeding Decider'."""
    return re.sub(r"\s*\[Bo\d+\]", "", sheet_phase or "").strip()


def best_of_from_phase(phase: str) -> str:
    m = re.search(r"\[Bo(\d+)\]", phase or "")
    return m.group(1) if m else ""


def series_id_of(series_key: str) -> str:
    return slug(series_key)


def sheet_series_id(sheet_key: str) -> str:
    return "sheet_" + slug(sheet_key)


def pre_patch_region(event: str) -> str:
    """The region matched against `pre_patch_regions`.

    'Asia/Stage 1/Korea' -> 'Korea'; 'Asia/Stage 1' (the shared Asia playoffs) -> 'Asia'.
    """
    return split_event(event)[0]


def assign_patch(
    local_date: dt.date | None,
    event: str,
    keys: Sequence[str],
    patches: Sequence[Patch],
    overrides: PatchOverrides,
) -> tuple[str, str | None]:
    """(patch_id, rule) for a series. `rule` is set only for patch-day or hand-set series.

    `keys` are the series' identifiers (Liquipedia key, series_id) checked against the hand-set
    list in patch_overrides.yaml.
    """
    for k in keys:
        if k in overrides.series:
            return overrides.series[k], "hand_set"
    if local_date is None:
        return "", None
    eligible = [p for p in patches if p.live_date <= local_date]
    if not eligible:
        return "", None
    latest = eligible[-1]
    if latest.live_date != local_date:
        return latest.patch_id, None
    if pre_patch_region(event) in overrides.pre_patch_regions:
        return (eligible[-2].patch_id if len(eligible) > 1 else ""), "pre_patch_region"
    return latest.patch_id, "new_patch"


def map_winner(winner_text: str) -> str:
    return {"1": "a", "2": "b", "0": "draw", "draw": "draw"}.get(str(winner_text).strip().lower(), "")


def _score_winner(s1: str, s2: str) -> str:
    try:
        a, b = float(s1), float(s2)
    except ValueError:
        return ""
    return "a" if a > b else "b" if b > a else "draw"


# --- team names -------------------------------------------------------------------------


class TeamNames:
    """Resolves team text from any source to a stable team ID.

    Uses the inventory's TeamMatcher (aliases.csv, Liquipedia names, spreadsheet abbreviations,
    close spellings), then maps the match key to an ID: an alias's stable ID when aliases.csv
    has the Liquipedia name, else `team:<slug of the Liquipedia name>`.
    """

    def __init__(self, lp_names: Iterable[str], aliases: AliasTable, sheet_abbrs: Iterable[tuple[str, str]] = ()):
        lp_names = [n for n in lp_names if n]
        self.aliases = aliases
        self.matcher = TeamMatcher(lp_names, aliases, list(sheet_abbrs))
        votes: dict[str, Counter] = {}
        shown: dict[str, Counter] = {}
        for n in lp_names:
            k = self.matcher.key(n)
            votes.setdefault(k, Counter())[self._id_for_name(n)] += 1
            shown.setdefault(k, Counter())[n] += 1
        # most common wins; ties go to the alphabetically first, so the result never depends on order
        self.key_to_id = {k: min(c, key=lambda i: (-c[i], i)) for k, c in votes.items()}
        self.display = {}
        for k, c in shown.items():
            self.display.setdefault(self.key_to_id[k], min(c, key=lambda n: (-c[n], n)))

    def _id_for_name(self, name: str) -> str:
        r = self.aliases.resolve("team", name)
        return r.stable_id if r.stable_id else team_id(name)

    def id_of(self, text: str) -> str | None:
        """Stable ID, or None if the text matches no Liquipedia team."""
        k = self.matcher.resolve(text)
        return self.key_to_id.get(k) if k else None

    def is_close_match(self, text: str) -> bool:
        """True when `text` resolved only through a close spelling, not an exact name or alias."""
        k = self.matcher.key(text)
        if k in self.key_to_id:
            return False
        return self.matcher.sheet_alias.get(k) not in self.key_to_id

    def id_or_new(self, text: str) -> str:
        return self.id_of(text) or self._id_for_name(text)


# --- the catalog -----------------------------------------------------------------------


@dataclass
class Catalog:
    """Every 2026 series (all events; `scoped` narrows to region-stages), maps, lineups and
    alias proposals. `series` also carries internal columns used for linking: `event`,
    `series_key`, `playoff`, `day`."""

    series: pd.DataFrame
    maps: pd.DataFrame
    lineups: pd.DataFrame
    patch_day: pd.DataFrame
    proposals: pd.DataFrame
    teams: pd.DataFrame
    players: pd.DataFrame
    names: TeamNames
    snapshots: dict[str, str] = field(default_factory=dict)

    def scoped(self, scope_keys: Sequence[str]) -> Catalog:
        keep = self.series[self.series.event.isin(scope_keys)]
        ids = set(keep.series_id)
        team_ids = set(keep.team_a_id) | set(keep.team_b_id)
        lineups = self.lineups[self.lineups.series_id.isin(ids)]
        return Catalog(
            series=keep, maps=self.maps[self.maps.series_id.isin(ids)], lineups=lineups,
            patch_day=self.patch_day[self.patch_day.series_id.isin(ids)],
            proposals=self.proposals[self.proposals.event.isin(scope_keys)],
            teams=self.teams[self.teams.team_id.isin(team_ids)],
            players=self.players[self.players.player_id.isin(set(lineups.player_id))],
            names=self.names, snapshots=self.snapshots,
        )  # fmt: skip


def _pair_sheet(lp: list[dict], sheet: list[dict]) -> dict[int, dict]:
    """Match spreadsheet series to Liquipedia series: same event and same two teams, paired in
    order (Liquipedia by date, spreadsheet by row). Returns lp index -> sheet row."""
    groups: dict[tuple, tuple[list, list]] = {}
    for i, s in enumerate(lp):
        groups.setdefault((s["event"], frozenset((s["team_a_id"], s["team_b_id"]))), ([], []))[0].append(i)
    for r in sheet:
        key = (r["event"], frozenset((r["team_a_id"], r["team_b_id"])))
        groups.setdefault(key, ([], []))[1].append(r)
    out = {}
    for lp_idx, rows in groups.values():
        lp_idx.sort(key=lambda i: (lp[i]["day"] or dt.date.max, lp[i]["series_key"]))
        rows.sort(key=lambda r: int(r["row"]))
        for i, r in zip(lp_idx, rows):
            out[i] = r
    return out


def build_catalog(
    lp_dir: str | Path,
    sheet_dir: str | Path,
    aliases: AliasTable,
    map_entities: pd.DataFrame,
    patches: Sequence[Patch],
    overrides: PatchOverrides,
    pilot: str,
) -> Catalog:
    """Build the catalog over every 2026 event from one Liquipedia and one spreadsheet snapshot."""
    lp_dir, sheet_dir = Path(lp_dir), Path(sheet_dir)
    lp_src, sheet_src = f"liquipedia:{lp_dir.name}", f"spreadsheet:{sheet_dir.name}"
    files = response_files(lp_dir)
    lp_series, lp_maps = parse_batch(files)
    lp_series = [s for s in lp_series if not is_bootcamp(s["event"])]
    sheet = read_table(sheet_dir / "sheet_series.csv", required=["series_key", "sheet", "row", "phase", "team1",
                                                                  "team2", "abbr1", "abbr2", "score1", "score2"])
    sheet = sheet[~sheet.sheet.map(is_bootcamp)]
    sheet_maps = read_table(sheet_dir / "sheet_maps.csv", required=["series_key", "map_number", "map_name",
                                                                     "score1", "score2"])

    names = TeamNames(
        [s["team1"] for s in lp_series] + [s["team2"] for s in lp_series], aliases,
        list(zip(sheet.abbr1, sheet.team1)) + list(zip(sheet.abbr2, sheet.team2)),
    )  # fmt: skip
    map_mode = dict(zip(map_entities.map_id, map_entities.mode_id))
    proposals: list[dict] = []

    # Liquipedia series
    maps_by_series: dict[str, list[dict]] = {}
    for m in lp_maps:
        maps_by_series.setdefault(m["series_key"], []).append(m)
    lp_rows = []
    for s in lp_series:
        marks = {s["opp_score1"].upper(), s["opp_score2"].upper()}
        n_maps = int(s["maps_played"])
        if "FF" in marks or "DQ" in marks:
            status = "forfeit"
        elif n_maps == 0 and marks & {"W", "L"}:
            status = "walkover"
        elif n_maps > 0:
            status = "played"
        else:
            continue  # not played (yet)
        day, time = local_datetime(s["date"])
        region, stage = split_event(s["event"])
        lp_rows.append({
            "series_key": s["series_key"], "series_id": series_id_of(s["series_key"]), "event": s["event"],
            "region": region, "stage": stage, "phase": "Regular Season" if s["part"] == "Regular Season" else "Playoffs",
            "playoff": s["part"] != "Regular Season", "best_of": s["bestof"],
            "start_utc": start_utc(day, time, s["tz"], region), "day": day,
            "local_date": day.isoformat() if day else "", "tz": s["tz"],
            "team_a_text": s["team1"], "team_b_text": s["team2"],
            "team_a_id": names.id_or_new(s["team1"]), "team_b_id": names.id_or_new(s["team2"]),
            "status": status, "locator": s["locator"],
        })  # fmt: skip

    # Spreadsheet series, paired with Liquipedia
    sheet_rows = []
    for r in sheet.to_dict(orient="records"):
        r = dict(r, event=sheet_tab_event(r["sheet"]))
        r["team_a_id"], r["team_b_id"] = names.id_or_new(r["team1"]), names.id_or_new(r["team2"])
        sheet_rows.append(r)
    paired = _pair_sheet(lp_rows, sheet_rows)
    paired_keys = {r["series_key"] for r in paired.values()}

    series, maps = [], []
    for i, s in enumerate(lp_rows):
        sh = paired.get(i)
        s["sources"] = ";".join([lp_src] + ([sheet_src] if sh else []))
        if not s["best_of"] and sh:
            s["best_of"] = best_of_from_phase(sh["phase"])
        # Liquipedia's "Playoffs" page also holds the seeding deciders and last-chance matches;
        # the spreadsheet names the round (e.g. "Seeding Decider", "Grand Finals").
        s["round"] = round_name(sh["phase"]) if sh else ""
        s["patch_id"], s["patch_rule"] = assign_patch(s["day"], s["event"], (s["series_key"], s["series_id"]),
                                                       patches, overrides)  # fmt: skip
        wins = Counter()
        for m in maps_by_series.get(s["series_key"], []):
            name = m["map_name"]
            ref = map_id(name)
            mode = map_mode.get(ref) or slug(m["mode"])
            forfeit = s["status"] == "forfeit" or {m["score1"].upper(), m["score2"].upper()} & FORFEIT_MARKS
            winner = map_winner(m["winner"])
            st = "forfeit" if forfeit else "clash_excluded" if mode == "clash" else "played"
            if st != "forfeit":
                wins[winner] += 1
            maps.append({"map_id": f"{s['series_id']}-m{m['map_number']}", "series_id": s["series_id"],
                         "map_number": int(m["map_number"]), "map_ref": ref, "mode_id": mode, "winner": winner,
                         "patch_id": s["patch_id"], "status": st})  # fmt: skip
        s["score_a"], s["score_b"] = ("", "") if s["status"] != "played" else (wins["a"], wins["b"])
        series.append(s)

    for r in sheet_rows:  # sheet-only series
        if r["series_key"] in paired_keys:
            continue
        region, stage = split_event(r["event"])
        sid = sheet_series_id(r["series_key"])
        rows = sheet_maps[sheet_maps.series_key == r["series_key"]].to_dict(orient="records")
        series.append({
            "series_key": r["series_key"], "series_id": sid, "event": r["event"], "region": region, "stage": stage,
            "phase": round_name(r["phase"]), "round": round_name(r["phase"]), "playoff": not re.search(
                r"round robin|regular|group|swiss", r["phase"], re.I),
            "best_of": best_of_from_phase(r["phase"]), "start_utc": "", "day": None, "local_date": "", "tz": "",
            "team_a_text": r["team1"], "team_b_text": r["team2"],
            "team_a_id": r["team_a_id"], "team_b_id": r["team_b_id"],
            "score_a": r["score1"], "score_b": r["score2"], "status": "played" if rows else "walkover",
            "sources": sheet_src, "patch_id": "", "patch_rule": None, "locator": r.get("locator", ""),
        })  # fmt: skip
        for m in rows:
            ref = map_id(m["map_name"])
            mode = map_mode.get(ref, "")
            maps.append({"map_id": f"{sid}-m{m['map_number']}", "series_id": sid, "map_number": int(m["map_number"]),
                         "map_ref": ref, "mode_id": mode, "winner": _score_winner(m["score1"], m["score2"]),
                         "patch_id": "", "status": "clash_excluded" if mode == "clash" else "played"})  # fmt: skip

    S = pd.DataFrame(series)
    S["in_pilot"] = S.event == pilot
    patch_day = S[S.patch_rule.notna()].rename(columns={"patch_rule": "rule"})[PATCH_DAY_COLUMNS]

    # Lineups (Liquipedia; event roster when the match has none)
    def roster_key(text: str) -> str:
        return names.id_of(text) or raw_key(text)

    sid_of = dict(zip(S.series_key, S.series_id))
    lineups, players = [], {}
    for r in parse_lineups(files, team_key=roster_key):
        sid = sid_of.get(r["series_key"])
        if sid is None:
            continue
        pid = player_id(r["player_page"])
        lineups.append({"series_id": sid, "team_id": names.id_or_new(r["team_text"]), "player_id": pid,
                        "source": r["source_kind"], "event": r["series_key"].split("|")[0],
                        "display": r["player_display"], "locator": r["locator"]})  # fmt: skip
        players.setdefault(pid, (r["player_display"], r["player_page"]))
    L = pd.DataFrame(lineups, columns=[*LINEUP_COLUMNS, "event", "display", "locator"])
    L = L.drop_duplicates(["series_id", "team_id", "player_id"]).reset_index(drop=True)

    proposals = _proposals(S, sheet_rows, L, names, aliases, lp_src, sheet_src)
    team_ids = sorted(set(S.team_a_id) | set(S.team_b_id))
    texts = {**dict(zip(S.team_b_id, S.team_b_text)), **dict(zip(S.team_a_id, S.team_a_text))}
    teams = pd.DataFrame([{"team_id": t, "name": names.display.get(t, texts.get(t, ""))} for t in team_ids],
                         columns=TEAM_COLUMNS)  # fmt: skip
    players_df = pd.DataFrame([{"player_id": p, "name": d, "liquipedia_page": pg} for p, (d, pg) in players.items()],
                              columns=PLAYER_COLUMNS)  # fmt: skip
    return Catalog(series=S, maps=pd.DataFrame(maps, columns=MAP_COLUMNS), lineups=L, patch_day=patch_day,
                   proposals=proposals, teams=teams, players=players_df, names=names,
                   snapshots={"liquipedia": lp_dir.name, "spreadsheet": sheet_dir.name})  # fmt: skip


def _proposals(S, sheet_rows, L, names: TeamNames, aliases: AliasTable, lp_src: str, sheet_src: str) -> pd.DataFrame:
    """Name variants worth adding to aliases.csv, for the researcher to accept or reject.

    Team: Liquipedia spellings that differ from the team's usual name, spreadsheet names and
    abbreviations. Player: display names that differ from the Liquipedia page name. Names
    aliases.csv already has, and a team's own usual name, are skipped.
    """
    from rapidfuzz import fuzz

    known = {(a.entity_type, a.alias) for a in aliases.entries()}
    out: dict[tuple, dict] = {}

    def add(entity_type, text, sid, score, seen_in, seen_at, event):
        norm = normalize_alias(text)
        if not norm or (entity_type, norm) in known:
            return
        if entity_type == "team" and norm == normalize_alias(names.display.get(sid, "")):
            return
        out.setdefault((entity_type, norm, sid), {
            "alias": text, "entity_type": entity_type, "candidate_stable_id": sid, "score": float(score),
            "seen_in": seen_in, "seen_at": seen_at, "event": event,
        })  # fmt: skip

    for s in S.to_dict(orient="records"):
        if lp_src not in s["sources"]:
            continue
        for side in ("a", "b"):
            add("team", s[f"team_{side}_text"], s[f"team_{side}_id"], 100.0, "liquipedia", s["locator"], s["event"])
    for r in sheet_rows:
        loc = r.get("locator") or f"{r['sheet']}!{r['row']}"
        for side, n in (("a", "1"), ("b", "2")):
            sid, full = r[f"team_{side}_id"], r[f"team{n}"]
            score = 100.0 if not names.is_close_match(full) else float(
                fuzz.ratio(raw_key(full), raw_key(names.display.get(sid, full))))
            add("team", full, sid, round(score, 1), "spreadsheet", loc, r["event"])
            if r[f"abbr{n}"]:
                add("team", r[f"abbr{n}"], sid, round(score, 1), "spreadsheet", loc, r["event"])
    for r in L.to_dict(orient="records"):
        add("player", r["display"], r["player_id"], 100.0, "liquipedia", r["locator"], r["event"])
    rows = [r for r in out.values() if not (r["entity_type"] == "player" and player_id(r["alias"]) == r["candidate_stable_id"])]
    return pd.DataFrame(rows, columns=[*PROPOSAL_COLUMNS, "event"])


@dataclass
class CatalogRun:
    catalog: Catalog  # scoped
    links: pd.DataFrame  # scoped, LINK_COLUMNS (+ title, event_text)
    paths: list[Path]


def run_catalog(data_dir: str | Path, cfg, scope_keys: Sequence[str]) -> CatalogRun:
    """`catalog build`: read the latest snapshots, build the catalog, link the channel's videos,
    and write the scoped results. No network."""
    from owstudy.collect.catalog.link import LINK_COLUMNS, in_scope_links, link_videos
    from owstudy.collect.config import load_patch_overrides, load_patches, load_video_overrides
    from owstudy.collect.refs.snapshot import latest_snapshot
    from owstudy.collect.refs.youtube_list import load_videos

    data = Path(data_dir)
    ref = data / "raw" / "reference"
    entities = data / "interim" / "entities"
    config_dir = Path(cfg.source_path).parent
    patches = load_patches(config_dir / "patches.yaml")
    aliases = AliasTable.load(entities / "aliases.csv")
    full = build_catalog(
        latest_snapshot("liquipedia", root=ref), latest_snapshot("spreadsheet", root=ref), aliases,
        read_table(entities / "maps.csv", required=["map_id", "mode_id"]), patches,
        load_patch_overrides(config_dir / "patch_overrides.yaml", patches), cfg.scope.pilot,
    )  # fmt: skip
    yt_dir = latest_snapshot("youtube", root=ref)
    from owstudy.collect.catalog.link import VIDEO_MAP_COLUMNS, video_maps
    from owstudy.collect.refs.youtube_details import load_details

    details = load_details(ref)
    links = link_videos(full, load_videos(yt_dir), aliases, cfg,
                        load_video_overrides(config_dir / "video_overrides.yaml"), details)  # fmt: skip
    full.snapshots["youtube"] = yt_dir.name
    cat = full.scoped(scope_keys)
    links = in_scope_links(links, set(cat.series.series_id), scope_keys)
    catalog_dir = data / "interim" / "catalog"
    paths = write_catalog(cat, catalog_dir, entities)
    paths.append(write_table(links[LINK_COLUMNS], catalog_dir / "video_links.csv", LINK_COLUMNS, key=["video_id"]))
    paths.append(write_table(video_maps(links, details, cat, aliases), catalog_dir / "video_maps.csv",
                             VIDEO_MAP_COLUMNS, key=["video_id", "order"]))  # fmt: skip
    return CatalogRun(cat, links, paths)


def write_catalog(cat: Catalog, catalog_dir: str | Path, entities_dir: str | Path) -> list[Path]:
    """Write a (scoped) catalog. Never touches aliases.csv."""
    out, ent = Path(catalog_dir), Path(entities_dir)
    return [
        write_table(cat.series[SERIES_COLUMNS], out / "series.csv", SERIES_COLUMNS, key=["series_id"]),
        write_table(cat.maps, out / "maps.csv", MAP_COLUMNS, key=["series_id", "map_number"]),
        write_table(cat.lineups[LINEUP_COLUMNS], out / "lineups.csv", LINEUP_COLUMNS,
                    key=["series_id", "team_id", "player_id"]),
        write_table(cat.patch_day, out / "patch_day_series.csv", PATCH_DAY_COLUMNS, key=["series_id"]),
        write_table(cat.teams, ent / "teams.csv", TEAM_COLUMNS, key=["team_id"]),
        write_table(cat.players, ent / "players.csv", PLAYER_COLUMNS, key=["player_id"]),
        write_table(cat.proposals[list(PROPOSAL_COLUMNS)], ent / "aliases_proposed.csv", PROPOSAL_COLUMNS,
                    key=["entity_type", "alias", "candidate_stable_id"], decimals={"score": 1}),
    ]  # fmt: skip

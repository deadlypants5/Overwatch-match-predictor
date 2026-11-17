"""Read Liquipedia page sources (ported from scripts/inventory/parse_lp.py).

Input: saved MediaWiki API responses (`action=query&prop=revisions`), one or more JSON files.
Output: one row per series (`{{Match}}` block with two opponents), one per played map, and the
team lineups for each series. Every record carries a `locator`: `<page title>@<revision>#match<n>`.

Lineups: a `{{Match}}` block can list players under each opponent. When it doesn't (the usual
case in 2026), the team's event roster from the event page's `{{TeamParticipants}}` block is
used instead (`source_kind = event_roster`). Staff (`type=staff`) are left out.

Downloading new pages (`fetch`) waits for the Liquipedia API key (task T028).
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

SERIES_COLUMNS = ["series_key", "event", "part", "date", "tz", "team1", "team2", "bestof",
                  "maps_played", "vod", "page_rev", "opp_score1", "opp_score2", "locator"]  # fmt: skip
MAPS_COLUMNS = ["series_key", "map_number", "map_name", "mode", "score1", "score2", "winner",
                "ban1", "ban2", "map_vod", "locator"]  # fmt: skip
LINEUP_COLUMNS = ["series_key", "team_text", "player_page", "player_display", "source_kind", "locator"]
LINEUP_KINDS = ("match", "event_roster")

EVENT_PREFIX = "Overwatch Champions Series/2026/"


def blocks(text: str, start: str) -> Iterator[str]:
    """Balanced `{{...}}` blocks that begin with `start`."""
    i = 0
    while (i := text.find(start, i)) != -1:
        depth, j = 0, i
        while j < len(text):
            if text.startswith("{{", j):
                depth += 1
                j += 2
                continue
            if text.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    break
                continue
            j += 1
        yield text[i:j]
        i = j


def field(block: str, name: str) -> str:
    m = re.search(r"\|\s*" + name + r"\s*=\s*([^|\n}]*)", block)
    return m.group(1).strip() if m else ""


def event_of(title: str) -> str:
    """'Overwatch Champions Series/2026/Asia/Stage 1/Korea/Regular Season' -> 'Asia/Stage 1/Korea'."""
    return title.replace(EVENT_PREFIX, "").replace("/Regular Season", "").replace("/Group Stage", "")


def _pages(json_files: Sequence[str | Path]) -> Iterator[dict]:
    for f in json_files:
        with open(f, encoding="utf-8") as fh:
            data = json.load(fh)
        yield from data["query"]["pages"].values()


def _page_text(p: dict) -> tuple[str, str, dict]:
    rev = p.get("revisions", [{}])[0]
    text = rev.get("slots", {}).get("main", {}).get("*", "")
    return text, str(rev.get("revid") or rev.get("timestamp", "")), rev


def _matches(json_files: Sequence[str | Path]) -> Iterator[tuple[dict, str, str, str, int, str, list[str]]]:
    """(page, revision ref, event, part, n, match block, opponent blocks) for each two-team match.

    `n` counts every `{{Match}}` block on the page, so keys don't move when an empty
    placeholder match elsewhere on the page is filled in later.
    """
    for p in _pages(json_files):
        text, rev_ref, _ = _page_text(p)
        part = "Regular Season" if p["title"].endswith(("Regular Season", "Group Stage")) else "Main/Playoffs"
        event = event_of(p["title"])
        for n, b in enumerate(blocks(text, "{{Match\n"), 1):
            opps = list(blocks(b, "{{TeamOpponent|"))
            if len(opps) < 2:
                continue
            yield p, rev_ref, event, part, n, b, opps


def _opp_name(opp_block: str) -> str:
    m = re.match(r"\{\{TeamOpponent\|([^}|]*)", opp_block)
    return m.group(1).strip() if m else ""


def parse_batch(json_files: Sequence[str | Path]) -> tuple[list[dict], list[dict]]:
    """Series and played maps from saved API responses."""
    series: list[dict] = []
    maps: list[dict] = []
    for p, rev_ref, event, stage_part, n, b, opps in _matches(json_files):
        _, _, rev = _page_text(p)
        key = f"{event}|{stage_part}|{n}"
        locator = f"{p['title']}@{rev_ref}#match{n}"
        date = field(b, "date")
        played = 0
        for k, mb in enumerate(blocks(b, "{{Map|"), 1):
            winner = field(mb, "winner")
            if not field(mb, "map") or winner == "":
                continue
            played += 1
            maps.append({
                "series_key": key, "map_number": k, "map_name": field(mb, "map"), "mode": field(mb, "mode"),
                "score1": field(mb, "score1"), "score2": field(mb, "score2"), "winner": winner,
                "ban1": field(mb, "t1b1"), "ban2": field(mb, "t2b1"), "map_vod": field(mb, "vod"),
                "locator": f"{locator}/map{k}",
            })  # fmt: skip
        tz = re.search(r"Abbr/(\w+)", date)
        series.append({
            "series_key": key, "event": event, "part": stage_part,
            "date": re.sub(r"\s*\{\{.*", "", date), "tz": tz.group(1) if tz else "",
            "team1": _opp_name(opps[0]), "team2": _opp_name(opps[1]), "bestof": field(b, "bestof"),
            "maps_played": played, "vod": field(b, "vod"), "page_rev": rev.get("timestamp", ""),
            "opp_score1": field(opps[0], "score"), "opp_score2": field(opps[1], "score"),
            "locator": locator,
        })  # fmt: skip
    return series, maps


def _persons(block: str) -> Iterator[tuple[str, str]]:
    """(page, display name) for each player `{{Person|...}}` in a block. Staff are left out."""
    for pb in blocks(block, "{{Person|"):
        if field(pb, "type").lower() == "staff":
            continue
        m = re.match(r"\{\{Person\|([^|}]*)", pb)
        display = m.group(1).strip() if m else ""
        if display:
            yield field(pb, "link") or display, display


def parse_rosters(json_files: Sequence[str | Path]) -> dict[str, list[dict]]:
    """Event rosters from `{{TeamParticipants}}`: event -> rows of team_text, player_page,
    player_display, locator."""
    out: dict[str, list[dict]] = {}
    for p in _pages(json_files):
        text, rev_ref, _ = _page_text(p)
        event = event_of(p["title"])
        for tp in blocks(text, "{{TeamParticipants"):
            for ob in blocks(tp, "{{Opponent|"):
                m = re.match(r"\{\{Opponent\|([^|}\n]*)", ob)
                team = m.group(1).strip() if m else ""
                if not team:
                    continue
                for page, display in _persons(ob):
                    out.setdefault(event, []).append({
                        "team_text": team, "player_page": page, "player_display": display,
                        "locator": f"{p['title']}@{rev_ref}#roster/{team}",
                    })  # fmt: skip
    return out


def _team_key(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def parse_lineups(json_files: Sequence[str | Path], team_key: Callable[[str], str] | None = None) -> list[dict]:
    """Lineup rows per series: the players listed in the match, else the team's event roster.

    `team_key` decides which roster team a match opponent is (default: same letters and digits,
    ignoring case). The catalog passes its alias-aware team resolver, so abbreviations match too.
    """
    team_key = team_key or _team_key
    json_files = list(json_files)
    rosters = parse_rosters(json_files)
    rows: list[dict] = []
    for p, rev_ref, event, part, n, _b, opps in _matches(json_files):
        key = f"{event}|{part}|{n}"
        locator = f"{p['title']}@{rev_ref}#match{n}"
        for opp in opps:
            team = _opp_name(opp)
            in_match = list(_persons(opp))
            if in_match:
                rows += [{"series_key": key, "team_text": team, "player_page": pg, "player_display": dp,
                          "source_kind": "match", "locator": locator} for pg, dp in in_match]  # fmt: skip
                continue
            want, seen = team_key(team), set()
            for r in rosters.get(event, []):
                if team_key(r["team_text"]) == want and r["player_page"] not in seen:
                    seen.add(r["player_page"])
                    rows.append({"series_key": key, "team_text": team, "player_page": r["player_page"],
                                 "player_display": r["player_display"], "source_kind": "event_roster",
                                 "locator": r["locator"]})  # fmt: skip
    return rows


def response_files(snapshot_folder: str | Path) -> list[Path]:
    """Saved API responses in a snapshot: `responses/*.json`, or (older snapshots) the `*.json`
    files next to snapshot.json."""
    folder = Path(snapshot_folder)
    files = sorted((folder / "responses").glob("*.json"))
    return files or sorted(f for f in folder.glob("*.json") if f.name != "snapshot.json")


def write_lp_tables(folder: str | Path, series: list[dict], maps: list[dict], lineups: list[dict] | None = None) -> None:
    from owstudy.collect.io.tables import write_table

    folder = Path(folder)
    write_table(series, folder / "lp_series.csv", SERIES_COLUMNS, key=["series_key"])
    write_table(maps, folder / "lp_maps.csv", MAPS_COLUMNS, key=["series_key", "map_number"])
    if lineups is not None:
        write_table(lineups, folder / "lp_lineups.csv", LINEUP_COLUMNS, key=["series_key", "team_text", "player_page"])

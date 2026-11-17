"""Read Liquipedia page sources (ported from scripts/inventory/parse_lp.py).

Input: saved MediaWiki API responses (`action=query&prop=revisions`), one or more JSON files.
Output: one row per series (`{{Match}}` block with two opponents) and one per played map.
Every record carries a `locator`: `<page title>@<revision>#match<n>`.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from pathlib import Path

SERIES_COLUMNS = ["series_key", "event", "part", "date", "tz", "team1", "team2", "bestof",
                  "maps_played", "vod", "page_rev", "locator"]  # fmt: skip
MAPS_COLUMNS = ["series_key", "map_number", "map_name", "mode", "score1", "score2", "winner",
                "ban1", "ban2", "map_vod", "locator"]  # fmt: skip

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


def parse_batch(json_files: Sequence[str | Path]) -> tuple[list[dict], list[dict]]:
    """Series and played maps from saved API responses."""
    series: list[dict] = []
    maps: list[dict] = []
    for p in _pages(json_files):
        rev = p.get("revisions", [{}])[0]
        text = rev.get("slots", {}).get("main", {}).get("*", "")
        rev_ref = str(rev.get("revid") or rev.get("timestamp", ""))
        stage_part = "Regular Season" if p["title"].endswith(("Regular Season", "Group Stage")) else "Main/Playoffs"
        event = event_of(p["title"])
        for n, b in enumerate(blocks(text, "{{Match\n"), 1):
            ops = re.findall(r"opponent\d=\{\{TeamOpponent\|([^}|]*)", b)
            if len(ops) < 2:
                continue
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
                "team1": ops[0].strip(), "team2": ops[1].strip(), "bestof": field(b, "bestof"),
                "maps_played": played, "vod": field(b, "vod"), "page_rev": rev.get("timestamp", ""),
                "locator": locator,
            })  # fmt: skip
    return series, maps


def write_lp_tables(folder: str | Path, series: list[dict], maps: list[dict]) -> None:
    from owstudy.collect.io.tables import write_table

    folder = Path(folder)
    write_table(series, folder / "lp_series.csv", SERIES_COLUMNS, key=["series_key"])
    write_table(maps, folder / "lp_maps.csv", MAPS_COLUMNS, key=["series_key", "map_number"])

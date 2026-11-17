"""Read the OWCS 2026 Hero Bans & Metas spreadsheet (ported from scripts/inventory/parse_sheet.py).

Each tab is one region-stage. A series block sits around its "abbreviation row" (team
abbreviations in C and J, series score in G and H). Below it, map rows list map name (F) and
map scores (D, J). To the right, one 17-column block per map holds each team's ban 10 rows
below the abbreviation row (team 1 in column Q, team 2 in column U, shifted 17 columns per map).

Every record carries a `locator` (`<tab>!<row>` or `<tab>!<cell>`) pointing back to the sheet.
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Any

from openpyxl.utils import get_column_letter

SKIP_TABS = re.compile(r"Landing|Index|Hero Bans|Regional Maps|LAN Maps|Self-Check|Copy of|Bootcamp", re.I)

SERIES_COLUMNS = ["series_key", "sheet", "row", "phase", "label", "team1", "team2", "abbr1", "abbr2",
                  "score1", "score2", "n_maps", "locator"]  # fmt: skip
MAPS_COLUMNS = ["series_key", "map_number", "map_name", "score1", "score2", "locator"]
BANS_COLUMNS = ["series_key", "map_number", "team_text", "hero_text", "locator"]
MAP_SCORE_DECIMALS = {"score1": 2, "score2": 2}

# Column numbers (A = 1)
COL_ABBR1, COL_SCORE1, COL_SCORE2, COL_ABBR2 = 3, 7, 8, 10
COL_MAP_SCORE1, COL_MAP_NAME, COL_MAP_SCORE2 = 4, 6, 10
COL_TEAM_NAME = 14
BAN_BLOCK_WIDTH, BAN_ROW_OFFSET, COL_BAN1, COL_BAN2, COL_BLOCK_MAP = 17, 10, 17, 21, 24


def _num(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _strip_record(text: str) -> str:
    """'Poker Face [0-0]' -> 'Poker Face'."""
    return re.sub(r"\s*\[.*?\]\s*$", "", text)


def _cell(tab: str, row: int, col: int) -> str:
    return f"{tab}!{get_column_letter(col)}{row}"


def parse_workbook(xlsx_path: str | Path) -> tuple[list[dict], list[dict], list[dict]]:
    """Every series, map and ban in the workbook, as plain rows."""
    import openpyxl

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    series_rows: list[dict] = []
    map_rows: list[dict] = []
    ban_rows: list[dict] = []
    for ws in wb.worksheets:
        if SKIP_TABS.search(ws.title):
            continue
        grid = {}
        for row in ws.iter_rows():
            for c in row:
                v = getattr(c, "value", None)
                if v not in (None, ""):
                    grid[(c.row, c.column)] = v
        if not grid:
            continue
        maxr = max(r for r, _ in grid)

        def g(r: int, c: int) -> Any:
            return grid.get((r, c))

        for r in range(1, maxr + 1):
            a1, s1, s2, a2 = g(r, COL_ABBR1), g(r, COL_SCORE1), g(r, COL_SCORE2), g(r, COL_ABBR2)
            if not (isinstance(a1, str) and isinstance(a2, str) and _num(s1) and _num(s2)):
                continue
            label = g(r - 2, COL_ABBR1) or ""
            phase = g(r - 3, COL_ABBR1) or ""
            t1 = _strip_record(str(g(r - 1, COL_TEAM_NAME) or a1))
            t2 = a2
            for rr in range(r + 5, r + 18):
                v = g(rr, COL_TEAM_NAME)
                if isinstance(v, str) and v.endswith("]"):
                    t2 = _strip_record(v)
                    break
            maps = []
            for rr in range(r + 3, r + 16):
                m, d, j = g(rr, COL_MAP_NAME), g(rr, COL_MAP_SCORE1), g(rr, COL_MAP_SCORE2)
                if isinstance(m, str) and (_num(d) or _num(j)):
                    maps.append((rr, m, d, j))
            sid = f"{ws.title}|{r}"
            series_rows.append({
                "series_key": sid, "sheet": ws.title, "row": r, "phase": phase,
                "label": str(label).replace("\n", " "), "team1": t1, "team2": t2, "abbr1": a1, "abbr2": a2,
                "score1": int(s1), "score2": int(s2), "n_maps": len(maps), "locator": f"{ws.title}!{r}",
            })  # fmt: skip
            for i, (rr, m, d, j) in enumerate(maps, 1):
                map_rows.append({"series_key": sid, "map_number": i, "map_name": m,
                                 "score1": d, "score2": j, "locator": _cell(ws.title, rr, COL_MAP_NAME)})  # fmt: skip
                shift = (i - 1) * BAN_BLOCK_WIDTH
                ban_row = r + BAN_ROW_OFFSET
                for team, col in ((t1, COL_BAN1 + shift), (t2, COL_BAN2 + shift)):
                    hero = g(ban_row, col)
                    if isinstance(hero, str) and hero.strip():
                        ban_rows.append({"series_key": sid, "map_number": i, "team_text": team,
                                         "hero_text": hero.strip(), "locator": _cell(ws.title, ban_row, col)})  # fmt: skip
    return series_rows, map_rows, ban_rows


def write_sheet_tables(folder: str | Path, series: list[dict], maps: list[dict], bans: list[dict]) -> None:
    from owstudy.collect.io.tables import write_table

    folder = Path(folder)
    write_table(series, folder / "sheet_series.csv", SERIES_COLUMNS, key=["sheet", "row"])
    write_table(maps, folder / "sheet_maps.csv", MAPS_COLUMNS, key=["series_key", "map_number"],
                decimals=MAP_SCORE_DECIMALS)  # fmt: skip
    write_table(bans, folder / "sheet_bans.csv", BANS_COLUMNS, key=["series_key", "map_number", "locator"])


def import_sheet(xlsx_path: str | Path, snapshot_folder: str | Path, retrieved_at: str | None = None) -> dict[str, int]:
    """Parse the workbook into a new snapshot folder (sheet_series, sheet_maps, sheet_bans,
    snapshot.json). Returns the row counts."""
    from owstudy.collect.io.manifest import snapshot_json

    series, maps, bans = parse_workbook(xlsx_path)
    write_sheet_tables(snapshot_folder, series, maps, bans)
    snapshot_json(
        snapshot_folder, "spreadsheet", retrieved_at or dt.date.today().isoformat(),
        "owstudy-collect refs import-sheet", description=f"parsed from {Path(xlsx_path).name}",
    )  # fmt: skip
    return {"series": len(series), "maps": len(maps), "bans": len(bans)}

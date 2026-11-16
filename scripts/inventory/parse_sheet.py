"""Exploratory parser: list every series/map in the OWCS 2026 spreadsheet.

Usage: python -I parse_sheet.py <xlsx> <out_dir>
Writes sheet_series.csv and sheet_maps.csv.
"""
import csv, re, sys
from pathlib import Path
import openpyxl

xlsx, out = sys.argv[1], Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
SKIP = re.compile(r"Landing|Index|Hero Bans|Regional Maps|LAN Maps|Self-Check|Copy of|Bootcamp", re.I)

wb = openpyxl.load_workbook(xlsx, read_only=True, data_only=True)
series_rows, map_rows = [], []
num = lambda v: isinstance(v, (int, float))

for ws in wb.worksheets:
    if SKIP.search(ws.title):
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
    g = lambda r, c: grid.get((r, c))
    # columns: C=3 D=4 F=6 G=7 H=8 J=10 N=14
    for r in range(1, maxr + 1):
        a1, s1, s2, a2 = g(r, 3), g(r, 7), g(r, 8), g(r, 10)
        if not (isinstance(a1, str) and isinstance(a2, str) and num(s1) and num(s2)):
            continue
        label = g(r - 2, 3) or ""
        phase = g(r - 3, 3) or ""
        t1 = re.sub(r"\s*\[.*?\]\s*$", "", str(g(r - 1, 14) or a1))
        t2 = a2
        for rr in range(r + 5, r + 18):
            v = g(rr, 14)
            if isinstance(v, str) and v.endswith("]"):
                t2 = re.sub(r"\s*\[.*?\]\s*$", "", v)
                break
        maps = []
        for rr in range(r + 3, r + 16):
            m, d, j = g(rr, 6), g(rr, 4), g(rr, 10)
            if isinstance(m, str) and (num(d) or num(j)):
                maps.append((m, d, j))
        sid = f"{ws.title}|{r}"
        series_rows.append(dict(series_key=sid, sheet=ws.title, row=r, phase=phase,
                                label=str(label).replace("\n", " "), team1=t1, team2=t2,
                                abbr1=a1, abbr2=a2, score1=int(s1), score2=int(s2),
                                n_maps=len(maps)))
        for i, (m, d, j) in enumerate(maps, 1):
            map_rows.append(dict(series_key=sid, map_number=i, map_name=m, score1=d, score2=j))

for name, rows in (("sheet_series.csv", series_rows), ("sheet_maps.csv", map_rows)):
    with open(out / name, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
print(len(series_rows), "series,", len(map_rows), "maps")

"""Exploratory parser: list every match/map in saved Liquipedia batch JSON files.

Usage: python -I parse_lp.py <out_dir> <batch.json>...
Writes lp_series.csv and lp_maps.csv.
"""
import csv, json, re, sys
from pathlib import Path

out = Path(sys.argv[1]); files = sys.argv[2:]

def blocks(text, start):
    """Yield balanced {{...}} blocks beginning with `start`."""
    i = 0
    while (i := text.find(start, i)) != -1:
        depth, j = 0, i
        while j < len(text):
            if text.startswith("{{", j): depth += 1; j += 2; continue
            if text.startswith("}}", j):
                depth -= 1; j += 2
                if depth == 0: break
                continue
            j += 1
        yield text[i:j]; i = j

def field(b, name):
    m = re.search(r"\|\s*" + name + r"\s*=\s*([^|\n}]*)", b)
    return m.group(1).strip() if m else ""

def event_of(title):
    t = title.replace("Overwatch Champions Series/2026/", "").replace("/Regular Season", "").replace("/Group Stage", "")
    return t

series, maps = [], []
for f in files:
    d = json.load(open(f, encoding="utf-8"))
    for p in d["query"]["pages"].values():
        text = p.get("revisions", [{}])[0].get("slots", {}).get("main", {}).get("*", "")
        stage_part = "Regular Season" if p["title"].endswith(("Regular Season", "Group Stage")) else "Main/Playoffs"
        for n, b in enumerate(blocks(text, "{{Match\n"), 1):
            ops = re.findall(r"opponent\d=\{\{TeamOpponent\|([^}|]*)", b)
            if len(ops) < 2:
                continue
            date = field(b, "date")
            vod = field(b, "vod")
            key = f"{event_of(p['title'])}|{stage_part}|{n}"
            mlist = list(blocks(b, "{{Map|"))
            played = 0
            for k, mb in enumerate(mlist, 1):
                w = field(mb, "winner")
                if not field(mb, "map") or w == "":
                    continue
                played += 1
                maps.append(dict(series_key=key, map_number=k, map_name=field(mb, "map"),
                                 mode=field(mb, "mode"), score1=field(mb, "score1"),
                                 score2=field(mb, "score2"), winner=w,
                                 ban1=field(mb, "t1b1"), ban2=field(mb, "t2b1"),
                                 map_vod=field(mb, "vod")))
            series.append(dict(series_key=key, event=event_of(p["title"]), part=stage_part,
                               date=re.sub(r"\s*\{\{.*", "", date), tz=(re.search(r"Abbr/(\w+)", date) or [None, ""])[1],
                               team1=ops[0].strip(), team2=ops[1].strip(), bestof=field(b, "bestof"),
                               maps_played=played, vod=vod, page_rev=p["revisions"][0]["timestamp"]))

out.mkdir(parents=True, exist_ok=True)
for name, rows in (("lp_series.csv", series), ("lp_maps.csv", maps)):
    with open(out / name, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print(len(series), "series,", len(maps), "maps played")

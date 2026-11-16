"""Exploratory footage inventory: match ObsSojourn POV videos to 2026 Liquipedia series.

Usage: python -I inventory.py <videos.json> <lp_series.csv> <lp_maps.csv> <sheet_series.csv> <out_dir>
"""
import csv, json, re, sys, datetime as dt, difflib, collections
from pathlib import Path
import pandas as pd

vid_f, lps_f, lpm_f, sh_f, out = sys.argv[1:6]
out = Path(out); out.mkdir(parents=True, exist_ok=True)

# ---------- Liquipedia series ----------
lp = pd.read_csv(lps_f)
lp = lp[lp.maps_played > 0].copy()
def pdate(s):
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", str(s)).split(" - ")[0].strip()
    m = re.match(r"\d{4}-\d{2}-\d{2}", s)
    if m: s = m.group(0)
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try: return dt.datetime.strptime(s, fmt).date()
        except ValueError: pass
    return None
lp["d"] = lp.date.map(pdate)
lpm = pd.read_csv(lpm_f)

def norm(t):
    t = str(t).lower().replace("ø", "o").replace("rode ", "")
    t = re.sub(r"\b(esports|gaming|team)\b", "", t)
    t = re.sub(r"[^a-z0-9]", "", t)
    return LP_CANON.get(t, t)
LP_CANON = {"ag": "allgamers", "jdg": "jd", "nyamgaming": "nyam"}

sheet = pd.read_csv(sh_f)
alias = {}
for _, r in sheet.iterrows():          # sheet abbreviations -> full names
    alias[norm(r.abbr1)] = norm(r.team1); alias[norm(r.abbr2)] = norm(r.team2)
alias.update({norm("Onside"): norm("ONSIDE Gaming"), norm("ZETA"): norm("ZETA Division"),
              norm("Falcons"): norm("Team Falcons"), norm("CR"): norm("Crazy Raccoon"),
              norm("All Gamers Global"): norm("All Gamers"), norm("AG.AL"): norm("All Gamers"),
              norm("4 Angry Men"): norm("Four Angry Men"), norm("Nightmare"): norm("NTMR")})
lp_teams = sorted(set(map(norm, lp.team1)) | set(map(norm, lp.team2)))
def team_id(t):
    n = norm(t)
    if n not in lp_teams and alias.get(n) in lp_teams: n = alias[n]
    if n in lp_teams: return n
    m = difflib.get_close_matches(n, lp_teams, n=1, cutoff=0.8)
    return m[0] if m else None
lp["k1"] = lp.team1.map(norm); lp["k2"] = lp.team2.map(norm)

# event hint -> Liquipedia event prefix
def event_hint(ev):
    e = ev.lower()
    reg = (("korea" if re.search(r"korea|\bkor\b", e) else
            "japan" if re.search(r"japan|\bjpn\b", e) else
            "pacific" if re.search(r"pacific|\bpac\b", e) else
            "china" if re.search(r"china|\bcn\b", e) else
            "emea" if "emea" in e else
            "na" if re.search(r"\bna\b|north america", e) else
            "midseason" if "midseason" in e else
            "clash" if "clash" in e else
            "asia" if "asia" in e else None))
    st = re.search(r"stage\s*(\d)|\bs(\d)\b", e)
    return reg, (st.group(1) or st.group(2)) if st else None
def lp_event_ok(event, reg, st):
    e = event.lower()
    if reg is None: return True
    want = {"korea": "korea", "japan": "japan", "pacific": "pacific", "china": "china/", "emea": "emea/",
            "na": "na/", "midseason": "midseason", "clash": "champions clash", "asia": "asia/stage"}[reg]
    if reg == "asia" and e.count("/") != 1: return False
    return want in e and (st is None or f"stage {st}" in e)

PHASE = re.compile(r"grand final|final|semifinal|quarterfinal|playoff|upper|lower|seeding|round robin|regular season|group|decider|road to", re.I)

# ---------- videos ----------
vids = json.load(open(vid_f, encoding="utf-8"))["entries"]
rows = []
for v in vids:
    title = v.get("title") or ""
    ts = v.get("timestamp")
    up = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date() if ts else None
    m = re.match(r"\s*\[\s*([^\]]+?)\s*\]\s*(.*)", title)
    player, rest = (m.group(1), m.group(2)) if m else ("", title)
    parts = [p.strip() for p in rest.split("|")]
    event = parts[-1] if len(parts) > 1 else ""
    pair = None
    for p in parts:
        mm = re.search(r"(.+?)\s+vs\.?\s+(.+)", p, re.I)
        if mm: pair = (mm.group(1).strip(), mm.group(2).strip()); break
    phase = " ".join(PHASE.findall(" ".join(parts))).lower()
    rec = dict(video_id=v["id"], title=title, player=player, event_text=event,
               duration_s=v.get("duration") or 0, upload_date=up,
               team_a=pair[0] if pair else "", team_b=pair[1] if pair else "",
               series_key="", status="", note="")
    is_owcs = bool(re.search(r"\bOWCS\b|Champions Clash|Midseason", event, re.I)) and not re.search(r"Qualifier|Bootcamp|Relegation", title, re.I)
    if not is_owcs:
        rec["status"] = "not_owcs_main"; rows.append(rec); continue
    if up and up.year < 2026:
        rec["status"] = "pre_2026"; rows.append(rec); continue
    if not pair:
        rec["status"] = "no_teams_in_title"; rows.append(rec); continue
    a, b = team_id(pair[0]), team_id(pair[1])
    if not a or not b:
        rec["status"] = "unknown_team"; rec["note"] = f"{pair[0]}->{a}, {pair[1]}->{b}"; rows.append(rec); continue
    reg, st = event_hint(event)
    c = lp[((lp.k1 == a) & (lp.k2 == b)) | ((lp.k1 == b) & (lp.k2 == a))]
    c = c[c.event.map(lambda e: lp_event_ok(e, reg, st)).astype(bool)] if len(c) else c
    if up and len(c):
        c = c[c.d.map(lambda d: d is not None and d <= up + dt.timedelta(days=45) and d >= up - dt.timedelta(days=120)).astype(bool)]
    if len(c) > 1 and phase:
        playoff = bool(re.search(r"final|playoff|upper|lower|road to", phase))
        cc = c[(c.part == "Main/Playoffs") == playoff]
        if len(cc): c = cc
    if len(c) == 0:
        rec["status"] = "no_2026_series"
    elif len(c) == 1:
        rec["status"] = "matched"; rec["series_key"] = c.series_key.iloc[0]
    else:
        # ambiguous: pick the latest series on/before upload, else earliest
        c = c.sort_values("d")
        pick = c[c.d <= up] if up is not None else c
        rec["series_key"] = (pick if len(pick) else c).series_key.iloc[-1 if len(pick) else 0]
        rec["status"] = "matched_ambiguous"; rec["note"] = f"{len(c)} candidates"
    rows.append(rec)

V = pd.DataFrame(rows)
V.to_csv(out / "video_matches.csv", index=False, encoding="utf-8")

# ---------- inventory ----------
mv = V[V.status.str.startswith("matched")]
per = mv.groupby("series_key").agg(n_pov=("video_id", "count"), pov_hours=("duration_s", lambda s: s.sum() / 3600),
                                   median_len_h=("duration_s", lambda s: s.median() / 3600)).reset_index()
S = lp.merge(per, on="series_key", how="left")
S["has_video"] = S.n_pov.fillna(0) > 0
# one-POV-per-series footage = median POV length (POVs of one series are ~same length)
S["one_pov_h"] = S.median_len_h.fillna(0)
# one POV per team: assume 2 x median when >= 2 POVs (cannot tell team from title alone)
S["two_pov_h"] = S.median_len_h.fillna(0) * S.n_pov.fillna(0).clip(upper=2)
S["region_stage"] = S.event
S[["series_key", "event", "part", "date", "team1", "team2", "maps_played", "vod", "n_pov", "pov_hours", "one_pov_h", "two_pov_h", "has_video"]] \
    .to_csv(out / "series_inventory.csv", index=False, encoding="utf-8")

def summary(df, name):
    return dict(scope=name, series=len(df), maps=int(df.maps_played.sum()),
                series_with_video=int(df.has_video.sum()), series_missing_video=int((~df.has_video).sum()),
                maps_with_video=int(df[df.has_video].maps_played.sum()), maps_missing_video=int(df[~df.has_video].maps_played.sum()),
                pov_videos=int(df.n_pov.fillna(0).sum()), hours_all_pov=round(df.pov_hours.fillna(0).sum(), 1),
                hours_one_pov=round(df.one_pov_h.sum(), 1), hours_one_pov_per_team=round(df.two_pov_h.sum(), 1))
rows = [summary(S[S.event == "Asia/Stage 1/Korea"], "PILOT Korea Stage 1")]
rows += [summary(g, ev) for ev, g in S.groupby("event")]
rows.append(summary(S, "ALL 2026"))
pd.DataFrame(rows).to_csv(out / "inventory_summary.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False))
print("\nvideo status:\n", V.status.value_counts().to_string())

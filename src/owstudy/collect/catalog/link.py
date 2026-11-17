"""Match ObsSojourn POV videos to Liquipedia series (ported from scripts/inventory/inventory.py).

Titles look like `[ Player ] Nickname | Team A vs Team B | Event`. A video is matched to a
series when both teams resolve to Liquipedia teams, the event text fits the series' event,
and the series date is near the upload date. This is the inventory-level matcher; the catalog's
video links (task T032) add confidence levels and review on top.

Team names are compared by a loose "match key" (lower case, letters and digits only, words like
"Team" and "Gaming" dropped). Hand-curated team aliases (aliases.csv) are applied to every name,
Liquipedia's included; spreadsheet abbreviations are used only for names Liquipedia doesn't have.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from collections.abc import Iterable
from dataclasses import dataclass

from owstudy.collect.catalog.entities import AliasTable, team_id

# Video statuses
MATCHED, AMBIGUOUS = "matched", "matched_ambiguous"
NOT_OWCS, BOOTCAMP, PRE_2026 = "not_owcs_main", "out_of_scope_bootcamp", "pre_2026"
NO_TEAMS, UNKNOWN_TEAM, NO_SERIES = "no_teams_in_title", "unknown_team", "no_2026_series"

PHASE = re.compile(
    r"grand final|final|semifinal|quarterfinal|playoff|upper|lower|seeding|round robin|regular season|group|decider|road to",
    re.I,
)
OWCS_EVENT = re.compile(r"\bOWCS\b|Champions Clash|Midseason", re.I)
NOT_MAIN = re.compile(r"Qualifier|Relegation", re.I)
BOOTCAMP_RE = re.compile(r"Bootcamp|Boot Camp", re.I)  # FR-023a: out of scope everywhere


def raw_key(text: str) -> str:
    t = str(text).lower().replace("ø", "o").replace("rode ", "")
    t = re.sub(r"\b(esports|gaming|team)\b", "", t)
    return re.sub(r"[^a-z0-9]", "", t)


def parse_date(text: str) -> dt.date | None:
    """Liquipedia date text ('2026-04-24 - 18:50', 'April 24, 2026') -> date."""
    s = re.sub(r"(\d)(st|nd|rd|th)", r"\1", str(text)).split(" - ")[0].strip()
    m = re.match(r"\d{4}-\d{2}-\d{2}", s)
    if m:
        s = m.group(0)
    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


class TeamMatcher:
    """Turns team text from any source into the match key of a Liquipedia team."""

    def __init__(self, lp_team_names: Iterable[str], aliases: AliasTable, sheet_abbrs: Iterable[tuple[str, str]] = ()):
        names = [n for n in lp_team_names if n]
        display_key = {}
        for n in names:  # stable ID -> match key of its Liquipedia name
            try:
                display_key.setdefault(team_id(n), raw_key(n))
            except ValueError:
                continue
        self.canon: dict[str, str] = {}
        for a in aliases.entries("team"):
            target = display_key.get(a.stable_id, raw_key(a.stable_id.split(":", 1)[1]))
            if raw_key(a.alias) != target:
                self.canon[raw_key(a.alias)] = target
        self.lp_keys = sorted({self.key(n) for n in names})
        self._lp_set = set(self.lp_keys)
        self.sheet_alias = {self.key(abbr): self.key(full) for abbr, full in sheet_abbrs}

    def key(self, text: str) -> str:
        k = raw_key(text)
        return self.canon.get(k, k)

    def resolve(self, text: str) -> str | None:
        k = self.key(text)
        if k not in self._lp_set and self.sheet_alias.get(k) in self._lp_set:
            k = self.sheet_alias[k]
        if k in self._lp_set:
            return k
        close = difflib.get_close_matches(k, self.lp_keys, n=1, cutoff=0.8)
        return close[0] if close else None


@dataclass(frozen=True)
class Title:
    player: str
    team_a: str
    team_b: str
    event_text: str
    phase: str

    @property
    def has_pair(self) -> bool:
        return bool(self.team_a and self.team_b)


def parse_title(title: str) -> Title:
    m = re.match(r"\s*\[\s*([^\]]+?)\s*\]\s*(.*)", title)
    player, rest = (m.group(1), m.group(2)) if m else ("", title)
    parts = [p.strip() for p in rest.split("|")]
    event = parts[-1] if len(parts) > 1 else ""
    pair = ("", "")
    for p in parts:
        mm = re.search(r"(.+?)\s+vs\.?\s+(.+)", p, re.I)
        if mm:
            pair = (mm.group(1).strip(), mm.group(2).strip())
            break
    phase = " ".join(PHASE.findall(" ".join(parts))).lower()
    return Title(player, pair[0], pair[1], event, phase)


def event_hint(event_text: str) -> tuple[str | None, str | None]:
    """(region, stage number) suggested by a title's event text."""
    e = event_text.lower()
    reg = (
        "korea" if re.search(r"korea|\bkor\b", e) else
        "japan" if re.search(r"japan|\bjpn\b", e) else
        "pacific" if re.search(r"pacific|\bpac\b", e) else
        "china" if re.search(r"china|\bcn\b", e) else
        "emea" if "emea" in e else
        "na" if re.search(r"\bna\b|north america", e) else
        "midseason" if "midseason" in e else
        "clash" if "clash" in e else
        "asia" if "asia" in e else None
    )  # fmt: skip
    st = re.search(r"stage\s*(\d)|\bs(\d)\b", e)
    return reg, (st.group(1) or st.group(2)) if st else None


EVENT_WANT = {"korea": "korea", "japan": "japan", "pacific": "pacific", "china": "china/", "emea": "emea/",
              "na": "na/", "midseason": "midseason", "clash": "champions clash", "asia": "asia/stage"}  # fmt: skip


def event_fits(lp_event: str, region: str | None, stage: str | None) -> bool:
    e = lp_event.lower()
    if region is None:
        return True
    if region == "asia" and e.count("/") != 1:
        return False
    return EVENT_WANT[region] in e and (stage is None or f"stage {stage}" in e)


def candidate_series(series: list[dict], a: str, b: str, title: Title, upload: dt.date | None) -> list[dict]:
    """Series between teams a and b that fit the event text, upload date and phase words."""
    region, stage = event_hint(title.event_text)
    c = [s for s in series if (s["k1"], s["k2"]) in ((a, b), (b, a))]
    c = [s for s in c if event_fits(s["event"], region, stage)]
    if upload:
        lo, hi = upload - dt.timedelta(days=120), upload + dt.timedelta(days=45)
        c = [s for s in c if s["d"] is not None and lo <= s["d"] <= hi]
    if len(c) > 1 and title.phase:
        playoff = bool(re.search(r"final|playoff|upper|lower|road to", title.phase))
        cc = [s for s in c if (s["part"] == "Main/Playoffs") == playoff]
        if cc:
            c = cc
    return c


def assign(candidates: list[dict], upload: dt.date | None) -> tuple[str, str, str]:
    """(status, series_key, note) from the candidate list."""
    if not candidates:
        return NO_SERIES, "", ""
    if len(candidates) == 1:
        return MATCHED, candidates[0]["series_key"], ""
    # Ambiguous: the latest series on or before the upload, else the earliest.
    c = sorted(candidates, key=lambda s: s["d"] or dt.date.min)  # stable, like pandas sort_values
    before = [s for s in c if upload is not None and s["d"] is not None and s["d"] <= upload] if upload else c
    pick = before[-1] if before else c[0]
    return AMBIGUOUS, pick["series_key"], f"{len(c)} candidates"


def match_videos(videos: list[dict], lp_series: list[dict], matcher: TeamMatcher) -> list[dict]:
    """One row per channel video: parsed title, matched series and a status."""
    series = []
    for s in lp_series:
        s = dict(s)
        s["d"] = parse_date(s["date"])
        s["k1"], s["k2"] = matcher.key(s["team1"]), matcher.key(s["team2"])
        series.append(s)

    rows = []
    for v in videos:
        title_text = v.get("title") or ""
        ts = v.get("timestamp")
        up = dt.datetime.fromtimestamp(ts, dt.timezone.utc).date() if ts else None
        t = parse_title(title_text)
        rec = {"video_id": v["id"], "title": title_text, "player": t.player, "event_text": t.event_text,
               "duration_s": v.get("duration") or 0, "upload_date": up.isoformat() if up else "",
               "team_a": t.team_a, "team_b": t.team_b, "series_key": "", "status": "", "note": ""}  # fmt: skip
        if BOOTCAMP_RE.search(title_text) and OWCS_EVENT.search(title_text):
            rec["status"] = BOOTCAMP
        elif not OWCS_EVENT.search(t.event_text) or NOT_MAIN.search(title_text):
            rec["status"] = NOT_OWCS
        elif up and up.year < 2026:
            rec["status"] = PRE_2026
        elif not t.has_pair:
            rec["status"] = NO_TEAMS
        else:
            a, b = matcher.resolve(t.team_a), matcher.resolve(t.team_b)
            if not a or not b:
                rec["status"] = UNKNOWN_TEAM
                rec["note"] = f"{t.team_a}->{a}, {t.team_b}->{b}"
            else:
                rec["status"], rec["series_key"], rec["note"] = assign(candidate_series(series, a, b, t, up), up)
        rows.append(rec)
    return rows

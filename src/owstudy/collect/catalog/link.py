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
    r"grand final|final|semifinal|quarterfinal|playoff|upper|lower|seeding|round robin|regular season|group|decider|"
    r"road to|last chance|third place",
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


# --- catalog video links (task T032) ---------------------------------------------------

LINK_COLUMNS = ["video_id", "series_id", "status", "link_confidence", "role", "pov_player_id", "pov_team_id",
                "confirmed", "note"]  # fmt: skip
LINKED, UNMATCHED, NOT_OWCS_2026, DUPLICATE = "linked", "unmatched", "not_owcs_2026", "duplicate"
PLAYOFF_WORDS = re.compile(r"final|playoff|upper|lower|road to|seeding|decider|last chance|third place", re.I)
LOOKBACK_DAYS = 120  # a video is linked to a series at most this long before its upload
UPLOAD_SLACK_DAYS = 1  # upload dates are UTC and series dates are local, so allow one day
DUPLICATE_MAX_GAP_S = 60  # same series + same player + lengths within this = a re-upload


def link_candidates(series: list[dict], a: str, b: str, title: Title, upload: dt.date | None) -> list[dict]:
    """Played series between teams a and b (IDs) that fit the title's event, on or before the
    upload date, nearest first (research R7)."""
    region, stage = event_hint(title.event_text)
    c = [s for s in series if {s["team_a_id"], s["team_b_id"]} == {a, b} and event_fits(s["event"], region, stage)]
    if upload is not None:
        lo, hi = upload - dt.timedelta(days=LOOKBACK_DAYS), upload + dt.timedelta(days=UPLOAD_SLACK_DAYS)
        c = [s for s in c if s["day"] is not None and lo <= s["day"] <= hi]
    return sorted(c, key=lambda s: (-(s["day"] or dt.date.min).toordinal(), s["series_id"]))


# Title words -> the rounds they can mean. ObsSojourn often calls a seeding decider "Playoffs",
# so "playoff" allows every round on Liquipedia's playoffs page.
ROUND_WORDS = [
    (re.compile(r"grand final", re.I), {"grand finals", "grand final"}),
    (re.compile(r"semi-?final", re.I), {"semifinals", "semifinal"}),
    (re.compile(r"quarter-?final", re.I), {"quarterfinal", "quarterfinals"}),
    (re.compile(r"third place|3rd place", re.I), {"third place match"}),
    (re.compile(r"seeding|decider", re.I), {"seeding decider"}),
    (re.compile(r"last chance", re.I), {"last chance qualifier"}),
]
DEFAULT_S_PER_MAP = 720.0  # used until high-confidence links give a measured value
SAME_SERIES_GAP_S = 60  # POVs of one series are this close in length (unless the replay has holes)
NEIGHBOUR_SPAN = 5  # channel-list positions looked at on each side of a video


def phase_filter(candidates: list[dict], title: Title) -> tuple[list[dict], str]:
    """Narrow candidates by the title's phase words. Returns (candidates, reason or "").

    A named round ("Grand Finals", "Seeding Decider") keeps that round; other playoff words keep
    playoff-page series (seeding deciders included); no phase words keep the regular season.
    A filter that would leave nothing is skipped.
    """
    text = title.phase
    for pattern, rounds in ROUND_WORDS:
        if pattern.search(text):
            kept = [s for s in candidates if str(s.get("round", "")).lower() in rounds]
            if kept:
                return kept, f"phase words '{text}' (round named)"
    if PLAYOFF_WORDS.search(text):
        kept = [s for s in candidates if s["playoff"]]
        return (kept, f"phase words '{text}'") if kept else (candidates, "")
    if not text or re.search(r"regular|round robin|group", text):
        kept = [s for s in candidates if not s["playoff"]]
        why = f"phase words '{text}'" if text else "no phase words in title (regular season)"
        return (kept, why) if kept else (candidates, "")
    return candidates, ""


def choose_series(candidates: list[dict], title: Title) -> tuple[dict | None, str, str]:
    """First pass, (series, confidence, note): one candidate -> high; the title's phase words
    leave one -> medium; otherwise the nearest date with low confidence. Low links are revisited
    by `settle_by_length`."""
    if not candidates:
        return None, "", ""
    if len(candidates) == 1:
        return candidates[0], "high", ""
    c, why = phase_filter(candidates, title)
    if len(c) == 1:
        return c[0], "medium", f"{len(candidates)} candidates; picked by {why}"
    return c[0], "low", f"{len(candidates)} candidates; picked the nearest date before upload"


def _n_maps(s: dict) -> int:
    try:
        return int(s["score_a"]) + int(s["score_b"])
    except (TypeError, ValueError):
        return 0


def settle_by_length(rows: list[dict], options: dict[str, list[dict]]) -> None:
    """Second pass for low-confidence links, using what the confident links show:

    - a player has one video per series, so a series where this player already has a confident
      video of a different length is ruled out;
    - all POVs of one series are about the same length, so the series whose confident videos are
      closest in length wins; with no confident video, the length expected from its map count.
    """
    import statistics

    sure = [r for r in rows if r["status"] == LINKED and r["link_confidence"] in ("high", "medium")]
    by_series: dict[str, list[dict]] = {}
    for r in sure:
        by_series.setdefault(r["series_id"], []).append(r)
    per_map = [r["duration_s"] / r["_n_maps"] for r in sure if r["link_confidence"] == "high" and r["_n_maps"]]
    s_per_map = statistics.median(per_map) if per_map else DEFAULT_S_PER_MAP

    for r in rows:
        if r["status"] != LINKED or r["link_confidence"] != "low":
            continue
        cands = options.get(r["video_id"], [])
        player = r["pov_player_id"] or "text:" + r["player_norm"]
        kept = []
        for s in cands:
            others = by_series.get(s["series_id"], [])
            if any((o["pov_player_id"] or "text:" + o["player_norm"]) == player
                   and abs(o["duration_s"] - r["duration_s"]) >= SAME_SERIES_GAP_S for o in others):
                continue  # this player already has a different video of that series
            if others:
                cost = abs(statistics.median(o["duration_s"] for o in others) - r["duration_s"])
                basis = "length of its other videos"
            else:
                cost = abs(_n_maps(s) * s_per_map - r["duration_s"])
                basis = f"{_n_maps(s)} maps x {s_per_map:.0f} s"
            kept.append((cost, s["series_id"], s, basis))
        if not kept:
            continue
        kept.sort(key=lambda k: (k[0], k[1]))
        cost, sid, s, basis = kept[0]
        clear = len(kept) == 1 or (kept[1][0] - cost) >= SAME_SERIES_GAP_S * 3
        r["series_id"] = sid
        r["_pick"] = s
        # medium only when the evidence is direct: other players' videos of that series, or
        # every other candidate ruled out; a guess from the map count alone stays low
        direct = basis.startswith("length") or len(kept) == 1
        r["link_confidence"] = "medium" if clear and direct else "low"
        r["note"] = (f"{len(cands)} candidates; {len(cands) - len(kept)} ruled out (same player already has a video), "
                     f"picked by video length ({basis})")
        r["_by_map_count"] = clear and not direct and (kept[1][0] - cost) >= s_per_map

    # A guess from the map count is raised to medium when 3+ POVs of the same length (other
    # players, so not one replay with holes) make the same clear pick.
    guesses = [r for r in rows if r.get("_by_map_count")]
    for r in guesses:
        same = [o for o in guesses if o["series_id"] == r["series_id"]
                and abs(o["duration_s"] - r["duration_s"]) < SAME_SERIES_GAP_S]
        if len(same) >= 3:
            r["link_confidence"] = "medium"
            r["note"] += f"; {len(same)} POVs of this length agree"

    # Last: ObsSojourn uploads a series' POVs together, so a still-low video whose neighbours in
    # the channel list are confident links of one candidate series belongs to that series.
    # This catches POVs shortened by holes in the replay, which video length gets wrong.
    for i, r in enumerate(rows):
        if r["status"] != LINKED or r["link_confidence"] != "low":
            continue
        cands = {s["series_id"]: s for s in options.get(r["video_id"], [])}
        near = [o for o in rows[max(0, i - NEIGHBOUR_SPAN):i + NEIGHBOUR_SPAN + 1]
                if o is not r and o["status"] == LINKED and o["link_confidence"] in ("high", "medium")
                and o["series_id"] in cands]
        votes = {o["series_id"] for o in near}
        if len(votes) == 1 and len(near) >= 2:
            sid = votes.pop()
            r.update(series_id=sid, _pick=cands[sid], link_confidence="medium",
                     note=f"{len(cands)} candidates; uploaded alongside {len(near)} confident videos of this series")


def _player_lookup(lineups) -> dict[str, list[tuple[str, str, str]]]:
    """series_id -> [(normalized name, player_id, team_id)] from the catalog lineups."""
    from owstudy.collect.catalog.entities import normalize_alias

    out: dict[str, list] = {}
    for r in lineups.to_dict(orient="records"):
        names = {normalize_alias(r.get("display", "") or ""), normalize_alias(r["player_id"].split(":", 1)[1])}
        for n in sorted(names - {""}):
            out.setdefault(r["series_id"], []).append((n, r["player_id"], r["team_id"]))
    return out


def link_videos(catalog, videos: list[dict], aliases: AliasTable, cfg, overrides=None):
    """One row per video: the series it shows, link confidence, POV player and team, role.

    `catalog` is a catalog.build.Catalog over every event, so a video of another region-stage
    links there instead of showing up as unmatched. Returns a DataFrame of LINK_COLUMNS plus
    `title` and `event_text` (used for scope filtering). `confirmed` starts false; it's set
    after extraction from the HUD names (research R7).

    `overrides` (configs/collect/video_overrides.yaml) are the researcher's notes: a series set by
    hand wins (confidence `manual`), and an incomplete replay is never the primary or cross-check POV.
    """
    import pandas as pd

    from owstudy.collect.catalog.entities import normalize_alias
    from owstudy.collect.refs.youtube_list import upload_day

    series = [s for s in catalog.series.to_dict(orient="records") if s["status"] == "played"]
    by_id = {s["series_id"]: s for s in series}
    players = _player_lookup(catalog.lineups)
    rows = []
    options: dict[str, list[dict]] = {}  # video -> candidates left after phase words (low links)
    for v in videos:
        title_text = v.get("title") or ""
        up = upload_day(v)
        t = parse_title(title_text)
        rec = {"video_id": v["id"], "series_id": "", "status": UNMATCHED, "link_confidence": "", "role": "",
               "pov_player_id": "", "pov_team_id": "", "confirmed": False, "note": "",
               "title": title_text, "event_text": t.event_text, "duration_s": v.get("duration") or 0,
               "player_norm": normalize_alias(t.player), "_n_maps": 0, "_title_player": t.player}  # fmt: skip
        if BOOTCAMP_RE.search(title_text) and OWCS_EVENT.search(title_text):
            rec.update(status=NOT_OWCS_2026, note="OWCS Preseason Bootcamp: out of scope (FR-023a)")
        elif not OWCS_EVENT.search(t.event_text) or NOT_MAIN.search(title_text):
            rec.update(status=NOT_OWCS_2026, note="not an OWCS main event")
        elif up and up.year < 2026:
            rec.update(status=NOT_OWCS_2026, note="uploaded before 2026")
        elif not t.has_pair:
            rec["note"] = "title names no 'Team A vs Team B'"
        else:
            a, b = catalog.names.id_of(t.team_a), catalog.names.id_of(t.team_b)
            if not a or not b:
                rec["note"] = "unknown team: " + ", ".join(x for x, r in ((t.team_a, a), (t.team_b, b)) if not r)
            else:
                cands = link_candidates(series, a, b, t, up)
                pick, conf, note = choose_series(cands, t)
                if pick is None:
                    rec["note"] = "no played 2026 series between these teams fits the event and date"
                else:
                    rec.update(series_id=pick["series_id"], status=LINKED, link_confidence=conf, note=note,
                               _n_maps=_n_maps(pick))  # fmt: skip
                    if conf == "low":
                        options[v["id"]] = phase_filter(cands, t)[0]
                    _set_pov(rec, players.get(pick["series_id"], []), aliases, t.player)
        rows.append(rec)

    settle_by_length(rows, options)
    _apply_overrides(rows, overrides or {}, by_id)
    for r in rows:  # the POV player and team follow the (possibly changed) series
        if "_pick" in r:
            r.update(pov_player_id="", pov_team_id="")
            _set_pov(r, players.get(r["series_id"], []), aliases, r["_title_player"])

    _set_roles(rows, by_id, cfg.video.povs_per_series)
    cols = [*LINK_COLUMNS, "title", "event_text"]
    return pd.DataFrame(rows, columns=[*cols, "duration_s", "player_norm"])[cols]


def _apply_overrides(rows: list[dict], overrides: dict, by_id: dict) -> None:
    from owstudy.collect.errors import ConfigError

    # A video no longer in the channel list has no row, so its note simply has nothing to change.
    for r in rows:
        o = overrides.get(r["video_id"])
        if o is None:
            continue
        if o.series_id:
            if o.series_id not in by_id:
                raise ConfigError(f"video_overrides.yaml: {o.video_id} -> unknown or unplayed series {o.series_id}")
            if o.series_id != r["series_id"]:
                r["_pick"] = by_id[o.series_id]
            r.update(series_id=o.series_id, status=LINKED, link_confidence="manual", note="set by hand")
        if o.incomplete:
            r["_incomplete"] = True
            r["note"] = "; ".join(x for x in (r["note"], "incomplete replay: not used as a main POV") if x)
        if o.note:
            r["note"] += f" ({o.note})"


def _set_pov(rec: dict, lineup: list[tuple[str, str, str]], aliases: AliasTable, player_text: str) -> None:
    """POV player and team: the title's player name in the series lineups, else aliases.csv."""
    for name, pid, tid in lineup:
        if name == rec["player_norm"]:
            rec.update(pov_player_id=pid, pov_team_id=tid)
            return
    if player_text:
        r = aliases.resolve("player", player_text)
        if r.stable_id:
            rec["pov_player_id"] = r.stable_id
            rec["pov_team_id"] = next((tid for _, pid, tid in lineup if pid == r.stable_id), "")


def _set_roles(rows: list[dict], by_id: dict, povs_per_series: int) -> None:
    """Duplicates first, then primary (longest video, ties by video_id), then with
    povs_per_series = 2 a cross-check POV from the other team; the rest are unused."""
    per_series: dict[str, list[dict]] = {}
    for r in rows:
        if r["status"] == LINKED:
            per_series.setdefault(r["series_id"], []).append(r)
    for sid, vids in per_series.items():
        by_player: dict[str, list[dict]] = {}
        for r in vids:
            by_player.setdefault(r["pov_player_id"] or "text:" + r["player_norm"], []).append(r)
        for group in by_player.values():
            group.sort(key=lambda r: (-r["duration_s"], r["video_id"]))
            keep = group[0]
            for r in group[1:]:
                if abs(r["duration_s"] - keep["duration_s"]) < DUPLICATE_MAX_GAP_S:
                    r.update(status=DUPLICATE, role=DUPLICATE, note=f"re-upload of {keep['video_id']}")
        live = sorted((r for r in vids if r["status"] == LINKED),
                      key=lambda r: (bool(r.get("_incomplete")), -r["duration_s"], r["video_id"]))  # fmt: skip
        for r in live:
            r["role"] = "unused"
        if not live:
            continue
        primary = live[0]
        primary["role"] = "primary"
        if povs_per_series == 2:
            s = by_id.get(sid, {})
            other = {s.get("team_a_id"), s.get("team_b_id")} - {primary["pov_team_id"]}
            if primary["pov_team_id"] and len(other) == 1:
                cross = [r for r in live[1:] if r["pov_team_id"] in other and not r.get("_incomplete")]
                if cross:
                    cross[0]["role"] = "cross_check"


def in_scope_links(links, scope_series_ids: set[str], scope_keys) -> object:
    """Rows to write for a scope: videos linked to an in-scope series, and videos linked to
    nothing whose title names an in-scope region (and stage, if it gives one). So in-scope
    unmatched videos and Bootcamp videos are listed; other region-stages' videos, and titles
    that name no region at all, aren't."""

    def keep(r) -> bool:
        if r.series_id:
            return r.series_id in scope_series_ids
        region, stage = event_hint(r.event_text)
        return region is not None and any(event_fits(k, region, stage) for k in scope_keys)

    return links[[keep(r) for r in links.itertuples()]]

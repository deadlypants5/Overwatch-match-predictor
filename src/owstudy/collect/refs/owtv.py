"""OWTV probe (task T064, research R10): find out what OWTV's API gives for the pilot.

OWTV's official API (docs: owtv.gg/api-docs) is read with a personal key in the `X-API-Key`
header. Never OWTV's web pages: their terms forbid scripts and scrapers. Permission to use the
API as a main source was granted on 2026-11-17, under 60 requests a minute; our client waits
`retrieval.owtv_min_interval_s` (5 s) between requests and caches every answer.

What the probe does, in order:

1. Finds the OWTV tournaments for the scope (region name in the title, dates overlapping the
   catalog's series), or uses the ones given with `--tournament`.
2. Lists their phases, matches and teams, and pairs each catalog series with an OWTV match
   (same two teams, start dates at most a day apart).
3. Lists every map of the paired matches, to count how many have a parsed replay and an event
   log (pilot coverage).
4. For 3 sample series (given, or picked to cover Control, Escort/Hybrid and Push/Flashpoint),
   also downloads team fights, player stats and per-hero stats.
5. Saves every answer byte for byte, plus `series_match.csv`, `map_coverage.csv` and a readable
   `summary.md`, to `data/interim/probes/owtv/<date>/`. That folder is kept out of git: OWTV's
   terms forbid publishing their data in bulk.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from owstudy.collect.errors import RetrievalBlocked, UsageError
from owstudy.collect.io.tables import read_table, write_table
from owstudy.collect.refs.ratelimit import HttpClient

API = "https://owtv.gg/api"
PAGE_LIMIT = 100  # the API's maximum page size
IN_CHUNK = 40  # IDs per `in` filter, to keep URLs short
MODE_FAMILIES = (("control",), ("escort", "hybrid"), ("push", "flashpoint"))
EVENT_TYPE_KEYS = ("type", "eventType", "event_type", "event", "kind", "name")

SERIES_MATCH_COLUMNS = ("series_id", "local_date", "team_a_id", "team_b_id", "owtv_match_id", "owtv_slug",
                        "owtv_start", "date_diff_days", "result", "note")  # fmt: skip
MAP_COVERAGE_COLUMNS = ("series_id", "map_number", "catalog_map", "owtv_map", "same_map", "owtv_match_map_id",
                        "map_index", "replay_parsed", "has_event_log", "event_log_items", "has_bans", "sample")  # fmt: skip
INDEX_COLUMNS = ("n", "file", "collection", "url", "params", "from_cache")


# --- the API -----------------------------------------------------------------------------


def ref_id(value: Any) -> str:
    """A relation field as an ID, whether the API gave the ID or the whole related item."""
    if isinstance(value, Mapping):
        value = value.get("id")
    return "" if value is None else str(value)


@dataclass
class SavedAnswer:
    collection: str
    url: str
    params: dict[str, Any]
    content: bytes
    from_cache: bool


class OwtvApi:
    """Read-only access to `https://owtv.gg/api/<collection>`. Every answer is kept in `answers`."""

    def __init__(self, client: HttpClient, api_key: str):
        if not api_key or api_key.startswith("<"):
            raise RetrievalBlocked(
                "no OWTV API key yet: set owtv_api_key in configs/collect/local.yaml. Nothing was downloaded."
            )
        self.client = client
        self._headers = {"X-API-Key": api_key}  # sent with each request, never saved
        self.answers: list[SavedAnswer] = []

    def get(self, collection: str, params: Mapping[str, Any] | None = None, item_id: str | None = None) -> Any:
        url = f"{API}/{collection}" + (f"/{item_id}" if item_id else "")
        params = dict(params or {})
        resp = self.client.get(url, params, headers=self._headers)
        self.answers.append(SavedAnswer(collection, url, params, resp.content, resp.from_cache))
        try:
            return resp.json()
        except ValueError as e:
            raise RetrievalBlocked(f"OWTV answered something that isn't JSON for {url}") from e

    def list(self, collection: str, where: Mapping[str, tuple[str, Any]] | None = None, depth: int = 0) -> list[dict]:
        """Every item of a collection matching `where` ({field: (operator, value)}), all pages."""
        params: dict[str, Any] = {"limit": PAGE_LIMIT, "depth": depth, "sort": "id"}
        for name, (op, value) in (where or {}).items():
            if isinstance(value, (list, tuple, set)):
                value = ",".join(str(v) for v in value)
            params[f"where[{name}][{op}]"] = value
        docs: list[dict] = []
        page = 1
        while True:
            body = self.get(collection, {**params, "page": page})
            if not isinstance(body, Mapping) or "docs" not in body:
                raise RetrievalBlocked(f"OWTV's {collection} list didn't have the expected layout (no 'docs')")
            docs.extend(body["docs"])
            if not body.get("hasNextPage"):
                return docs
            page += 1

    def list_in(self, collection: str, field_name: str, ids: Iterable[str], depth: int = 0) -> list[dict]:
        """Items whose `field_name` is one of `ids`, asked in chunks."""
        ids = sorted(set(i for i in ids if i))
        out: list[dict] = []
        for i in range(0, len(ids), IN_CHUNK):
            out.extend(self.list(collection, {field_name: ("in", ids[i:i + IN_CHUNK])}, depth))
        return out


# --- pairing catalog series with OWTV matches ------------------------------------------


def _date(value: Any) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return dt.date.fromisoformat(str(value)[:10])
        except ValueError:
            return None


def _region_word(scope_key: str) -> str:
    from owstudy.collect.catalog.build import split_event

    return split_event(scope_key)[0]


def pick_tournaments(tournaments: Sequence[Mapping], scope_keys: Sequence[str], first: dt.date, last: dt.date) -> list[dict]:
    """Tournaments whose title names a scope region and whose dates overlap [first, last]."""
    from owstudy.collect.catalog.build import is_bootcamp

    words = {_region_word(k).lower() for k in scope_keys}
    picked = []
    for t in tournaments:
        title = f"{t.get('name', '')} {t.get('slug', '')}".lower()
        if not any(re.search(rf"\b{re.escape(w)}\b", title) for w in words) or is_bootcamp(title):
            continue
        start, end = _date(t.get("startDate")), _date(t.get("endDate")) or _date(t.get("startDate"))
        if start and end and start <= last + dt.timedelta(days=3) and end >= first - dt.timedelta(days=3):
            picked.append(dict(t))
    return picked


def team_resolver(aliases_path: Path, teams_path: Path):
    """OWTV team (name, initials) -> our team ID, or "" when no name matches exactly."""
    from owstudy.collect.catalog.entities import AliasTable

    table = AliasTable.load(aliases_path) if aliases_path.exists() else AliasTable()
    if teams_path.exists():
        for r in read_table(teams_path, required=["team_id", "name"]).itertuples():
            table.add_known("team", r.team_id, r.name)

    def resolve(team: Mapping) -> str:
        for text in (team.get("name"), team.get("initials")):
            if text:
                hit = table.resolve("team", str(text))
                if hit.stable_id:
                    return hit.stable_id
        return ""

    return resolve


def pair_series(series, matches: Sequence[Mapping], team_of: Mapping[str, str]) -> list[dict]:
    """One row per catalog series: its OWTV match (same teams, dates at most one day apart)."""
    by_pair: dict[frozenset, list[Mapping]] = {}
    for m in matches:
        pair = frozenset((team_of.get(ref_id(m.get("team1")), ""), team_of.get(ref_id(m.get("team2")), "")))
        if "" not in pair:
            by_pair.setdefault(pair, []).append(m)
    rows = []
    for s in series.itertuples():
        row = {"series_id": s.series_id, "local_date": s.local_date, "team_a_id": s.team_a_id,
               "team_b_id": s.team_b_id, "result": "none", "note": ""}  # fmt: skip
        day = _date(s.local_date) or _date(s.start_utc)
        options = []
        for m in by_pair.get(frozenset((s.team_a_id, s.team_b_id)), []):
            mday = _date(m.get("startDate"))
            if day and mday and abs((mday - day).days) <= 1:
                options.append((abs((mday - day).days), str(m.get("startDate")), m))
        options.sort(key=lambda o: (o[0], o[1]))
        if options:
            diff, _, m = options[0]
            row.update(owtv_match_id=ref_id(m), owtv_slug=m.get("slug", ""), owtv_start=m.get("startDate", ""),
                       date_diff_days=diff, result="matched")  # fmt: skip
            if len(options) > 1 and options[1][0] == diff:
                row.update(result="ambiguous", note=f"{len(options)} OWTV matches with these teams that day")
        rows.append(row)
    return rows


# --- looking inside answers ----------------------------------------------------------------


def parse_json_field(value: Any) -> Any:
    """`eventLog` may arrive as JSON text or as already-parsed JSON."""
    if isinstance(value, str) and value.strip()[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def event_items(log: Any) -> list:
    """The list of events in an event log: the log itself, or its longest list-valued entry."""
    log = parse_json_field(log)
    if isinstance(log, list):
        return log
    if isinstance(log, Mapping):
        lists = [v for v in log.values() if isinstance(v, list)]
        return max(lists, key=len) if lists else []
    return []


def describe_event_logs(logs: Iterable[Any]) -> dict[str, Any]:
    """What the event logs look like: top-level shape, item keys and event types (with counts)."""
    shapes, keys, types, n_items = Counter(), Counter(), Counter(), 0
    top_keys: Counter = Counter()
    for raw in logs:
        log = parse_json_field(raw)
        if _is_empty(log):
            continue
        shapes[type(log).__name__] += 1
        if isinstance(log, Mapping):
            top_keys.update(log.keys())
        for item in event_items(log):
            n_items += 1
            if isinstance(item, Mapping):
                keys.update(item.keys())
                for k in EVENT_TYPE_KEYS:
                    if k in item and isinstance(item[k], (str, int)):
                        types[f"{k}={item[k]}"] += 1
                        break
            elif isinstance(item, list) and item and isinstance(item[0], (str, int)):
                types[f"[0]={item[0]}"] += 1  # rows like ["kill", 12.3, ...]
    return {"shapes": dict(shapes), "top_keys": dict(top_keys), "item_keys": dict(keys),
            "event_types": dict(types), "items": n_items}  # fmt: skip


def field_fill(docs: Sequence[Mapping]) -> dict[str, tuple[int, int]]:
    """{field: (items where it is filled, items)} over a collection's items."""
    counts: Counter = Counter()
    for d in docs:
        for k, v in d.items():
            counts[k] += 0 if _is_empty(v) else 1
    return {k: (counts[k], len(docs)) for k in sorted(counts)}


def is_parsed(value: Any) -> bool:
    """`replayParsed` is described as a parsing status; treat true or a done-like word as parsed."""
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "parsed", "complete", "completed", "done", "success", "ok"}


# --- the probe -------------------------------------------------------------------------------


@dataclass
class ProbeResult:
    out_dir: Path
    tournaments: list[dict]
    series_rows: list[dict]
    coverage_rows: list[dict]
    sample: list[str]
    summary: list[str] = field(default_factory=list)


def _choose_sample(maps, coverage_rows: Sequence[Mapping], matched: Sequence[str]) -> list[str]:
    """3 matched series covering Control, Escort/Hybrid and Push/Flashpoint, preferring parsed ones."""
    parsed = Counter(r["series_id"] for r in coverage_rows if r["replay_parsed"] == "true")
    chosen: list[str] = []
    for family in MODE_FAMILIES:
        options = sorted({m.series_id for m in maps.itertuples() if m.mode_id in family and m.series_id in matched}
                         - set(chosen), key=lambda s: (-parsed[s], s))  # fmt: skip
        if options:
            chosen.append(options[0])
    return chosen


def run_probe(
    api: OwtvApi,
    data_dir: Path,
    scope_keys: Sequence[str],
    series_ids: Sequence[str] = (),
    tournament_ids: Sequence[str] = (),
    date: str | None = None,
) -> ProbeResult:
    from owstudy.collect.catalog.entities import map_id as map_slug

    catalog = data_dir / "interim" / "catalog"
    if not (catalog / "series.csv").exists():
        raise UsageError("no catalog yet: run `owstudy-collect catalog build` first")
    series = read_table(catalog / "series.csv", required=["series_id", "region", "stage", "start_utc", "local_date",
                                                          "team_a_id", "team_b_id"])  # fmt: skip
    from owstudy.collect.catalog.build import region_stage

    series = series[[region_stage(r, s) in scope_keys for r, s in zip(series.region, series.stage)]]
    maps = read_table(catalog / "maps.csv", required=["map_id", "series_id", "map_number", "map_ref", "mode_id"])
    maps = maps[maps.series_id.isin(series.series_id)]
    unknown = sorted(set(series_ids) - set(series.series_id))
    if unknown:
        raise UsageError(f"not in the catalog for this scope: {', '.join(unknown)}")
    if series.empty:
        raise UsageError("the catalog has no series for this scope")

    days = [d for d in (_date(x) for x in series.local_date) if d]
    first, last = min(days), max(days)

    # 1-2. tournaments, phases, matches, teams
    if tournament_ids:
        tournaments = [api.get("tournament", {"depth": 0}, item_id=t) for t in tournament_ids]
    else:
        tournaments = pick_tournaments(api.list("tournament"), scope_keys, first, last)
    if not tournaments:
        raise UsageError("no OWTV tournament found for this scope; pass --tournament ID (IDs are in "
                         "data/interim/probes/owtv/<date>/responses)")  # fmt: skip
    phases = api.list_in("tournament-phase", "tournament", [ref_id(t) for t in tournaments])
    matches = api.list_in("match", "tournamentPhase", [ref_id(p) for p in phases])
    team_ids = {ref_id(m.get(k)) for m in matches for k in ("team1", "team2")}
    teams = api.list_in("team", "id", team_ids)
    resolve = team_resolver(data_dir / "interim" / "entities" / "aliases.csv",
                            data_dir / "interim" / "entities" / "teams.csv")  # fmt: skip
    team_of = {ref_id(t): resolve(t) for t in teams}
    unresolved = sorted(f"{t.get('name')} ({t.get('initials')})" for t in teams if not team_of[ref_id(t)])
    series_rows = pair_series(series, matches, team_of)
    matched = {r["series_id"]: r["owtv_match_id"] for r in series_rows if r["result"] in ("matched", "ambiguous")}

    # 3. every map of the paired matches (coverage)
    game_maps = {ref_id(g): g for g in api.list("game-map")}
    match_maps = api.list_in("match-map", "match", matched.values())
    by_match: dict[str, list[dict]] = {}
    for mm in match_maps:
        by_match.setdefault(ref_id(mm.get("match")), []).append(mm)
    ours = {(m.series_id, int(m.map_number)): m for m in maps.itertuples()}
    coverage_rows = []
    for sid, mid in sorted(matched.items()):
        for n, mm in enumerate(sorted(by_match.get(mid, []), key=lambda x: (x.get("mapIndex") is None,
                                                                           x.get("mapIndex"))), start=1):  # fmt: skip
            gm = game_maps.get(ref_id(mm.get("map")), {})
            our = ours.get((sid, n))
            owtv_name = str(gm.get("name", ""))
            coverage_rows.append({
                "series_id": sid, "map_number": n, "catalog_map": our.map_ref if our else "",
                "owtv_map": owtv_name,
                "same_map": ("" if not (our and owtv_name) else str(map_slug(owtv_name) == our.map_ref).lower()),
                "owtv_match_map_id": ref_id(mm), "map_index": mm.get("mapIndex", ""),
                "replay_parsed": str(is_parsed(mm.get("replayParsed"))).lower(),
                "has_event_log": str(not _is_empty(parse_json_field(mm.get("eventLog")))).lower(),
                "event_log_items": len(event_items(mm.get("eventLog"))),
                "has_bans": str(not (_is_empty(mm.get("team1Ban")) and _is_empty(mm.get("team2Ban")))).lower(),
                "sample": "false",
            })  # fmt: skip

    # 4. sample series in depth
    sample = list(series_ids) or _choose_sample(maps, coverage_rows, list(matched))
    missing = [s for s in sample if s not in matched]
    sample = [s for s in sample if s in matched]
    sample_maps = [r["owtv_match_map_id"] for r in coverage_rows if r["series_id"] in sample]
    for r in coverage_rows:
        r["sample"] = str(r["series_id"] in sample).lower()
    fights = api.list_in("map-fight", "matchMap", sample_maps)
    stats = api.list_in("player-map-stats", "matchMap", sample_maps)
    hero_stats = api.list_in("player-map-stats-hero", "playerMapStats", [ref_id(s) for s in stats])
    api.list("game-hero")  # hero names, saved for reading the per-hero stats

    # 5. write everything
    out = data_dir / "interim" / "probes" / "owtv" / (date or dt.date.today().isoformat())
    if out.exists():
        shutil.rmtree(out)
    _save_answers(api.answers, out / "responses")
    write_table(series_rows, out / "series_match.csv", SERIES_MATCH_COLUMNS, key=["series_id"])
    write_table(coverage_rows, out / "map_coverage.csv", MAP_COVERAGE_COLUMNS, key=["series_id", "map_number"])

    sample_mm = [mm for mm in match_maps if ref_id(mm) in set(sample_maps)]
    result = ProbeResult(out, tournaments, series_rows, coverage_rows, sample)
    result.summary = _summary(result, series, matches, unresolved, missing, api.answers, {
        "match": [m for m in matches if ref_id(m) in set(matched.values())],
        "match-map": sample_mm, "map-fight": fights, "player-map-stats": stats,
        "player-map-stats-hero": hero_stats,
    }, describe_event_logs(mm.get("eventLog") for mm in sample_mm),
        describe_event_logs(f.get("eventLog") for f in fights))  # fmt: skip
    (out / "summary.md").write_text("\n".join(result.summary) + "\n", encoding="utf-8", newline="\n")
    return result


def _save_answers(answers: Sequence[SavedAnswer], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, a in enumerate(answers, start=1):
        name = f"{n:04d}_{a.collection}.json"
        (folder / name).write_bytes(a.content)  # byte for byte, as received
        rows.append({"n": n, "file": name, "collection": a.collection, "url": a.url,
                     "params": json.dumps(a.params, sort_keys=True), "from_cache": str(a.from_cache).lower()})  # fmt: skip
    write_table(rows, folder / "index.csv", INDEX_COLUMNS, key=["n"])


def _pct(a: int, b: int) -> str:
    return f"{a}/{b} ({100 * a / b:.0f}%)" if b else "0/0"


def _top(counter: Mapping[str, int], n: int = 25) -> str:
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))[:n]
    return ", ".join(f"`{k}` {v}" for k, v in items) or "none"


def _summary(res: ProbeResult, series, matches, unresolved, missing, answers, docs, map_log, fight_log) -> list[str]:
    cov = res.coverage_rows
    n_series = len(series)
    n_matched = sum(r["result"] == "matched" for r in res.series_rows)
    n_amb = sum(r["result"] == "ambiguous" for r in res.series_rows)
    parsed = sum(r["replay_parsed"] == "true" for r in cov)
    logged = sum(r["has_event_log"] == "true" for r in cov)
    bans = sum(r["has_bans"] == "true" for r in cov)
    same = [r["same_map"] for r in cov if r["same_map"]]
    fetched = sum(not a.from_cache for a in answers)
    lines = [
        f"# OWTV probe, {res.out_dir.name}",
        "",
        "## In short",
        "",
        f"- **Series found on OWTV:** {_pct(n_matched + n_amb, n_series)} of the catalog's series"
        + (f" ({n_amb} with more than one possible match; see `series_match.csv`)" if n_amb else ""),
        f"- **Maps with a parsed replay:** {_pct(parsed, len(cov))}",
        f"- **Maps with an event log:** {_pct(logged, len(cov))}",
        f"- **Maps with bans:** {_pct(bans, len(cov))}",
        f"- **Map names agree with the catalog:** {_pct(sum(s == 'true' for s in same), len(same))}",
        f"- **Sample series (looked at in depth):** {', '.join(res.sample) or 'none'}"
        + (f"; not on OWTV: {', '.join(missing)}" if missing else ""),
        f"- **Requests:** {len(answers)} ({fetched} sent, {len(answers) - fetched} from the cache)",
        "",
        "## Tournaments used",
        "",
        *[f"- `{ref_id(t)}` {t.get('name', '')} ({t.get('startDate', '')[:10]} to {t.get('endDate', '')[:10]})"
          for t in res.tournaments],
        "",
        f"OWTV matches in these tournaments: {len(matches)}.",
    ]  # fmt: skip
    if unresolved:
        lines += ["", "**OWTV team names we couldn't match** (add them to `aliases.csv` if they're ours):", "",
                  *[f"- {u}" for u in unresolved]]  # fmt: skip
    lines += ["", "## Event logs (sample maps)", "",
              f"- Shape: {_top(map_log['shapes'])}; top-level keys: {_top(map_log['top_keys'])}",
              f"- Events: {map_log['items']}",
              f"- Keys inside events: {_top(map_log['item_keys'], 40)}",
              f"- Event types: {_top(map_log['event_types'], 40)}",
              "", "### Team-fight event logs", "",
              f"- Events: {fight_log['items']}; types: {_top(fight_log['event_types'], 40)}",
              "", "## Fields filled, per collection (sample series)", ""]  # fmt: skip
    for name, items in docs.items():
        fill = field_fill(items)
        lines += [f"### {name} ({len(items)} items)", ""]
        lines += [f"- `{k}`: {_pct(a, b)}" for k, (a, b) in fill.items()] or ["- no items"]
        lines.append("")
    lines += ["## Next", "",
              "Copy the field list, coverage and event types into contracts/reference-sources.md §OWTV and",
              "research.md R10, then decide which Phase 5 tasks OWTV replaces (task T065)."]  # fmt: skip
    return lines


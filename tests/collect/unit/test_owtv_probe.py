"""OWTV probe (T064) against a small fake OWTV API: no network."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from urllib.parse import urlsplit

import pytest

from owstudy.collect.cli import main
from owstudy.collect.errors import RetrievalBlocked, UsageError
from owstudy.collect.refs import owtv
from owstudy.collect.refs.owtv import OwtvApi, describe_event_logs, run_probe
from owstudy.collect.refs.ratelimit import HttpClient

KEY = "secret-test-key"
SCOPE = ["Asia/Stage 1/Korea"]
REPO = Path(__file__).resolve().parents[3]

DATA = {
    "tournament": [
        {"id": "t1", "name": "OWCS 2026 Korea Stage 1", "startDate": "2026-03-20T00:00:00Z", "endDate": "2026-05-05T00:00:00Z"},
        {"id": "t2", "name": "OWCS 2026 Japan Stage 1", "startDate": "2026-03-20T00:00:00Z", "endDate": "2026-05-05T00:00:00Z"},
        {"id": "t3", "name": "OWCS Korea Preseason Bootcamp", "startDate": "2026-03-01T00:00:00Z", "endDate": "2026-03-25T00:00:00Z"},
        {"id": "t4", "name": "OWCS 2026 Korea Stage 2", "startDate": "2026-07-01T00:00:00Z", "endDate": "2026-08-01T00:00:00Z"},
    ],
    "tournament-phase": [{"id": "p1", "tournament": "t1"}, {"id": "p2", "tournament": "t2"}],
    "team": [
        {"id": "A", "name": "Alpha Esports", "initials": "ALP"},
        {"id": "B", "name": "Bravo", "initials": "BRV"},
        {"id": "C", "name": "Charlie Gaming Global", "initials": "CG"},  # resolves through an alias
        {"id": "D", "name": "Delta Unknown", "initials": "DU"},  # not one of ours
    ],
    "match": [
        {"id": "m1", "slug": "a-vs-b", "tournamentPhase": "p1", "team1": "A", "team2": "B", "startDate": "2026-04-01T10:00:00Z"},
        {"id": "m2", "slug": "b-vs-c", "tournamentPhase": "p1", "team1": "B", "team2": "C", "startDate": "2026-04-02T10:00:00Z"},
        {"id": "m3", "slug": "a-vs-c", "tournamentPhase": "p1", "team1": "A", "team2": "C", "startDate": "2026-04-10T10:00:00Z"},
        {"id": "m4", "slug": "d-vs-a", "tournamentPhase": "p1", "team1": "D", "team2": "A", "startDate": "2026-04-05T10:00:00Z"},
        {"id": "m9", "slug": "japan", "tournamentPhase": "p2", "team1": "A", "team2": "B", "startDate": "2026-04-01T10:00:00Z"},
    ],
    "game-map": [{"id": "g1", "name": "Lijiang Tower"}, {"id": "g2", "name": "Runasapi"}, {"id": "g3", "name": "Havana"}],
    "game-hero": [{"id": "h1", "name": "Ana"}],
    "match-map": [
        {"id": "mm1", "match": "m1", "mapIndex": 0, "map": "g1", "replayParsed": True, "team1Ban": "h1",
         "eventLog": json.dumps([{"type": "kill", "t": 1.0}, {"type": "hero_swap", "t": 2.0}])},
        {"id": "mm2", "match": "m1", "mapIndex": 1, "map": "g2", "replayParsed": "pending", "eventLog": None},
        {"id": "mm3", "match": "m2", "mapIndex": 0, "map": "g3", "replayParsed": True,
         "eventLog": {"version": 1, "events": [{"type": "kill"}]}},
        {"id": "mm4", "match": "m2", "mapIndex": 1, "map": "g1", "replayParsed": False, "eventLog": []},
    ],
    "map-fight": [{"id": "f1", "matchMap": "mm1", "fightNumber": 1, "eventLog": [{"type": "kill"}]}],
    "player-map-stats": [{"id": "ps1", "matchMap": "mm1", "deaths": 3, "eliminations": 10},
                         {"id": "ps2", "matchMap": "mm3", "deaths": 0, "eliminations": ""}],
    "player-map-stats-hero": [{"id": "hs1", "playerMapStats": "ps1", "hero": "h1", "playtime": 300}],
}  # fmt: skip


class FakeResponse:
    def __init__(self, status, content):
        self.status_code, self.content = status, content


class FakeOwtv:
    """Answers like OWTV's list and item endpoints (equals/in filters, pages)."""

    def __init__(self):
        self.calls = []
        self.bodies = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        if (headers or {}).get("X-API-Key") != KEY:
            return FakeResponse(403, b"{}")
        parts = urlsplit(url).path.split("/")[2:]  # /api/<collection>[/<id>]
        docs = DATA[parts[0]]
        if len(parts) == 2:
            body = json.dumps(next(d for d in docs if d["id"] == parts[1])).encode()
        else:
            p = dict(params)
            for k, v in p.items():
                if k.startswith("where["):
                    name, op = k[6:-1].split("][")
                    allowed = set(str(v).split(",")) if op == "in" else {str(v)}
                    docs = [d for d in docs if str(d.get(name)) in allowed]
            limit, page = int(p.get("limit", 10)), int(p.get("page", 1))
            chunk = docs[(page - 1) * limit:page * limit]
            body = json.dumps({"docs": chunk, "totalDocs": len(docs), "page": page,
                               "hasNextPage": page * limit < len(docs)}).encode()  # fmt: skip
        self.bodies.append(body)
        return FakeResponse(200, body)


class FakeClock:
    def __init__(self):
        self.now, self.slept = 100.0, []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(s)
        self.now += s


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


@pytest.fixture
def data_dir(tmp_path):
    d = tmp_path / "data"
    cat, ent = d / "interim" / "catalog", d / "interim" / "entities"
    _write(cat / "series.csv", "series_id,region,stage,start_utc,local_date,team_a_id,team_b_id\n"
           "s1,Korea,Stage 1,2026-04-01T10:00:00Z,2026-04-01,team:alpha,team:bravo\n"
           "s2,Korea,Stage 1,2026-04-03T01:00:00Z,2026-04-03,team:charlie,team:bravo\n"
           "s3,Korea,Stage 1,2026-04-12T10:00:00Z,2026-04-12,team:alpha,team:charlie\n"
           "x1,Japan,Stage 1,2026-04-01T10:00:00Z,2026-04-01,team:alpha,team:bravo\n")
    _write(cat / "maps.csv", "map_id,series_id,map_number,map_ref,mode_id\n"
           "s1-m1,s1,1,map:lijiang_tower,control\ns1-m2,s1,2,map:runasapi,push\n"
           "s2-m1,s2,1,map:havana,escort\ns2-m2,s2,2,map:ilios,control\ns3-m1,s3,1,map:numbani,hybrid\n")
    _write(ent / "teams.csv", "team_id,name\nteam:alpha,Alpha Esports\nteam:bravo,Bravo\nteam:charlie,Charlie\n")
    _write(ent / "aliases.csv", "entity_type,alias,stable_id,valid_from,valid_to,source\nteam,CG,team:charlie,,,manual\n")
    return d


def _api(tmp_path, key=KEY):
    server, clock = FakeOwtv(), FakeClock()
    client = HttpClient({"owtv.gg": 5.0}, tmp_path / "cache", "researcher@example.org",
                        session=server, clock=clock.clock, sleep=clock.sleep)  # fmt: skip
    return OwtvApi(client, key), server, clock


def _rows(path: Path) -> list[dict]:
    import csv

    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_probe_pairs_series_and_measures_coverage(tmp_path, data_dir, monkeypatch):
    monkeypatch.setattr(owtv, "PAGE_LIMIT", 2)  # forces several pages
    api, server, clock = _api(tmp_path)
    res = run_probe(api, data_dir, SCOPE, date="2026-11-17")

    assert [t["id"] for t in res.tournaments] == ["t1"]  # Japan, bootcamp and Stage 2 left out
    pairs = {r["series_id"]: (r["result"], r.get("owtv_match_id", "")) for r in res.series_rows}
    assert pairs == {"s1": ("matched", "m1"), "s2": ("matched", "m2"), "s3": ("none", "")}  # s3: 2 days apart

    cov = {(r["series_id"], r["map_number"]): r for r in _rows(res.out_dir / "map_coverage.csv")}
    assert len(cov) == 4
    assert [cov[k]["replay_parsed"] for k in sorted(cov)] == ["true", "false", "true", "false"]
    assert [cov[k]["has_event_log"] for k in sorted(cov)] == ["true", "false", "true", "false"]
    assert cov[("s1", "1")]["event_log_items"] == "2" and cov[("s1", "1")]["has_bans"] == "true"
    assert cov[("s1", "2")]["same_map"] == "true" and cov[("s2", "2")]["same_map"] == "false"

    assert res.sample == ["s1", "s2"]  # Control and Escort; no unpicked Push/Flashpoint series left
    summary = (res.out_dir / "summary.md").read_text(encoding="utf-8")
    assert "Maps with a parsed replay:** 2/4 (50%)" in summary
    assert "`type=kill` 2" in summary and "Delta Unknown" in summary
    assert "`deaths`: 2/2 (100%)" in summary and "`eliminations`: 1/2 (50%)" in summary


def test_key_sent_but_never_saved_and_answers_kept_byte_for_byte(tmp_path, data_dir):
    api, server, clock = _api(tmp_path)
    res = run_probe(api, data_dir, SCOPE, date="2026-11-17")
    assert all(h["X-API-Key"] == KEY for _, _, h in server.calls)
    saved = sorted((res.out_dir / "responses").glob("*.json"))
    assert [p.read_bytes() for p in saved] == server.bodies
    for p in [*res.out_dir.rglob("*"), *(tmp_path / "cache").rglob("*")]:
        if p.is_file():
            assert KEY.encode() not in p.read_bytes(), p
    # one request every 5 s at most (OWTV allows 60 a minute)
    assert len(clock.slept) == len(server.calls) - 1 and all(s == pytest.approx(5.0) for s in clock.slept)


def test_rerun_uses_the_cache(tmp_path, data_dir):
    api, server, _ = _api(tmp_path)
    run_probe(api, data_dir, SCOPE, date="2026-11-17")
    sent = len(server.calls)
    api2 = OwtvApi(api.client, KEY)
    run_probe(api2, data_dir, SCOPE, date="2026-11-17")
    assert len(server.calls) == sent and all(a.from_cache for a in api2.answers)


def test_given_series_and_tournament(tmp_path, data_dir):
    api, server, _ = _api(tmp_path)
    res = run_probe(api, data_dir, SCOPE, series_ids=["s2"], tournament_ids=["t1"], date="2026-11-17")
    assert res.sample == ["s2"]
    assert not any(urlsplit(u).path == "/api/tournament" for u, _, _ in server.calls)  # no search
    with pytest.raises(UsageError):
        run_probe(api, data_dir, SCOPE, series_ids=["x1"])  # Japan isn't in the pilot scope


def test_wrong_key_stops(tmp_path, data_dir):
    api, _, _ = _api(tmp_path, key="wrong")
    with pytest.raises(RetrievalBlocked):
        run_probe(api, data_dir, SCOPE)
    with pytest.raises(RetrievalBlocked):
        _api(tmp_path, key="")


def test_describe_event_logs_handles_row_lists():
    d = describe_event_logs([[["kill", 1.0], ["kill", 2.0], ["swap", 3.0]], None, "", "not json"])
    assert d["items"] == 3 and d["event_types"] == {"[0]=kill": 2, "[0]=swap": 1}


def test_cli_without_key_exits_3(tmp_path, data_dir, capsys):
    conf = tmp_path / "conf"
    shutil.copytree(REPO / "configs" / "collect", conf, ignore=shutil.ignore_patterns("local.yaml"))
    code = main(["refs", "probe-owtv", "--config", str(conf / "default.yaml"), "--data-dir", str(data_dir)])
    assert code == 3 and "owtv_api_key" in capsys.readouterr().err

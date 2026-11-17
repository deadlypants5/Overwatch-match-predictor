"""Command-line shell, polite web client and dated snapshots (T017-T019)."""

from __future__ import annotations

from pathlib import Path

import pytest

from owstudy.collect.cli import COMMANDS, HANDLERS, build_parser, main, resolve_scope
from owstudy.collect.config import load_config
from owstudy.collect.errors import RetrievalBlocked, UsageError, ValidationError
from owstudy.collect.refs.ratelimit import HttpClient
from owstudy.collect.refs.snapshot import diff_snapshots, latest_snapshot, new_snapshot, write_diff_report

REPO = Path(__file__).resolve().parents[3]
DEFAULT = REPO / "configs" / "collect" / "default.yaml"


# --- command line ----------------------------------------------------------------------


@pytest.fixture
def cfg(tmp_path):
    return load_config(DEFAULT, local_path=tmp_path / "none.yaml")


def test_scope_resolution(cfg):
    assert resolve_scope(cfg, "pilot") == ["Asia/Stage 1/Korea"]
    assert resolve_scope(cfg, "all") == ["Asia/Stage 1/Korea"]
    with pytest.raises(UsageError, match="approved"):
        resolve_scope(cfg, "NA/Stage 1")
    assert resolve_scope(cfg, "NA/Stage 1", force=True) == ["NA/Stage 1"]


@pytest.mark.parametrize("path,_help,task,_setup", [c for c in COMMANDS if c[0] not in HANDLERS])
def test_unbuilt_commands_name_their_task(path, _help, task, _setup, capsys, tmp_path):
    extra = {
        ("refs", "fetch"): ["liquipedia"], ("refs", "import-sheet"): ["sheet.xlsx"],
        ("plant-errors",): ["--maps", "1", "--out", "x"],
        ("extract",): [], ("review",): [], ("export",): [],  # options only
    }.get(path, ["x"] if _setup else [])  # fmt: skip
    code = main(["--config", str(DEFAULT), "--data-dir", str(tmp_path), *path, *extra])
    assert code == 2
    assert task in capsys.readouterr().err


def test_unapproved_scope_is_usage_error(capsys):
    assert main(["--config", str(DEFAULT), "--scope", "EMEA/Stage 1", "status"]) == 2
    assert "approved" in capsys.readouterr().err


def test_options_also_work_after_the_command(capsys):
    # `status --scope ...` must behave like `--scope ... status` (both orders are documented).
    assert main(["status", "--config", str(DEFAULT), "--scope", "EMEA/Stage 1"]) == 2
    assert "approved" in capsys.readouterr().err
    args = build_parser().parse_args(["--scope", "all", "catalog", "build"])
    assert args.scope == "all"  # not reset by the command's own (unused) --scope
    args = build_parser().parse_args(["catalog", "build", "--scope", "all", "-v"])
    assert args.scope == "all" and args.verbose == 1


def test_bad_config_path_is_config_error(tmp_path):
    assert main(["--config", str(tmp_path / "missing.yaml"), "status"]) == 2


def test_help_exits_zero(capsys):
    assert main(["--help"]) == 0
    assert "catalog" in capsys.readouterr().out


# --- web client ------------------------------------------------------------------------


class FakeResponse:
    def __init__(self, status, content=b"{}"):
        self.status_code = status
        self.content = content


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


class FakeClock:
    def __init__(self):
        self.now = 100.0
        self.slept = []

    def clock(self):
        return self.now

    def sleep(self, s):
        self.slept.append(round(s, 3))
        self.now += s


def _client(tmp_path, responses, contact="researcher@example.org"):
    clock = FakeClock()
    session = FakeSession(responses)
    client = HttpClient({"liquipedia.net": 2.0, "owtv.gg": 5.0}, tmp_path / "cache", contact,
                        session=session, clock=clock.clock, sleep=clock.sleep)  # fmt: skip
    return client, session, clock


def test_requests_spaced_per_host_and_headers_sent(tmp_path):
    client, session, clock = _client(tmp_path, [FakeResponse(200, b"a"), FakeResponse(200, b"b"), FakeResponse(200)])
    client.get("https://liquipedia.net/overwatch/api.php", {"page": "A"})
    clock.now += 0.5
    client.get("https://liquipedia.net/overwatch/api.php", {"page": "B"})
    client.get("https://owtv.gg/api/x")  # a different host doesn't wait
    assert clock.slept == [1.5]
    ua = session.calls[0][2]["User-Agent"]
    assert "researcher@example.org" in ua
    assert session.calls[0][2]["Accept-Encoding"] == "gzip"


def test_responses_cached_on_disk(tmp_path):
    client, session, _ = _client(tmp_path, [FakeResponse(200, b'{"x": 1}')])
    first = client.get("https://liquipedia.net/api", {"b": 2, "a": 1})
    again = client.get("https://liquipedia.net/api", {"a": 1, "b": 2})
    assert not first.from_cache and again.from_cache
    assert again.json() == {"x": 1}
    assert len(session.calls) == 1


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limit_or_refusal_blocks(tmp_path, status):
    client, _, _ = _client(tmp_path, [FakeResponse(status)])
    with pytest.raises(RetrievalBlocked, match=str(status)):
        client.get("https://liquipedia.net/api")
    assert not (tmp_path / "cache").exists() or not any((tmp_path / "cache").iterdir())


def test_network_error_blocks(tmp_path):
    client, _, _ = _client(tmp_path, [ConnectionError("offline")])
    with pytest.raises(RetrievalBlocked, match="offline"):
        client.get("https://liquipedia.net/api")


@pytest.mark.parametrize("contact", ["", "<contact for Liquipedia API User-Agent>"])
def test_missing_contact_blocks(tmp_path, contact):
    with pytest.raises(RetrievalBlocked, match="user_agent_contact"):
        _client(tmp_path, [], contact=contact)


def test_unconfigured_host_refused(tmp_path):
    client, session, _ = _client(tmp_path, [FakeResponse(200)])
    with pytest.raises(RetrievalBlocked, match="no rate limit"):
        client.get("https://example.com/")
    assert session.calls == []


# --- snapshots -------------------------------------------------------------------------


def test_new_snapshot_refuses_existing(tmp_path):
    folder = new_snapshot("liquipedia", "2026-11-20", root=tmp_path)
    assert folder == tmp_path / "liquipedia" / "2026-11-20"
    with pytest.raises(ValidationError, match="already exists"):
        new_snapshot("liquipedia", "2026-11-20", root=tmp_path)
    with pytest.raises(UsageError):
        new_snapshot("reddit", "2026-11-20", root=tmp_path)


def test_latest_and_pinned_snapshot(tmp_path):
    for d in ("2026-11-15", "2026-12-01", "2026-11-20"):
        new_snapshot("youtube", d, root=tmp_path)
    (tmp_path / "youtube" / "notes").mkdir()
    assert latest_snapshot("youtube", root=tmp_path).name == "2026-12-01"
    assert latest_snapshot("youtube", pinned="2026-11-15", root=tmp_path).name == "2026-11-15"
    with pytest.raises(UsageError):
        latest_snapshot("owtv", root=tmp_path)


def test_repo_snapshots_found():
    assert latest_snapshot("liquipedia", root=REPO / "data" / "raw" / "reference").name == "2026-11-15"


def test_diff_snapshots(tmp_path):
    old = tmp_path / "old.csv"
    new = tmp_path / "new.csv"
    old.write_text("series_key,score1,score2\na,3,1\nb,2,3\nc,3,0\n", encoding="utf-8")
    new.write_text("series_key,score1,score2\na,3,1\nb,3,2\nd,3,2\n", encoding="utf-8")
    diff = diff_snapshots(old, new, ["series_key"])
    assert list(zip(diff["series_key"], diff["change"], diff["changed_fields"])) == [
        ("b", "changed", "score1;score2"), ("c", "removed", ""), ("d", "added", ""),
    ]  # fmt: skip
    row_b = diff[diff["series_key"] == "b"].iloc[0]
    assert (row_b["old_score1"], row_b["new_score1"]) == ("2", "3")
    moved = tmp_path / "moved.csv"  # same values, different locator: not a change
    moved.write_text("series_key,score1,score2,locator\na,3,1,x!2\nb,2,3,x!3\nc,3,0,x!9\n", encoding="utf-8")
    assert diff_snapshots(old, moved, ["series_key"], ignore=["locator"]).empty
    report = write_diff_report(diff, "liquipedia", "2026-11-20", tmp_path / "reports", ["series_key"])
    assert report.name == "snapshot_diff_liquipedia_2026-11-20.csv"
    assert b"\r" not in report.read_bytes()

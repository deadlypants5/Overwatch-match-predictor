"""T013: deterministic tables, append-only files and folder fingerprints."""

from __future__ import annotations

import json

import pandas as pd
import pytest

from owstudy.collect.errors import ValidationError
from owstudy.collect.io.manifest import (
    snapshot_json,
    verify_folder,
    verify_snapshot,
    write_folder_manifest,
    write_run_json,
)
from owstudy.collect.io.tables import append_rows, read_table, write_table

COLS = ["map_id", "n", "conf", "flag", "note"]
KEY = ["map_id", "n"]
DEC = {"conf": 3}
ROWS = [
    {"map_id": "m2", "n": 10, "conf": 0.5, "flag": True, "note": "x"},
    {"map_id": "m1", "n": 2, "conf": 0.91234, "flag": False, "note": None},
    {"map_id": "m1", "n": 10, "conf": 1.0, "flag": False, "note": 'has, comma "and quote"'},
]


def test_same_rows_give_identical_bytes_without_cr(tmp_path):
    a = write_table(ROWS, tmp_path / "a.csv", COLS, KEY, DEC).read_bytes()
    b = write_table(list(reversed(ROWS)), tmp_path / "b.csv", COLS, KEY, DEC).read_bytes()
    assert a == b
    assert b"\r" not in a
    assert a.endswith(b"\n")


def test_rows_sorted_by_key_numerically(tmp_path):
    p = write_table(ROWS, tmp_path / "t.csv", COLS, KEY, DEC)
    lines = p.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(COLS)
    assert [line.split(",")[:2] for line in lines[1:]] == [["m1", "2"], ["m1", "10"], ["m2", "10"]]


def test_fixed_decimals_bools_and_missing(tmp_path):
    p = write_table(ROWS, tmp_path / "t.csv", COLS, KEY, DEC)
    text = p.read_text(encoding="utf-8")
    assert "m1,2,0.912,false,\n" in text
    assert "m2,10,0.500,true,x\n" in text
    assert '"has, comma ""and quote"""' in text


def test_negative_zero_written_as_zero(tmp_path):
    p = write_table([{"map_id": "m", "n": 1, "conf": -0.0001}], tmp_path / "t.csv", COLS, KEY, DEC)
    assert "m,1,0.000," in p.read_text(encoding="utf-8")


def test_dataframe_input_matches_rows(tmp_path):
    a = write_table(ROWS, tmp_path / "a.csv", COLS, KEY, DEC).read_bytes()
    b = write_table(pd.DataFrame(ROWS), tmp_path / "b.csv", COLS, KEY, DEC).read_bytes()
    assert a == b


def test_float_without_decimals_rejected(tmp_path):
    with pytest.raises(ValidationError, match="decimal"):
        write_table(ROWS, tmp_path / "t.csv", COLS, KEY, {})


def test_duplicate_key_rejected(tmp_path):
    with pytest.raises(ValidationError, match="duplicate key"):
        write_table(ROWS + [ROWS[0]], tmp_path / "t.csv", COLS, KEY, DEC)


def test_unknown_column_rejected(tmp_path):
    with pytest.raises(ValidationError, match="unknown column"):
        write_table([{"map_id": "m", "n": 1, "extra": 1}], tmp_path / "t.csv", COLS, KEY, DEC)


def test_read_table_checks_columns(tmp_path):
    p = write_table(ROWS, tmp_path / "t.csv", COLS, KEY, DEC)
    df = read_table(p, COLS)
    assert df.loc[0, "note"] == "" and df.loc[0, "conf"] == "0.912"
    with pytest.raises(ValidationError, match="missing"):
        read_table(p, COLS + ["other"])
    with pytest.raises(ValidationError, match="unknown"):
        read_table(p, COLS[:-1])


# --- append-only ----------------------------------------------------------------------


def test_append_keeps_earlier_lines(tmp_path):
    p = tmp_path / "decisions.csv"
    append_rows(p, COLS, ROWS[:1], DEC)
    before = p.read_bytes()
    append_rows(p, COLS, ROWS[1:], DEC)
    after = p.read_bytes()
    assert after.startswith(before)
    assert len(after.splitlines()) == 1 + len(ROWS)
    assert b"\r" not in after


def test_append_refuses_header_mismatch(tmp_path):
    p = tmp_path / "decisions.csv"
    append_rows(p, COLS, ROWS[:1], DEC)
    with pytest.raises(ValidationError, match="header"):
        append_rows(p, list(reversed(COLS)), ROWS[1:], DEC)


def test_append_refuses_incomplete_last_line(tmp_path):
    p = tmp_path / "decisions.csv"
    append_rows(p, COLS, ROWS[:1], DEC)
    p.write_bytes(p.read_bytes().rstrip(b"\n"))
    with pytest.raises(ValidationError, match="incomplete"):
        append_rows(p, COLS, ROWS[1:], DEC)


# --- manifests ------------------------------------------------------------------------


def test_verify_folder_reports_edit_missing_and_added(tmp_path):
    (tmp_path / "readings.csv").write_text("a\n1\n", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "kills.csv").write_text("b\n2\n", encoding="utf-8")
    write_folder_manifest(tmp_path)
    assert verify_folder(tmp_path) == []

    (tmp_path / "readings.csv").write_text("a\n9\n", encoding="utf-8")
    (tmp_path / "sub" / "kills.csv").unlink()
    (tmp_path / "new.csv").write_text("c\n", encoding="utf-8")
    assert verify_folder(tmp_path) == ["changed: readings.csv", "missing: sub/kills.csv", "added: new.csv"]


def test_run_json_fields_checked(tmp_path):
    from owstudy.collect.io.manifest import RUN_FIELDS

    run = {k: None for k in RUN_FIELDS}
    run["run_id"] = "r1"
    p = write_run_json(tmp_path, run)
    assert list(json.loads(p.read_text(encoding="utf-8"))) == list(RUN_FIELDS)
    with pytest.raises(ValidationError):
        write_run_json(tmp_path, {**run, "surprise": 1})
    with pytest.raises(ValidationError):
        write_run_json(tmp_path, {k: v for k, v in run.items() if k != "outcome"})


def test_snapshot_json_round_trip(tmp_path):
    (tmp_path / "lp_series.csv").write_bytes(b"a,b\r\n1,2\r\n")
    snapshot_json(tmp_path, "liquipedia", "2026-11-20", "test")
    meta = json.loads((tmp_path / "snapshot.json").read_text(encoding="utf-8"))
    assert [f["path"] for f in meta["files"]] == ["lp_series.csv"]
    assert verify_snapshot(tmp_path) == []
    (tmp_path / "lp_series.csv").write_bytes(b"a,b\n1,2\n")  # line endings alone count as a change
    assert verify_snapshot(tmp_path) == ["changed: lp_series.csv"]

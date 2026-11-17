"""Dated snapshots of reference data, and the differences between two snapshots.

Each retrieval goes into a new folder `data/raw/reference/<source>/<YYYY-MM-DD>/` that is
never edited afterwards (FR-001).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from pathlib import Path

from owstudy.collect.errors import UsageError, ValidationError

REFERENCE_ROOT = Path("data/raw/reference")
SOURCES = ("liquipedia", "spreadsheet", "owtv", "youtube", "youtube_details")
DIFF_COLUMNS_FIXED = ("change", "changed_fields")


def _date_text(date: str | dt.date) -> str:
    text = date.isoformat() if isinstance(date, dt.date) else str(date)
    try:
        dt.date.fromisoformat(text)
    except ValueError:
        raise UsageError(f"snapshot date must look like 2026-11-15, not {text!r}") from None
    return text


def _check_source(source: str) -> None:
    if source not in SOURCES:
        raise UsageError(f"unknown reference source {source!r}; expected one of {', '.join(SOURCES)}")


def new_snapshot(source: str, date: str | dt.date, root: str | Path = REFERENCE_ROOT) -> Path:
    """Create the empty folder for a new snapshot. Refuses if that date's folder exists."""
    _check_source(source)
    folder = Path(root) / source / _date_text(date)
    if folder.exists():
        raise ValidationError(f"snapshot {folder} already exists; snapshots are never overwritten")
    folder.mkdir(parents=True)
    return folder


def list_snapshots(source: str, root: str | Path = REFERENCE_ROOT) -> list[Path]:
    """Snapshot folders for a source, oldest first."""
    _check_source(source)
    base = Path(root) / source
    if not base.exists():
        return []
    out = []
    for p in base.iterdir():
        if p.is_dir():
            try:
                dt.date.fromisoformat(p.name)
            except ValueError:
                continue
            out.append(p)
    return sorted(out, key=lambda p: p.name)


def latest_snapshot(source: str, pinned: str | None = None, root: str | Path = REFERENCE_ROOT) -> Path:
    """The newest snapshot, or the pinned one (by date) if given."""
    snaps = list_snapshots(source, root)
    if pinned is not None:
        for p in snaps:
            if p.name == _date_text(pinned):
                return p
        raise UsageError(f"no {source} snapshot dated {pinned}")
    if not snaps:
        raise UsageError(f"no {source} snapshot yet under {Path(root) / source}")
    return snaps[-1]


def diff_snapshots(old_csv: str | Path, new_csv: str | Path, key_columns: Sequence[str], ignore: Sequence[str] = ()):
    """Records added, removed or changed between two versions of the same table.

    Returns a DataFrame with `change` (added / removed / changed), `changed_fields`
    (`;`-separated), the key columns, then `old_<col>` / `new_<col>` for every other column.
    Columns in `ignore` (e.g. `locator`, which says where a record sits, not what it says)
    aren't compared.
    """
    import pandas as pd

    from owstudy.collect.io.tables import read_table

    old = read_table(old_csv, required=key_columns)
    new = read_table(new_csv, required=key_columns)
    old = old.drop(columns=[c for c in ignore if c in old.columns])
    new = new.drop(columns=[c for c in ignore if c in new.columns])
    for name, df in (("old", old), ("new", new)):
        if df.duplicated(list(key_columns)).any():
            raise ValidationError(f"{name} table has duplicate keys over {list(key_columns)}")
    values = sorted((set(old.columns) | set(new.columns)) - set(key_columns))
    for df in (old, new):
        for c in values:
            if c not in df.columns:
                df[c] = ""

    merged = old.merge(new, on=list(key_columns), how="outer", suffixes=("_old", "_new"), indicator=True)
    rows = []
    for r in merged.to_dict(orient="records"):
        if r["_merge"] == "left_only":
            change, fields = "removed", []
        elif r["_merge"] == "right_only":
            change, fields = "added", []
        else:
            fields = [c for c in values if r[f"{c}_old"] != r[f"{c}_new"]]
            if not fields:
                continue
            change = "changed"
        row = {"change": change, "changed_fields": ";".join(fields)}
        row.update({k: r[k] for k in key_columns})
        for c in values:
            row[f"old_{c}"] = "" if change == "added" else r[f"{c}_old"]
            row[f"new_{c}"] = "" if change == "removed" else r[f"{c}_new"]
        rows.append(row)
    columns = [*DIFF_COLUMNS_FIXED, *key_columns, *[f"{p}_{c}" for c in values for p in ("old", "new")]]
    out = pd.DataFrame(rows, columns=columns)
    return out.sort_values(list(key_columns), kind="stable").reset_index(drop=True)


def write_diff_report(diff, source: str, date: str | dt.date, reports_dir: str | Path, key_columns: Sequence[str]) -> Path:
    """Save a diff as data/interim/reports/snapshot_diff_<source>_<date>.csv."""
    from owstudy.collect.io.tables import write_table

    path = Path(reports_dir) / f"snapshot_diff_{source}_{_date_text(date)}.csv"
    return write_table(diff, path, list(diff.columns), key=list(key_columns))

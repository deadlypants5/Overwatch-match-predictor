"""Write and read CSV tables the same way every time (contracts/storage-layout.md).

Rules: UTF-8, header row, `,` separator, `\\n` line endings, empty cell = missing, rows sorted by
the table's key, fixed decimals per float column, `true`/`false` for booleans. The same rows
always give byte-identical files.
"""

from __future__ import annotations

import csv
import io
import math
import os
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from owstudy.collect.errors import ValidationError

Row = Mapping[str, Any]


def _is_missing(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    try:  # pandas NA / NaT
        import pandas as pd

        return v is pd.NA or v is pd.NaT
    except ImportError:  # pragma: no cover
        return False


def format_value(v: Any, col: str, decimals: Mapping[str, int]) -> str:
    """One cell as text, following the shared rules."""
    if _is_missing(v):
        return ""
    if isinstance(v, bool) or type(v).__name__ == "bool_":
        return "true" if v else "false"
    if isinstance(v, float) or type(v).__name__.startswith("float"):
        if col not in decimals:
            raise ValidationError(f"column {col!r} holds decimals but has no fixed decimal places set")
        text = f"{float(v):.{decimals[col]}f}"
        return "0" + text[2:] if text.startswith("-0") and float(text) == 0 else text  # no "-0.00"
    if col in decimals and isinstance(v, int):
        return f"{v:.{decimals[col]}f}"
    return str(v)


def _sort_key(v: Any) -> tuple:
    if _is_missing(v):
        return (2, "")
    if isinstance(v, bool):
        return (0, int(v))
    if isinstance(v, (int, float)) or type(v).__name__.startswith(("int", "float")):
        return (0, float(v))
    return (1, str(v))


def _to_rows(rows_or_df: Any) -> list[dict[str, Any]]:
    if hasattr(rows_or_df, "to_dict") and hasattr(rows_or_df, "columns"):
        return rows_or_df.to_dict(orient="records")
    return [dict(r) for r in rows_or_df]


def _encode(lines: Iterable[Sequence[str]]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    w.writerows(lines)
    return buf.getvalue().encode("utf-8")


def _check_columns(rows: list[dict[str, Any]], columns: Sequence[str], where: str) -> None:
    if len(set(columns)) != len(columns):
        raise ValidationError(f"{where}: duplicate column names")
    allowed = set(columns)
    for r in rows:
        extra = set(r) - allowed
        if extra:
            raise ValidationError(f"{where}: unknown column(s) {sorted(extra)}")


def write_table(
    rows_or_df: Any,
    path: str | Path,
    columns: Sequence[str],
    key: Sequence[str],
    decimals: Mapping[str, int] | None = None,
) -> Path:
    """Write a table sorted by `key`. Missing columns in a row are empty cells.

    Raises ValidationError for unknown columns, a missing key value, a duplicate key, or a
    float column without fixed decimals. The file is replaced in one step.
    """
    path = Path(path)
    decimals = dict(decimals or {})
    rows = _to_rows(rows_or_df)
    _check_columns(rows, columns, str(path))
    missing_key = [k for k in key if k not in columns]
    if missing_key:
        raise ValidationError(f"{path}: key column(s) {missing_key} not in columns")

    seen: set[tuple] = set()
    for r in rows:
        k = tuple(_sort_key(r.get(c)) for c in key)
        if any(part[0] == 2 for part in k):
            raise ValidationError(f"{path}: row with an empty key value: {r}")
        if k in seen:
            raise ValidationError(f"{path}: duplicate key {tuple(r.get(c) for c in key)}")
        seen.add(k)
    rows.sort(key=lambda r: tuple(_sort_key(r.get(c)) for c in key))

    lines = [list(columns)] + [[format_value(r.get(c), c, decimals) for c in columns] for r in rows]
    data = _encode(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)
    return path


def read_table(path: str | Path, columns: Sequence[str] | None = None, required: Sequence[str] | None = None):
    """Read a table as text (a pandas DataFrame of strings; empty cell = "").

    With `columns`, the header must contain exactly those columns (in any order); unknown or
    missing columns are a ValidationError. With only `required`, extra columns are allowed.
    """
    import pandas as pd

    path = Path(path)
    if not path.exists():
        raise ValidationError(f"table not found: {path}")
    df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8")
    header = list(df.columns)
    if columns is not None:
        unknown = sorted(set(header) - set(columns))
        missing = sorted(set(columns) - set(header))
        if unknown or missing:
            raise ValidationError(f"{path}: unknown column(s) {unknown}, missing column(s) {missing}")
        df = df[list(columns)]
    if required is not None:
        missing = sorted(set(required) - set(header))
        if missing:
            raise ValidationError(f"{path}: missing column(s) {missing}")
    return df


def append_rows(
    path: str | Path,
    columns: Sequence[str],
    rows: Iterable[Row],
    decimals: Mapping[str, int] | None = None,
) -> int:
    """Add rows to the end of an append-only file, never touching earlier lines.

    Creates the file with a header if it doesn't exist. Refuses if the existing header differs.
    Returns the number of rows added.
    """
    path = Path(path)
    decimals = dict(decimals or {})
    rows = [dict(r) for r in rows]
    _check_columns(rows, columns, str(path))
    header = _encode([list(columns)])
    body = _encode([[format_value(r.get(c), c, decimals) for c in columns] for r in rows])

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(header + body)
        return len(rows)

    with open(path, "rb") as f:
        first = f.readline()
    if first != header:
        raise ValidationError(f"{path}: existing header {first!r} doesn't match {header!r}")
    if not rows:
        return 0
    with open(path, "rb+") as f:
        f.seek(0, os.SEEK_END)
        if f.tell() > 0:
            f.seek(-1, os.SEEK_END)
            if f.read(1) != b"\n":
                raise ValidationError(f"{path}: last line is incomplete; refusing to append")
        f.write(body)
    return len(rows)

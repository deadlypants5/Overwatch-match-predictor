"""File fingerprints for raw folders: run.json, MANIFEST.sha256 and snapshot.json.

Raw folders are never edited (FR-001). A manifest lists the SHA-256 of every file so that any
later change is caught by `verify_folder`.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from owstudy.collect.errors import ValidationError

MANIFEST = "MANIFEST.sha256"
SNAPSHOT = "snapshot.json"

# contracts/storage-layout.md §run.json, in this order.
RUN_FIELDS = (
    "run_id", "video_id", "extraction_key", "extractor_version", "layout_id", "icon_lib_hash",
    "ocr_model_hash", "sampling", "video_sha256", "format_id", "resolution", "started_at",
    "finished_at", "frames_sampled", "frames_with_hud", "outcome", "error",
)  # fmt: skip


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _dump_json(data: Any) -> bytes:
    return (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _files_in(folder: Path, skip: set[str]) -> list[Path]:
    return sorted(
        (p for p in folder.rglob("*") if p.is_file() and p.relative_to(folder).as_posix() not in skip),
        key=lambda p: p.relative_to(folder).as_posix(),
    )


def write_run_json(folder: str | Path, run: Mapping[str, Any]) -> Path:
    """Write run.json with exactly the fields in the storage contract."""
    unknown = sorted(set(run) - set(RUN_FIELDS))
    missing = sorted(set(RUN_FIELDS) - set(run))
    if unknown or missing:
        raise ValidationError(f"run.json: unknown field(s) {unknown}, missing field(s) {missing}")
    path = Path(folder) / "run.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_dump_json({k: run[k] for k in RUN_FIELDS}))
    return path


def write_folder_manifest(folder: str | Path) -> Path:
    """Write MANIFEST.sha256 listing every other file in the folder (sorted by path)."""
    folder = Path(folder)
    lines = [f"{sha256_file(p)}  {p.relative_to(folder).as_posix()}\n" for p in _files_in(folder, {MANIFEST})]
    path = folder / MANIFEST
    path.write_bytes("".join(lines).encode("utf-8"))
    return path


def read_manifest(folder: str | Path) -> dict[str, str]:
    path = Path(folder) / MANIFEST
    if not path.exists():
        raise ValidationError(f"no {MANIFEST} in {folder}")
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        digest, _, name = line.partition("  ")
        out[name] = digest
    return out


def verify_folder(folder: str | Path) -> list[str]:
    """Problems found by comparing the folder with its MANIFEST.sha256 (empty = all fine).

    Each problem is "changed: <file>", "missing: <file>" or "added: <file>".
    """
    folder = Path(folder)
    listed = read_manifest(folder)
    problems = []
    for name, digest in sorted(listed.items()):
        p = folder / name
        if not p.exists():
            problems.append(f"missing: {name}")
        elif sha256_file(p) != digest:
            problems.append(f"changed: {name}")
    for p in _files_in(folder, {MANIFEST}):
        name = p.relative_to(folder).as_posix()
        if name not in listed:
            problems.append(f"added: {name}")
    return problems


def snapshot_json(
    folder: str | Path,
    source: str,
    retrieved_at: str,
    tool: str,
    files: Sequence[str] | None = None,
    description: str | None = None,
) -> Path:
    """Write snapshot.json: where a reference snapshot came from and a fingerprint per file.

    `files` defaults to every file in the folder (except snapshot.json itself).
    """
    folder = Path(folder)
    names = sorted(files) if files is not None else [
        p.relative_to(folder).as_posix() for p in _files_in(folder, {SNAPSHOT})
    ]
    meta: dict[str, Any] = {"source": source}
    if description:
        meta["description"] = description
    meta.update({
        "retrieved_at": retrieved_at,
        "tool": tool,
        "files": [
            {"path": n, "sha256": sha256_file(folder / n), "bytes": (folder / n).stat().st_size} for n in names
        ],
    })
    path = folder / SNAPSHOT
    path.write_bytes(_dump_json(meta))
    return path


def verify_snapshot(folder: str | Path) -> list[str]:
    """Problems found by comparing a snapshot folder with its snapshot.json (empty = all fine)."""
    folder = Path(folder)
    path = folder / SNAPSHOT
    if not path.exists():
        return [f"missing: {SNAPSHOT}"]
    meta = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    for f in meta["files"]:
        p = folder / f["path"]
        if not p.exists():
            problems.append(f"missing: {f['path']}")
        elif sha256_file(p) != f["sha256"]:
            problems.append(f"changed: {f['path']}")
    return problems

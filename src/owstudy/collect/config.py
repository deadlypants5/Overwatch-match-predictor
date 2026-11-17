"""Load, merge and check the settings files (contracts/config-schema.md).

`default.yaml` holds the shared settings; `local.yaml` (not committed) is merged on top and also
holds the machine-specific values. Unknown keys and bad values are a ConfigError (exit 2).
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, get_args, get_origin, get_type_hints

import yaml

from owstudy.collect import __version__
from owstudy.collect.errors import ConfigError

DEFAULT_CONFIG = Path("configs/collect/default.yaml")

SOURCES = {"liquipedia", "spreadsheet", "owtv", "video"}
INCLUDE_VALUES = {"verified", "partial", "all"}
SOURCE_KINDS = {"pov", "broadcast"}


# --- settings sections (one dataclass per block of default.yaml) -------------------------


@dataclass(frozen=True)
class ScopeSettings:
    pilot: str
    approved: tuple[str, ...]


@dataclass(frozen=True)
class VideoSettings:
    source_kinds: tuple[str, ...]
    povs_per_series: int
    format: str
    cache_max_videos: int
    sleep_between_downloads_s: tuple[float, ...]
    rate_limit: str
    delete_after_extract: bool


@dataclass(frozen=True)
class SamplingSettings:
    fps: float
    hud_anchor_min_score: float


@dataclass(frozen=True)
class RecognitionSettings:
    ocr_threads: int
    low_conf_threshold: float
    icon_min_margin: float


@dataclass(frozen=True)
class InterpretSettings:
    swap_min_frames: int
    short_segment_s: float
    replay_repeat_window_s: float
    clock_must_advance: bool


@dataclass(frozen=True)
class RetrievalSettings:
    liquipedia_min_interval_s: float
    owtv_min_interval_s: float


@dataclass(frozen=True)
class VerifySettings:
    team_kills_abs: int
    player_deaths_abs: int
    player_final_blows_abs: int
    date_tz_one_day_note: bool
    roster_match: str
    source_priority: dict[str, str]


@dataclass(frozen=True)
class ExportSettings:
    include: str
    source_ref_format: str
    analysis_tables: bool
    objective_event_step: float
    min_interval_s: float


@dataclass(frozen=True)
class LocalSettings:
    """Machine-specific values from local.yaml. Defaults are the safe ones."""

    platform_terms_acknowledged: bool = False
    video_cache_dir: str = ""
    user_agent_contact: str = ""
    reviewer: str = ""
    owtv_api_key: str = field(default="", repr=False)  # secret: never printed


@dataclass(frozen=True)
class Config:
    scope: ScopeSettings
    video: VideoSettings
    sampling: SamplingSettings
    recognition: RecognitionSettings
    interpret: InterpretSettings
    retrieval: RetrievalSettings
    verify: VerifySettings
    export: ExportSettings
    local: LocalSettings
    source_path: str = ""

    def section(self, name: str) -> dict[str, Any]:
        """A settings block as a plain dict (used for hashing)."""
        return dataclasses.asdict(getattr(self, name))


SECTIONS = {
    "scope": ScopeSettings,
    "video": VideoSettings,
    "sampling": SamplingSettings,
    "recognition": RecognitionSettings,
    "interpret": InterpretSettings,
    "retrieval": RetrievalSettings,
    "verify": VerifySettings,
    "export": ExportSettings,
}
LOCAL_KEYS = {f.name for f in dataclasses.fields(LocalSettings)}


# --- loading --------------------------------------------------------------------------


def _read_yaml(path: Path) -> Any:
    try:
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        raise ConfigError(f"settings file not found: {path}") from None
    except yaml.YAMLError as e:
        raise ConfigError(f"{path} is not valid YAML: {e}") from None


def _deep_merge(base: dict, over: dict) -> dict:
    out = dict(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _coerce(value: Any, typ: Any, where: str) -> Any:
    """Check one value against its declared type and convert lists to tuples."""
    origin = get_origin(typ)
    if origin is tuple:
        if not isinstance(value, list):
            raise ConfigError(f"{where} must be a list")
        (item,) = {a for a in get_args(typ) if a is not Ellipsis}
        return tuple(_coerce(v, item, f"{where}[]") for v in value)
    if origin is dict:
        if not isinstance(value, dict):
            raise ConfigError(f"{where} must be a mapping")
        return {str(k): _coerce(v, get_args(typ)[1], f"{where}.{k}") for k, v in value.items()}
    if typ is bool:
        if not isinstance(value, bool):
            raise ConfigError(f"{where} must be true or false")
        return value
    if typ is int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"{where} must be a whole number")
        return value
    if typ is float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"{where} must be a number")
        return float(value)
    if typ is str:
        if value is None:
            return ""
        if not isinstance(value, str):
            raise ConfigError(f"{where} must be text")
        return value
    raise TypeError(f"unsupported settings type {typ!r}")


def _build(cls: type, data: Any, where: str) -> Any:
    if not isinstance(data, dict):
        raise ConfigError(f"{where} must be a mapping")
    hints = get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls)}
    unknown = sorted(set(data) - set(fields))
    if unknown:
        raise ConfigError(f"unknown setting(s) in {where}: {', '.join(unknown)}")
    kwargs = {}
    for name, f in fields.items():
        if name in data:
            kwargs[name] = _coerce(data[name], hints[name], f"{where}.{name}")
        elif f.default is dataclasses.MISSING:
            raise ConfigError(f"missing setting {where}.{name}")
    return cls(**kwargs)


def _check_values(cfg: Config) -> None:
    bad = sorted(set(cfg.verify.source_priority.values()) - SOURCES)
    if bad:
        raise ConfigError(f"verify.source_priority uses unknown source(s): {', '.join(bad)}")
    if cfg.export.include not in INCLUDE_VALUES:
        raise ConfigError(f"export.include must be one of {sorted(INCLUDE_VALUES)}, not {cfg.export.include!r}")
    if cfg.video.povs_per_series not in (1, 2):
        raise ConfigError("video.povs_per_series must be 1 or 2")
    bad = sorted(set(cfg.video.source_kinds) - SOURCE_KINDS)
    if bad:
        raise ConfigError(f"video.source_kinds has unknown kind(s): {', '.join(bad)}")
    if cfg.scope.pilot not in cfg.scope.approved:
        raise ConfigError("scope.pilot must be listed in scope.approved")
    if cfg.export.min_interval_s < 0 or not 0 < cfg.export.objective_event_step <= 1:
        raise ConfigError("export.min_interval_s must be >= 0 and objective_event_step in (0, 1]")


def load_config(path: str | Path = DEFAULT_CONFIG, local_path: str | Path | None = None) -> Config:
    """Load default.yaml, merge local.yaml on top (if present), and check every value.

    `local_path` defaults to `local.yaml` next to `path`. A missing local.yaml is fine: the safe
    defaults apply (terms not acknowledged, no User-Agent contact).
    """
    path = Path(path)
    data = _read_yaml(path) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping")
    local_file = Path(local_path) if local_path is not None else path.with_name("local.yaml")
    if local_file.exists():
        local = _read_yaml(local_file) or {}
        if not isinstance(local, dict):
            raise ConfigError(f"{local_file} must be a mapping")
        data = _deep_merge(data, local)

    unknown = sorted(set(data) - set(SECTIONS) - LOCAL_KEYS)
    if unknown:
        raise ConfigError(f"unknown setting(s): {', '.join(unknown)}")
    missing = sorted(set(SECTIONS) - set(data))
    if missing:
        raise ConfigError(f"missing settings block(s): {', '.join(missing)}")

    sections = {name: _build(cls, data[name], name) for name, cls in SECTIONS.items()}
    local_settings = _build(LocalSettings, {k: data[k] for k in LOCAL_KEYS if k in data}, "local")
    cfg = Config(**sections, local=local_settings, source_path=str(path))
    _check_values(cfg)
    return cfg


# --- patches --------------------------------------------------------------------------


@dataclass(frozen=True)
class Patch:
    patch_id: str
    live_date: dt.date
    note: str = ""


@dataclass(frozen=True)
class PatchOverrides:
    """Patch-day rule by region, plus hand-set series (configs/collect/patch_overrides.yaml)."""

    pre_patch_regions: tuple[str, ...] = ()
    series: dict[str, str] = field(default_factory=dict)  # series_key -> patch_id


def _as_date(value: Any, where: str) -> dt.date:
    if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except ValueError:
        raise ConfigError(f"{where} must be a date like 2026-03-10, not {value!r}") from None


def load_patches(path: str | Path) -> list[Patch]:
    """The patch list, oldest first. Patch IDs and dates must be unique."""
    data = _read_yaml(Path(path)) or []
    if not isinstance(data, list):
        raise ConfigError(f"{path} must be a list of patches")
    patches = []
    for i, row in enumerate(data):
        where = f"{path}[{i}]"
        if not isinstance(row, dict):
            raise ConfigError(f"{where} must be a mapping")
        unknown = sorted(set(row) - {"patch_id", "live_date", "note"})
        if unknown or "patch_id" not in row or "live_date" not in row:
            raise ConfigError(f"{where} needs patch_id and live_date (and optional note); got {sorted(row)}")
        patches.append(Patch(str(row["patch_id"]), _as_date(row["live_date"], where), str(row.get("note") or "")))
    patches.sort(key=lambda p: p.live_date)
    for kind, values in (("patch_id", [p.patch_id for p in patches]), ("live_date", [p.live_date for p in patches])):
        if len(set(values)) != len(values):
            raise ConfigError(f"{path}: duplicate {kind}")
    return patches


def load_patch_overrides(path: str | Path, patches: list[Patch] | None = None) -> PatchOverrides:
    data = _read_yaml(Path(path)) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must be a mapping")
    unknown = sorted(set(data) - {"pre_patch_regions", "series"})
    if unknown:
        raise ConfigError(f"unknown setting(s) in {path}: {', '.join(unknown)}")
    regions = tuple(str(r) for r in (data.get("pre_patch_regions") or []))
    series: dict[str, str] = {}
    for i, row in enumerate(data.get("series") or []):
        if not isinstance(row, dict) or "series_key" not in row or "patch_id" not in row:
            raise ConfigError(f"{path} series[{i}] needs series_key and patch_id")
        series[str(row["series_key"])] = str(row["patch_id"])
    if patches is not None:
        known = {p.patch_id for p in patches}
        bad = sorted(set(series.values()) - known)
        if bad:
            raise ConfigError(f"{path} names unknown patch(es): {', '.join(bad)}")
    return PatchOverrides(regions, series)


# --- extraction key (research R13) -----------------------------------------------------


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: str | Path) -> str:
    return _sha256_bytes(Path(path).read_bytes())


def hash_tree(folder: str | Path) -> str:
    """One hash over every file below `folder` (relative path + contents, sorted)."""
    folder = Path(folder)
    h = hashlib.sha256()
    if folder.exists():
        for p in sorted(x for x in folder.rglob("*") if x.is_file()):
            h.update(p.relative_to(folder).as_posix().encode("utf-8") + b"\0")
            h.update(hash_file(p).encode("ascii") + b"\n")
    return h.hexdigest()


def extraction_key(
    cfg: Config,
    layout_path: str | Path,
    icon_lib_dir: str | Path,
    ocr_model_files: list[str | Path],
) -> str:
    """Short fingerprint of everything that can change readings for the same video.

    Covers the extractor version, the HUD layout file, the icon library, the OCR model files
    and the `sampling` settings. Readings are stored per (video_id, extraction_key).
    """
    parts = {
        "extractor_version": __version__,
        "layout": hash_file(layout_path),
        "icons": hash_tree(icon_lib_dir),
        "ocr": [hash_file(p) for p in sorted(map(str, ocr_model_files))],
        "sampling": cfg.section("sampling"),
    }
    blob = json.dumps(parts, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(blob)[:8]

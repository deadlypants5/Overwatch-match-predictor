"""T010: settings loading, merging, checking, and the extraction key."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from owstudy.collect.config import (
    extraction_key,
    load_config,
    load_patch_overrides,
    load_patches,
)
from owstudy.collect.errors import ConfigError

REPO = Path(__file__).resolve().parents[3]
DEFAULT = REPO / "configs" / "collect" / "default.yaml"


def _default() -> dict:
    return yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))


def _write(path: Path, data) -> Path:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture
def cfg_file(tmp_path: Path) -> Path:
    return _write(tmp_path / "default.yaml", _default())


def test_repo_default_loads_with_safe_local_defaults(tmp_path):
    cfg = load_config(DEFAULT, local_path=tmp_path / "absent.yaml")
    assert cfg.scope.pilot == "Asia/Stage 1/Korea"
    assert cfg.local.platform_terms_acknowledged is False
    assert cfg.export.min_interval_s == 20
    assert cfg.verify.source_priority["bans"] == "spreadsheet"


def test_unknown_key_rejected(tmp_path):
    data = _default()
    data["sampling"]["fsp"] = 2
    with pytest.raises(ConfigError, match="fsp"):
        load_config(_write(tmp_path / "d.yaml", data), local_path=tmp_path / "none.yaml")


def test_unknown_top_level_key_rejected(tmp_path):
    data = _default()
    data["extras"] = {}
    with pytest.raises(ConfigError, match="extras"):
        load_config(_write(tmp_path / "d.yaml", data), local_path=tmp_path / "none.yaml")


def test_unknown_key_in_local_rejected(cfg_file, tmp_path):
    local = _write(tmp_path / "local.yaml", {"reviewr": "x"})
    with pytest.raises(ConfigError, match="reviewr"):
        load_config(cfg_file, local_path=local)


def test_local_overrides_are_merged(cfg_file, tmp_path):
    local = _write(tmp_path / "local.yaml", {
        "platform_terms_acknowledged": True,
        "reviewer": "MW",
        "sampling": {"fps": 4},
    })
    cfg = load_config(cfg_file, local_path=local)
    assert cfg.local.platform_terms_acknowledged is True
    assert cfg.local.reviewer == "MW"
    assert cfg.sampling.fps == 4
    assert cfg.sampling.hud_anchor_min_score == 0.80  # untouched keys survive the merge


def test_local_yaml_next_to_default_is_picked_up(cfg_file):
    _write(cfg_file.with_name("local.yaml"), {"user_agent_contact": "someone"})
    assert load_config(cfg_file).local.user_agent_contact == "someone"


def test_api_key_not_shown_in_repr(cfg_file, tmp_path):
    local = _write(tmp_path / "local.yaml", {"owtv_api_key": "secret-123"})
    assert "secret-123" not in repr(load_config(cfg_file, local_path=local))


@pytest.mark.parametrize(
    "section,key,value,match",
    [
        ("export", "include", "everything", "export.include"),
        ("video", "povs_per_series", 3, "povs_per_series"),
        ("video", "source_kinds", ["pov", "stream"], "source_kinds"),
        ("sampling", "fps", "fast", "sampling.fps"),
        ("export", "analysis_tables", "yes", "analysis_tables"),
    ],
)
def test_bad_values_rejected(tmp_path, section, key, value, match):
    data = _default()
    data[section][key] = value
    with pytest.raises(ConfigError, match=match):
        load_config(_write(tmp_path / "d.yaml", data), local_path=tmp_path / "none.yaml")


def test_bad_source_priority_rejected(tmp_path):
    data = _default()
    data["verify"]["source_priority"]["bans"] = "reddit"
    with pytest.raises(ConfigError, match="reddit"):
        load_config(_write(tmp_path / "d.yaml", data), local_path=tmp_path / "none.yaml")


def test_missing_key_rejected(tmp_path):
    data = _default()
    del data["interpret"]["swap_min_frames"]
    with pytest.raises(ConfigError, match="swap_min_frames"):
        load_config(_write(tmp_path / "d.yaml", data), local_path=tmp_path / "none.yaml")


# --- extraction key -----------------------------------------------------------------


@pytest.fixture
def key_inputs(tmp_path):
    layout = tmp_path / "layout.yaml"
    layout.write_text("layout_id: test\n", encoding="utf-8")
    icons = tmp_path / "icons"
    (icons / "hero_ana").mkdir(parents=True)
    (icons / "hero_ana" / "1.png").write_bytes(b"icon-a")
    model = tmp_path / "model.onnx"
    model.write_bytes(b"model")
    return layout, icons, model


def _key(cfg, layout, icons, model):
    return extraction_key(cfg, layout, icons, [model])


def test_extraction_key_is_stable(cfg_file, tmp_path, key_inputs):
    cfg = load_config(cfg_file, local_path=tmp_path / "none.yaml")
    k1 = _key(cfg, *key_inputs)
    assert len(k1) == 8 and all(c in "0123456789abcdef" for c in k1)
    assert _key(load_config(cfg_file, local_path=tmp_path / "none.yaml"), *key_inputs) == k1


def test_extraction_key_ignores_unrelated_settings(cfg_file, tmp_path, key_inputs):
    base = _key(load_config(cfg_file, local_path=tmp_path / "none.yaml"), *key_inputs)
    local = _write(tmp_path / "local.yaml", {"reviewer": "someone", "export": {"include": "all"}})
    assert _key(load_config(cfg_file, local_path=local), *key_inputs) == base


def test_extraction_key_changes_with_layout(cfg_file, tmp_path, key_inputs):
    cfg = load_config(cfg_file, local_path=tmp_path / "none.yaml")
    layout, icons, model = key_inputs
    before = _key(cfg, layout, icons, model)
    layout.write_text("layout_id: test2\n", encoding="utf-8")
    assert _key(cfg, layout, icons, model) != before


def test_extraction_key_changes_with_icon_file(cfg_file, tmp_path, key_inputs):
    cfg = load_config(cfg_file, local_path=tmp_path / "none.yaml")
    layout, icons, model = key_inputs
    before = _key(cfg, layout, icons, model)
    (icons / "hero_ana" / "2.png").write_bytes(b"icon-b")
    after_add = _key(cfg, layout, icons, model)
    assert after_add != before
    (icons / "hero_ana" / "2.png").write_bytes(b"icon-c")
    assert _key(cfg, layout, icons, model) != after_add


def test_extraction_key_changes_with_fps(cfg_file, tmp_path, key_inputs):
    before = _key(load_config(cfg_file, local_path=tmp_path / "none.yaml"), *key_inputs)
    local = _write(tmp_path / "local.yaml", {"sampling": {"fps": 3}})
    assert _key(load_config(cfg_file, local_path=local), *key_inputs) != before


def test_extraction_key_changes_with_ocr_model(cfg_file, tmp_path, key_inputs):
    cfg = load_config(cfg_file, local_path=tmp_path / "none.yaml")
    layout, icons, model = key_inputs
    before = _key(cfg, layout, icons, model)
    model.write_bytes(b"model-v2")
    assert _key(cfg, layout, icons, model) != before


# --- patches --------------------------------------------------------------------------


def test_repo_patch_files_load():
    patches = load_patches(REPO / "configs" / "collect" / "patches.yaml")
    assert len(patches) == 44
    assert patches[0].live_date == dt.date(2026, 1, 8)
    assert [p.live_date for p in patches] == sorted(p.live_date for p in patches)
    overrides = load_patch_overrides(REPO / "configs" / "collect" / "patch_overrides.yaml", patches)
    assert overrides.pre_patch_regions == ("Korea",)
    assert overrides.series == {}


def test_duplicate_patch_date_rejected(tmp_path):
    p = _write(tmp_path / "patches.yaml", [
        {"patch_id": "a", "live_date": "2026-01-01"},
        {"patch_id": "b", "live_date": "2026-01-01"},
    ])
    with pytest.raises(ConfigError, match="duplicate live_date"):
        load_patches(p)


def test_override_with_unknown_patch_rejected(tmp_path):
    patches = load_patches(_write(tmp_path / "p.yaml", [{"patch_id": "p1", "live_date": "2026-01-01"}]))
    o = _write(tmp_path / "o.yaml", {"series": [{"series_key": "x", "patch_id": "p9"}]})
    with pytest.raises(ConfigError, match="p9"):
        load_patch_overrides(o, patches)

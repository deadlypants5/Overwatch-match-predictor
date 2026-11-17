"""Shared test helpers for the match data collection tests."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CONFIG_DIR = REPO / "configs" / "collect"

# Stand-in for local.yaml so tests never depend on the researcher's machine.
LOCAL_STUB = {
    "platform_terms_acknowledged": False,
    "video_cache_dir": "",  # replaced with a temp folder in the cfg fixture
    "user_agent_contact": "owstudy-tests",
    "reviewer": "test",
    "owtv_api_key": "",
}

# Folders of the data/ layout (contracts/storage-layout.md) created for each test.
DATA_LAYOUT = [
    "raw/reference",
    "raw/observations",
    "raw/gold",
    "raw/decisions",
    "interim",
    "processed",
]


@pytest.fixture
def fixtures_dir() -> Path:
    """Folder holding the small, hand-made test inputs."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """An empty copy of the data/ folder layout, plus a copy of the config folder."""
    data = tmp_path / "data"
    for sub in DATA_LAYOUT:
        (data / sub).mkdir(parents=True, exist_ok=True)
    shutil.copytree(CONFIG_DIR, tmp_path / "configs" / "collect", ignore=shutil.ignore_patterns("local.yaml"))
    return data


@pytest.fixture
def cfg(tmp_path: Path) -> dict:
    """The default settings with local.yaml values stubbed out."""
    with open(CONFIG_DIR / "default.yaml", encoding="utf-8") as f:
        merged = yaml.safe_load(f)
    local = dict(LOCAL_STUB, video_cache_dir=str(tmp_path / "videos"))
    merged.update(local)
    return merged

"""T015: stable IDs and the alias table."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from owstudy.collect.catalog.entities import (
    ALIAS_COLUMNS,
    PROPOSAL_COLUMNS,
    AliasTable,
    hero_id,
    map_id,
    normalize_alias,
    player_id,
    propose,
    slug,
    team_id,
)
from owstudy.collect.errors import ValidationError
from owstudy.collect.io.tables import read_table, write_table

REPO = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("D.Va", "dva"),
        ("Soldier: 76", "soldier_76"),
        ("Lúcio", "lucio"),
        ("Torbjörn", "torbjorn"),
        ("King's Row", "kings_row"),
        ("Watchpoint: Grímsvötn", "watchpoint_grimsvotn"),
        ("  Crazy  Raccoon ", "crazy_raccoon"),
        ("ZETA DIVISION", "zeta_division"),
    ],
)
def test_slug(text, expected):
    assert slug(text) == expected


def test_typed_ids():
    assert team_id("T1") == "team:t1"
    assert player_id("Proper") == "player:proper"
    assert hero_id("D.Va") == "hero:dva"
    assert map_id("Paraíso") == "map:paraiso"
    with pytest.raises(ValueError):
        team_id("!!!")


def test_normalize_alias():
    assert normalize_alias("  Crazy\tRACCOON  ") == "crazy raccoon"


def _aliases(tmp_path, rows):
    p = tmp_path / "aliases.csv"
    write_table(rows, p, ALIAS_COLUMNS, key=["entity_type", "alias", "valid_from"])
    return AliasTable.load(p)


RENAME = [
    {"entity_type": "team", "alias": "Old Name", "stable_id": "team:new_name",
     "valid_from": "", "valid_to": "2026-04-30", "source": "liquipedia"},
    {"entity_type": "team", "alias": "New Name", "stable_id": "team:new_name",
     "valid_from": "2026-05-01", "valid_to": "", "source": "liquipedia"},
]  # fmt: skip


def test_rename_old_and_new_names_resolve_to_same_id(tmp_path):
    table = _aliases(tmp_path, RENAME)
    assert table.resolve("team", "old name", dt.date(2026, 3, 1)).stable_id == "team:new_name"
    assert table.resolve("team", "NEW NAME", dt.date(2026, 6, 1)).stable_id == "team:new_name"


def test_alias_only_valid_in_its_dates(tmp_path):
    table = _aliases(tmp_path, RENAME)
    assert table.resolve("team", "Old Name", dt.date(2026, 6, 1)).stable_id is None


def test_overlapping_validity_rejected(tmp_path):
    rows = [
        {"entity_type": "player", "alias": "Max", "stable_id": "player:max_a",
         "valid_from": "", "valid_to": "2026-05-01", "source": ""},
        {"entity_type": "player", "alias": "max", "stable_id": "player:max_b",
         "valid_from": "2026-04-01", "valid_to": "", "source": ""},
    ]  # fmt: skip
    with pytest.raises(ValidationError, match="overlapping"):
        _aliases(tmp_path, rows)


def test_same_alias_in_separate_periods_allowed(tmp_path):
    rows = [
        {"entity_type": "player", "alias": "Max", "stable_id": "player:max_a",
         "valid_from": "", "valid_to": "2026-03-31", "source": ""},
        {"entity_type": "player", "alias": "Max", "stable_id": "player:max_b",
         "valid_from": "2026-04-01", "valid_to": "", "source": ""},
    ]  # fmt: skip
    table = _aliases(tmp_path, rows)
    assert table.resolve("player", "max", dt.date(2026, 3, 1)).stable_id == "player:max_a"
    assert table.resolve("player", "max", dt.date(2026, 4, 1)).stable_id == "player:max_b"


def test_near_miss_is_not_resolved_and_is_proposed(tmp_path):
    table = AliasTable()
    table.add_known("player", "player:proper", "Proper")
    res = table.resolve("player", "Propper", dt.date(2026, 4, 1))
    assert res.stable_id is None
    assert res.candidate == "player:proper"
    assert 80 <= res.score < 100

    proposals = tmp_path / "aliases_proposed.csv"
    assert propose(proposals, "Propper", "player", res.candidate, res.score, "obs:vid#name:L1@10", "2026-11-20")
    assert not propose(proposals, "propper", "player", res.candidate, res.score, "elsewhere", "2026-11-21")
    df = read_table(proposals, PROPOSAL_COLUMNS)
    assert len(df) == 1 and df.loc[0, "candidate_stable_id"] == "player:proper"
    assert not (tmp_path / "aliases.csv").exists()  # nothing auto-created


def test_propose_never_writes_aliases_csv(tmp_path):
    with pytest.raises(ValidationError):
        propose(tmp_path / "aliases.csv", "x", "player", None, 0, "", "")


def test_resolution_limited_to_candidate_roster(tmp_path):
    table = AliasTable()
    table.add_known("player", "player:kevster", "Kevster")
    table.add_known("player", "player:kellan", "Kellan")
    roster = ["player:kellan"]
    assert table.resolve("player", "Kevster", candidates=roster).stable_id is None
    res = table.resolve("player", "Kevstr", candidates=roster)
    assert res.stable_id is None and res.candidate == "player:kellan"
    assert table.resolve("player", "Kellan", candidates=roster).stable_id == "player:kellan"


def test_seeded_entity_files():
    ents = REPO / "data" / "interim" / "entities"
    heroes = read_table(ents / "heroes.csv", ["hero_id", "name", "role"])
    maps = read_table(ents / "maps.csv", ["map_id", "name", "mode_id"])
    read_table(ents / "aliases.csv", ALIAS_COLUMNS)
    assert len(heroes) == 54 and heroes["hero_id"].is_unique
    assert set(heroes["role"]) == {"tank", "damage", "support"}
    assert all(h == hero_id(n) for h, n in zip(heroes["hero_id"], heroes["name"]))
    assert set(maps["mode_id"]) <= {"control", "escort", "hybrid", "push", "flashpoint", "clash"}
    assert all(m == map_id(n) for m, n in zip(maps["map_id"], maps["name"]))

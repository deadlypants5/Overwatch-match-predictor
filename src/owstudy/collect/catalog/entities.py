"""Stable IDs and the name-alias table (research: entities and aliases).

IDs are short slugs with a type prefix: `team:t1`, `player:<liquipedia page slug>`,
`hero:dva`, `map:kings_row`. `aliases.csv` is curated by hand; tools only ever *propose* new
aliases (aliases_proposed.csv) and never write aliases.csv.
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

from owstudy.collect.errors import ValidationError
from owstudy.collect.io.tables import append_rows, read_table

ENTITY_TYPES = ("team", "player", "hero", "map")
ALIAS_COLUMNS = ("entity_type", "alias", "stable_id", "valid_from", "valid_to", "source")
PROPOSAL_COLUMNS = ("alias", "entity_type", "candidate_stable_id", "score", "seen_in", "seen_at")

_DROP = re.compile(r"[.'’:]")  # dropped outright, so "D.Va" -> "dva", "King's Row" -> "kings_row"
_OTHER = re.compile(r"[^a-z0-9]+")


def slug(text: str) -> str:
    """Lower-case ASCII slug: accents removed, `. ' :` dropped, other runs of symbols -> `_`."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return _OTHER.sub("_", _DROP.sub("", ascii_text)).strip("_")


def make_id(entity_type: str, name: str) -> str:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"unknown entity type {entity_type!r}")
    s = slug(name)
    if not s:
        raise ValueError(f"can't make an ID from {name!r}")
    return f"{entity_type}:{s}"


def team_id(name: str) -> str:
    return make_id("team", name)


def player_id(liquipedia_page: str) -> str:
    return make_id("player", liquipedia_page)


def hero_id(name: str) -> str:
    return make_id("hero", name)


def map_id(name: str) -> str:
    return make_id("map", name)


def normalize_alias(text: str) -> str:
    """How names are compared: Unicode-normalized, case-folded, whitespace collapsed."""
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _date(value: str, where: str) -> dt.date | None:
    if value == "":
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{where}: bad date {value!r}") from None


@dataclass(frozen=True)
class Alias:
    entity_type: str
    alias: str  # normalized
    stable_id: str
    valid_from: dt.date | None  # None = open
    valid_to: dt.date | None  # None = open; inclusive
    source: str = ""

    def valid_on(self, day: dt.date | None) -> bool:
        if day is None:
            return True
        return (self.valid_from is None or self.valid_from <= day) and (self.valid_to is None or day <= self.valid_to)

    def overlaps(self, other: Alias) -> bool:
        lo = max(self.valid_from or dt.date.min, other.valid_from or dt.date.min)
        hi = min(self.valid_to or dt.date.max, other.valid_to or dt.date.max)
        return lo <= hi


class Resolution(NamedTuple):
    stable_id: str | None  # set only on an exact alias or known-name match
    score: float  # 100 for exact, otherwise the best fuzzy score (0-100)
    candidate: str | None  # best fuzzy candidate when there's no exact match


class AliasTable:
    """Hand-curated aliases plus the entities' own names, used to resolve text to stable IDs."""

    def __init__(self, aliases: Iterable[Alias] = ()):
        self._aliases: list[Alias] = []
        for a in aliases:
            self.add(a)

    @classmethod
    def load(cls, path: str | Path) -> AliasTable:
        df = read_table(path, ALIAS_COLUMNS)
        rows = []
        for i, r in enumerate(df.to_dict(orient="records"), start=2):
            where = f"{path}:{i}"
            if r["entity_type"] not in ENTITY_TYPES:
                raise ValidationError(f"{where}: unknown entity_type {r['entity_type']!r}")
            if not r["alias"] or not r["stable_id"]:
                raise ValidationError(f"{where}: alias and stable_id are required")
            rows.append(Alias(
                r["entity_type"], normalize_alias(r["alias"]), r["stable_id"],
                _date(r["valid_from"], where), _date(r["valid_to"], where), r["source"],
            ))  # fmt: skip
        return cls(rows)

    def add(self, alias: Alias) -> None:
        if alias.valid_from and alias.valid_to and alias.valid_from > alias.valid_to:
            raise ValidationError(f"alias {alias.alias!r}: valid_from is after valid_to")
        for other in self._aliases:
            if (
                other.entity_type == alias.entity_type
                and other.alias == alias.alias
                and other.overlaps(alias)
                and other.stable_id != alias.stable_id
            ):
                raise ValidationError(
                    f"{alias.entity_type} alias {alias.alias!r} points to both {other.stable_id} "
                    f"and {alias.stable_id} over overlapping dates"
                )
            if other == alias:
                return
        self._aliases.append(alias)

    def add_known(self, entity_type: str, stable_id: str, name: str) -> None:
        """Register an entity's own display name, so it resolves without an alias row."""
        self.add(Alias(entity_type, normalize_alias(name), stable_id, None, None, "entity"))

    def resolve(
        self,
        entity_type: str,
        text: str,
        on_date: dt.date | None = None,
        candidates: Iterable[str] | None = None,
    ) -> Resolution:
        """Exact match first (valid on `on_date`, within `candidates` if given), then fuzzy.

        A fuzzy match never resolves: it returns `stable_id = None` with the best candidate and
        its score, so the caller can propose an alias for the researcher to approve.
        """
        from rapidfuzz import fuzz

        norm = normalize_alias(text)
        allowed = set(candidates) if candidates is not None else None
        pool = [
            a for a in self._aliases
            if a.entity_type == entity_type and a.valid_on(on_date) and (allowed is None or a.stable_id in allowed)
        ]  # fmt: skip
        exact = sorted({a.stable_id for a in pool if a.alias == norm})
        if len(exact) == 1:
            return Resolution(exact[0], 100.0, None)
        if len(exact) > 1:  # only possible across different candidates sharing a name
            return Resolution(None, 100.0, exact[0])

        best_id, best = None, 0.0
        for a in sorted(pool, key=lambda a: (a.stable_id, a.alias)):
            score = float(fuzz.ratio(norm, a.alias))
            if score > best:
                best_id, best = a.stable_id, score
        return Resolution(None, round(best, 1), best_id)


def propose(
    path: str | Path,
    alias: str,
    entity_type: str,
    candidate_stable_id: str | None,
    score: float,
    seen_in: str,
    seen_at: str,
) -> bool:
    """Add an alias proposal for the researcher to review (aliases_proposed.csv).

    Never writes aliases.csv. Skips a proposal already on file (same alias, type and
    candidate). Returns True if a row was added.
    """
    path = Path(path)
    if path.name == "aliases.csv":
        raise ValidationError("proposals go to aliases_proposed.csv; aliases.csv is curated by hand")
    if path.exists():
        existing = read_table(path, PROPOSAL_COLUMNS)
        norm = normalize_alias(alias)
        for r in existing.to_dict(orient="records"):
            if (
                normalize_alias(r["alias"]) == norm
                and r["entity_type"] == entity_type
                and r["candidate_stable_id"] == (candidate_stable_id or "")
            ):
                return False
    append_rows(
        path,
        PROPOSAL_COLUMNS,
        [{
            "alias": alias, "entity_type": entity_type, "candidate_stable_id": candidate_stable_id,
            "score": float(score), "seen_in": seen_in, "seen_at": seen_at,
        }],  # fmt: skip
        decimals={"score": 1},
    )
    return True

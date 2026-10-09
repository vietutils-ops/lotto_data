"""Rulesets: the rules of a game during one era (mirror of the app's model).

A game whose pool or extra balls changed has one ruleset per era, and every
draw names the ruleset it was drawn under. See the app's
docs/ruleset-versioning.md for the shared rules; this module enforces the same
ones so the app never receives data it would reject.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .errors import DataInvalid, RulesetUnknown

MAX_NUMBER = 127
MAX_BALLS_PER_SET = 10
MAX_RULESETS = 50

KINDS = ("main", "same_pool_extra", "separate_pool")
FIELDS = ("main_numbers", "bonus_number", "supplementary_numbers", "special_numbers")

_RULESET_ID = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_BALL_SET_ID = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_LANGUAGE = re.compile(r"^[a-z]{2}$")


@dataclass(frozen=True)
class BallSet:
    id: str
    kind: str
    count: int
    min: int
    max: int
    field: str
    player_selectable: bool
    label: Mapping[str, str]

    @property
    def pool_size(self) -> int:
        return self.max - self.min + 1

    def contains(self, n: int) -> bool:
        return self.min <= n <= self.max

    def to_json(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "field": self.field,
            "player_selectable": self.player_selectable,
            "label": dict(self.label),
        }


@dataclass(frozen=True)
class Ruleset:
    ruleset_id: str
    game_code: str
    effective_from: date
    effective_to: Optional[date]
    ball_sets: Sequence[BallSet]
    notes: Optional[str] = None

    @property
    def main(self) -> BallSet:
        return self.ball_sets[0]

    @property
    def extras(self) -> Sequence[BallSet]:
        return self.ball_sets[1:]

    def by_field(self, field: str) -> List[BallSet]:
        return [b for b in self.extras if b.field == field]

    def covers(self, day: date) -> bool:
        return day >= self.effective_from and (self.effective_to is None or day <= self.effective_to)

    def to_json(self) -> Dict[str, Any]:
        return {
            "ruleset_id": self.ruleset_id,
            "effective_from": self.effective_from.isoformat(),
            "effective_to": None if self.effective_to is None else self.effective_to.isoformat(),
            "ball_sets": [b.to_json() for b in self.ball_sets],
            "notes": self.notes,
        }

    def problems(self) -> List[str]:
        """Structural problems; empty when the ruleset is usable."""
        issues: List[str] = []

        def add(message: str) -> None:
            issues.append(f"{self.ruleset_id}: {message}")

        if not _RULESET_ID.match(self.ruleset_id):
            add("ruleset_id must be lowercase [a-z0-9_]")
        if self.effective_to is not None and self.effective_to < self.effective_from:
            add("effective_to is before effective_from")
        if not self.ball_sets:
            add("no ball sets")
            return issues
        seen = set()
        for b in self.ball_sets:
            if b.id in seen:
                add(f"duplicate ball set {b.id}")
            seen.add(b.id)
            if not _BALL_SET_ID.match(b.id):
                add(f"{b.id}: ball set id must be lowercase [a-z0-9_]")
            if not 1 <= b.count <= MAX_BALLS_PER_SET:
                add(f"{b.id}: count {b.count} out of 1–{MAX_BALLS_PER_SET}")
            if b.min < 0 or b.max > MAX_NUMBER or b.min > b.max:
                add(f"{b.id}: range {b.min}–{b.max} not within 0–{MAX_NUMBER}")
            elif b.count > b.pool_size:
                add(f"{b.id}: {b.count} balls from a pool of {b.pool_size}")
            if not b.label.get("en"):
                add(f"{b.id}: an English label is required")
        main = self.main
        if main.kind != "main" or main.field != "main_numbers" or not main.player_selectable:
            add("the first ball set must be the player-selected main numbers")
        same_pool = main.count
        bonus_sets = supplementary_sets = 0
        for b in self.extras:
            if b.kind == "main":
                add(f"{b.id}: only the first ball set can be the main numbers")
            elif b.kind == "same_pool_extra":
                same_pool += b.count
                if (b.min, b.max) != (main.min, main.max):
                    add(f"{b.id}: same-pool balls must use the main range")
                if b.player_selectable:
                    add(f"{b.id}: same-pool extra balls are drawn, not chosen")
                if b.field == "bonus_number":
                    bonus_sets += 1
                    if b.count != 1:
                        add(f"{b.id}: bonus_number holds exactly one ball")
                elif b.field == "supplementary_numbers":
                    supplementary_sets += 1
                else:
                    add(f"{b.id}: same-pool balls go to bonus_number or supplementary_numbers")
            elif b.kind == "separate_pool":
                if b.field != "special_numbers":
                    add(f"{b.id}: separate pools go to special_numbers")
            else:
                add(f"{b.id}: unknown kind {b.kind}")
        if bonus_sets > 1:
            add("more than one bonus_number ball set")
        if supplementary_sets > 1:
            add("more than one supplementary_numbers ball set")
        if same_pool > main.pool_size:
            add(f"{same_pool} balls drawn from a pool of {main.pool_size}")
        return issues


class Timeline:
    """All rulesets of one game, in date order."""

    def __init__(self, game_code: str, rulesets: Sequence[Ruleset]):
        self.game_code = game_code
        self.rulesets: List[Ruleset] = sorted(rulesets, key=lambda r: r.effective_from)

    @property
    def current(self) -> Ruleset:
        return self.rulesets[-1]

    def for_date(self, day: date) -> Optional[Ruleset]:
        found = None
        for r in self.rulesets:
            if r.covers(day):
                found = r
        return found

    def require_for_date(self, day: date) -> Ruleset:
        ruleset = self.for_date(day)
        if ruleset is None:
            raise RulesetUnknown(f"no ruleset covers {day.isoformat()}", game=self.game_code)
        return ruleset

    def by_id(self, ruleset_id: str) -> Optional[Ruleset]:
        return next((r for r in self.rulesets if r.ruleset_id == ruleset_id), None)

    def problems(self) -> List[str]:
        if not self.rulesets:
            return [f"{self.game_code}: no rulesets"]
        issues: List[str] = []
        ids = set()
        for r in self.rulesets:
            issues.extend(r.problems())
            if r.game_code != self.game_code:
                issues.append(f"{r.ruleset_id}: belongs to {r.game_code}, not {self.game_code}")
            if r.ruleset_id in ids:
                issues.append(f"{self.game_code}: duplicate ruleset id {r.ruleset_id}")
            ids.add(r.ruleset_id)
        for a, b in zip(self.rulesets, self.rulesets[1:]):
            if a.effective_to is None:
                issues.append(f"{a.ruleset_id}: only the latest ruleset may be open-ended")
            elif a.effective_to >= b.effective_from:
                issues.append(f"{a.ruleset_id} overlaps {b.ruleset_id}")
        return issues

    def to_document(self) -> Dict[str, Any]:
        from . import SCHEMA_VERSION

        return {
            "schema_version": SCHEMA_VERSION,
            "game_code": self.game_code,
            "rulesets": [r.to_json() for r in self.rulesets],
        }


def _strict_keys(obj: Mapping[str, Any], keys: Sequence[str], what: str) -> None:
    if set(obj) != set(keys):
        raise DataInvalid(f"{what} must have exactly the keys {', '.join(keys)}; has {', '.join(sorted(obj))}")


def parse_ball_set(raw: Any, where: str) -> BallSet:
    if not isinstance(raw, dict):
        raise DataInvalid(f"{where}: a ball set must be an object")
    _strict_keys(raw, ("id", "kind", "count", "min", "max", "field", "player_selectable", "label"), where)
    label = raw["label"]
    if (
        not isinstance(label, dict)
        or not all(isinstance(k, str) and _LANGUAGE.match(k) for k in label)
        or not all(isinstance(v, str) and v.strip() and len(v) <= 60 for v in label.values())
    ):
        raise DataInvalid(f"{where}: label must map language codes to short texts")
    for key in ("count", "min", "max"):
        if type(raw[key]) is not int:
            raise DataInvalid(f"{where}: {key} must be an integer")
    if raw["kind"] not in KINDS or raw["field"] not in FIELDS or not isinstance(raw["player_selectable"], bool):
        raise DataInvalid(f"{where}: invalid kind, field or player_selectable")
    if not isinstance(raw["id"], str):
        raise DataInvalid(f"{where}: id must be a string")
    return BallSet(
        id=raw["id"],
        kind=raw["kind"],
        count=raw["count"],
        min=raw["min"],
        max=raw["max"],
        field=raw["field"],
        player_selectable=raw["player_selectable"],
        label=dict(label),
    )


def parse_rulesets(document: Any, game_code: str) -> Timeline:
    """Parses and validates a game's ``rulesets.json``."""
    from . import SCHEMA_VERSION

    if not isinstance(document, dict):
        raise DataInvalid("rulesets.json must be an object", game=game_code)
    _strict_keys(document, ("schema_version", "game_code", "rulesets"), "rulesets.json")
    if document["schema_version"] != SCHEMA_VERSION:
        raise DataInvalid(f"rulesets.json schema_version {document['schema_version']}", game=game_code)
    if document["game_code"] != game_code:
        raise DataInvalid(f"rulesets.json belongs to {document['game_code']}", game=game_code)
    items = document["rulesets"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_RULESETS:
        raise DataInvalid(f"rulesets must be a list of 1–{MAX_RULESETS} entries", game=game_code)
    rulesets: List[Ruleset] = []
    for index, raw in enumerate(items):
        where = f"rulesets[{index}]"
        if not isinstance(raw, dict):
            raise DataInvalid(f"{where} must be an object", game=game_code)
        _strict_keys(raw, ("ruleset_id", "effective_from", "effective_to", "ball_sets", "notes"), where)
        notes = raw["notes"]
        if notes is not None and (not isinstance(notes, str) or len(notes) > 2000):
            raise DataInvalid(f"{where}: notes must be text of at most 2000 characters", game=game_code)
        sets = raw["ball_sets"]
        if not isinstance(sets, list) or not 1 <= len(sets) <= 8:
            raise DataInvalid(f"{where}: ball_sets must be a list of 1–8 entries", game=game_code)
        try:
            effective_from = date.fromisoformat(raw["effective_from"])
            effective_to = None if raw["effective_to"] is None else date.fromisoformat(raw["effective_to"])
        except (TypeError, ValueError) as exc:
            raise DataInvalid(f"{where}: effective dates must be YYYY-MM-DD", game=game_code) from exc
        if not isinstance(raw["ruleset_id"], str):
            raise DataInvalid(f"{where}: ruleset_id must be a string", game=game_code)
        rulesets.append(
            Ruleset(
                ruleset_id=raw["ruleset_id"],
                game_code=game_code,
                effective_from=effective_from,
                effective_to=effective_to,
                ball_sets=tuple(parse_ball_set(b, f"{where}.ball_sets[{i}]") for i, b in enumerate(sets)),
                notes=notes,
            )
        )
    timeline = Timeline(game_code, rulesets)
    problems = timeline.problems()
    if problems:
        raise DataInvalid("; ".join(problems), game=game_code)
    return timeline


def draw_problems(ruleset: Ruleset, record: Mapping[str, Any]) -> List[str]:
    """Problems of one canonical draw record under its ruleset (empty when valid)."""
    issues: List[str] = []
    main_rule = ruleset.main
    main = record["main_numbers"]

    def check(rule: BallSet, numbers: Sequence[int], *, ascending: bool) -> None:
        if len(numbers) != rule.count:
            issues.append(f"{rule.id}: expected {rule.count} numbers, got {len(numbers)}")
        if len(set(numbers)) != len(numbers):
            issues.append(f"{rule.id}: duplicate numbers {list(numbers)}")
        for n in numbers:
            if not rule.contains(n):
                issues.append(f"{rule.id}: {n} out of range {rule.min}–{rule.max}")
        if ascending and list(numbers) != sorted(numbers):
            issues.append(f"{rule.id}: numbers must be ascending")

    check(main_rule, main, ascending=True)
    drawn = set(main)

    bonus_rules = ruleset.by_field("bonus_number")
    bonus = record["bonus_number"]
    if not bonus_rules:
        if bonus is not None:
            issues.append("bonus_number: the ruleset has no bonus ball")
    elif bonus is None:
        issues.append(f"{bonus_rules[0].id}: bonus number missing")
    else:
        check(bonus_rules[0], [bonus], ascending=False)
        if bonus in drawn:
            issues.append(f"{bonus_rules[0].id}: {bonus} repeats a drawn ball")
        drawn.add(bonus)

    supplementary_rules = ruleset.by_field("supplementary_numbers")
    supplementary = record["supplementary_numbers"]
    if not supplementary_rules:
        if supplementary:
            issues.append("supplementary_numbers: the ruleset has no supplementary balls")
    else:
        check(supplementary_rules[0], supplementary, ascending=False)
        for n in set(supplementary):
            if n in drawn:
                issues.append(f"{supplementary_rules[0].id}: {n} repeats a drawn ball")

    special_rules = {b.id: b for b in ruleset.by_field("special_numbers")}
    special = record["special_numbers"]
    for key in special:
        if key not in special_rules:
            issues.append(f"special_numbers.{key}: the ruleset has no such ball set")
    for key, rule in special_rules.items():
        if key not in special:
            issues.append(f"{key}: missing")
        else:
            check(rule, special[key], ascending=False)
    return issues

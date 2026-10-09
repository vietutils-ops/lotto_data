"""Raw records from an adapter → canonical draws.

Rules: never fabricate or guess a value; a record that cannot be mapped
unambiguously is rejected with a reason (and quarantined). Canonicalization
is limited to formatting: zero-padded or date IDs, ISO dates, ascending main
numbers, integers. The ruleset comes from the draw date, never from the source.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from .errors import RulesetUnknown
from .games import GameDefinition
from .models import Draw, RejectedRecord
from .rulesets import draw_problems

_DIGITS = re.compile(r"^[0-9]+$")
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d", "%d-%m-%Y", "%d.%m.%Y", "%Y%m%d")


class NormalizationError(ValueError):
    """A single record cannot be normalized."""


@dataclass
class RawRecord:
    """A record as an adapter read it, with explicit field names:
    draw_id, draw_date, main_numbers, and optionally bonus_number,
    supplementary_numbers and special_numbers."""

    ref: str
    data: Mapping[str, Any]


@dataclass
class NormalizationResult:
    draws: List[Draw] = field(default_factory=list)
    rejected: List[RejectedRecord] = field(default_factory=list)


def normalize_date(value: Any) -> date:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        raise NormalizationError(f"date must be a string, got {value!r}")
    text = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise NormalizationError(f"unsupported or invalid date {value!r}")


def _int(value: Any, what: str) -> int:
    if type(value) is int:
        return value
    if isinstance(value, str) and _DIGITS.match(value.strip()):
        return int(value.strip())
    raise NormalizationError(f"{what} must be an integer, got {value!r}")


def _ints(value: Any, what: str) -> List[int]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [_int(v, what) for v in value]
    raise NormalizationError(f"{what} must be a list, got {value!r}")


def normalize_draw_id(value: Any, game: GameDefinition, draw_date: date) -> str:
    fmt = game.draw_id_format
    if fmt.type == "date":
        expected = fmt.for_date(draw_date)
        if value is not None and str(value).strip() not in ("", expected):
            raise NormalizationError(f"draw id {value!r} is not the draw date {expected}")
        return expected
    if type(value) is int:
        number = value
    elif isinstance(value, str) and _DIGITS.match(value.strip().lstrip("#").strip()):
        number = int(value.strip().lstrip("#").strip())
    else:
        raise NormalizationError(f"draw id {value!r} is not numeric")
    if number <= 0:
        raise NormalizationError(f"draw id {value!r} must be positive")
    formatted = fmt.format_number(number)
    if len(formatted) != fmt.digits:
        raise NormalizationError(f"draw id {value!r} exceeds {fmt.digits} digits")
    return formatted


def normalize_record(raw: RawRecord, game: GameDefinition) -> Draw:
    data = raw.data
    if not isinstance(data, Mapping):
        raise NormalizationError("record must be an object")
    draw_date = normalize_date(data.get("draw_date"))
    draw_id = normalize_draw_id(data.get("draw_id"), game, draw_date)
    if game.timeline is None:
        raise NormalizationError("the game has no rulesets.json")
    ruleset = game.timeline.for_date(draw_date)
    if ruleset is None:
        raise NormalizationError(f"no ruleset covers {draw_date.isoformat()}")
    main = sorted(_ints(data.get("main_numbers"), "main number"))
    bonus = data.get("bonus_number")
    special_raw = data.get("special_numbers") or {}
    if not isinstance(special_raw, Mapping):
        raise NormalizationError("special_numbers must be an object")
    draw = Draw(
        draw_id=draw_id,
        draw_date=draw_date,
        ruleset_version=ruleset.ruleset_id,
        main_numbers=tuple(main),
        bonus_number=None if bonus is None else _int(bonus, "bonus number"),
        supplementary_numbers=tuple(_ints(data.get("supplementary_numbers"), "supplementary number")),
        special_numbers=tuple((str(k), tuple(_ints(v, f"{k} number"))) for k, v in special_raw.items()),
    )
    problems = draw_problems(ruleset, draw.to_record())
    if problems:
        raise NormalizationError("; ".join(problems))
    return draw


def normalize_records(records: Sequence[RawRecord], game: GameDefinition) -> NormalizationResult:
    """Normalizes every record; duplicates with identical content collapse,
    conflicting duplicates are all rejected."""
    result = NormalizationResult()
    by_id: Dict[str, Tuple[Draw, str]] = {}
    conflicts = set()
    for raw in records:
        try:
            draw = normalize_record(raw, game)
        except NormalizationError as exc:
            result.rejected.append(RejectedRecord(raw.ref, str(exc), dict(raw.data) if isinstance(raw.data, Mapping) else raw.data))
            continue
        seen = by_id.get(draw.draw_id)
        if seen is None:
            by_id[draw.draw_id] = (draw, raw.ref)
        elif not seen[0].same_content(draw):
            conflicts.add(draw.draw_id)
            result.rejected.append(RejectedRecord(raw.ref, f"conflicts with {seen[1]}", draw.to_record()))
    for draw_id in conflicts:
        draw, ref = by_id.pop(draw_id)
        result.rejected.append(RejectedRecord(ref, "conflicting duplicate", draw.to_record()))
    result.draws = sorted((d for d, _ in by_id.values()), key=lambda d: (d.draw_date, d.sequence))
    return result

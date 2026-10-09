"""Validation of a game's draws: the same rules the app applies.

Each draw is checked under the ruleset it names, which must exist and cover
its date; the dataset must be sorted, unique per ID and date, IDs must rise
with dates, and numbered games may only skip IDs recorded as known gaps.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Set
from zoneinfo import ZoneInfo

from . import SCHEMA_VERSION
from .errors import DataInvalid, SchemaMismatch
from .games import GameDefinition
from .models import Dataset, Draw
from .rulesets import MAX_BALLS_PER_SET, draw_problems

_VERSION = re.compile(r"^\d{4}\.\d{2}\.\d{2}\.\d{3}$")
_TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DRAW_KEYS = (
    "draw_id",
    "draw_date",
    "ruleset_version",
    "main_numbers",
    "bonus_number",
    "supplementary_numbers",
    "special_numbers",
)
DOCUMENT_KEYS = (
    "schema_version",
    "game_code",
    "country_code",
    "operator_code",
    "dataset_version",
    "updated_at",
    "draw_count",
    "draws",
)


@dataclass(frozen=True)
class Issue:
    code: str
    message: str
    draw_id: Optional[str] = None
    severity: str = "error"  # error | warning

    def render(self) -> str:
        where = f" ({self.draw_id})" if self.draw_id else ""
        return f"{self.severity.upper()} {self.code}{where}: {self.message}"


@dataclass
class ValidationReport:
    issues: List[Issue] = field(default_factory=list)

    def error(self, code: str, message: str, draw_id: Optional[str] = None) -> None:
        self.issues.append(Issue(code, message, draw_id))

    def warning(self, code: str, message: str, draw_id: Optional[str] = None) -> None:
        self.issues.append(Issue(code, message, draw_id, "warning"))

    @property
    def errors(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> List[Issue]:
        return [i for i in self.issues if i.severity == "warning"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def raise_for_errors(self, game: str) -> None:
        if self.errors:
            shown = "; ".join(i.render() for i in self.errors[:10])
            more = f" (+{len(self.errors) - 10} more)" if len(self.errors) > 10 else ""
            raise DataInvalid(shown + more, game=game)


def today_in(timezone: str, now: datetime) -> date:
    """Today's calendar date in the game's IANA time zone."""
    if now.tzinfo is None:
        raise ValueError("naive datetime; use an aware UTC datetime")
    return now.astimezone(ZoneInfo(timezone)).date()


def parse_draws_document(document: Any, game: GameDefinition) -> Dataset:
    """Reads a canonical ``draws.json`` strictly (types and keys only)."""
    if not isinstance(document, dict) or set(document) != set(DOCUMENT_KEYS):
        raise SchemaMismatch(f"draws.json must have exactly the keys {', '.join(DOCUMENT_KEYS)}", game=game.game_code)
    if document["schema_version"] != SCHEMA_VERSION:
        raise SchemaMismatch(f"draws.json schema_version {document['schema_version']}", game=game.game_code)
    for key, expected in (
        ("game_code", game.game_code),
        ("country_code", game.country_code),
        ("operator_code", game.operator_code),
    ):
        if document[key] != expected:
            raise DataInvalid(f"draws.json {key} is {document[key]!r}, expected {expected!r}", game=game.game_code)
    version, updated = document["dataset_version"], document["updated_at"]
    if not isinstance(version, str) or not _VERSION.match(version):
        raise DataInvalid(f"dataset_version {version!r} is not YYYY.MM.DD.NNN", game=game.game_code)
    if not isinstance(updated, str) or not _TIMESTAMP.match(updated):
        raise DataInvalid(f"updated_at {updated!r} is not a UTC timestamp", game=game.game_code)
    records = document["draws"]
    if not isinstance(records, list) or document["draw_count"] != len(records):
        raise DataInvalid("draw_count must equal the number of draws", game=game.game_code)
    draws = []
    for index, record in enumerate(records):
        draws.append(record_to_draw(record, f"draws[{index}]", game.game_code))
    return Dataset(game.game_code, game.country_code, game.operator_code, version, updated, draws)


def _ints(value: Any) -> bool:
    return isinstance(value, list) and len(value) <= MAX_BALLS_PER_SET and all(type(v) is int for v in value)


def record_to_draw(record: Any, where: str, game_code: str) -> Draw:
    if not isinstance(record, dict) or set(record) != set(DRAW_KEYS):
        raise SchemaMismatch(f"{where} must have exactly the keys {', '.join(DRAW_KEYS)}", game=game_code)
    special = record["special_numbers"]
    if (
        not isinstance(record["draw_id"], str)
        or not isinstance(record["draw_date"], str)
        or not isinstance(record["ruleset_version"], str)
        or not _ints(record["main_numbers"])
        or (record["bonus_number"] is not None and type(record["bonus_number"]) is not int)
        or not _ints(record["supplementary_numbers"])
        or not isinstance(special, dict)
        or len(special) > 8
        or not all(isinstance(k, str) and _ints(v) for k, v in special.items())
    ):
        raise SchemaMismatch(f"{where}: field types do not match the canonical draw", game=game_code)
    try:
        return Draw.from_record(record)
    except ValueError as exc:
        raise DataInvalid(f"{where}: draw_date {record['draw_date']!r} is not a calendar date", game=game_code) from exc


def validate_dataset(
    game: GameDefinition,
    dataset: Dataset,
    *,
    known_gaps: Iterable[str] = (),
    today: date,
) -> ValidationReport:
    """Every rule the app checks, plus the known-gap allow-list."""
    report = ValidationReport()
    timeline = game.timeline
    if timeline is None:
        report.error("ruleset_unknown", "the game has no rulesets.json")
        return report
    fmt = game.draw_id_format
    if not dataset.draws:
        report.error("empty_dataset", "no draws")
        return report

    for d in dataset.draws:
        if not fmt.is_valid(d.draw_id):
            report.error("invalid_draw_id", f"{d.draw_id!r} does not match the game's draw ID format", d.draw_id)
            continue
        if fmt.type == "date" and fmt.for_date(d.draw_date) != d.draw_id:
            report.error("draw_id_date_mismatch", "the draw ID must be the draw date", d.draw_id)
        if d.draw_date > today:
            report.error("future_draw_date", f"{d.draw_date} is after today ({today}) in {game.timezone}", d.draw_id)
        if d.draw_date < game.historical_coverage_start:
            report.error("implausible_draw_date", "draw date before the game's coverage start", d.draw_id)
        ruleset = timeline.by_id(d.ruleset_version)
        if ruleset is None:
            report.error("unknown_ruleset", f"ruleset {d.ruleset_version} is not defined", d.draw_id)
            continue
        if not ruleset.covers(d.draw_date):
            report.error("ruleset_date_mismatch", f"{ruleset.ruleset_id} does not cover {d.draw_date}", d.draw_id)
        for problem in draw_problems(ruleset, d.to_record()):
            report.error("invalid_numbers", problem, d.draw_id)

    ids: Set[str] = set()
    dates: Set[date] = set()
    for prev, d in zip([None, *dataset.draws], dataset.draws):
        if d.draw_id in ids:
            report.error("duplicate_draw_id", "duplicate draw id", d.draw_id)
        if d.draw_date in dates:
            report.error("duplicate_draw_date", "two draws on one date", d.draw_id)
        ids.add(d.draw_id)
        dates.add(d.draw_date)
        if prev is not None:
            if d.draw_date <= prev.draw_date:
                report.error("unsorted_draws", "draws must be strictly ascending by date", d.draw_id)
            elif fmt.is_valid(d.draw_id) and fmt.is_valid(prev.draw_id) and d.sequence <= prev.sequence:
                report.error("id_date_order_mismatch", "draw ids must increase with dates", d.draw_id)

    if fmt.consecutive and report.ok:
        declared = set(known_gaps)
        present = {d.sequence for d in dataset.draws}
        for n in range(dataset.draws[0].sequence, dataset.draws[-1].sequence + 1):
            draw_id = fmt.format_number(n)
            if n not in present and draw_id not in declared:
                report.error("missing_draw_id", "gap not recorded in config/known_gaps.json", draw_id)
        for draw_id in sorted(declared & ids):
            report.warning("gap_resolved", "recorded as missing but present; remove it from known_gaps.json", draw_id)
    return report


def missing_ids(game: GameDefinition, draws: Sequence[Draw]) -> List[str]:
    """IDs absent between the first and the latest draw (numbered games)."""
    fmt = game.draw_id_format
    if not fmt.consecutive or not draws:
        return []
    present = {d.sequence for d in draws}
    return [fmt.format_number(n) for n in range(draws[0].sequence, draws[-1].sequence + 1) if n not in present]


def known_gaps_for(document: Mapping[str, Any], game_code: str) -> List[str]:
    """Draw IDs recorded as knowingly missing for a game (config/known_gaps.json)."""
    entries = (document.get("gaps") or {}).get(game_code) or []
    return [e["draw_id"] for e in entries]

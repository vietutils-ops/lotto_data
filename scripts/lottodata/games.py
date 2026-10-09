"""Game registry (sources/source_registry.json) and game definitions.

A game's rules live in its ``rulesets.json``; everything else the tools need
(identity, schedule, ID format, official source, compliance record, adapter)
lives in the registry. No code branches on a game code.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Sequence

from .errors import DataInvalid
from .layout import RepoLayout
from .rulesets import Timeline, parse_rulesets
from .serialization import read_json_file

DISTRIBUTION_MODES = ("public", "restricted", "disabled")
_GAME_CODE = re.compile(r"^[a-z][a-z0-9_]{2,39}$")


@dataclass(frozen=True)
class DrawIdFormat:
    """``sequential`` (zero-padded numbers, consecutive) or ``date`` (YYYYMMDD)."""

    type: str
    digits: int = 8

    @property
    def consecutive(self) -> bool:
        return self.type == "sequential"

    def is_valid(self, draw_id: str) -> bool:
        if not isinstance(draw_id, str) or not draw_id.isdigit() or not draw_id.isascii():
            return False
        if self.type == "sequential":
            return len(draw_id) == self.digits
        try:
            date(int(draw_id[0:4]), int(draw_id[4:6]), int(draw_id[6:8]))
        except ValueError:
            return False
        return len(draw_id) == 8

    def format_number(self, number: int) -> str:
        return str(number).zfill(self.digits)

    @staticmethod
    def for_date(day: date) -> str:
        return day.strftime("%Y%m%d")


@dataclass(frozen=True)
class GameDefinition:
    game_code: str
    country_code: str
    operator_code: str
    display_name: str
    path: str
    timezone: str
    draw_weekdays: Sequence[int]
    draw_id_format: DrawIdFormat
    historical_coverage_start: date
    distribution_mode: str
    adapter: Optional[str]
    official_source: Mapping[str, Any]
    compliance: Mapping[str, Any]
    timeline: Optional[Timeline] = field(default=None, compare=False)

    @property
    def publishes_data(self) -> bool:
        return self.distribution_mode == "public"


def _require(entry: Mapping[str, Any], key: str, kind: type, where: str):
    value = entry.get(key)
    if not isinstance(value, kind):
        raise DataInvalid(f"{where}: {key} must be {kind.__name__}")
    return value


def parse_registry(document: Any) -> List[GameDefinition]:
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise DataInvalid("source_registry.json must be an object with schema_version 1")
    games = document.get("games")
    if not isinstance(games, list):
        raise DataInvalid("source_registry.json: games must be a list")
    result: List[GameDefinition] = []
    seen = set()
    for index, entry in enumerate(games):
        where = f"source_registry.games[{index}]"
        if not isinstance(entry, dict):
            raise DataInvalid(f"{where} must be an object")
        code = _require(entry, "game_code", str, where)
        if not _GAME_CODE.match(code) or code in seen:
            raise DataInvalid(f"{where}: invalid or duplicate game_code {code!r}")
        seen.add(code)
        id_format = _require(entry, "draw_id_format", dict, where)
        if id_format.get("type") == "sequential":
            digits = id_format.get("digits")
            if type(digits) is not int or not 1 <= digits <= 12:
                raise DataInvalid(f"{where}: sequential draw IDs need 1–12 digits")
            fmt = DrawIdFormat("sequential", digits)
        elif id_format.get("type") == "date":
            fmt = DrawIdFormat("date", 8)
        else:
            raise DataInvalid(f"{where}: draw_id_format.type must be sequential or date")
        weekdays = _require(entry, "draw_weekdays", list, where)
        if not weekdays or any(type(w) is not int or not 1 <= w <= 7 for w in weekdays):
            raise DataInvalid(f"{where}: draw_weekdays must be ISO weekdays 1–7")
        mode = _require(entry, "distribution_mode", str, where)
        if mode not in DISTRIBUTION_MODES:
            raise DataInvalid(f"{where}: distribution_mode must be one of {', '.join(DISTRIBUTION_MODES)}")
        country = _require(entry, "country_code", str, where)
        if not re.match(r"^[A-Z]{2}$", country):
            raise DataInvalid(f"{where}: country_code must be ISO 3166-1 alpha-2")
        path = _require(entry, "path", str, where)
        if not re.match(r"^games/[a-z]{2}/[a-z0-9_]+$", path):
            raise DataInvalid(f"{where}: path must be games/<cc>/<slug>")
        adapter = entry.get("adapter")
        if adapter is not None and not isinstance(adapter, str):
            raise DataInvalid(f"{where}: adapter must be a string or null")
        result.append(
            GameDefinition(
                game_code=code,
                country_code=country,
                operator_code=_require(entry, "operator_code", str, where),
                display_name=_require(entry, "display_name", str, where),
                path=path,
                timezone=_require(entry, "timezone", str, where),
                draw_weekdays=tuple(weekdays),
                draw_id_format=fmt,
                historical_coverage_start=date.fromisoformat(_require(entry, "historical_coverage_start", str, where)),
                distribution_mode=mode,
                adapter=adapter,
                official_source=dict(_require(entry, "official_source", dict, where)),
                compliance=dict(_require(entry, "compliance", dict, where)),
            )
        )
    return result


def load_games(layout: RepoLayout, *, with_rulesets: bool = True) -> Dict[str, GameDefinition]:
    """All registered games, with their rulesets when they have a folder."""
    games: Dict[str, GameDefinition] = {}
    for game in parse_registry(read_json_file(layout.registry_file)):
        timeline = None
        rulesets_path = layout.rulesets_file(game)
        if with_rulesets and rulesets_path.is_file():
            timeline = parse_rulesets(read_json_file(rulesets_path), game.game_code)
        games[game.game_code] = GameDefinition(**{**game.__dict__, "timeline": timeline})
    return games


def require_game(games: Mapping[str, GameDefinition], code: str) -> GameDefinition:
    try:
        return games[code]
    except KeyError as exc:
        raise DataInvalid(f"unknown game {code!r}; registered: {', '.join(sorted(games))}") from exc

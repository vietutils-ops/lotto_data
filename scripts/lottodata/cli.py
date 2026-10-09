"""Shared helpers of the command-line tools."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from typing import Any, Iterable, List, Mapping

from .errors import LottoDataError
from .games import GameDefinition, require_game


def add_game_selection(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--game", action="append", metavar="CODE", help="game code (repeatable)")
    group.add_argument("--all", action="store_true", help="every game in sources/source_registry.json")


def selected_games(args: argparse.Namespace, games: Mapping[str, GameDefinition]) -> List[GameDefinition]:
    if args.all:
        return list(games.values())
    return [require_game(games, code) for code in args.game]


def now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def print_json(obj: Any) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def report_errors(errors: Iterable[LottoDataError]) -> int:
    errors = list(errors)
    for e in errors:
        print(e.render(), file=sys.stderr)
    return 1 if errors else 0

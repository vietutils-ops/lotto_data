"""Shared test helpers.

TEST-ONLY DATA: the fictional game ``zz_starlotto`` (country ZZ, a
user-assigned code) and every draw built by ``make_draws`` are invented for
tests and never published. Vietlott draws used in tests are read from the
published files of this repository.
"""

from __future__ import annotations

import json
import random
import shutil
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import pytest

from scripts.lottodata.adapters import FetchResult, LotterySourceAdapter
from scripts.lottodata.games import GameDefinition, load_games
from scripts.lottodata.layout import ROOT, RepoLayout
from scripts.lottodata.models import Draw
from scripts.lottodata.normalize import RawRecord

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

FICTIONAL_GAME = {
    "game_code": "zz_starlotto",
    "country_code": "ZZ",
    "operator_code": "zz_operator",
    "display_name": "Star Lotto (test)",
    "path": "games/zz/starlotto",
    "timezone": "America/New_York",
    "draw_weekdays": [2, 5],
    "draw_id_format": {"type": "date"},
    "historical_coverage_start": "2000-01-01",
    "distribution_mode": "public",
    "adapter": "fake",
    "official_source": {"name": "Test operator", "url": "https://example.test/"},
    "compliance": {"terms_url": None, "terms_reviewed_at": None, "robots_txt_checked_at": None,
                   "notes": "Fictional game for tests."},
}

_MAIN = {"en": "Main numbers"}
_STAR = {"en": "Star ball"}
FICTIONAL_RULESETS = {
    "schema_version": 2,
    "game_code": "zz_starlotto",
    "rulesets": [
        {"ruleset_id": "zz_starlotto_v1", "effective_from": "2000-01-04", "effective_to": "2009-12-29",
         "ball_sets": [
             {"id": "main", "kind": "main", "count": 5, "min": 1, "max": 59, "field": "main_numbers",
              "player_selectable": True, "label": _MAIN},
             {"id": "star", "kind": "separate_pool", "count": 1, "min": 1, "max": 35, "field": "special_numbers",
              "player_selectable": True, "label": _STAR}],
         "notes": None},
        {"ruleset_id": "zz_starlotto_v2", "effective_from": "2010-01-05", "effective_to": None,
         "ball_sets": [
             {"id": "main", "kind": "main", "count": 5, "min": 1, "max": 70, "field": "main_numbers",
              "player_selectable": True, "label": _MAIN},
             {"id": "star", "kind": "separate_pool", "count": 1, "min": 1, "max": 25, "field": "special_numbers",
              "player_selectable": True, "label": _STAR}],
         "notes": None},
    ],
}


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch) -> RepoLayout:
    """A fresh repository: the real registry, rulesets, schemas and gaps (no
    draws), plus the fictional test game."""
    root = tmp_path / "repo"
    for folder in ("schemas", "sources", "config"):
        shutil.copytree(ROOT / folder, root / folder)
    for rulesets in (ROOT / "games").rglob("rulesets.json"):
        target = root / rulesets.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(rulesets, target)
    registry = json.loads((root / "sources" / "source_registry.json").read_text(encoding="utf-8"))
    registry["games"].append(FICTIONAL_GAME)
    write_json(root / "sources" / "source_registry.json", registry)
    write_json(root / "games" / "zz" / "starlotto" / "rulesets.json", FICTIONAL_RULESETS)
    write_json(root / "sources" / "adapters" / "fake.json", {"schema_version": 1, "adapter": "fake"})
    monkeypatch.setenv("LOTTO_DATA_ROOT", str(root))
    return RepoLayout(root)


@pytest.fixture
def games(repo: RepoLayout) -> Dict[str, GameDefinition]:
    return load_games(repo)


def published_vietlott(code: str) -> List[Dict[str, Any]]:
    """Records of the real published Vietlott draws of this repository."""
    folder = {"mega645": "vietlott_mega645", "power655": "vietlott_power655"}[code]
    document = json.loads((ROOT / "games" / "vn" / folder / "draws.json").read_text(encoding="utf-8"))
    return document["draws"]


def make_draws(game: GameDefinition, count: int, *, start: date, seed: int = 1) -> List[Draw]:
    """TEST-ONLY random draws of [game], each valid under the ruleset of its date."""
    rng = random.Random(seed)
    draws: List[Draw] = []
    day, number = start, 1
    while len(draws) < count:
        ruleset = game.timeline.for_date(day)
        if day.isoweekday() in game.draw_weekdays and ruleset is not None:
            main = sorted(rng.sample(range(ruleset.main.min, ruleset.main.max + 1), ruleset.main.count))
            bonus = None
            for b in ruleset.by_field("bonus_number"):
                bonus = rng.choice([n for n in range(b.min, b.max + 1) if n not in main])
            special = tuple((b.id, tuple(sorted(rng.sample(range(b.min, b.max + 1), b.count))))
                            for b in ruleset.by_field("special_numbers"))
            fmt = game.draw_id_format
            draw_id = fmt.for_date(day) if fmt.type == "date" else fmt.format_number(number)
            draws.append(Draw(draw_id, day, ruleset.ruleset_id, tuple(main), bonus, (), special))
            number += 1
        day += timedelta(days=1)
    return draws


def raw(draw: Draw, ref: str = "test") -> RawRecord:
    """A draw as an adapter would report it (explicit fields, source formats)."""
    return RawRecord(ref, {
        "draw_id": draw.draw_id,
        "draw_date": draw.draw_date.strftime("%d/%m/%Y"),
        "main_numbers": list(reversed(draw.main_numbers)),  # sources need not sort
        "bonus_number": draw.bonus_number,
        "special_numbers": draw.special(),
    })


class FakeAdapter(LotterySourceAdapter):
    """Serves scripted records instead of contacting a source."""

    adapter_id = "fake"
    source_name = "fake test source"
    pages: Dict[str, FetchResult] = {}

    def fetch(self, *, since: Optional[Draw], max_pages: int) -> FetchResult:
        return FakeAdapter.pages[self.game.game_code]


@pytest.fixture
def fake_source():
    FakeAdapter.pages = {}

    def serve(game_code: str, records: List[RawRecord], *, rejected=(), complete: bool = False) -> None:
        FakeAdapter.pages[game_code] = FetchResult(
            records=list(records), rejected=list(rejected), source_url="https://example.test/results",
            retrieved_at="2026-10-08T12:00:00Z", complete=complete)

    return serve


FACTORIES = {"fake": FakeAdapter, "vietlott": FakeAdapter}

"""The published files of this repository."""

import json
from datetime import datetime, timezone

import pytest

from scripts.lottodata.games import load_games
from scripts.lottodata.layout import ROOT, RepoLayout
from scripts.lottodata.repo_validation import validate_repository
from scripts.lottodata.repository import load_published

VIETLOTT_DATA = ROOT.parent / "vietlott-data"


def test_the_repository_validates():
    report = validate_repository(RepoLayout(ROOT), datetime.now(timezone.utc))
    assert report.ok, report.lines()


def test_the_catalog_lists_every_public_game_with_data():
    layout = RepoLayout(ROOT)
    catalog = json.loads(layout.catalog_file.read_text())
    games = load_games(layout)
    with_data = sorted(code for code, g in games.items() if g.publishes_data and layout.draws_file(g).is_file())
    assert sorted(g["game_code"] for g in catalog["games"]) == with_data


@pytest.mark.skipif(not VIETLOTT_DATA.is_dir(), reason="needs a vietlott-data checkout next to this repository")
@pytest.mark.parametrize("code", ["mega645", "power655"])
def test_vietlott_draws_are_identical_to_the_vietlott_repository(code):
    layout = RepoLayout(ROOT)
    game = load_games(layout)[code]
    ours = [d.to_record() for d in load_published(layout, game).dataset.draws]
    theirs = json.loads((VIETLOTT_DATA / "data" / f"{code}.json").read_text())["draws"]
    stripped = [{k: r[k] for k in ("draw_id", "draw_date", "main_numbers", "bonus_number")} for r in ours]
    assert stripped == theirs
    assert {r["ruleset_version"] for r in ours} == {f"{code}_v1"}
    assert all(r["supplementary_numbers"] == [] and r["special_numbers"] == {} for r in ours)

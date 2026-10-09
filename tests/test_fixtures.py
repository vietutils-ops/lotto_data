"""Captured source pages (tests/fixtures/<adapter>/) must parse, and every
row must match the published draw with the same ID. See tests/fixtures/README.md."""

import pytest

from scripts.lottodata.games import load_games
from scripts.lottodata.layout import ROOT, RepoLayout
from scripts.lottodata.normalize import normalize_records
from scripts.lottodata.repository import load_published
from scripts.lottodata.serialization import read_json_file

CAPTURES = sorted((ROOT / "tests" / "fixtures").glob("*/*.txt"))


@pytest.mark.skipif(not CAPTURES, reason="no captured source pages yet (tests/fixtures/README.md)")
@pytest.mark.parametrize("capture", CAPTURES, ids=lambda p: p.name)
def test_captured_pages_match_the_published_draws(capture):
    from scripts.lottodata.adapters import adapters
    from scripts.lottodata.http import CollectorConfig, HttpClient

    layout = RepoLayout(ROOT)
    games = load_games(layout)
    game = games[capture.name.split("_page")[0]]
    settings = read_json_file(ROOT / "sources" / "adapters" / f"{game.adapter}.json")
    adapter = adapters()[game.adapter](HttpClient(CollectorConfig()), game, settings)
    page = adapter.parse_response(capture.read_text(encoding="utf-8"), 0)
    assert page.records and not page.rejected
    draws = normalize_records(page.records, game).draws
    published = load_published(layout, game).dataset.by_id()
    for d in draws:
        if d.draw_id in published:
            assert d.to_record() == published[d.draw_id].to_record()

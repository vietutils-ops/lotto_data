from datetime import date

import pytest

from scripts.lottodata.errors import DataInvalid, LottoDataError, SchemaMismatch
from scripts.lottodata.models import Dataset, Draw
from scripts.lottodata.serialization import dumps_draws, loads_json, read_json_file
from scripts.lottodata.validation import parse_draws_document
from tests.conftest import make_draws


def test_draws_file_is_canonical_and_round_trips(games):
    game = games["zz_starlotto"]
    draws = make_draws(game, 5, start=date(2025, 1, 1))
    dataset = Dataset(game.game_code, "ZZ", "zz_operator", "2026.10.08.001", "2026-10-08T12:00:00Z", draws)
    data = dumps_draws(dataset)
    assert data == dumps_draws(dataset)
    lines = data.decode().splitlines()
    assert len(lines) == 9 + 5 + 2 and lines[9].startswith('    {"draw_id": "2025')
    assert data.endswith(b"}\n")
    parsed = parse_draws_document(loads_json(data), game)
    assert parsed.draws == draws and parsed.dataset_version == "2026.10.08.001"


def test_reading_is_strict(games):
    game = games["mega645"]
    draw = Draw("00001", date(2017, 10, 25), "mega645_v1", (1, 2, 3, 4, 5, 6))
    document = loads_json(dumps_draws(Dataset("mega645", "VN", "vietlott", "2026.10.08.001", "2026-10-08T12:00:00Z", [draw])))
    with pytest.raises(SchemaMismatch):
        parse_draws_document({**document, "extra": 1}, game)
    with pytest.raises(DataInvalid):
        parse_draws_document({**document, "country_code": "KR"}, game)
    bad = dict(document["draws"][0], main_numbers=[1, 2, "3", 4, 5, 6])
    with pytest.raises(SchemaMismatch):
        parse_draws_document({**document, "draws": [bad]}, game)
    with pytest.raises(DataInvalid):
        parse_draws_document({**document, "draw_count": 2}, game)


def test_unreadable_files_are_reported_like_every_other_error(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    for path in (broken, tmp_path / "missing.json"):
        with pytest.raises(LottoDataError) as info:
            read_json_file(path)
        assert info.value.code == "file_unreadable"

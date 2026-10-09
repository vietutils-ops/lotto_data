"""Command-line tools on a temporary repository (network faked)."""

from datetime import date

from scripts import health_check, update, validate
from scripts.lottodata import pipeline
from tests.conftest import FACTORIES, make_draws, raw


def test_update_dry_run_then_write_then_validate(repo, games, fake_source, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "adapters", lambda: FACTORIES)
    fake_source("zz_starlotto", [raw(d) for d in make_draws(games["zz_starlotto"], 10, start=date(2026, 3, 1))])
    assert update.main(["--game", "zz_starlotto"]) == 0
    assert '"written": false' in capsys.readouterr().out
    assert update.main(["--game", "zz_starlotto", "--write"]) == 0
    assert validate.main([]) == 0
    assert health_check.main(["--game", "zz_starlotto"]) == 0


def test_one_game_failing_does_not_stop_the_others(repo, games, fake_source, monkeypatch, capsys):
    monkeypatch.setattr(pipeline, "adapters", lambda: FACTORIES)
    fake_source("zz_starlotto", [raw(d) for d in make_draws(games["zz_starlotto"], 5, start=date(2026, 3, 1))])
    fake_source("mega645", [])  # the source returns nothing
    assert update.main(["--game", "mega645", "--game", "zz_starlotto", "--write"]) == 1
    out = capsys.readouterr().out
    assert '"error": "no_data_found"' in out and '"status": "changed"' in out

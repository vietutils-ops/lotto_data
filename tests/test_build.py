import json
from datetime import date, timedelta

import pytest

from scripts import build
from scripts.lottodata.audit import read_events
from scripts.lottodata.games import load_games
from scripts.lottodata.repo_validation import validate_repository
from scripts.lottodata.repository import load_published
from tests.conftest import FICTIONAL_RULESETS, NOW, make_draws, raw, write_json
from tests.test_pipeline import run


@pytest.fixture
def published_star(repo, games, fake_source):
    draws = make_draws(games["zz_starlotto"], 40, start=date(2026, 3, 1))  # until mid-July
    fake_source("zz_starlotto", [raw(d) for d in draws])
    run(repo, "zz_starlotto")
    return draws


def test_nothing_to_rebuild_when_nothing_changed(repo, published_star, capsys):
    assert build.main(["--write"]) == 0
    assert '"rulesets_changed": false' in capsys.readouterr().out
    assert len(read_events(repo)) == 1


def test_a_rule_change_bumps_the_version_and_relabelling_needs_acceptance(repo, published_star, monkeypatch):
    # The game changes its rules on 2026-06-02: close v2, add v3 (fictional).
    document = json.loads(json.dumps(FICTIONAL_RULESETS))
    document["rulesets"][1]["effective_to"] = "2026-05-29"
    v3 = json.loads(json.dumps(document["rulesets"][1]))
    v3.update(ruleset_id="zz_starlotto_v3", effective_from="2026-06-02", effective_to=None)
    document["rulesets"].append(v3)
    write_json(repo.root / "games" / "zz" / "starlotto" / "rulesets.json", document)
    monkeypatch.setattr(build, "now_utc", lambda: NOW + timedelta(hours=1))
    assert build.main(["--write"]) == 1, "draws after 2026-06-02 need relabelling"
    assert build.main(["--write", "--accept-changes"]) == 0
    game = load_games(repo)["zz_starlotto"]
    published = load_published(repo, game)
    assert published.metadata["dataset_version"] == "2026.10.08.002"
    assert set(published.metadata["ruleset_ids"]) == {"zz_starlotto_v2", "zz_starlotto_v3"}
    assert all(d.ruleset_version == "zz_starlotto_v3" for d in published.dataset.draws if d.draw_date >= date(2026, 6, 2))
    assert read_events(repo)[-1]["action"] == "rebuild" and read_events(repo)[-1]["relabelled"]
    assert validate_repository(repo, NOW + timedelta(hours=1)).ok


def test_a_restricted_game_is_listed_with_its_rules_and_source_only(repo, games):
    registry = json.loads(repo.registry_file.read_text())
    for entry in registry["games"]:
        if entry["game_code"] == "zz_starlotto":
            entry["distribution_mode"] = "restricted"
    write_json(repo.registry_file, registry)
    assert build.main(["--write"]) == 0
    catalog = json.loads(repo.catalog_file.read_text())
    entry = next(g for g in catalog["games"] if g["game_code"] == "zz_starlotto")
    assert entry["distribution_mode"] == "restricted" and "draw_count" not in entry
    game = load_games(repo)["zz_starlotto"]
    assert repo.source_file(game).is_file() and not repo.draws_file(game).exists()
    assert validate_repository(repo, NOW).ok


def test_a_missing_or_unreadable_source_file_is_rebuilt(repo, published_star, capsys):
    path = repo.source_file(load_games(repo)["zz_starlotto"])
    expected = path.read_bytes()
    path.unlink()
    assert build.main([]) == 0
    assert '"source_changed": true' in capsys.readouterr().out
    assert not path.exists(), "a dry run writes nothing"
    path.write_text("{")
    assert build.main(["--write"]) == 0
    assert path.read_bytes() == expected
    assert validate_repository(repo, NOW).ok

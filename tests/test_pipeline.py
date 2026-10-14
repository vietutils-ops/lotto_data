import json
from dataclasses import replace
from datetime import date, timedelta

import pytest

from scripts.lottodata.audit import read_events
from scripts.lottodata.errors import DistributionRestricted, HistoryChanged, NoDataFound, ParseFailed
from scripts.lottodata.games import load_games
from scripts.lottodata.http import CollectorConfig, HttpClient
from scripts.lottodata.models import RejectedRecord
from scripts.lottodata.pipeline import update_game
from scripts.lottodata.repo_validation import validate_repository
from scripts.lottodata.repository import load_published
from tests.conftest import FACTORIES, NOW, make_draws, raw, write_json


def run(repo, game_code, *, now=NOW, write=True, accept=False):
    games = load_games(repo)
    client = HttpClient(CollectorConfig(), transport=lambda *a: (_ for _ in ()).throw(AssertionError("no network")))
    return update_game(repo, games, games[game_code], client, now=now, write=write, accept_changes=accept,
                       adapter_factories=FACTORIES)


def test_first_collection_publishes_a_valid_game(repo, games, fake_source):
    game = games["zz_starlotto"]
    draws = make_draws(game, 30, start=date(2026, 3, 1))
    fake_source("zz_starlotto", [raw(d) for d in draws])
    result = run(repo, "zz_starlotto")
    assert result.written and result.changes.summary()["added"] == 30
    published = load_published(repo, game)
    assert published.dataset.draws == draws
    assert published.metadata["dataset_version"] == "2026.10.08.001"
    assert published.metadata["ruleset_ids"] == ["zz_starlotto_v2"]
    assert published.metadata["provenance"]["acquisition_method"] == "collector"
    catalog = json.loads(repo.catalog_file.read_text(encoding="utf-8"))
    assert [g["game_code"] for g in catalog["games"]] == ["zz_starlotto"]
    report = validate_repository(repo, NOW)
    assert report.ok, report.lines()
    event = read_events(repo)[-1]
    assert (event["action"], event["game"], event["added"]) == ("collect", "zz_starlotto", 30)


def test_dry_run_writes_nothing(repo, games, fake_source):
    fake_source("zz_starlotto", [raw(d) for d in make_draws(games["zz_starlotto"], 5, start=date(2026, 3, 1))])
    result = run(repo, "zz_starlotto", write=False)
    assert not result.written and result.dataset_version == "2026.10.08.001"
    assert not repo.draws_file(games["zz_starlotto"]).exists() and not repo.audit_log.exists()


def test_new_draws_get_a_new_version_and_the_same_data_is_up_to_date(repo, games, fake_source):
    game = games["zz_starlotto"]
    draws = make_draws(game, 12, start=date(2026, 3, 1))
    fake_source("zz_starlotto", [raw(d) for d in draws[:10]])
    run(repo, "zz_starlotto")
    fake_source("zz_starlotto", [raw(d) for d in draws[5:]])  # recent slice overlapping the published draws
    result = run(repo, "zz_starlotto", now=NOW + timedelta(hours=1))
    assert result.changes.summary()["added"] == 2 and result.dataset_version == "2026.10.08.002"
    assert load_published(repo, game).dataset.draws == draws
    again = run(repo, "zz_starlotto", now=NOW + timedelta(hours=2))
    assert again.up_to_date and not again.written
    assert len(read_events(repo)) == 2


def test_published_history_is_never_changed_silently(repo, games, fake_source):
    game = games["zz_starlotto"]
    draws = make_draws(game, 6, start=date(2026, 3, 1))
    fake_source("zz_starlotto", [raw(d) for d in draws])
    run(repo, "zz_starlotto")
    corrected = replace(draws[2], main_numbers=(1, 2, 3, 4, 5))
    fake_source("zz_starlotto", [raw(d) for d in draws[:2] + [corrected] + draws[3:]])
    with pytest.raises(HistoryChanged):
        run(repo, "zz_starlotto", now=NOW + timedelta(hours=1))
    assert load_published(repo, game).dataset.draws == draws
    result = run(repo, "zz_starlotto", now=NOW + timedelta(hours=1), accept=True)
    assert result.changes.summary()["changed"] == [draws[2].draw_id]
    assert read_events(repo)[-1]["accepted_history_changes"]


def test_rejected_rows_are_quarantined_and_all_rejected_fails(repo, games, fake_source):
    game = games["zz_starlotto"]
    draws = make_draws(game, 4, start=date(2026, 3, 1))
    broken = raw(draws[3], "page 0 row 4")
    broken.data["special_numbers"] = {"star": [99]}
    fake_source("zz_starlotto", [raw(d) for d in draws[:3]] + [broken],
                rejected=[RejectedRecord("page 0 row 9", "no draw id", ["?"])])
    result = run(repo, "zz_starlotto")
    assert result.written and len(result.rejected) == 2
    quarantined = list(repo.quarantine_dir.glob("zz_starlotto_*.json"))
    assert len(quarantined) == 1 and "page 0 row 4" in quarantined[0].read_text(encoding="utf-8")
    fake_source("zz_starlotto", [], rejected=[RejectedRecord("page 0 row 1", "unreadable", [])])
    with pytest.raises(ParseFailed):
        run(repo, "zz_starlotto", now=NOW + timedelta(hours=1))
    fake_source("zz_starlotto", [])
    with pytest.raises(NoDataFound):
        run(repo, "zz_starlotto", now=NOW + timedelta(hours=1))


def test_numbered_games_need_known_gaps_and_vietlott_numbers_are_checked(repo, games, fake_source):
    game = games["power655"]
    draws = make_draws(game, 8, start=date(2026, 3, 1))
    fake_source("power655", [raw(d) for d in draws[:3] + draws[4:]])
    with pytest.raises(Exception, match="missing_draw_id"):
        run(repo, "power655")
    bad = raw(draws[3])
    bad.data["bonus_number"] = draws[3].main_numbers[0]
    fake_source("power655", [raw(d) for d in draws[:3]] + [bad] + [raw(d) for d in draws[4:]])
    with pytest.raises(Exception, match="missing_draw_id"):
        run(repo, "power655")  # the bad row is rejected, which leaves a gap


def test_restricted_games_are_never_published(repo, games, fake_source):
    registry = json.loads(repo.registry_file.read_text(encoding="utf-8"))
    for entry in registry["games"]:
        if entry["game_code"] == "zz_starlotto":
            entry["distribution_mode"] = "restricted"
    write_json(repo.registry_file, registry)
    fake_source("zz_starlotto", [raw(d) for d in make_draws(games["zz_starlotto"], 3, start=date(2026, 3, 1))])
    with pytest.raises(DistributionRestricted):
        run(repo, "zz_starlotto")
    assert not repo.draws_file(games["zz_starlotto"]).exists()

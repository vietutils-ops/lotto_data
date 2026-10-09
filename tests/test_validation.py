from dataclasses import replace
from datetime import date, datetime, timezone

from scripts.lottodata.models import Dataset, Draw
from scripts.lottodata.validation import today_in, validate_dataset
from tests.conftest import make_draws


def dataset(game, draws):
    return Dataset(game.game_code, game.country_code, game.operator_code, "2026.10.08.001", "2026-10-08T12:00:00Z", draws)


def codes(report):
    return {i.code for i in report.errors}


def test_a_two_era_game_validates_each_draw_under_its_era(games):
    game = games["zz_starlotto"]
    draws = make_draws(game, 20, start=date(2009, 11, 1)) + make_draws(game, 20, start=date(2025, 1, 1), seed=2)
    report = validate_dataset(game, dataset(game, draws), today=date(2026, 10, 8))
    assert report.ok, [i.render() for i in report.issues]
    assert {d.ruleset_version for d in draws} == {"zz_starlotto_v1", "zz_starlotto_v2"}


def test_rulesets_ids_and_dates_are_enforced(games):
    game = games["zz_starlotto"]
    draws = make_draws(game, 4, start=date(2025, 1, 1))
    today = date(2026, 10, 8)
    assert "unknown_ruleset" in codes(validate_dataset(
        game, dataset(game, draws[:3] + [replace(draws[3], ruleset_version="zz_starlotto_v9")]), today=today))
    assert "ruleset_date_mismatch" in codes(validate_dataset(
        game, dataset(game, draws[:3] + [replace(draws[3], ruleset_version="zz_starlotto_v1")]), today=today))
    assert "draw_id_date_mismatch" in codes(validate_dataset(
        game, dataset(game, draws[:3] + [replace(draws[3], draw_id="20250101")]), today=today))
    assert "unsorted_draws" in codes(validate_dataset(game, dataset(game, list(reversed(draws))), today=today))
    assert "future_draw_date" in codes(validate_dataset(game, dataset(game, draws), today=date(2025, 1, 6)))
    assert "invalid_numbers" in codes(validate_dataset(
        game, dataset(game, draws[:3] + [replace(draws[3], special_numbers=(("star", (26,)),))]), today=today))


def test_numbered_games_may_only_skip_recorded_gaps(games):
    game = games["power655"]
    draws = make_draws(game, 6, start=date(2025, 1, 1))
    with_gap = draws[:2] + draws[3:]
    assert "missing_draw_id" in codes(validate_dataset(game, dataset(game, with_gap), today=date(2026, 10, 8)))
    report = validate_dataset(game, dataset(game, with_gap), known_gaps=[draws[2].draw_id], today=date(2026, 10, 8))
    assert report.ok
    resolved = validate_dataset(game, dataset(game, draws), known_gaps=[draws[2].draw_id], today=date(2026, 10, 8))
    assert resolved.ok and [w.code for w in resolved.warnings] == ["gap_resolved"]


def test_duplicate_dates_and_coverage(games):
    game = games["mega645"]
    draws = make_draws(game, 3, start=date(2025, 1, 1))
    same_day = [draws[0], replace(draws[1], draw_date=draws[0].draw_date)]
    assert "duplicate_draw_date" in codes(validate_dataset(game, dataset(game, same_day), today=date(2026, 10, 8)))
    early = make_draws(game, 1, start=date(2016, 7, 1))
    early = [replace(early[0], draw_date=date(2016, 6, 29))]
    assert "implausible_draw_date" in codes(validate_dataset(game, dataset(game, early), today=date(2026, 10, 8)))


def test_today_is_the_date_in_the_game_time_zone():
    late_evening_utc = datetime(2026, 10, 8, 18, 0, tzinfo=timezone.utc)
    assert today_in("Asia/Ho_Chi_Minh", late_evening_utc) == date(2026, 10, 9)
    assert today_in("America/New_York", late_evening_utc) == date(2026, 10, 8)

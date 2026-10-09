import copy
import json
from datetime import date

import pytest

from scripts.lottodata.errors import DataInvalid, RulesetUnknown
from scripts.lottodata.layout import ROOT
from scripts.lottodata.rulesets import draw_problems, parse_rulesets
from tests.conftest import FICTIONAL_RULESETS


def vietlott(code: str, folder: str):
    return parse_rulesets(json.loads((ROOT / "games" / "vn" / folder / "rulesets.json").read_text()), code)


def record(**overrides):
    base = {"main_numbers": [1, 2, 3, 4, 5, 6], "bonus_number": None, "supplementary_numbers": [], "special_numbers": {}}
    return {**base, **overrides}


def test_vietlott_rulesets_match_the_app():
    mega = vietlott("mega645", "vietlott_mega645").current
    assert (mega.ruleset_id, mega.effective_from, mega.main.count, mega.main.max) == ("mega645_v1", date(2016, 7, 1), 6, 45)
    assert mega.extras == ()
    power = vietlott("power655", "vietlott_power655").current
    assert (power.ruleset_id, power.effective_from, power.main.max) == ("power655_v1", date(2017, 8, 1), 55)
    bonus = power.by_field("bonus_number")[0]
    assert (bonus.id, bonus.kind, bonus.min, bonus.max) == ("bonus", "same_pool_extra", 1, 55)


def test_a_timeline_resolves_the_era_of_a_date():
    timeline = parse_rulesets(FICTIONAL_RULESETS, "zz_starlotto")
    assert timeline.for_date(date(2005, 6, 1)).ruleset_id == "zz_starlotto_v1"
    assert timeline.for_date(date(2010, 1, 2)) is None
    assert timeline.for_date(date(2026, 1, 6)).ruleset_id == "zz_starlotto_v2"
    with pytest.raises(RulesetUnknown):
        timeline.require_for_date(date(1999, 12, 31))


@pytest.mark.parametrize("edit, message", [
    (lambda d: d["rulesets"][0].update(effective_to=None), "only the latest ruleset may be open-ended"),
    (lambda d: d["rulesets"][0].update(effective_to="2010-01-05"), "overlaps"),
    (lambda d: d["rulesets"][1]["ball_sets"][0].update(max=128), "not within 0–127"),
    (lambda d: d["rulesets"][1]["ball_sets"][1].update(field="bonus_number"), "separate pools go to special_numbers"),
    (lambda d: d["rulesets"][1]["ball_sets"][0].update(label={"fr": "Numéros"}), "English label"),
    (lambda d: d["rulesets"][1].update(extra=True), "exactly the keys"),
    (lambda d: d.update(game_code="other"), "belongs to other"),
])
def test_invalid_rulesets_are_rejected(edit, message):
    document = copy.deepcopy(FICTIONAL_RULESETS)
    edit(document)
    with pytest.raises(DataInvalid, match=message):
        parse_rulesets(document, "zz_starlotto")


def test_same_pool_extras_must_fit_the_main_pool():
    document = copy.deepcopy(FICTIONAL_RULESETS)
    document["rulesets"][1]["ball_sets"].append({
        "id": "bonus", "kind": "same_pool_extra", "count": 1, "min": 1, "max": 69,
        "field": "bonus_number", "player_selectable": False, "label": {"en": "Bonus"}})
    with pytest.raises(DataInvalid, match="same-pool balls must use the main range"):
        parse_rulesets(document, "zz_starlotto")


def test_draws_are_checked_under_their_ruleset():
    power = vietlott("power655", "vietlott_power655").current
    assert draw_problems(power, record(bonus_number=7)) == []
    assert "bonus: bonus number missing" in draw_problems(power, record())
    assert any("repeats a drawn ball" in p for p in draw_problems(power, record(bonus_number=6)))
    mega = vietlott("mega645", "vietlott_mega645").current
    assert any("no bonus ball" in p for p in draw_problems(mega, record(bonus_number=7)))
    assert any("ascending" in p for p in draw_problems(mega, record(main_numbers=[2, 1, 3, 4, 5, 6])))
    assert any("out of range" in p for p in draw_problems(mega, record(main_numbers=[1, 2, 3, 4, 5, 46])))

    star = parse_rulesets(FICTIONAL_RULESETS, "zz_starlotto").current
    ok = record(main_numbers=[3, 41, 63, 69, 70], special_numbers={"star": [25]})
    assert draw_problems(star, ok) == []
    assert any("star: missing" in p for p in draw_problems(star, {**ok, "special_numbers": {}}))
    assert any("out of range" in p for p in draw_problems(star, {**ok, "special_numbers": {"star": [26]}}))
    assert any("no such ball set" in p for p in draw_problems(star, {**ok, "special_numbers": {"star": [1], "x": [1]}}))

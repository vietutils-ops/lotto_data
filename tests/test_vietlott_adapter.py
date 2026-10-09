"""Vietlott listing parser and adapter (network faked).

The pages below are HAND-WRITTEN in the listing's structure (header row, then
date / draw ID / numbers cells), not captures; their numbers are the
published results of those draws in this repository.
"""

import json

import pytest

from scripts.lottodata.adapters.vietlott import VietlottAdapter, looks_like_challenge, parse_listing_html
from scripts.lottodata.errors import AccessDenied, ParseFailed
from scripts.lottodata.http import CollectorConfig, HttpClient, HttpResponse
from scripts.lottodata.normalize import normalize_records
from scripts.lottodata.serialization import read_json_file
from tests.conftest import published_vietlott


def by_id(code):
    return {r["draw_id"]: r for r in published_vietlott(code)}


def mega_page(*draw_ids):
    rows = []
    for draw_id in draw_ids:
        r = by_id("mega645")[draw_id]
        y, m, d = r["draw_date"].split("-")
        balls = "".join(f'<span class="bong_tron small">{n:02d}</span>' for n in r["main_numbers"])
        rows.append(f"<tr><td>{d}/{m}/{y}</td><td><a href='#'>{draw_id}</a></td><td><div>{balls}</div></td></tr>")
    return "<table><thead><tr><th>Ngày</th><th>Kỳ</th><th>Bộ số</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"


def power_row(draw_id, *, separator=True, marker=True):
    r = by_id("power655")[draw_id]
    y, m, d = r["draw_date"].split("-")
    balls = "".join(f"<span>{n:02d}</span>" for n in r["main_numbers"])
    bonus = f'<span class="{"bong_tron active" if marker else "x"}">{r["bonus_number"]:02d}</span>'
    return f"<tr><td>{d}/{m}/{y}</td><td>#{draw_id}</td><td>{balls}{'<i>|</i>' if separator else ''}{bonus}</td></tr>"


def test_mega_rows_parse_into_the_published_draws(games):
    game = games["mega645"]
    page = parse_listing_html(mega_page("01572", "01571"), game, page_ref="page 0")
    assert page.row_count == 2 and not page.rejected
    draws = normalize_records(page.records, game).draws
    published = by_id("mega645")
    assert [d.to_record() for d in draws] == [published["01571"], published["01572"]]


def test_power_bonus_needs_a_separator_or_a_marker(games):
    game = games["power655"]
    published = by_id("power655")
    for row in (power_row("01407"), power_row("01407", separator=False)):
        page = parse_listing_html(f"<table>{row}</table>", game, page_ref="p")
        assert [d.to_record() for d in normalize_records(page.records, game).draws] == [published["01407"]]
    ambiguous = parse_listing_html(f"<table>{power_row('01407', separator=False, marker=False)}</table>", game, page_ref="p")
    assert not ambiguous.records and "unambiguously" in ambiguous.rejected[0].reason


def test_malformed_rows_are_rejected_with_reasons(games):
    page = parse_listing_html(
        "<table><tr><td>2026-10-07</td><td>01572</td><td>1 2 3 4 5 6</td></tr>"
        "<tr><td>07/10/2026</td><td>01572</td><td>1 2 3 4 5</td></tr></table>",
        games["mega645"], page_ref="p")
    assert not page.records
    assert ["no dd/mm/yyyy date" in page.rejected[0].reason, "expected 6 numbers" in page.rejected[1].reason] == [True, True]


def adapter(games, responses):
    settings = read_json_file(__import__("scripts.lottodata.layout", fromlist=["ROOT"]).ROOT / "sources" / "adapters" / "vietlott.json")
    pages = iter(responses)

    def transport(method, url, headers, body, timeout):
        if url.endswith("/robots.txt"):
            return HttpResponse(404, b"")
        return next(pages)

    client = HttpClient(CollectorConfig(retry_count=0), transport=transport, sleep=lambda s: None)
    return VietlottAdapter(client, games["mega645"], settings)


def ajax(html):
    return HttpResponse(200, json.dumps({"value": {"HtmlContent": html}}).encode())


def test_fetch_reads_pages_back_to_the_published_draw(games):
    a = adapter(games, [ajax(mega_page("01572", "01571")), ajax(mega_page("01570", "01569")), ajax("<table></table>")])
    since = normalize_records(parse_listing_html(mega_page("01570"), games["mega645"], page_ref="x").records,
                              games["mega645"]).draws[0]
    result = a.fetch(since=since, max_pages=5)
    assert [r.data["draw_id"] for r in result.records] == ["01572", "01571", "01570", "01569"]
    assert result.source_url.startswith("https://vietlott.vn/ajaxpro/")


def test_challenge_pages_and_garbage_are_refused(games):
    assert looks_like_challenge("<html>Please complete the CAPTCHA</html>")
    with pytest.raises(AccessDenied):
        adapter(games, [HttpResponse(200, b"<html>Attention Required! captcha</html>")]).fetch_page(0)
    with pytest.raises(ParseFailed):
        adapter(games, [HttpResponse(200, b"not json")]).fetch_page(0)
    with pytest.raises(ParseFailed):
        adapter(games, [HttpResponse(200, b'{"value": {}}')]).fetch_page(0)

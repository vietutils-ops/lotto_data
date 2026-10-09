"""Vietlott (Vietnam): the public result listing of vietlott.vn.

The same paginated requests the site's own result table performs. The parser
is strict: a row is accepted only when its structure is unambiguous (date
cell, draw-ID cell, number cell; a bonus ball must be separated by '|' or
marked with a special CSS class). Anything else is rejected with a reason —
results are never inferred.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, ClassVar, Dict, List, Mapping, Optional, Tuple

from ..errors import AccessDenied, ParseFailed, SourceUnavailable
from ..games import GameDefinition
from ..http import HttpClient
from ..models import Draw, RejectedRecord
from ..normalize import NormalizationError, RawRecord, normalize_date
from ..serialization import utc_now_iso
from . import FetchResult, LotterySourceAdapter

_CHALLENGE_MARKERS = ("captcha", "cf-challenge", "challenge-platform", "access denied",
                      "attention required", "request unsuccessful", "are you a robot")
_BONUS_CLASSES = {"active", "special", "power", "jackpot2", "dac-biet", "dac_biet", "bonus"}
_DATE_TEXT = re.compile(r"([0-9]{1,2})/([0-9]{1,2})/([0-9]{4})")
_ID_TEXT = re.compile(r"#?\s*([0-9]{1,7})")


@dataclass
class ParsedPage:
    records: List[RawRecord] = field(default_factory=list)
    rejected: List[RejectedRecord] = field(default_factory=list)
    row_count: int = 0


def looks_like_challenge(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CHALLENGE_MARKERS)


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise ParseFailed("beautifulsoup4 is required: pip install -r requirements.txt") from exc
    return BeautifulSoup(html, "html.parser")


def _split_number_cell(cell, main_count: int, has_bonus: bool) -> Tuple[List[int], Optional[int]]:
    """Return (main, bonus) from the numbers cell or raise ValueError."""
    from bs4 import Comment, NavigableString

    tokens: List[Tuple[str, set]] = []
    for node in cell.descendants:
        if not isinstance(node, NavigableString) or isinstance(node, Comment):
            continue
        classes: set = set()
        ancestor = node.parent
        while ancestor is not None and ancestor is not cell:
            classes |= {c.lower() for c in (ancestor.get("class") or [])}
            ancestor = ancestor.parent
        for text in re.findall(r"\||[0-9]+", str(node)):
            tokens.append((text, classes))
    if not tokens:
        raise ValueError("number cell is empty")

    groups: List[List[int]] = [[]]
    marked: List[int] = []
    for text, classes in tokens:
        if text == "|":
            groups.append([])
            continue
        value = int(text)
        groups[-1].append(value)
        if classes & _BONUS_CLASSES:
            marked.append(value)
    numbers = [n for g in groups for n in g]

    if not has_bonus:
        if len(numbers) != main_count:
            raise ValueError(f"expected {main_count} numbers, found {len(numbers)}: {numbers}")
        return numbers, None

    if len(numbers) != main_count + 1:
        raise ValueError(f"expected {main_count + 1} numbers (main + bonus), found {len(numbers)}: {numbers}")
    non_empty = [g for g in groups if g]
    if len(non_empty) == 2 and len(non_empty[1]) == 1 and len(non_empty[0]) == main_count:
        return non_empty[0], non_empty[1][0]
    if len(marked) == 1:
        bonus = marked[0]
        main = list(numbers)
        main.remove(bonus)
        return main, bonus
    raise ValueError("cannot identify the bonus number unambiguously (no '|' separator or "
                     f"special marker): {numbers}")


def parse_listing_html(html: str, game: GameDefinition, *, page_ref: str) -> ParsedPage:
    """Rows of one listing page. Expected ball counts come from the ruleset
    covering each row's date."""
    soup = _soup(html)
    parsed = ParsedPage()
    for row_index, row in enumerate(soup.find_all("tr")):
        cells = row.find_all("td")
        if not cells:
            continue  # header row (th) or layout row
        parsed.row_count += 1
        ref = f"{page_ref} row {row_index}"
        raw_cells = [c.get_text(" ", strip=True) for c in cells]
        try:
            if len(cells) < 3:
                raise ValueError(f"expected at least 3 cells, found {len(cells)}")
            date_match = _DATE_TEXT.search(cells[0].get_text(" ", strip=True))
            if not date_match:
                raise ValueError(f"no dd/mm/yyyy date in {raw_cells[0]!r}")
            id_match = _ID_TEXT.fullmatch(cells[1].get_text("", strip=True))
            if not id_match:
                raise ValueError(f"no draw id in {raw_cells[1]!r}")
            day, month, year = date_match.groups()
            draw_date = f"{int(day):02d}/{int(month):02d}/{year}"
            ruleset = game.timeline.for_date(normalize_date(draw_date)) if game.timeline else None
            if ruleset is None:
                raise ValueError(f"no ruleset covers {draw_date}")
            main, bonus = _split_number_cell(
                cells[2], ruleset.main.count, bool(ruleset.by_field("bonus_number")))
        except (ValueError, NormalizationError) as exc:
            parsed.rejected.append(RejectedRecord(ref, str(exc), raw_cells))
            continue
        parsed.records.append(RawRecord(ref, {
            "draw_id": id_match.group(1),
            "draw_date": draw_date,
            "main_numbers": main,
            "bonus_number": bonus,
        }))
    return parsed


class VietlottAdapter(LotterySourceAdapter):
    """Pages of the public result listing (page 0 = most recent)."""

    adapter_id: ClassVar[str] = "vietlott"
    source_name: ClassVar[str] = "vietlott.vn public result listing"

    def __init__(self, client: HttpClient, game: GameDefinition, settings: Mapping[str, Any]):
        super().__init__(client, game, settings)
        try:
            self.game_settings = settings["games"][game.game_code]
        except KeyError as exc:
            raise SourceUnavailable(f"no Vietlott listing settings for {game.game_code}", game=game.game_code) from exc

    @property
    def endpoint_url(self) -> str:
        return self.settings["base_url"] + self.game_settings["endpoint"]

    def _body(self, page_index: int) -> bytes:
        body = {
            "ORenderInfo": self.settings["render_info"],
            "Key": self.game_settings["key"],
            "GameDrawId": "",
            "ArrayNumbers": [["" for _ in range(18)] for _ in range(5)],
            "CheckMulti": False,
            "PageIndex": page_index,
        }
        return json.dumps(body).encode("utf-8")

    def fetch_raw_page(self, page_index: int) -> str:
        """The source's response for one listing page, unparsed (for fixtures)."""
        response = self.client.request(
            "POST", self.endpoint_url,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "X-AjaxPro-Method": self.settings["method_header"],
                "Referer": self.settings["base_url"] + self.game_settings["referer_path"],
            },
            body=self._body(page_index))
        return response.body.decode("utf-8", errors="replace")

    def fetch_page(self, page_index: int) -> ParsedPage:
        return self.parse_response(self.fetch_raw_page(page_index), page_index)

    def parse_response(self, text: str, page_index: int) -> ParsedPage:
        code = self.game.game_code
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            if looks_like_challenge(text):
                raise AccessDenied("The source returned an access-control/challenge page instead of data. "
                                   "The collector does not bypass access controls.", game=code) from exc
            raise ParseFailed(f"page {page_index}: response is not JSON ({text[:120]!r})", game=code) from exc
        if not isinstance(payload, dict):
            raise ParseFailed(f"page {page_index}: unexpected JSON payload type", game=code)
        if payload.get("error"):
            raise SourceUnavailable(f"page {page_index}: source error {payload['error']!r}", game=code)
        html = (payload.get("value") or {}).get("HtmlContent")
        if not isinstance(html, str):
            raise ParseFailed(f"page {page_index}: payload has no value.HtmlContent", game=code)
        if looks_like_challenge(html) and "<td" not in html:
            raise AccessDenied("The source returned a challenge page instead of results.", game=code)
        return parse_listing_html(html, self.game, page_ref=f"page {page_index}")

    def fetch(self, *, since: Optional[Draw], max_pages: int) -> FetchResult:
        result = FetchResult(source_url=self.endpoint_url, retrieved_at=utc_now_iso())
        for page_index in range(max_pages):
            page = self.fetch_page(page_index)
            result.records.extend(page.records)
            result.rejected.extend(page.rejected)
            if page.row_count == 0:
                break
            if since is not None and any(
                str(r.data["draw_id"]).isdigit() and int(r.data["draw_id"]) <= since.sequence for r in page.records
            ):
                break
        return result

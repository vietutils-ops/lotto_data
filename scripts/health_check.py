"""Health of every game: repository validation, data freshness against the
game's schedule, audit log consistency and, with --live, whether each
official source is reachable and how far behind the published data is.

    python -m scripts.health_check
    python -m scripts.health_check --live [--game CODE]

Exit code 1 when any game has an error (warnings do not fail).
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from typing import Any, Dict, List

from scripts.lottodata.adapters import adapters
from scripts.lottodata.audit import read_events
from scripts.lottodata.cli import now_utc, print_json
from scripts.lottodata.errors import LottoDataError
from scripts.lottodata.games import GameDefinition, load_games
from scripts.lottodata.http import CollectorConfig, HttpClient
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.normalize import normalize_records
from scripts.lottodata.repo_validation import validate_repository
from scripts.lottodata.repository import load_published
from scripts.lottodata.serialization import read_json_file
from scripts.lottodata.validation import today_in

#: A scheduled draw missing for longer than this makes the data "stale".
PUBLISH_GRACE = timedelta(days=2)


def last_scheduled_on_or_before(day, weekdays):
    for _ in range(8):
        if day.isoweekday() in weekdays:
            return day
        day -= timedelta(days=1)
    raise ValueError("no draw weekdays")


def offline_checks(layout: RepoLayout, game: GameDefinition, now) -> Dict[str, Any]:
    status: Dict[str, Any] = {"game": game.game_code, "distribution_mode": game.distribution_mode}
    published = load_published(layout, game)
    if not game.publishes_data or published.dataset is None:
        status["latest_draw_date"] = None
        return status
    latest = published.dataset.latest()
    today = today_in(game.timezone, now)
    expected = last_scheduled_on_or_before(today - PUBLISH_GRACE, game.draw_weekdays)
    status.update(
        dataset_version=published.dataset.dataset_version,
        latest_draw_id=latest.draw_id,
        latest_draw_date=latest.draw_date.isoformat(),
        stale=latest.draw_date < expected,
        expected_at_least=expected.isoformat(),
    )
    events = [e for e in read_events(layout) if e.get("game") == game.game_code]
    status["audit_consistent"] = bool(events) and events[-1].get("dataset_version") == published.dataset.dataset_version
    return status


def live_check(layout: RepoLayout, game: GameDefinition, client: HttpClient, latest_published) -> Dict[str, Any]:
    factories = adapters()
    if game.adapter not in factories:
        return {"live": "no_adapter"}
    settings = read_json_file(layout.root / "sources" / "adapters" / f"{game.adapter}.json")
    try:
        fetched = factories[game.adapter](client, game, settings).fetch(since=None, max_pages=1)
    except LottoDataError as exc:
        return {"live": "error", "error": exc.code, "detail": str(exc)}
    draws = normalize_records(fetched.records, game).draws
    if not draws:
        return {"live": "error", "error": "parse_failed", "detail": f"{len(fetched.rejected)} rows rejected"}
    newest = draws[-1]
    behind = 0 if latest_published is None else sum(1 for d in draws if d.sequence > latest_published.sequence)
    return {"live": "ok", "source_latest_draw_id": newest.draw_id, "source_latest_draw_date": newest.draw_date.isoformat(),
            "draws_behind_on_first_page": behind}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--live", action="store_true", help="also query each official source (network)")
    parser.add_argument("--game", action="append", metavar="CODE", help="limit to these games")
    args = parser.parse_args(argv)

    layout = RepoLayout()
    now = now_utc()
    report = validate_repository(layout, now)
    games = load_games(layout)
    selected: List[GameDefinition] = [g for code, g in games.items() if not args.game or code in args.game]
    client = HttpClient(CollectorConfig.from_env()) if args.live else None
    failed = not report.repository.ok
    results = []
    for game in selected:
        status = offline_checks(layout, game, now)
        game_report = report.games.get(game.game_code)
        status["errors"] = [i.render() for i in game_report.errors] if game_report else []
        status["warnings"] = [i.render() for i in game_report.warnings] if game_report else []
        if status.get("stale"):
            status["warnings"].append("WARNING stale: a scheduled draw is missing (run scripts.update)")
        if status.get("audit_consistent") is False:
            status["warnings"].append("WARNING audit_log: the latest audit event does not match the dataset version")
        if client is not None and game.publishes_data:
            published = load_published(layout, game)
            status.update(live_check(layout, game, client, published.dataset.latest() if published.dataset else None))
            if status.get("live") == "error":
                status["errors"].append(f"ERROR {status['error']}: {status['detail']}")
        failed = failed or bool(status["errors"])
        results.append(status)
    print_json({"checked_at": now.isoformat(), "repository_errors": [i.render() for i in report.repository.errors],
                "games": results})
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

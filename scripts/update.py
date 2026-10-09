"""Collects new draws from each game's official source and publishes them.

    python -m scripts.update --game power655            # dry run: what would change
    python -m scripts.update --game power655 --write    # write files, catalog, checksums, audit log
    python -m scripts.update --all --write [--run-tests]

Per game: fetch (source adapter, robots.txt honoured, rate-limited) →
normalize → assign ruleset → validate → detect changes → (write) draws,
metadata, source, catalog, checksums → audit log. One game's failure never
stops the others. Published draws are never changed or removed unless
--accept-changes is given after checking the official source.

Network settings: LOTTO_HTTP_TIMEOUT, LOTTO_RETRY_COUNT, LOTTO_RETRY_BACKOFF,
LOTTO_RATE_LIMIT_DELAY (>= 1 s), LOTTO_USER_AGENT, LOTTO_PROXY.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from typing import List

from scripts.lottodata.cli import add_game_selection, now_utc, print_json, selected_games
from scripts.lottodata.errors import LottoDataError
from scripts.lottodata.games import load_games
from scripts.lottodata.http import CollectorConfig, HttpClient
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.pipeline import update_game
from scripts.lottodata.repo_validation import validate_repository


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    add_game_selection(parser)
    parser.add_argument("--write", action="store_true", help="write the files (default: dry run)")
    parser.add_argument("--accept-changes", action="store_true",
                        help="allow published draws to change or disappear (check the official source first)")
    parser.add_argument("--max-pages", type=int, default=3, help="source pages to read per game (default 3)")
    parser.add_argument("--run-tests", action="store_true", help="run pytest after writing")
    args = parser.parse_args(argv)

    layout = RepoLayout()
    games = load_games(layout)
    client = HttpClient(CollectorConfig.from_env(), log=lambda message: print(message, file=sys.stderr))
    failures: List[LottoDataError] = []
    for game in selected_games(args, games):
        try:
            result = update_game(
                layout, games, game, client,
                now=now_utc(), write=args.write, accept_changes=args.accept_changes, max_pages=args.max_pages,
            )
            print_json({**result.summary(), "status": "up_to_date" if result.up_to_date else "changed"})
        except LottoDataError as exc:
            exc.game = exc.game or game.game_code
            failures.append(exc)
            print_json({"game": game.game_code, "status": "failed", "error": exc.code, "detail": str(exc)})
    if args.write:
        report = validate_repository(layout, now_utc())
        if not report.ok:
            print("\n".join(report.lines()), file=sys.stderr)
            return 1
        if args.run_tests and subprocess.call([sys.executable, "-m", "pytest", "-q"]) != 0:
            return 1
    for e in failures:
        print(e.render(), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

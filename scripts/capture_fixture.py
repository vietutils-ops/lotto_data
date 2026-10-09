"""Saves one raw response of a game's official source as a test fixture
(tests/fixtures/<adapter>/<game>_page<N>_<date>.txt), so parser tests run on
real samples. The tests check every saved row against the published draws.

    python -m scripts.capture_fixture --game power655 [--page 0]

Run it from a network where the source is reachable; robots.txt and the rate
limit apply as for the collector. Review a capture before committing it.
"""

from __future__ import annotations

import argparse
import sys

from scripts.lottodata.adapters import adapters
from scripts.lottodata.cli import now_utc
from scripts.lottodata.errors import LottoDataError
from scripts.lottodata.games import load_games, require_game
from scripts.lottodata.http import CollectorConfig, HttpClient
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.serialization import atomic_write_bytes, read_json_file


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--game", required=True)
    parser.add_argument("--page", type=int, default=0)
    args = parser.parse_args(argv)
    layout = RepoLayout()
    game = require_game(load_games(layout), args.game)
    settings = read_json_file(layout.root / "sources" / "adapters" / f"{game.adapter}.json")
    adapter = adapters()[game.adapter](HttpClient(CollectorConfig.from_env()), game, settings)
    if not hasattr(adapter, "fetch_raw_page"):
        print(f"adapter {game.adapter} cannot capture raw pages", file=sys.stderr)
        return 1
    try:
        text = adapter.fetch_raw_page(args.page)
    except LottoDataError as exc:
        print(exc.render(), file=sys.stderr)
        return 1
    path = layout.root / "tests" / "fixtures" / game.adapter / (
        f"{game.game_code}_page{args.page}_{now_utc().strftime('%Y%m%d')}.txt")
    atomic_write_bytes(path, text.encode("utf-8"))
    print(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())

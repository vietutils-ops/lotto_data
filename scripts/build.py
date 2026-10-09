"""Regenerates the derived files after a hand edit of rulesets.json, the
registry or the known gaps: metadata.json, source.json, catalog.json and the
checksums. A game whose draws or rulesets changed gets a new dataset version,
so apps download it again.

    python -m scripts.build                          # dry run
    python -m scripts.build --write
    python -m scripts.build --write --accept-changes # also relabel draws whose
                                                     # date now falls in another ruleset

Relabelling changes published history, so it needs --accept-changes and is
recorded in the audit log.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from typing import List

from scripts.lottodata.audit import append_event
from scripts.lottodata.checksum import sha256_bytes
from scripts.lottodata.cli import now_utc, print_json
from scripts.lottodata.errors import HistoryChanged, LottoDataError
from scripts.lottodata.games import load_games
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.metadata import build_source
from scripts.lottodata.models import Dataset
from scripts.lottodata.repo_validation import validate_repository
from scripts.lottodata.repository import load_published, next_dataset_version, rebuild_index, write_game
from scripts.lottodata.serialization import (
    JsonFileError, atomic_write_bytes, dumps_json, format_utc, read_bytes, read_json_file,
)
from scripts.lottodata.validation import known_gaps_for, today_in, validate_dataset


def _source_differs(path, expected) -> bool:
    """source.json is derived: a missing or unreadable one is rebuilt like an outdated one."""
    try:
        return read_json_file(path) != expected
    except JsonFileError:
        return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write", action="store_true", help="write the files (default: dry run)")
    parser.add_argument("--accept-changes", action="store_true", help="relabel draws whose ruleset changed")
    args = parser.parse_args(argv)

    layout = RepoLayout()
    games = load_games(layout)
    now = now_utc()
    failures: List[LottoDataError] = []
    anything = False
    for game in games.values():
        if game.distribution_mode == "restricted" and layout.rulesets_file(game).is_file():
            # Listed in the catalog without draws: only its source record is published.
            expected = build_source(game, None)
            path = layout.source_file(game)
            if _source_differs(path, expected):
                print_json({"game": game.game_code, "source_changed": True})
                if args.write:
                    atomic_write_bytes(path, dumps_json(expected))
                anything = True
            continue
        published = load_published(layout, game)
        if not game.publishes_data or published.dataset is None:
            continue
        try:
            draws = published.dataset.draws
            relabelled = []
            for d in draws:
                ruleset = game.timeline.require_for_date(d.draw_date)
                if ruleset.ruleset_id != d.ruleset_version:
                    relabelled.append(replace(d, ruleset_version=ruleset.ruleset_id))
            if relabelled and not args.accept_changes:
                raise HistoryChanged(
                    f"{len(relabelled)} draws fall in another ruleset now (first {relabelled[0].draw_id}); "
                    "re-run with --accept-changes", game=game.game_code)
            by_id = {d.draw_id: d for d in relabelled}
            draws = [by_id.get(d.draw_id, d) for d in draws]
            metadata = published.metadata or {}
            rulesets_changed = metadata.get("rulesets_sha256") != sha256_bytes(read_bytes(layout.rulesets_file(game)))
            draws_changed = metadata.get("sha256") != sha256_bytes(read_bytes(layout.draws_file(game))) or bool(relabelled)
            provenance = metadata.get("provenance") or {}
            status = {"game": game.game_code, "rulesets_changed": rulesets_changed, "draws_changed": draws_changed,
                      "relabelled": len(relabelled)}
            if rulesets_changed or draws_changed:
                version = next_dataset_version(metadata.get("dataset_version"), now)
                dataset = Dataset(game.game_code, game.country_code, game.operator_code, version, format_utc(now), draws)
                gaps = known_gaps_for(read_json_file(layout.known_gaps_file), game.game_code) \
                    if layout.known_gaps_file.is_file() else []
                validate_dataset(game, dataset, known_gaps=gaps, today=today_in(game.timezone, now)) \
                    .raise_for_errors(game.game_code)
                status["dataset_version"] = version
                if args.write:
                    write_game(layout, game, dataset, provenance=provenance)
                    append_event(layout, {
                        "at": format_utc(now), "action": "rebuild", "game": game.game_code,
                        "dataset_version": version, "previous_version": metadata.get("dataset_version"),
                        "rulesets_changed": rulesets_changed, "relabelled": [d.draw_id for d in relabelled],
                    })
                anything = True
            elif _source_differs(layout.source_file(game), build_source(game, provenance)):
                status["source_changed"] = True
                if args.write:
                    atomic_write_bytes(layout.source_file(game), dumps_json(build_source(game, provenance)))
                anything = True
            print_json(status)
        except LottoDataError as exc:
            failures.append(exc)
    if args.write and anything:
        rebuild_index(layout, list(games.values()), updated_at=format_utc(now))
        report = validate_repository(layout, now)
        if not report.ok:
            print("\n".join(report.lines()), file=sys.stderr)
            return 1
    for e in failures:
        print(e.render(), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

"""Converts the Vietlott-only repository (vietlott-data, schema 1) into this
repository's per-game files (schema 2) without re-collecting anything.

Every draw keeps its ID, date and numbers; the ruleset comes from its date.
The conversion is refused unless the result is identical draw for draw.

    python -m scripts.convert_vietlott_data --source ../vietlott-data            # dry run
    python -m scripts.convert_vietlott_data --source ../vietlott-data --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

from scripts.lottodata.cli import now_utc, print_json
from scripts.lottodata.errors import DataInvalid, LottoDataError
from scripts.lottodata.games import GameDefinition, load_games
from scripts.lottodata.layout import RepoLayout
from scripts.lottodata.models import Draw
from scripts.lottodata.checksum import sha256_bytes
from scripts.lottodata.pipeline import apply_draws
from scripts.lottodata.serialization import loads_json, read_bytes
from scripts.lottodata.repository import load_published

_V1_KEYS = {"draw_id", "draw_date", "main_numbers", "bonus_number"}


def read_v1(source: Path, game: GameDefinition, product: str):
    data_bytes = read_bytes(source / "data" / f"{product}.json")
    metadata = loads_json(read_bytes(source / "metadata" / f"{product}.json"))
    if metadata.get("schema_version") != 1 or metadata.get("product") != product:
        raise DataInvalid(f"{product}: not a schema-1 metadata file", game=game.game_code)
    if sha256_bytes(data_bytes) != metadata.get("sha256"):
        raise DataInvalid(f"{product}: data file does not match its metadata checksum", game=game.game_code)
    document = loads_json(data_bytes)
    if document.get("schema_version") != 1 or document.get("product") != product:
        raise DataInvalid(f"{product}: not a schema-1 dataset", game=game.game_code)
    draws: List[Draw] = []
    for record in document["draws"]:
        if set(record) != _V1_KEYS:
            raise DataInvalid(f"{product}: unexpected record keys {sorted(record)}", game=game.game_code)
        from datetime import date

        day = date.fromisoformat(record["draw_date"])
        ruleset = game.timeline.require_for_date(day)
        draws.append(Draw(
            draw_id=record["draw_id"],
            draw_date=day,
            ruleset_version=ruleset.ruleset_id,
            main_numbers=tuple(record["main_numbers"]),
            bonus_number=record["bonus_number"],
        ))
    return draws, metadata


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", required=True, type=Path, help="checkout of the vietlott-data repository")
    parser.add_argument("--write", action="store_true", help="write the files (default: dry run)")
    args = parser.parse_args(argv)

    layout = RepoLayout()
    games = load_games(layout)
    now = now_utc()
    failures: List[LottoDataError] = []
    for game in games.values():
        product = None
        # The registry names the schema-1 product of each Vietlott game.
        from scripts.lottodata.serialization import read_json_file

        for entry in read_json_file(layout.registry_file)["games"]:
            if entry["game_code"] == game.game_code:
                product = entry.get("vietlott_data_product")
        if product is None:
            continue
        try:
            draws, metadata = read_v1(args.source, game, product)
            source_provenance = metadata.get("provenance") or {}
            provenance = {
                "original_source": source_provenance.get("original_source"),
                "acquisition_method": "conversion",
                "source_name": "viettran88/vietlott-data",
                "source_url": "https://github.com/viettran88/vietlott-data",
                "source_dataset_version": metadata["dataset_version"],
                "source_sha256": metadata["sha256"],
                "retrieved_at": source_provenance.get("retrieved_at"),
                "normalized_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "notes": "Converted from the Vietlott-only repository (schema 1) without re-collecting; every "
                "draw is identical. That repository's records were bootstrapped from "
                f"{source_provenance.get('source_name')} at {source_provenance.get('source_revision')} "
                "(see PROVENANCE.md). Full history: metadata/audit_log.jsonl.",
            }
            result = apply_draws(
                layout, games, game, draws,
                complete=True, now=now, provenance=provenance, write=args.write,
                accept_changes=False, action="convert",
            )
            if args.write:
                converted = load_published(layout, game).dataset.draws
                if [d.to_record() for d in converted] != [d.to_record() for d in draws]:
                    raise DataInvalid("converted draws differ from the source", game=game.game_code)
            print_json(result.summary())
        except LottoDataError as exc:
            failures.append(exc)
    for e in failures:
        print(e.render(), file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

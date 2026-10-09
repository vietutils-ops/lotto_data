"""Generated files: metadata.json, source.json and catalog.json."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional, Sequence

from . import CATALOG_SCHEMA_VERSION, SCHEMA_VERSION, TOOL_NAME, TOOL_VERSION
from .checksum import sha256_bytes
from .games import GameDefinition
from .models import Dataset


def build_metadata(
    game: GameDefinition,
    dataset: Dataset,
    *,
    draws_bytes: bytes,
    rulesets_bytes: bytes,
    missing_draw_ids: Sequence[str],
    provenance: Mapping[str, Any],
) -> Dict[str, Any]:
    """``metadata.json`` for exactly these ``draws.json`` and ``rulesets.json`` bytes."""
    first, latest = dataset.first(), dataset.latest()
    if first is None or latest is None:
        raise ValueError("cannot describe an empty dataset")
    ruleset_ids = []
    for d in dataset.draws:
        if d.ruleset_version not in ruleset_ids:
            ruleset_ids.append(d.ruleset_version)
    return {
        "schema_version": SCHEMA_VERSION,
        "game_code": game.game_code,
        "country_code": game.country_code,
        "operator_code": game.operator_code,
        "dataset_version": dataset.dataset_version,
        "dataset_updated_at": dataset.updated_at,
        "record_count": dataset.draw_count,
        "sha256": sha256_bytes(draws_bytes),
        "byte_size": len(draws_bytes),
        "rulesets_sha256": sha256_bytes(rulesets_bytes),
        "first_draw_id": first.draw_id,
        "first_draw_date": first.draw_date.isoformat(),
        "latest_draw_id": latest.draw_id,
        "latest_draw_date": latest.draw_date.isoformat(),
        "missing_draw_ids": list(missing_draw_ids),
        "ruleset_ids": ruleset_ids,
        "provenance": dict(provenance),
        "generator": f"{TOOL_NAME}/{TOOL_VERSION}",
    }


def build_source(game: GameDefinition, provenance: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """``source.json``: where the facts come from and under which terms they are shared."""
    return {
        "schema_version": SCHEMA_VERSION,
        "game_code": game.game_code,
        "display_name": game.display_name,
        "official_source": dict(game.official_source),
        "distribution_mode": game.distribution_mode,
        "compliance": dict(game.compliance),
        "data_origin": None if provenance is None else dict(provenance),
        "disclaimer": "Historical results for statistical research. Not an official source; "
        "not affiliated with the operator. Always check results with the official source.",
    }


def build_catalog(
    games: Sequence[GameDefinition],
    metadata_by_game: Mapping[str, Mapping[str, Any]],
    *,
    updated_at: str,
) -> Dict[str, Any]:
    """``catalog.json``: every game with published files (relative URLs)."""
    entries = []
    for game in sorted(games, key=lambda g: (g.country_code, g.game_code)):
        if game.distribution_mode == "disabled":
            continue
        meta = metadata_by_game.get(game.game_code)
        if game.publishes_data and meta is None:
            continue  # no data collected yet
        entry: Dict[str, Any] = {
            "game_code": game.game_code,
            "country_code": game.country_code,
            "operator_code": game.operator_code,
            "dataset_version": meta["dataset_version"] if meta else "0000.00.00.000",
            "draws_url": f"{game.path}/draws.json",
            "metadata_url": f"{game.path}/metadata.json",
            "rulesets_url": f"{game.path}/rulesets.json",
            "source_url": f"{game.path}/source.json",
            "distribution_mode": game.distribution_mode,
        }
        if meta and game.publishes_data:
            entry.update(
                draw_count=meta["record_count"],
                first_draw_date=meta["first_draw_date"],
                latest_draw_date=meta["latest_draw_date"],
            )
        entries.append(entry)
    return {"schema_version": CATALOG_SCHEMA_VERSION, "updated_at": updated_at, "games": entries}

"""Reading and writing a game's published files consistently.

``draws.json`` is generated; ``rulesets.json`` is maintained by hand and
written only by the tools that create a game folder; ``metadata.json``,
``source.json``, ``catalog.json`` and ``checksums/SHA256SUMS`` are always
regenerated from them, so they can never disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Mapping, Optional, Sequence

from .checksum import write_checksums
from .games import GameDefinition
from .layout import RepoLayout
from .metadata import build_catalog, build_metadata, build_source
from .models import Dataset
from .serialization import atomic_write_bytes, dumps_draws, dumps_json, read_bytes, read_json_file
from .validation import missing_ids, parse_draws_document


@dataclass
class PublishedGame:
    game: GameDefinition
    dataset: Optional[Dataset]
    metadata: Optional[Dict[str, Any]]


def load_published(layout: RepoLayout, game: GameDefinition) -> PublishedGame:
    draws_path, metadata_path = layout.draws_file(game), layout.metadata_file(game)
    dataset = parse_draws_document(read_json_file(draws_path), game) if draws_path.is_file() else None
    metadata = read_json_file(metadata_path) if metadata_path.is_file() else None
    return PublishedGame(game, dataset, metadata)


def next_dataset_version(previous: Optional[str], now: datetime) -> str:
    """``YYYY.MM.DD.NNN``: today's UTC date, NNN counting up within a day.

    Always greater than [previous] (the app never downgrades, comparing
    versions as strings), even when a clock runs behind.
    """
    if now.tzinfo is None:
        raise ValueError("naive datetime; use an aware UTC datetime")
    candidate = f"{now.astimezone(timezone.utc).strftime('%Y.%m.%d')}.001"
    if previous is None or candidate > previous:
        return candidate
    prefix, counter = previous.rsplit(".", 1)
    if int(counter) >= 999:
        raise ValueError(f"no dataset version left after {previous}")
    return f"{prefix}.{int(counter) + 1:03d}"


def write_game(
    layout: RepoLayout,
    game: GameDefinition,
    dataset: Dataset,
    *,
    provenance: Mapping[str, Any],
) -> Dict[str, Any]:
    """Writes draws.json, metadata.json and source.json; returns the metadata."""
    draws_bytes = dumps_draws(dataset)
    rulesets_bytes = read_bytes(layout.rulesets_file(game))
    metadata = build_metadata(
        game,
        dataset,
        draws_bytes=draws_bytes,
        rulesets_bytes=rulesets_bytes,
        missing_draw_ids=missing_ids(game, dataset.draws),
        provenance=provenance,
    )
    atomic_write_bytes(layout.draws_file(game), draws_bytes)
    atomic_write_bytes(layout.metadata_file(game), dumps_json(metadata))
    atomic_write_bytes(layout.source_file(game), dumps_json(build_source(game, provenance)))
    return metadata


def rebuild_index(layout: RepoLayout, games: Sequence[GameDefinition], *, updated_at: str) -> Dict[str, Any]:
    """Regenerates catalog.json and checksums/SHA256SUMS from the game folders."""
    metadata_by_game: Dict[str, Dict[str, Any]] = {}
    for game in games:
        path = layout.metadata_file(game)
        if game.publishes_data and path.is_file():
            metadata_by_game[game.game_code] = read_json_file(path)
    catalog = build_catalog(games, metadata_by_game, updated_at=updated_at)
    atomic_write_bytes(layout.catalog_file, dumps_json(catalog))
    write_checksums(layout)
    return catalog

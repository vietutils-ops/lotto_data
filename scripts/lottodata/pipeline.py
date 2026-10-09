"""The update flow shared by every game:

fetch (adapter) → normalize → assign ruleset → validate each draw → detect
changes (history is never overwritten silently) → merge and sort → validate
the whole dataset → (write) draws, metadata, source, catalog, checksums →
audit log. Nothing is written in a dry run.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional

from . import TOOL_NAME, TOOL_VERSION
from .adapters import AdapterFactory, adapters
from .audit import append_event
from .changes import ChangeSet, diff, merge
from .errors import DistributionRestricted, HistoryChanged, NoDataFound, ParseFailed
from .games import GameDefinition
from .http import HttpClient
from .layout import RepoLayout
from .models import Dataset, Draw, RejectedRecord
from .normalize import normalize_records
from .repository import load_published, next_dataset_version, rebuild_index, write_game
from .serialization import atomic_write_bytes, dumps_json, format_utc, read_json_file
from .validation import known_gaps_for, today_in, validate_dataset


@dataclass
class UpdateResult:
    game_code: str
    changes: ChangeSet
    dataset_version: Optional[str]
    rejected: List[RejectedRecord] = field(default_factory=list)
    written: bool = False

    @property
    def up_to_date(self) -> bool:
        return self.changes.empty

    def summary(self) -> Dict[str, Any]:
        return {
            "game": self.game_code,
            "dataset_version": self.dataset_version,
            "written": self.written,
            "rejected": len(self.rejected),
            **self.changes.summary(),
        }


def _known_gaps(layout: RepoLayout, game: GameDefinition) -> List[str]:
    if not layout.known_gaps_file.is_file():
        return []
    return known_gaps_for(read_json_file(layout.known_gaps_file), game.game_code)


def apply_draws(
    layout: RepoLayout,
    games: Mapping[str, GameDefinition],
    game: GameDefinition,
    incoming: List[Draw],
    *,
    complete: bool,
    now: datetime,
    provenance: Mapping[str, Any],
    write: bool,
    accept_changes: bool,
    action: str,
    rejected: Optional[List[RejectedRecord]] = None,
) -> UpdateResult:
    """Validates [incoming] against the published draws and (when [write])
    publishes the result. Shared by the collector and the importers."""
    if not game.publishes_data:
        raise DistributionRestricted(f"distribution mode is {game.distribution_mode}", game=game.game_code)
    published = load_published(layout, game)
    old = published.dataset.draws if published.dataset else []
    changes = diff(old, incoming, complete=complete)
    if changes.touches_history and not accept_changes:
        raise HistoryChanged(
            "published draws would change or disappear (re-run with --accept-changes after checking "
            "the official source): " + "; ".join(changes.describe_history()[:5]),
            game=game.game_code,
        )
    previous_version = published.metadata["dataset_version"] if published.metadata else None
    result = UpdateResult(game.game_code, changes, previous_version, list(rejected or []))
    if changes.empty:
        return result
    version = next_dataset_version(previous_version, now)
    dataset = Dataset(
        game.game_code, game.country_code, game.operator_code, version, format_utc(now), merge(old, changes)
    )
    report = validate_dataset(game, dataset, known_gaps=_known_gaps(layout, game), today=today_in(game.timezone, now))
    report.raise_for_errors(game.game_code)
    result.dataset_version = version
    if not write:
        return result
    write_game(layout, game, dataset, provenance=provenance)
    rebuild_index(layout, list(games.values()), updated_at=format_utc(now))
    if result.rejected:
        _quarantine(layout, game, result.rejected, now)
    append_event(layout, {
        "at": format_utc(now),
        "action": action,
        "game": game.game_code,
        "dataset_version": version,
        "previous_version": previous_version,
        "source": provenance.get("source_name"),
        "source_url": provenance.get("source_url"),
        "accepted_history_changes": changes.describe_history() if changes.touches_history else [],
        "rejected_records": len(result.rejected),
        **changes.summary(),
    })
    result.written = True
    return result


def _quarantine(layout: RepoLayout, game: GameDefinition, rejected: List[RejectedRecord], now: datetime) -> None:
    stamp = format_utc(now).replace(":", "").replace("-", "")
    path = layout.quarantine_dir / f"{game.game_code}_{stamp}.json"
    atomic_write_bytes(path, dumps_json({"game": game.game_code, "rejected": [r.to_dict() for r in rejected]}))


def update_game(
    layout: RepoLayout,
    games: Mapping[str, GameDefinition],
    game: GameDefinition,
    client: HttpClient,
    *,
    now: datetime,
    write: bool = False,
    accept_changes: bool = False,
    max_pages: int = 3,
    adapter_factories: Optional[Mapping[str, AdapterFactory]] = None,
) -> UpdateResult:
    """Collects recent draws of [game] from its official source."""
    if not game.publishes_data:
        raise DistributionRestricted(f"distribution mode is {game.distribution_mode}", game=game.game_code)
    factories = adapter_factories if adapter_factories is not None else adapters()
    if game.adapter not in factories:
        raise ParseFailed(f"no source adapter {game.adapter!r} is available", game=game.game_code)
    settings = read_json_file(layout.root / "sources" / "adapters" / f"{game.adapter}.json")
    adapter = factories[game.adapter](client, game, settings)
    published = load_published(layout, game)
    since = published.dataset.latest() if published.dataset else None
    fetched = adapter.fetch(since=since, max_pages=max_pages)
    if not fetched.records:
        if fetched.rejected:
            raise ParseFailed(
                f"every one of {len(fetched.rejected)} source rows was rejected, first: {fetched.rejected[0].reason}",
                game=game.game_code,
            )
        raise NoDataFound("the source returned no draws", game=game.game_code)
    normalized = normalize_records(fetched.records, game)
    if not normalized.draws:
        raise ParseFailed(
            f"no record could be normalized, first: {normalized.rejected[0].reason}", game=game.game_code
        )
    provenance = {
        "original_source": f"{game.official_source.get('name')} ({game.official_source.get('url')})",
        "acquisition_method": "collector",
        "source_name": adapter.source_name,
        "source_url": fetched.source_url,
        "retrieved_at": fetched.retrieved_at,
        "normalized_at": format_utc(now),
        "notes": "Latest acquisition; the full history is in metadata/audit_log.jsonl.",
    }
    return apply_draws(
        layout,
        games,
        game,
        normalized.draws,
        complete=fetched.complete,
        now=now,
        provenance=provenance,
        write=write,
        accept_changes=accept_changes,
        action="collect",
        rejected=[*fetched.rejected, *normalized.rejected],
    )

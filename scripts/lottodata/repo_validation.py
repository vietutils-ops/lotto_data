"""Whole-repository validation: every file against its schema, every
dataset against its rules, every generated file against what the tools would
generate now, and the checksums."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional

from .checksum import sha256_bytes, verify_checksums
from .errors import LottoDataError
from .games import GameDefinition, load_games
from .layout import RepoLayout
from .metadata import build_catalog, build_metadata, build_source
from .schema import schema_problems
from .serialization import dumps_draws, read_bytes, read_json_file
from .validation import Issue, ValidationReport, known_gaps_for, missing_ids, parse_draws_document, today_in, validate_dataset

_GENERATED_METADATA_KEYS = (
    "schema_version",
    "game_code",
    "country_code",
    "operator_code",
    "dataset_version",
    "dataset_updated_at",
    "record_count",
    "sha256",
    "byte_size",
    "rulesets_sha256",
    "first_draw_id",
    "first_draw_date",
    "latest_draw_id",
    "latest_draw_date",
    "missing_draw_ids",
    "ruleset_ids",
)


@dataclass
class RepositoryReport:
    games: Dict[str, ValidationReport] = field(default_factory=dict)
    repository: ValidationReport = field(default_factory=ValidationReport)

    @property
    def ok(self) -> bool:
        return self.repository.ok and all(r.ok for r in self.games.values())

    def lines(self) -> List[str]:
        out = [f"repository: {i.render()}" for i in self.repository.issues]
        for code, report in self.games.items():
            out += [f"{code}: {i.render()}" for i in report.issues]
        return out


def _check_schema(report: ValidationReport, layout: RepoLayout, document: Any, schema: str, where: str) -> None:
    for problem in schema_problems(layout, document, schema):
        report.error("schema_mismatch", f"{where}: {problem}")


def validate_game(layout: RepoLayout, game: GameDefinition, now: datetime) -> ValidationReport:
    report = ValidationReport()
    rulesets_path = layout.rulesets_file(game)
    if not rulesets_path.is_file():
        if game.distribution_mode != "disabled":
            report.error("missing_file", f"{layout.relative(rulesets_path)} is missing")
        return report
    _check_schema(report, layout, read_json_file(rulesets_path), "rulesets", "rulesets.json")
    draws_path, metadata_path, source_path = layout.draws_file(game), layout.metadata_file(game), layout.source_file(game)
    if not game.publishes_data:
        for path in (draws_path, metadata_path):
            if path.is_file():
                report.error("distribution_restricted", f"{layout.relative(path)} must not be published ({game.distribution_mode})")
        if game.distribution_mode == "restricted":
            # Listed in the catalog: its rules and source record are published, its draws are not.
            if not source_path.is_file():
                report.error("missing_file", f"{layout.relative(source_path)} is missing (run scripts.build --write)")
            elif read_json_file(source_path) != build_source(game, None):
                report.error("source_mismatch", "source.json differs from the registry (regenerate it)")
        return report
    if not draws_path.is_file():
        report.warning("no_data", "no draws collected yet")
        return report
    for path in (metadata_path, source_path):
        if not path.is_file():
            report.error("missing_file", f"{layout.relative(path)} is missing")
    if not report.ok:
        return report

    draws_bytes = read_bytes(draws_path)
    document = read_json_file(draws_path)
    _check_schema(report, layout, document, "draws", "draws.json")
    try:
        dataset = parse_draws_document(document, game)
    except LottoDataError as exc:
        report.error(exc.code, str(exc))
        return report
    if dumps_draws(dataset) != draws_bytes:
        report.error("not_canonical", "draws.json is not in canonical form (regenerate it with the tools)")
    gaps = known_gaps_for(read_json_file(layout.known_gaps_file), game.game_code) if layout.known_gaps_file.is_file() else []
    report.issues.extend(validate_dataset(game, dataset, known_gaps=gaps, today=today_in(game.timezone, now)).issues)

    metadata = read_json_file(metadata_path)
    _check_schema(report, layout, metadata, "metadata", "metadata.json")
    if report.ok:
        expected = build_metadata(
            game,
            dataset,
            draws_bytes=draws_bytes,
            rulesets_bytes=read_bytes(rulesets_path),
            missing_draw_ids=missing_ids(game, dataset.draws),
            provenance=metadata.get("provenance") or {},
        )
        for key in _GENERATED_METADATA_KEYS:
            if metadata.get(key) != expected[key]:
                report.error("metadata_mismatch", f"metadata.json {key} is {metadata.get(key)!r}, expected {expected[key]!r}")
        source = read_json_file(source_path)
        _check_schema(report, layout, source, "source", "source.json")
        if source != build_source(game, metadata.get("provenance")):
            report.error("source_mismatch", "source.json differs from the registry and metadata (regenerate it)")
    return report


def validate_repository(layout: RepoLayout, now: datetime) -> RepositoryReport:
    result = RepositoryReport()
    repo = result.repository
    try:
        registry = read_json_file(layout.registry_file)
        _check_schema(repo, layout, registry, "source_registry", "sources/source_registry.json")
        games = load_games(layout)
    except LottoDataError as exc:
        repo.error(exc.code, str(exc))
        return result
    if layout.known_gaps_file.is_file():
        _check_schema(repo, layout, read_json_file(layout.known_gaps_file), "known_gaps", "config/known_gaps.json")
    for code, game in games.items():
        result.games[code] = validate_game(layout, game, now)

    if not layout.catalog_file.is_file():
        repo.error("missing_file", "catalog.json is missing")
    else:
        catalog = read_json_file(layout.catalog_file)
        _check_schema(repo, layout, catalog, "catalog", "catalog.json")
        metadata_by_game: Dict[str, Mapping[str, Any]] = {}
        for game in games.values():
            path = layout.metadata_file(game)
            if game.publishes_data and path.is_file():
                metadata_by_game[game.game_code] = read_json_file(path)
        expected = build_catalog(list(games.values()), metadata_by_game, updated_at=catalog.get("updated_at", ""))
        if catalog != expected:
            repo.error("catalog_mismatch", "catalog.json differs from the game folders (regenerate it)")
    for problem in verify_checksums(layout):
        repo.error("checksum_failed", problem.render())
    return result

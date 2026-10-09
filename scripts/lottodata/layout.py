"""Paths of the repository; the only place that knows the folder layout."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .games import GameDefinition

ROOT = Path(__file__).resolve().parents[2]


class RepoLayout:
    """The repository at [root]; by default this checkout, or the directory in
    the ``LOTTO_DATA_ROOT`` environment variable (used by tests)."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root or os.environ.get("LOTTO_DATA_ROOT") or ROOT)

    @property
    def catalog_file(self) -> Path:
        return self.root / "catalog.json"

    @property
    def registry_file(self) -> Path:
        return self.root / "sources" / "source_registry.json"

    @property
    def known_gaps_file(self) -> Path:
        return self.root / "config" / "known_gaps.json"

    @property
    def audit_log(self) -> Path:
        return self.root / "metadata" / "audit_log.jsonl"

    @property
    def quarantine_dir(self) -> Path:
        return self.root / "metadata" / "quarantine"

    @property
    def checksums_file(self) -> Path:
        return self.root / "checksums" / "SHA256SUMS"

    @property
    def schemas_dir(self) -> Path:
        return self.root / "schemas"

    def game_dir(self, game: "GameDefinition") -> Path:
        return self.root / game.path

    def draws_file(self, game: "GameDefinition") -> Path:
        return self.game_dir(game) / "draws.json"

    def metadata_file(self, game: "GameDefinition") -> Path:
        return self.game_dir(game) / "metadata.json"

    def rulesets_file(self, game: "GameDefinition") -> Path:
        return self.game_dir(game) / "rulesets.json"

    def source_file(self, game: "GameDefinition") -> Path:
        return self.game_dir(game) / "source.json"

    def relative(self, path: Path) -> str:
        return Path(path).resolve().relative_to(self.root.resolve()).as_posix()

    def published_files(self) -> List[Path]:
        """Every file the app may download, in a stable order."""
        files = [self.catalog_file] if self.catalog_file.is_file() else []
        games_root = self.root / "games"
        if games_root.is_dir():
            files.extend(sorted(p for p in games_root.rglob("*.json") if p.is_file()))
        return files

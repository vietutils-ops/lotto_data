"""Canonical in-memory model of draws and datasets (schema 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class Draw:
    """One normalized draw. ``main_numbers`` is strictly ascending."""

    draw_id: str
    draw_date: date
    ruleset_version: str
    main_numbers: Tuple[int, ...]
    bonus_number: Optional[int] = None
    supplementary_numbers: Tuple[int, ...] = ()
    special_numbers: Tuple[Tuple[str, Tuple[int, ...]], ...] = ()

    @property
    def sequence(self) -> int:
        """Ordering number: the draw number, or YYYYMMDD for date IDs."""
        return int(self.draw_id)

    def special(self) -> Dict[str, List[int]]:
        return {key: list(values) for key, values in self.special_numbers}

    def to_record(self) -> Dict[str, Any]:
        return {
            "draw_id": self.draw_id,
            "draw_date": self.draw_date.isoformat(),
            "ruleset_version": self.ruleset_version,
            "main_numbers": list(self.main_numbers),
            "bonus_number": self.bonus_number,
            "supplementary_numbers": list(self.supplementary_numbers),
            "special_numbers": self.special(),
        }

    def same_content(self, other: "Draw") -> bool:
        return self.to_record() == other.to_record()

    @staticmethod
    def from_record(record: Mapping[str, Any]) -> "Draw":
        """Inverse of :meth:`to_record` for already-canonical records."""
        special = record.get("special_numbers") or {}
        return Draw(
            draw_id=record["draw_id"],
            draw_date=date.fromisoformat(record["draw_date"]),
            ruleset_version=record["ruleset_version"],
            main_numbers=tuple(record["main_numbers"]),
            bonus_number=record.get("bonus_number"),
            supplementary_numbers=tuple(record.get("supplementary_numbers") or ()),
            special_numbers=tuple((key, tuple(values)) for key, values in special.items()),
        )


@dataclass
class Dataset:
    """The draws of one game (``draws.json``)."""

    game_code: str
    country_code: str
    operator_code: str
    dataset_version: str
    updated_at: str  # RFC 3339 UTC "YYYY-MM-DDTHH:MM:SSZ"
    draws: List[Draw] = field(default_factory=list)

    @property
    def draw_count(self) -> int:
        return len(self.draws)

    def latest(self) -> Optional[Draw]:
        return self.draws[-1] if self.draws else None

    def first(self) -> Optional[Draw]:
        return self.draws[0] if self.draws else None

    def by_id(self) -> Dict[str, Draw]:
        return {d.draw_id: d for d in self.draws}


@dataclass(frozen=True)
class RejectedRecord:
    """A raw record that could not be normalized or failed validation."""

    source_ref: str
    reason: str
    raw: Any

    def to_dict(self) -> Dict[str, Any]:
        return {"source_ref": self.source_ref, "reason": self.reason, "raw": self.raw}

"""Change detection between the published draws and newly collected ones.

New draws are expected. A published draw that would change or disappear is
never overwritten silently: the run stops with HistoryChanged unless the
maintainer accepts the change explicitly (and the audit log records it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Tuple

from .models import Draw


@dataclass
class ChangeSet:
    added: List[Draw] = field(default_factory=list)
    changed: List[Tuple[Draw, Draw]] = field(default_factory=list)
    removed: List[Draw] = field(default_factory=list)
    unchanged: int = 0

    @property
    def touches_history(self) -> bool:
        return bool(self.changed or self.removed)

    @property
    def empty(self) -> bool:
        return not (self.added or self.changed or self.removed)

    def summary(self) -> Dict[str, object]:
        """Counts, the range of added draws, and every changed or removed ID."""
        return {
            "added": len(self.added),
            "added_first": self.added[0].draw_id if self.added else None,
            "added_last": self.added[-1].draw_id if self.added else None,
            "changed": [old.draw_id for old, _ in self.changed],
            "removed": [d.draw_id for d in self.removed],
            "unchanged": self.unchanged,
        }

    def describe_history(self) -> List[str]:
        lines = [f"{old.draw_id}: {old.to_record()} -> {new.to_record()}" for old, new in self.changed]
        lines += [f"{d.draw_id}: removed ({d.to_record()})" for d in self.removed]
        return lines


def diff(published: Sequence[Draw], incoming: Sequence[Draw], *, complete: bool) -> ChangeSet:
    """Compares draws by ID. ``complete`` means ``incoming`` is the whole
    history (a conversion or full backfill), so absent draws count as removed;
    otherwise ``incoming`` is a recent slice and only adds or changes."""
    old: Dict[str, Draw] = {d.draw_id: d for d in published}
    new: Dict[str, Draw] = {d.draw_id: d for d in incoming}
    changes = ChangeSet()
    for draw_id, draw in new.items():
        before = old.get(draw_id)
        if before is None:
            changes.added.append(draw)
        elif before.same_content(draw):
            changes.unchanged += 1
        else:
            changes.changed.append((before, draw))
    if complete:
        changes.removed = [d for draw_id, d in old.items() if draw_id not in new]
    changes.added.sort(key=lambda d: (d.draw_date, d.sequence))
    return changes


def merge(published: Sequence[Draw], changes: ChangeSet) -> List[Draw]:
    """The published draws with the change set applied, sorted by date."""
    result: Dict[str, Draw] = {d.draw_id: d for d in published}
    for d in changes.removed:
        result.pop(d.draw_id, None)
    for _, d in changes.changed:
        result[d.draw_id] = d
    for d in changes.added:
        result[d.draw_id] = d
    return sorted(result.values(), key=lambda d: (d.draw_date, d.sequence))

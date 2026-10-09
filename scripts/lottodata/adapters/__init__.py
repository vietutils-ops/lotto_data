"""Source adapters: one per official source, all behind one interface.

An adapter only reads its source and returns raw records with explicit field
names; normalization, ruleset assignment, validation, change detection and
writing are shared. Adding a game means adding (or reusing) an adapter and a
registry entry, never changing the pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, ClassVar, Dict, List, Mapping, Optional

from ..games import GameDefinition
from ..http import HttpClient
from ..models import Draw, RejectedRecord
from ..normalize import RawRecord


@dataclass
class FetchResult:
    records: List[RawRecord] = field(default_factory=list)
    rejected: List[RejectedRecord] = field(default_factory=list)
    source_url: str = ""
    retrieved_at: str = ""

    #: True when the records are the source's whole history (absent draws
    #: then count as removed); False for a recent slice.
    complete: bool = False


class LotterySourceAdapter(ABC):
    adapter_id: ClassVar[str]

    #: Human-readable source name for provenance records.
    source_name: ClassVar[str]

    def __init__(self, client: HttpClient, game: GameDefinition, settings: Mapping[str, Any]):
        self.client = client
        self.game = game
        self.settings = settings

    @abstractmethod
    def fetch(self, *, since: Optional[Draw], max_pages: int) -> FetchResult:
        """Recent draws, newest first or in any order, back to (and including)
        [since] when given; at most [max_pages] requests."""


AdapterFactory = Callable[[HttpClient, GameDefinition, Mapping[str, Any]], LotterySourceAdapter]


def adapters() -> Dict[str, AdapterFactory]:
    from .vietlott import VietlottAdapter

    return {VietlottAdapter.adapter_id: VietlottAdapter}

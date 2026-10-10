from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DraftMarketRecord:
    internal_player_id: int | None
    source_player_id: str
    player_name: str
    team: str | None
    positions: tuple[str, ...]
    adp: float | None
    draft_rank: int | None
    xrank: float | None
    draft_frequency: float | None
    sample_size: int | None
    source: str
    season: str
    fetched_at: datetime
    source_updated_at: datetime | None = None


class DraftMarketProvider(Protocol):
    name: str

    async def fetch(self, season: str) -> Sequence[DraftMarketRecord]: ...
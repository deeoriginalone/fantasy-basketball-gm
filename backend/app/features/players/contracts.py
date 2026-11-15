from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class PlayerIdentityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    yahoo_player_id: str
    nba_player_id: str | None
    espn_player_id: str | None
    player_name: str
    team: str | None
    position: str | None
    status: str | None
    created_at: datetime
    updated_at: datetime


class RosterPlayerResponse(BaseModel):
    id: int
    yahoo_player_id: str
    player_name: str
    team: str | None
    position: str | None
    status: str | None
    roster_position: str | None


class FantasyRosterResponse(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None
    roster_data_status: Literal["available", "stale", "not_imported"]
    roster_source: Literal["yahoo"] | None
    roster_as_of: datetime | None
    players: list[RosterPlayerResponse]


class PlayerChange(BaseModel):
    id: int
    yahoo_player_id: str
    fields: list[str]


class PlayerImportResult(BaseModel):
    league_count: int
    players_seen: int
    created_count: int
    updated_count: int
    unchanged_count: int
    roster_entry_count: int
    changes: list[PlayerChange]
    # Stamped on every replaced pool and roster row; verification compares persisted rows to it.
    imported_at: datetime | None = None
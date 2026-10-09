from pydantic import BaseModel, Field


class DraftMetricsResult(BaseModel):
    league_key: str
    season: str
    players_scored: int
    players_missing_nba_mapping: int
    players_missing_stats: int


class DraftUtilityRequest(BaseModel):
    league_key: str
    team_key: str
    season: str
    drafted_player_ids: list[int] = Field(max_length=1500)
    available_player_ids: list[int] = Field(min_length=1, max_length=1500)


class DraftUtilityPick(BaseModel):
    player_identity_id: int
    yahoo_player_id: str
    nba_player_id: str
    player_name: str
    positions: list[str]
    fantasy_value: float
    replacement_value: float
    positional_scarcity: float
    durability_score: float
    risk_score: float
    upside_score: float
    positional_need_score: float
    roster_construction_score: float
    utility_score: float


class DraftUtilityResult(BaseModel):
    league_key: str
    team_key: str
    season: str
    drafted_count: int
    available_count: int
    best_pick: DraftUtilityPick | None
    unscored_available_player_ids: list[int]

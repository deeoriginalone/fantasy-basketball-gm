from typing import Literal

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
    draft_position: int | None = Field(default=None, ge=1, le=30, description="Manager's fixed snake-draft slot, 1-based")
    round_number: int | None = Field(default=None, ge=1, le=100, description="Current round, 1-based")
    total_teams: int | None = Field(default=None, ge=2, le=30)
    recent_pick_player_ids: list[int] = Field(default_factory=list, max_length=30)
    adp_by_player_id: dict[int, float] = Field(default_factory=dict, max_length=1500)
    mode: Literal["balanced", "upside", "safe"] = "balanced"


class DraftTiming(BaseModel):
    draft_position: int
    round_number: int
    total_teams: int
    current_pick_number: int
    picks_until_next_turn: int
    next_pick_number: int


class DraftRun(BaseModel):
    position_group: Literal["center", "guard", "forward"]
    recent_pick_count: int
    window_size: int
    active: bool


class DraftPlayerAvailability(BaseModel):
    player_identity_id: int
    adp: float | None
    market_value_delta: float | None
    reach_score: float | None
    fall_score: float | None
    draft_rank: int | None
    draft_frequency: float | None
    adp_source: str | None
    positional_scarcity: float | None
    availability_score: float | None
    next_pick_survival_probability: float | None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"]
    data_freshness: Literal["unknown", "fresh", "stale", "request"]
    draft_now: bool | None
    safe_to_wait: bool | None
    explanation: str
    blocker: str | None


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
    mode_adjusted_utility_score: float
    adp: float | None
    market_value_delta: float | None
    reach_score: float | None
    fall_score: float | None
    opportunity_cost_if_wait: float | None
    draft_rank: int | None
    draft_frequency: float | None
    adp_source: str | None
    availability_score: float | None
    next_pick_survival_probability: float | None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"]
    data_freshness: Literal["unknown", "fresh", "stale", "request"]
    draft_now: bool | None
    safe_to_wait: bool | None
    run_bonus: float
    reasons: list[str]


class DraftUtilityResult(BaseModel):
    league_key: str
    team_key: str
    season: str
    drafted_count: int
    available_count: int
    mode: Literal["balanced", "upside", "safe"]
    draft_timing: DraftTiming | None
    draft_runs: list[DraftRun]
    player_availability: list[DraftPlayerAvailability]
    best_pick: DraftUtilityPick | None
    best_value_before_next_pick: DraftUtilityPick | None
    adp_missing_available_player_ids: list[int]
    unscored_available_player_ids: list[int]

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


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
    miss_risk_score: float | None
    expected_loss_if_gone: float | None = None
    opportunity_cost_if_wait: float | None = None
    survival_confidence: Literal["unknown", "heuristic_unvalidated"]
    data_freshness: Literal["unknown", "fresh", "stale", "request"]
    draft_now: bool | None
    safe_to_wait: bool | None
    decision_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    explanation: str
    blocker: str | None


class DraftWaitFallback(BaseModel):
    player_identity_id: int
    player_name: str
    utility_score: float
    survival_probability: float
    probability_selected_if_waiting: float


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
    wait_utility_now: float
    adp: float | None
    market_value_delta: float | None
    reach_score: float | None
    fall_score: float | None
    miss_risk_score: float | None
    expected_loss_if_gone: float | None
    opportunity_cost_if_wait: float | None
    expected_fallback_utility: float | None
    expected_wait_utility: float | None
    expected_wait_cost: float | None
    wait_fallbacks: list[DraftWaitFallback]
    decision_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    wait_cost_method: Literal["independent_heuristic", "unavailable"]
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
    primary_action: Literal["draft_now", "wait", "insufficient_evidence"]
    decision_confidence: Literal["low", "medium", "high", "unavailable"]
    draft_timing: DraftTiming | None
    draft_runs: list[DraftRun]
    player_availability: list[DraftPlayerAvailability]
    best_pick: DraftUtilityPick | None
    best_value_before_next_pick: DraftUtilityPick | None
    adp_missing_available_player_ids: list[int]
    unscored_available_player_ids: list[int]


class DraftSessionCreateRequest(BaseModel):
    league_key: str
    season: str = Field(pattern=r"^\d{4}-\d{2}$")
    manager_team_key: str
    draft_position: int = Field(ge=1, le=30)
    total_teams: int = Field(ge=2, le=30)
    rounds: int = Field(ge=1, le=100)
    team_slots: dict[str, int] = Field(min_length=2, max_length=30)
    mode: Literal["balanced", "upside", "safe"] = "balanced"

    @model_validator(mode="after")
    def validate_team_slots(self) -> "DraftSessionCreateRequest":
        if len(self.team_slots) != self.total_teams:
            raise ValueError("team_slots must include every league team exactly once")
        slots = list(self.team_slots.values())
        if sorted(slots) != list(range(1, self.total_teams + 1)):
            raise ValueError("team_slots must map teams to unique 1-based draft slots")
        if self.team_slots.get(self.manager_team_key) != self.draft_position:
            raise ValueError("manager_team_key must map to draft_position")
        return self


class DraftPickUpdateRequest(BaseModel):
    selected_player_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    source: str = Field(default="manual", min_length=1, max_length=80)
    picked_at: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_picked_at(self) -> "DraftPickUpdateRequest":
        if self.picked_at is not None and self.picked_at.tzinfo is None:
            raise ValueError("picked_at must include a timezone")
        return self


class DraftPickUndoRequest(BaseModel):
    expected_version: int = Field(ge=0)
    source: str = Field(default="manual", min_length=1, max_length=80)
    evidence: dict[str, Any] = Field(default_factory=dict)


class DraftTargetRequest(BaseModel):
    status: Literal["target", "priority", "watch", "avoid"]
    expected_version: int = Field(ge=0)
    note: str | None = Field(default=None, max_length=2000)


class DraftPickView(BaseModel):
    overall_pick: int
    round_number: int
    team_slot: int
    team_key: str
    selected_player_id: int | None
    source: str
    picked_at: str | None


class DraftTargetView(BaseModel):
    player_id: int
    status: Literal["target", "priority", "watch", "avoid"]
    note: str | None


class DraftSessionState(BaseModel):
    session_id: str
    league_key: str
    season: str
    manager_team_key: str
    draft_position: int
    total_teams: int
    rounds: int
    status: Literal["active", "paused", "completed"]
    mode: Literal["balanced", "upside", "safe"]
    version: int
    next_overall_pick: int
    picks: list[DraftPickView]
    targets: list[DraftTargetView]
    latest_recommendation: dict[str, Any] | None
    recommendation_version: int | None


class DraftSessionEventResult(BaseModel):
    state: DraftSessionState
    event: Literal["created", "recorded", "corrected", "undone", "unchanged"]

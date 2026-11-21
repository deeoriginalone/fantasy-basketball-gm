from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.services.draft.player_status import YahooStatusDecisionState, YahooStatusField, YahooStatusReason

Mode = Literal["this_week", "next_7_days", "next_14_days", "ros"]
QualityState = Literal["available", "partial", "missing", "stale", "unknown", "unsupported", "unavailable"]
SampleLabel = Literal["EXCELLENT", "GOOD", "LIMITED", "VERY LIMITED", "INSUFFICIENT FOR STRONG RECOMMENDATION", "NO CURRENT-SEASON EVIDENCE"]
# Recent-sample tiers for the evidence gate (relevant games: the last 14 days in weekly horizons, this season in
# Rest of Season Outlook). Tiers are evidence labels, never probabilities.
SampleTier = Literal["INSUFFICIENT", "VERY_LOW", "LIMITED", "SUPPORTED"]
FormWindowKey = Literal["LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "CURRENT_SEASON", "PREVIOUS_SEASON"]
FormTrendLabel = Literal["IMPROVING", "DECLINING", "STABLE", "MIXED", "INSUFFICIENT EVIDENCE"]
# What a supported move is for: STREAM (Rest of Week / Next 7 Days), TWO_WEEK_STREAM (Next 14 Days) or
# LONGER_TERM_ADD (Rest of Season Outlook, or a value-led add with longer-term Season Evidence).
MoveIntent = Literal["STREAM", "TWO_WEEK_STREAM", "LONGER_TERM_ADD", "WATCH", "HOLD", "INSUFFICIENT_EVIDENCE"]
Decision = Literal["MUST ADD", "ADD", "STREAM", "WATCH", "PASS", "INSUFFICIENT EVIDENCE"]
# Transaction shape and plain-language action vocabulary shared by every waiver surface.
ActionType = Literal["ADD_ONLY", "MOVE_TO_IL_THEN_ADD", "ADD_DROP", "WATCH", "HOLD", "INSUFFICIENT_EVIDENCE"]
TransactionShape = Literal["ADD_ONLY", "MOVE_TO_IL_THEN_ADD", "ADD_DROP", "UNDETERMINED"]
ComparisonType = Literal["ADD_DROP", "ADD_ONLY", "MOVE_TO_IL_THEN_ADD"]
SlotKind = Literal["starting", "bench", "injury", "unsupported"]
# Non-actionable decision support never changes a strict action type. MEASURED is a comparable
# player that is neither featured nor interesting; UNAVAILABLE cannot be compared at all.
# POTENTIAL_TARGET is measurable but its Yahoo availability is unconfirmed: it may only be shown
# under POTENTIAL TARGETS TO CHECK IN YAHOO, never as a move, best option, group pick or WATCH.
DecisionSupportClass = Literal[
    "SUPPORTED_ACTION", "BEST_MEASURED_OPTION", "WATCH", "MEASURED", "POTENTIAL_TARGET", "UNAVAILABLE",
]
DecisionSupportState = Literal["SUPPORTED_ACTION", "BEST_MEASURED_OPTION", "WATCH", "POTENTIAL_TARGETS", "UNAVAILABLE"]
AvailabilityClass = Literal[
    "CONFIRMED_FA",
    "CONFIRMED_WAIVER",
    "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT",
    "ROSTERED_BY_OTHER_TEAM",
    "ROSTERED_BY_MANAGER",
    "AVAILABILITY_UNVERIFIED",
    "EXCLUDED_STATUS",
    "SOURCE_STALE",
]
# Only these classes can back a supported move or any featured recommendation.
ACTIONABLE_AVAILABILITY: frozenset[str] = frozenset({
    "CONFIRMED_FA", "CONFIRMED_WAIVER", "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT",
})
# Not rostered and not excluded, but unconfirmed: POTENTIAL TARGETS TO CHECK IN YAHOO only.
CHECKABLE_AVAILABILITY: frozenset[str] = frozenset({"AVAILABILITY_UNVERIFIED", "SOURCE_STALE"})
AVAILABILITY_CLASS_LABELS: dict[str, str] = {
    "CONFIRMED_FA": "FREE AGENT (YAHOO)",
    "CONFIRMED_WAIVER": "ON WAIVERS (YAHOO)",
    "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT": "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO",
    "ROSTERED_BY_OTHER_TEAM": "ROSTERED BY ANOTHER TEAM",
    "ROSTERED_BY_MANAGER": "ON YOUR ROSTER",
    "AVAILABILITY_UNVERIFIED": "AVAILABILITY UNVERIFIED",
    "EXCLUDED_STATUS": "EXCLUDED (YAHOO O/OFS/NA)",
    "SOURCE_STALE": "SAVED ROSTERS STALE — CHECK IN YAHOO",
}
# Legacy `availability` values map onto classes only for candidates built without an explicit class.
LEGACY_AVAILABILITY_CLASS: dict[str, str] = {
    "free_agent": "CONFIRMED_FA",
    "waivers": "CONFIRMED_WAIVER",
    "unrostered": "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT",
    "rostered": "ROSTERED_BY_OTHER_TEAM",
    "unknown": "AVAILABILITY_UNVERIFIED",
}
NeedLevel = Literal["HIGH", "MEDIUM", "COVERED"]
PositionFamily = Literal["GUARD", "WING_FORWARD", "CENTER"]
OptionGroupKey = Literal[
    "BEST_GUARD", "BEST_WING_FORWARD", "BEST_CENTER", "BEST_MULTI_POSITION", "BEST_SHORT_TERM", "BEST_LONGER_TERM",
]
# The answer every option gives to "should I make this move?" (backend-owned; the page never infers one).
TransactionVerdict = Literal["SUPPORTED_ADD", "WATCH_ONLY", "NEAR_TIE", "DO_NOT_ADD", "CANNOT_EVALUATE"]
# Why a form window has no fantasy PPG; the page shows the reason instead of a bare "n/a".
FormReason = Literal[
    "NO_GAMES_IN_WINDOW", "GAME_LOGS_MISSING", "MAPPING_UNRESOLVED", "DATA_STALE", "SCORING_FIELD_MISSING",
    "SCORING_UNSUPPORTED", "NO_PREVIOUS_SEASON",
]
FORM_REASON_LABELS: dict[str, str] = {
    "NO_GAMES_IN_WINDOW": "No games played in window",
    "GAME_LOGS_MISSING": "Game logs missing",
    "MAPPING_UNRESOLVED": "Mapping unresolved",
    "DATA_STALE": "Data stale",
    "SCORING_FIELD_MISSING": "Required scoring field missing",
    "SCORING_UNSUPPORTED": "Scoring settings unavailable",
    "NO_PREVIOUS_SEASON": "No previous-season stats",
}
ProductionBasisCode = Literal["RECENT_BLENDED", "RECENT_ONLY", "SEASON_EVIDENCE", "PREVIOUS_SEASON_FALLBACK", "UNAVAILABLE"]
EvidenceDimensionKey = Literal["PRODUCTION_SAMPLE", "CURRENT_ROLE", "SCHEDULE", "SOURCE_FRESHNESS", "TRANSACTION_VERDICT"]
RESOLVED_IDENTITY_STATES = frozenset({
    "EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM", "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED",
})
MODEL_VERSION = "waiver-decision-integrity-phase7"


class Evidence(BaseModel):
    state: QualityState
    source: str
    as_of: datetime | None = None
    detail: str
    sample_count: int | None = None


class Components(BaseModel):
    roster_fit: float | None = None
    player_value: float | None = None
    opportunity: float | None = None
    schedule: float | None = None
    acquisition_value: float | None = None


class ValueEvidence(BaseModel):
    value: float | None = None
    games: int = 0
    season: str | None = None
    per_game_stats: dict[str, float] = Field(default_factory=dict)
    label: str
    sample_label: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    scoring_contributions: dict[str, float] = Field(default_factory=dict)


class RankingEvidence(BaseModel):
    value: float | None = None
    recent_weight: float | None = None
    historical_value: float | None = None
    historical_games: int = 0
    historical_season: str | None = None
    label: str = "Production ranking unavailable"


class MeasuredProduction(BaseModel):
    """Non-actionable Yahoo-rule production used only to compare players for decision support.

    The current sample is shrunk toward independent prior-season production with the model's
    existing n/(n+10) weight. Import age never removes the value; it is labeled instead.
    """
    value: float | None = None
    comparable: bool = False
    basis: Literal["RECENT", "CURRENT_SEASON", "NONE"] = "NONE"
    current_value: float | None = None
    current_games: int = 0
    current_season: str | None = None
    current_weight: float | None = None
    prior_value: float | None = None
    prior_games: int = 0
    prior_season: str | None = None
    state: QualityState = "unavailable"
    as_of: datetime | None = None
    sample_label: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    detail: str = ""


class RoleWindow(BaseModel):
    average: float | None = None
    median: float | None = None
    games: int = 0
    game_ids: list[str] = Field(default_factory=list)
    window_start: date | None = None
    window_end: date | None = None
    as_of: datetime | None = None
    missing_game_ids: list[str] = Field(default_factory=list)
    stale_game_ids: list[str] = Field(default_factory=list)


class RoleMetric(BaseModel):
    quality: Evidence
    recent: RoleWindow = Field(default_factory=RoleWindow)
    comparison: RoleWindow = Field(default_factory=RoleWindow)
    delta: float | None = None
    median_delta: float | None = None
    unit: str


class StartsEvidence(BaseModel):
    quality: Evidence
    season: str | None = None
    season_starts: int | None = None
    season_games: int | None = None
    recent_starts: int | None = None
    detail: str = "Game-level starter evidence is not established; season starts do not prove the current lineup."


class CurrentRole(BaseModel):
    minutes: RoleMetric
    usage: RoleMetric
    starts: StartsEvidence
    quality: Evidence
    trend: Literal["RISING", "STABLE", "FALLING", "INSUFFICIENT EVIDENCE"] = "INSUFFICIENT EVIDENCE"
    season_usage: float | None = None
    season_usage_quality: Evidence
    method: str
    limitations: list[str]


class Opportunity(BaseModel):
    minutes: float | None = None
    minutes_trend: float | None = None
    usage_trend: float | None = None
    historical_start_rate: float | None = None
    role: str = "Unknown"
    score: float | None = None
    score_parts: dict[str, float] = Field(default_factory=dict)
    current_role: CurrentRole | None = None


class FormWindow(BaseModel):
    """Historical evidence for one look-back window. A form window never sets a decision horizon."""
    key: FormWindowKey
    label: str
    games: int = 0
    fantasy_ppg: float | None = None
    minutes_average: float | None = None
    minutes_median: float | None = None
    starts: int | None = None
    starts_detail: str = ""
    usage: float | None = None
    usage_detail: str = ""
    sample_tier: SampleTier = "INSUFFICIENT"
    sample_label: str = "INSUFFICIENT SAMPLE"
    window_start: date | None = None
    window_end: date | None = None
    latest_game: date | None = None
    season: str | None = None
    as_of: datetime | None = None
    state: QualityState = "missing"
    detail: str = ""
    # Why `fantasy_ppg` is missing (or stale); never a bare "n/a".
    reason: FormReason | None = None
    reason_label: str = ""


class FormTrend(BaseModel):
    """Descriptive: Last 14 Days against the non-overlapping days 15-30. Never used by an evidence gate."""
    trend: FormTrendLabel = "INSUFFICIENT EVIDENCE"
    recent_games: int = 0
    baseline_games: int = 0
    recent_ppg: float | None = None
    baseline_ppg: float | None = None
    ppg_change: float | None = None
    recent_minutes: float | None = None
    baseline_minutes: float | None = None
    minutes_change: float | None = None
    detail: str = ""
    method: str = ""


class RecentForm(BaseModel):
    windows: list[FormWindow] = Field(default_factory=list)
    trend: FormTrend = Field(default_factory=FormTrend)
    limitations: list[str] = Field(default_factory=list)


class SampleCheck(BaseModel):
    key: str
    label: str
    passed: bool
    detail: str


class SampleAssessment(BaseModel):
    """The recent-sample evidence gate for one player in one horizon (backend-owned explanation)."""
    mode: Mode
    window: Literal["LAST_14_DAYS", "CURRENT_SEASON"]
    relevant_games: int
    current_season_games: int
    tier: SampleTier
    passes: bool
    corroborated: bool = False
    required: list[SampleCheck] = Field(default_factory=list)
    corroborations: list[SampleCheck] = Field(default_factory=list)
    corroborations_passed: int = 0
    detail: str


class Schedule(BaseModel):
    games_remaining: int | None = None
    off_day_games: int | None = None
    back_to_backs: int | None = None
    next_7_days_games: int | None = None
    next_14_days_games: int | None = None
    # Persisted schedulable games from today through the season end (PARTIAL: no completeness manifest).
    rest_of_season_games: int | None = None
    # Persisted rows in the window regardless of import age (PARTIAL; stale when the import is
    # stale). Decision support may show it with its freshness; scoring never uses it.
    persisted_window_games: int | None = None
    opponents: list[str] = Field(default_factory=list)
    game_dates: list[date] = Field(default_factory=list)
    source_row_count: int = 0
    window_start: date
    window_end: date
    imported_at: datetime | None = None
    freshness: Literal["fresh", "stale", "unknown"] = "unknown"
    coverage: Literal["COMPLETE", "PARTIAL", "UNKNOWN", "STALE"] = "UNKNOWN"
    diagnostic_reason: Literal[
        "NBA_ID_UNMAPPED",
        "TEAM_MAPPING_MISSING",
        "NO_PLAYER_SCHEDULE_ROWS",
        "NO_GAMES_IN_WINDOW",
        "SCHEDULE_STALE",
        "SCHEDULE_ROWS_PRESENT",
        "SCHEDULE_SOURCE_INCOMPLETE",
    ] = "NO_PLAYER_SCHEDULE_ROWS"


class CoverageMetric(BaseModel):
    count: int
    total: int
    percentage: float


class CoverageScope(BaseModel):
    total: int
    candidates: int
    roster: int


class IdentityCoverage(BaseModel):
    complete: CoverageMetric
    unresolved: CoverageMetric
    resolution_counts: dict[str, int] = Field(default_factory=dict)


class ProductionCoverage(BaseModel):
    recent_supported: CoverageMetric
    recent_missing: CoverageMetric
    recent_stale: CoverageMetric
    season_supported: CoverageMetric
    season_missing: CoverageMetric
    season_stale: CoverageMetric


class ScheduleCoverage(BaseModel):
    supported: CoverageMetric
    unknown: CoverageMetric
    stale: CoverageMetric
    source_incomplete: CoverageMetric


class StatusCoverage(BaseModel):
    explicit: CoverageMetric
    yahoo_blank: CoverageMetric
    field_missing: CoverageMetric
    no_current_designation: CoverageMetric
    stale: CoverageMetric


class RoleCoverage(BaseModel):
    minutes_qualified: CoverageMetric
    usage_supported: CoverageMetric
    game_level_starts_supported: CoverageMetric
    season_starts_supported: CoverageMetric
    insufficient_sample: CoverageMetric
    missing_inputs: CoverageMetric


class AcquisitionCoverage(BaseModel):
    supported: CoverageMetric
    unsupported: CoverageMetric


class CoverageSlice(BaseModel):
    identity: IdentityCoverage
    production: ProductionCoverage
    schedule: ScheduleCoverage
    status: StatusCoverage
    role: RoleCoverage


class PotentialNbaMatch(BaseModel):
    nba_player_id: str
    player_name: str
    team: str | None


class MappingWorklistItem(BaseModel):
    internal_id: int
    yahoo_player_id: str
    yahoo_name: str
    yahoo_team: str | None
    normalized_name: str
    potential_nba_matches: list[PotentialNbaMatch] = Field(default_factory=list)
    conflict_reason: str
    resolution_state: Literal[
        "EXACT_ID",
        "EXACT_NAME_TEAM",
        "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM",
        "TEAM_CHANGE_SUPPORTED",
        "AMBIGUOUS",
        "NO_MATCH",
        "MISSING_MAPPING",
        "NON_NBA_PLAYER",
    ]


RootCause = Literal[
    "RESOLVABLE_INTERNAL_DEFECT",
    "STALE_EXISTING_SOURCE",
    "MISSING_MAPPING",
    "MISSING_EXISTING_SOURCE_FIELD",
    "SOURCE_DOES_NOT_SUPPLY",
    "SOURCE_CONTRACT_UNVERIFIED",
    "REQUIRES_MORE_GAMES",
    "REQUIRES_NEW_SOURCE",
    "INTENTIONALLY_UNSUPPORTED",
]


class WaiverCoverage(BaseModel):
    population: CoverageScope
    pool: CoverageSlice
    candidates: CoverageSlice
    roster: CoverageSlice
    acquisition: AcquisitionCoverage
    mapping_worklist: list[MappingWorklistItem] = Field(default_factory=list)


DataGapCategory = Literal[
    "FIXABLE DATA ISSUE",
    "WAITING FOR MORE GAMES",
    "SOURCE DOES NOT SUPPLY",
    "NEW SOURCE REQUIRED",
    "UNVERIFIED YAHOO CONTEXT",
    "SOURCE CONTRACT UNVERIFIED",
    "INTENTIONALLY UNSUPPORTED",
]


class DataGap(BaseModel):
    category: DataGapCategory
    field: str
    count: int
    total: int
    percentage: float
    reason: str
    root_cause: RootCause


class ProductionBasis(BaseModel):
    """The per-game Yahoo-rule production a comparison actually used (the value behind the production percentile),
    with its provenance. Weekly horizons blend the last 14 days with the prior season (n/(n+10)); Rest of Season
    Outlook uses current-season Season Evidence. Historical evidence, never a projection."""
    value: float | None = None
    basis: ProductionBasisCode = "UNAVAILABLE"
    label: str = "Production unavailable"
    percentile: float | None = None
    window_value: float | None = None
    window_games: int = 0
    window_weight: float | None = None
    prior_value: float | None = None
    prior_games: int = 0
    prior_season: str | None = None
    prior_weight: float | None = None
    current_season_value: float | None = None
    current_season_games: int = 0
    math: str = ""


class ComponentContribution(BaseModel):
    component: str
    before: float
    after: float
    delta: float
    effective_weight: float
    weighted_contribution: float


class ExplanationCheck(BaseModel):
    key: Literal["ARITHMETIC", "CLAIMS_MEASURED", "COMPENSATION", "NEAR_TIE"]
    passed: bool
    detail: str


class PairExplanation(BaseModel):
    """Backend-owned explanation of one exact comparison and its consistency checks.

    The contributions reproduce the returned net. A favorable claim is made only for a component in the common mask
    with a positive weighted contribution. When the add's production is lower, every compensating claim must hold
    in the league's own scoring unit (window Yahoo fantasy points), or the positive net is not supported."""
    horizon: str
    window_start: date | None = None
    window_end: date | None = None
    comparison_type: ComparisonType = "ADD_DROP"
    add_player_id: int
    add_name: str
    drop_player_id: int | None = None
    drop_name: str | None = None
    add_production: ProductionBasis
    drop_production: ProductionBasis | None = None
    production_gap: float | None = None
    add_games: int | None = None
    drop_games: int | None = None
    add_window_points: float | None = None
    drop_window_points: float | None = None
    window_points_gap: float | None = None
    starting_slots_before: int | None = None
    starting_slots_after: int | None = None
    starting_slots_required: int | None = None
    contributions: list[ComponentContribution] = Field(default_factory=list)
    contribution_sum: float | None = None
    net: float | None = None
    favorable: list[str] = Field(default_factory=list)
    unfavorable: list[str] = Field(default_factory=list)
    omitted: dict[str, str] = Field(default_factory=dict)
    compensating: list[str] = Field(default_factory=list)
    refuted: dict[str, str] = Field(default_factory=dict)
    net_without: dict[str, float | None] = Field(default_factory=dict)
    reconciled_net: float | None = None
    near_tie: bool = False
    fragile: bool = False
    prior_season_driven: bool = False
    checks: list[ExplanationCheck] = Field(default_factory=list)
    consistent: bool = False
    statement: str = ""
    primary_reason: str = ""
    tradeoffs: list[str] = Field(default_factory=list)
    primary_tradeoff: str | None = None
    blocker: str | None = None


class DropAlternative(BaseModel):
    """Another roster drop measured for the same add (the page's "why this drop" evidence)."""
    player_id: int
    player_name: str
    net: float | None = None
    margin: float | None = None
    consistent: bool = False
    near_tie: bool = False
    note: str = ""


class EvidenceDimension(BaseModel):
    """One labeled evidence dimension, so labels from different systems are never shown unlabeled side by side."""
    key: EvidenceDimensionKey
    label: str
    state: str
    text: str
    detail: str = ""


class DropOption(BaseModel):
    player_id: int | None
    player_name: str
    before_score: float | None
    after_score: float | None
    net_improvement: float | None
    component_deltas: Components
    reasons: list[str]
    component_before: Components = Field(default_factory=Components)
    component_after: Components = Field(default_factory=Components)
    effective_weights: dict[str, float] = Field(default_factory=dict)
    starting_slots_before: int | None = None
    starting_slots_after: int | None = None
    starting_slots_required: int | None = None
    comparison_type: ComparisonType = "ADD_DROP"
    moved_to_injury_slot_player_id: int | None = None
    moved_to_injury_slot_player_name: str | None = None
    target_roster_position: str | None = None
    roster_spots_basis: int | None = None
    open_roster_spots_before: int | None = None
    open_roster_spots_after: int | None = None
    explanation: PairExplanation | None = None


class RosterSlot(BaseModel):
    position: str
    count: int
    kind: SlotKind
    occupied: int | None = None
    open: int | None = None


class RosterAssignment(BaseModel):
    player_id: int
    player_name: str
    positions: str | None = None
    roster_slot: str | None = None
    slot_kind: SlotKind | None = None
    yahoo_status: str | None = None
    status_state: QualityState = "unknown"
    status_label: str | None = None
    decision_status_state: YahooStatusDecisionState = "UNKNOWN"
    eligible_positions_known: bool = False
    eligible_injury_slots: list[str] = Field(default_factory=list)
    injured: bool = False
    lineup_eligible: bool = False
    injury_note: str | None = None
    detail: str = ""


class InjuryMoveOption(BaseModel):
    player_id: int
    player_name: str
    from_slot: str
    to_slot: str
    released_slot: str
    released_slot_kind: SlotKind
    certainty: Literal["conditional"] = "conditional"
    detail: str


class InjuryMoveBlocker(BaseModel):
    player_id: int
    player_name: str
    roster_slot: str | None = None
    reason: str


class RosterCapacity(BaseModel):
    state: Literal["available", "stale", "missing", "conflicting"]
    transaction_shape: TransactionShape
    slots: list[RosterSlot] = Field(default_factory=list)
    assignments: list[RosterAssignment] = Field(default_factory=list)
    total_capacity: int | None = None
    non_injury_capacity: int | None = None
    active_slot_capacity: int | None = None
    bench_capacity: int | None = None
    injury_slot_capacity: int | None = None
    roster_count: int = 0
    occupied_roster_spots: int | None = None
    occupied_active_slots: int | None = None
    occupied_bench_slots: int | None = None
    occupied_injury_slots: int | None = None
    open_roster_spots: int | None = None
    open_active_slots: list[str] = Field(default_factory=list)
    open_bench_slots: int | None = None
    open_injury_slots: int | None = None
    unassigned_player_ids: list[int] = Field(default_factory=list)
    injured_players: list[RosterAssignment] = Field(default_factory=list)
    injured_players_outside_injury_slots: list[int] = Field(default_factory=list)
    injured_players_in_injury_slots: list[int] = Field(default_factory=list)
    no_drop_additions_available: int | None = None
    move_to_injury_slot_options: list[InjuryMoveOption] = Field(default_factory=list)
    injury_move_blockers: list[InjuryMoveBlocker] = Field(default_factory=list)
    additions_after_injury_moves: int | None = None
    requires_drop: bool | None = None
    requires_roster_move: bool | None = None
    drop_requirement_reason: str
    headline: str = ""
    short_reason: str = ""
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    assignment_as_of: date | None = None
    evidence: Evidence
    status_evidence: Evidence
    transaction_legality_quality: Evidence
    limitations: list[str] = Field(default_factory=list)


class SlotCoverage(BaseModel):
    slot: str
    kind: SlotKind
    required: int
    covered: int | None = None
    uncovered: int | None = None
    eligible_player_ids: list[int] = Field(default_factory=list)
    weakened_by_injury: bool = False
    injured_player_ids: list[int] = Field(default_factory=list)
    need_score: float | None = None
    # Dates in the window with at least one of this slot's starting instances uncovered (never above the date count).
    open_slot_days: int | None = None
    # Uncovered slot instances summed over those dates (two C slots open on one date count 2).
    open_slot_games: int | None = None
    detail: str


class LineupDay(BaseModel):
    date: date
    players_with_games: int
    fillable_starting_slots: int
    starting_slots_required: int
    open_starting_slots: list[str] = Field(default_factory=list)


class TeamNeed(BaseModel):
    priority: int
    slot: str
    kind: Literal["OPEN_STARTING_SLOT", "INJURY_WEAKENED", "LINEUP_DAY_GAP", "BENCH_DEPTH"]
    # LINEUP_DAY_GAP: dates in the window (never above the date count); other kinds: slot instances.
    count: int
    slot_games: int | None = None
    positions: list[str] = Field(default_factory=list)
    reason: str
    compatible_candidate_ids: list[int] = Field(default_factory=list)


class NeedPlayer(BaseModel):
    player_id: int
    player_name: str
    positions: str | None = None
    roster_slot: str | None = None
    yahoo_status: str | None = None
    lineup_eligible: bool
    injured: bool = False
    multi_position: bool = False
    games_in_window: int | None = None
    schedule_state: QualityState = "unavailable"
    fantasy_ppg: float | None = None
    production_state: QualityState = "unavailable"
    role_trend: str = "INSUFFICIENT EVIDENCE"
    minutes: float | None = None


class ProductionNeed(BaseModel):
    state: QualityState
    lineup_players: int
    supported_players: int
    lowest_supported_ppg: float | None = None
    lowest_supported_player_id: int | None = None
    median_supported_ppg: float | None = None
    detail: str


class NeedSummary(BaseModel):
    """Plain-language positional need for one position family; UTIL and bench are never positional."""
    priority: int
    family: PositionFamily
    label: str
    level: NeedLevel
    slots: list[str] = Field(default_factory=list)
    positions: list[str] = Field(default_factory=list)
    reason: str
    eligible_player_ids: list[int] = Field(default_factory=list)


class TeamNeeds(BaseModel):
    state: QualityState
    mode: Mode
    window_start: date
    window_end: date
    lineup_player_count: int
    starting_slots_required: int | None = None
    starting_slots_covered: int | None = None
    open_starting_slots: list[str] = Field(default_factory=list)
    weakened_positions: list[str] = Field(default_factory=list)
    slot_coverage: list[SlotCoverage] = Field(default_factory=list)
    position_need_scores: dict[str, float] = Field(default_factory=dict)
    needs: list[TeamNeed] = Field(default_factory=list)
    multi_position_player_ids: list[int] = Field(default_factory=list)
    redundancy: dict[str, int] = Field(default_factory=dict)
    players: list[NeedPlayer] = Field(default_factory=list)
    lineup_days: list[LineupDay] = Field(default_factory=list)
    lineup_day_state: QualityState = "unavailable"
    lineup_day_detail: str = ""
    production: ProductionNeed
    injured_player_ids: list[int] = Field(default_factory=list)
    uncertain_status_player_ids: list[int] = Field(default_factory=list)
    unknown_status_player_ids: list[int] = Field(default_factory=list)
    hold_guidance: str
    summary: list[NeedSummary] = Field(default_factory=list)
    depth_note: str | None = None
    basis: str = ""
    limitations: list[str] = Field(default_factory=list)


class AvailabilityEvidence(BaseModel):
    """Why a player is (or is not) a waiver-eligible candidate, from persisted Yahoo evidence only."""
    classification: AvailabilityClass
    label: str
    actionable: bool
    source: str
    imported_at: datetime | None = None
    roster_snapshot_complete: bool = False
    roster_snapshots_current: int = 0
    roster_snapshots_expected: int = 0
    # Explicit Yahoo free-agent / waiver state, only when a persisted payload supplied it.
    yahoo_ownership_state: Literal["FA", "W"] | None = None
    waiver_clear_date: date | None = None
    eligibility_reason: str | None = None
    blockers: list[str] = Field(default_factory=list)
    detail: str


class AvailabilitySummary(BaseModel):
    state: QualityState
    roster_snapshot_complete: bool
    roster_snapshots_current: int
    roster_snapshots_expected: int
    oldest_roster_snapshot: datetime | None = None
    player_pool_imported_at: datetime | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    explicit_state_supplied: bool = False
    source_gap: str | None = None
    detail: str


class Candidate(BaseModel):
    player_id: int
    yahoo_player_id: str
    player_name: str
    position: str | None
    yahoo_team: str | None = None
    nba_team: str | None
    raw_yahoo_status: str | None = None
    yahoo_status: str | None
    # Backend-owned status interpretation (player_status.interpret_yahoo_status). Defaults fail closed: a candidate
    # built without it is UNKNOWN and cannot pass the Yahoo status gate.
    status_field_state: YahooStatusField | None = None
    decision_status_state: YahooStatusDecisionState = "UNKNOWN"
    status_reason: YahooStatusReason | None = None
    status_gate_supported: bool = False
    status_label: str | None = None
    status_detail: str | None = None
    identity_mapping_state: Literal[
        "EXACT_ID",
        "EXACT_NAME_TEAM",
        "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM",
        "TEAM_CHANGE_SUPPORTED",
        "AMBIGUOUS",
        "NO_MATCH",
        "MISSING_MAPPING",
        "NON_NBA_PLAYER",
    ] = "MISSING_MAPPING"
    identity_mapping_reason: str = "NBA player identity has not been mapped."
    mapping_diagnostic: Literal[
        "YAHOO_ID_MISSING",
        "NBA_ID_UNMAPPED",
        "NBA_PLAYER_MISSING",
        "TEAM_MAPPING_MISSING",
        "GAME_LOGS_MISSING",
        "SEASON_STATS_MISSING",
        "SCHEDULE_ROWS_MISSING",
        "SCHEDULE_STALE",
        "COMPLETE_MAPPING",
    ] = "NBA_ID_UNMAPPED"
    status_diagnostic: Literal[
        "YAHOO_SUPPLIED_BLANK",
        "STATUS_FIELD_MISSING",
        "STALE_PLAYER_POOL_IMPORT",
        "NORMALIZATION_DEFECT",
        "MISSING_PLAYER_OBSERVATION",
        "MAPPING_ISSUE",
        "UNRECOGNIZED_STATUS",
        "STATUS_PRESENT",
    ] = "MISSING_PLAYER_OBSERVATION"
    availability: Literal["free_agent", "waivers", "unrostered", "rostered", "unknown"]
    eligible: bool
    # Always set by the persisted-data loader; candidates built without it fall back to the
    # legacy `availability` mapping through `availability_class`.
    availability_classification: AvailabilityClass | None = None
    availability_evidence: AvailabilityEvidence | None = None
    recent: ValueEvidence
    ros: ValueEvidence
    opportunity: Opportunity
    schedule: Schedule
    components: Components
    overall_score: float | None = None
    effective_weights: dict[str, float] = Field(default_factory=dict)
    recommended_action: Decision
    current_season_games: int = 0
    evidence_quality: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    hold_type: Literal["streamer", "longer_term_hold", "undetermined"]
    best_drop_options: list[DropOption] = Field(default_factory=list)
    net_improvement: float | None = None
    reasons: list[str]
    limitations: list[str]
    data_quality: dict[str, Evidence]
    ranking_value: RankingEvidence = Field(default_factory=RankingEvidence)
    comparison: DropOption | None = None
    # Derived from the same gated exact-pair decisions the optimizer uses: a supported replacement exists, only
    # WATCH (positive but sample-blocked) replacements exist, no replacement improves the roster, or nothing measured.
    roster_decision: Literal["review_replacement", "watch_replacement", "keep_on_measured_model", "unavailable"] = "unavailable"
    recommended_action_type: ActionType = "INSUFFICIENT_EVIDENCE"
    action_label: str = ""
    requires_drop: bool | None = None
    requires_injury_slot_move: bool = False
    suggested_injury_move: InjuryMoveOption | None = None
    target_roster_position: str | None = None
    fills_needs: list[str] = Field(default_factory=list)
    add_only_impact: DropOption | None = None
    evidence_blockers: list[str] = Field(default_factory=list)
    decision_priority: int | None = None
    lineup_slot_days_gained: int | None = None
    measured: MeasuredProduction = Field(default_factory=MeasuredProduction)
    decision_support_class: DecisionSupportClass | None = None
    decision_rank: int | None = None
    form: RecentForm | None = None
    sample: SampleAssessment | None = None
    move_intent: MoveIntent = "INSUFFICIENT_EVIDENCE"
    move_intent_detail: str = ""
    verdict: TransactionVerdict = "CANNOT_EVALUATE"
    verdict_text: str = ""
    # Other measured drops for this add, best first, with the margin to the chosen drop.
    drop_alternatives: list[DropAlternative] = Field(default_factory=list)
    drop_choice: str = ""
    evidence_dimensions: list[EvidenceDimension] = Field(default_factory=list)


def availability_class(row: Candidate) -> str:
    return row.availability_classification or LEGACY_AVAILABILITY_CLASS[row.availability]


def availability_actionable(row: Candidate) -> bool:
    """A player may back a supported move or featured recommendation only with an actionable class."""
    return row.eligible and availability_class(row) in ACTIONABLE_AVAILABILITY


class OptionForm(BaseModel):
    """Compact form and schedule numbers for client-side exploratory sorting; never a ranking input."""
    last_7_ppg: float | None = None
    last_7_games: int = 0
    last_14_ppg: float | None = None
    last_14_games: int = 0
    last_30_ppg: float | None = None
    last_30_games: int = 0
    season_ppg: float | None = None
    season_games: int = 0
    previous_season_ppg: float | None = None
    previous_season_games: int = 0
    trend: FormTrendLabel = "INSUFFICIENT EVIDENCE"
    next_7_games: int | None = None
    next_14_games: int | None = None
    # Reason labels for windows without a value (None when a value is present and current).
    last_7_reason: str | None = None
    last_14_reason: str | None = None
    last_30_reason: str | None = None
    season_reason: str | None = None
    previous_season_reason: str | None = None


class OptionPair(BaseModel):
    """The exact comparison behind an option card: who to drop (or no drop), the net and why, on one basis."""
    comparison_type: ComparisonType = "ADD_DROP"
    drop_player_id: int | None = None
    drop_player_name: str | None = None
    net: float | None = None
    add_ppg: float | None = None
    drop_ppg: float | None = None
    basis_label: str = ""
    add_games: int | None = None
    drop_games: int | None = None
    window_points_gap: float | None = None
    starting_slots_before: int | None = None
    starting_slots_after: int | None = None
    starting_slots_required: int | None = None
    statement: str = ""
    primary_reason: str = ""
    primary_tradeoff: str | None = None
    blocker: str | None = None
    consistent: bool = False
    near_tie: bool = False
    alternatives: list[DropAlternative] = Field(default_factory=list)
    drop_choice: str = ""


class DecisionOption(BaseModel):
    """One player in the decision-support layer. Only SUPPORTED_ACTION carries a strict action;
    every other class is guidance to investigate in Yahoo, never an ADD/STREAM/MUST ADD."""
    player_id: int
    yahoo_player_id: str | None = None
    player_name: str
    positions: str | None = None
    nba_team: str | None = None
    decision_rank: int
    classification: DecisionSupportClass
    action_type: ActionType
    availability: Literal["free_agent", "waivers", "unrostered", "rostered", "unknown"]
    availability_confirmed: bool
    availability_label: str
    availability_classification: AvailabilityClass = "AVAILABILITY_UNVERIFIED"
    availability_evidence: AvailabilityEvidence | None = None
    yahoo_status: str | None = None
    status_label: str
    status_detail: str
    decision_status_state: YahooStatusDecisionState = "UNKNOWN"
    measured: MeasuredProduction
    games_in_window: int | None = None
    games_in_window_state: QualityState = "unavailable"
    fills: list[str] = Field(default_factory=list)
    fills_level: NeedLevel | None = None
    fills_slots: list[str] = Field(default_factory=list)
    multi_position: bool = False
    evidence_level: SampleLabel = "NO CURRENT-SEASON EVIDENCE"
    reason: str
    why: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    confirm: list[str] = Field(default_factory=list)
    user_action: str
    roster_rank_if_added: int | None = None
    roster_measured_count: int = 0
    form: OptionForm | None = None
    move_intent: MoveIntent | None = None
    verdict: TransactionVerdict = "CANNOT_EVALUATE"
    verdict_text: str = ""
    # One-line answer to the transaction question (A: ADD/DROP, B: WATCH, C: DO NOT ADD, D: ADD ONLY / IL move).
    headline: str = ""
    pair: OptionPair | None = None
    current_season_games: int = 0
    evidence_dimensions: list[EvidenceDimension] = Field(default_factory=list)


class OptionGroupPick(BaseModel):
    key: OptionGroupKey
    # Qualified by the pick's verdict: "BEST SUPPORTED GUARD ADD" only for a supported add, otherwise
    # "BEST AVAILABLE GUARD TO MONITOR — not a supported add" (or DO NOT ADD / NEAR TIE / cannot evaluate).
    title: str
    player_id: int | None = None
    verdict: TransactionVerdict | None = None
    empty_reason: str | None = None


class DecisionSupport(BaseModel):
    state: DecisionSupportState
    headline: str
    detail: str
    availability_state: QualityState
    availability_note: str
    best_measured_ids: list[int] = Field(default_factory=list)
    groups: list[OptionGroupPick] = Field(default_factory=list)
    watch_ids: list[int] = Field(default_factory=list)
    potential_target_ids: list[int] = Field(default_factory=list)
    potential_target_count: int = 0
    options: list[DecisionOption] = Field(default_factory=list)
    supported_count: int = 0
    comparable_count: int = 0
    not_comparable_reasons: dict[str, int] = Field(default_factory=dict)
    roster_floor_ppg: float | None = None
    roster_floor_player_id: int | None = None
    method: str
    limitations: list[str] = Field(default_factory=list)


class FreshnessItem(BaseModel):
    source: str
    state: QualityState
    as_of: datetime | None = None
    detail: str


class NeedOption(BaseModel):
    slot: str
    candidate_id: int | None = None
    action_type: ActionType | None = None
    reason: str


class OptionGroups(BaseModel):
    by_need: list[NeedOption] = Field(default_factory=list)
    flexible_candidate_id: int | None = None
    short_term_candidate_id: int | None = None
    longer_term_candidate_id: int | None = None
    watch_candidate_ids: list[int] = Field(default_factory=list)
    detail: str


class FillRecommendation(BaseModel):
    step: int
    action_type: ActionType
    label: str
    decision: Decision
    add_player: Candidate
    target_roster_position: str | None = None
    fills_needs: list[str] = Field(default_factory=list)
    suggested_injury_move: InjuryMoveOption | None = None
    requires_drop: bool = False
    comparison: DropOption | None = None
    reasons: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class WaiverBoard(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None = None
    mode: Mode
    generated_at: datetime
    model_version: str = MODEL_VERSION
    weights: dict[str, float]
    best_overall_available_id: int | None
    best_add_for_team_id: int | None
    # On a full roster, the drop of the supported pair; it always equals the optimizer's best transaction.
    best_drop_for_team_id: int | None = None
    team_needs: list[str]
    candidates: list[Candidate]
    excluded_count: int
    unknown_availability_count: int
    limitations: list[str]
    data_quality: dict[str, Evidence]
    coverage: WaiverCoverage
    data_gaps: list[DataGap] = Field(default_factory=list)
    roster: list[Candidate] = Field(default_factory=list)
    selected_drop_player_id: int | None = None
    top_measured_candidate_id: int | None = None
    waiver_rules: list[str] = Field(default_factory=list)
    selected_player_result: str = "INSUFFICIENT EVIDENCE"
    recommended_action_type: ActionType = "INSUFFICIENT_EVIDENCE"
    roster_capacity: RosterCapacity | None = None
    team_needs_analysis: TeamNeeds | None = None
    option_groups: OptionGroups | None = None
    decision_support: DecisionSupport | None = None
    evidence_freshness: list[FreshnessItem] = Field(default_factory=list)
    # Every waiver-eligible candidate (actionable availability); every featured recommendation
    # must be a member. `candidates` carries full evidence for at most `candidate_limit` of them.
    eligible_candidate_ids: list[int] = Field(default_factory=list)
    candidate_count: int = 0
    candidate_limit: int = 0
    availability_summary: AvailabilitySummary | None = None
    acquisition_context: "AcquisitionContext | None" = None
    sample_policy: str = ""


class WaiverImpact(BaseModel):
    league_key: str
    team_key: str
    mode: Mode
    model_version: str = MODEL_VERSION
    candidate: Candidate
    comparison: DropOption | None
    limitations: list[str]
    roster_capacity: RosterCapacity | None = None


class SwapAnalysis(BaseModel):
    add_player: Candidate
    drop_player: Candidate
    mode: Mode
    decision: Decision
    comparison: DropOption
    reasons: list[str]
    limitations: list[str]


class AcquisitionContext(BaseModel):
    rules: list[str]
    data_quality: Evidence
    current_priority: int | None = None
    weekly_adds_used: int | None = None
    weekly_adds_remaining: int | None = None
    weekly_add_limit: int | None = None
    yahoo_week: int | None = None
    claim_clear_at: datetime | None = None
    state: QualityState = "missing"
    source: str | None = None
    as_of: datetime | None = None
    detail: str = "Current priority, weekly usage and exact claim-clear time are unverified; acquisition value does not affect ranking."


class TransactionAnalysis(BaseModel):
    league_key: str
    team_key: str
    team_name: str | None = None
    mode: Mode
    generated_at: datetime
    model_version: str = MODEL_VERSION
    decision: Literal["MUST ADD", "ADD", "STREAM", "HOLD", "INSUFFICIENT EVIDENCE"]
    decision_reasons: list[str] = Field(default_factory=list)
    best_transaction: SwapAnalysis | None
    top_supported_transactions: list[SwapAnalysis]
    watch_transactions: list[SwapAnalysis]
    evaluated_pair_count: int
    supported_pair_count: int
    # Supported pairs with a positive net and an ADD / STREAM / MUST ADD decision (PASS pairs excluded).
    supported_move_count: int = 0
    watch_pair_count: int
    excluded_pair_count: int
    excluded_pair_reasons: dict[str, int]
    data_quality: dict[str, Evidence]
    acquisition_context: AcquisitionContext
    limitations: list[str]
    recommended_action_type: ActionType = "INSUFFICIENT_EVIDENCE"
    action_label: str = ""
    roster_capacity: RosterCapacity | None = None
    team_needs_analysis: TeamNeeds | None = None
    best_addition: FillRecommendation | None = None
    add_only_recommendations: list[FillRecommendation] = Field(default_factory=list)
    watch_additions: list[FillRecommendation] = Field(default_factory=list)
    unfilled_needs: list[str] = Field(default_factory=list)
    evaluated_addition_count: int = 0
    supported_addition_count: int = 0
    watch_addition_count: int = 0
    excluded_addition_count: int = 0
    excluded_addition_reasons: dict[str, int] = Field(default_factory=dict)



RefreshStageName = Literal[
    "LEAGUE_SETTINGS",
    "PLAYER_POOL",
    "LEAGUE_ROSTERS",
    "ROSTER_SLOTS",
    "YAHOO_AVAILABILITY_STATUS",
    "NBA_TEAMS_PLAYERS",
    "NBA_SCHEDULE",
    "NBA_GAME_LOGS",
    "NBA_SEASON_STATS",
    "POST_REFRESH_VERIFICATION",
]
RefreshStageState = Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "SKIPPED"]
RefreshOverallState = Literal["RUNNING", "SUCCEEDED", "PARTIAL_FAILURE", "FAILED"]


class RefreshCheck(BaseModel):
    name: str
    passed: bool
    detail: str


class RefreshStage(BaseModel):
    stage: RefreshStageName
    label: str
    source: Literal["YAHOO", "NBA", "VERIFICATION"]
    state: RefreshStageState = "PENDING"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    rows_fetched: int | None = None
    rows_persisted: int | None = None
    source_timestamp: datetime | None = None
    verification: Literal["PASSED", "FAILED", "NOT_RUN"] = "NOT_RUN"
    checks: list[RefreshCheck] = Field(default_factory=list)
    summary: str = ""
    error_code: str | None = None
    message: str = ""


class RefreshJob(BaseModel):
    job_id: str
    state: RefreshOverallState
    active: bool
    scope: Literal["ALL", "FAILED_STAGES"] = "ALL"
    retry_of: str | None = None
    league_key: str
    team_key: str
    season: str | None = None
    requested_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    stages: list[RefreshStage]
    message: str = ""
    # Every Yahoo request the refresh made was a read; transactions are never requested or executed.
    yahoo_requests: int = 0
    practice_league_requests_blocked: int = 0
    yahoo_transactions_executed: int = 0
    board_reload_recommended: bool = False


class EvidenceStatus(BaseModel):
    stage: RefreshStageName
    label: str
    state: Literal["current", "stale", "missing"]
    as_of: datetime | None = None
    summary: str
    detail: str


class RefreshStatus(BaseModel):
    job: RefreshJob | None = None
    already_running: bool = False
    evidence: list[EvidenceStatus] = Field(default_factory=list)
    needs_refresh: bool
    stale_stages: list[str] = Field(default_factory=list)
    last_complete_refresh_at: datetime | None = None
    last_complete_refresh_source: Literal["refresh_job", "persisted_evidence"] | None = None
    checked_at: datetime


class RefreshRequest(BaseModel):
    retry_failed: bool = False


WaiverBoard.model_rebuild()

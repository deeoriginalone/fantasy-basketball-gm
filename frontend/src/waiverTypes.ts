export type WaiverMode = "this_week" | "next_7_days" | "next_14_days" | "ros";
export type SampleTier = "INSUFFICIENT" | "VERY_LOW" | "LIMITED" | "SUPPORTED";
export type FormTrendLabel = "IMPROVING" | "DECLINING" | "STABLE" | "MIXED" | "INSUFFICIENT EVIDENCE";
export type MoveIntent = "STREAM" | "TWO_WEEK_STREAM" | "LONGER_TERM_ADD" | "WATCH" | "HOLD" | "INSUFFICIENT_EVIDENCE";

/** One backend-computed look-back evidence window; never a decision horizon. */
export interface FormWindow {
  key: "LAST_7_DAYS" | "LAST_14_DAYS" | "LAST_30_DAYS" | "CURRENT_SEASON" | "PREVIOUS_SEASON";
  label: string;
  games: number;
  fantasy_ppg: number | null;
  minutes_average: number | null;
  minutes_median: number | null;
  starts: number | null;
  starts_detail: string;
  usage: number | null;
  usage_detail: string;
  sample_tier: SampleTier;
  sample_label: string;
  window_start: string | null;
  window_end: string | null;
  latest_game: string | null;
  season: string | null;
  as_of: string | null;
  state: QualityState;
  detail: string;
}

export interface FormTrend {
  trend: FormTrendLabel;
  recent_games: number;
  baseline_games: number;
  recent_ppg: number | null;
  baseline_ppg: number | null;
  ppg_change: number | null;
  recent_minutes: number | null;
  baseline_minutes: number | null;
  minutes_change: number | null;
  detail: string;
  method: string;
}

export interface RecentForm {
  windows: FormWindow[];
  trend: FormTrend;
  limitations: string[];
}

export interface SampleCheck {
  key: string;
  label: string;
  passed: boolean;
  detail: string;
}

export interface SampleAssessment {
  mode: WaiverMode;
  window: "LAST_14_DAYS" | "CURRENT_SEASON";
  relevant_games: number;
  current_season_games: number;
  tier: SampleTier;
  passes: boolean;
  corroborated: boolean;
  required: SampleCheck[];
  corroborations: SampleCheck[];
  corroborations_passed: number;
  detail: string;
}

/** Compact backend form and schedule numbers for exploratory client sorting only. */
export interface OptionForm {
  last_7_ppg: number | null;
  last_7_games: number;
  last_14_ppg: number | null;
  last_14_games: number;
  last_30_ppg: number | null;
  last_30_games: number;
  season_ppg: number | null;
  season_games: number;
  previous_season_ppg: number | null;
  previous_season_games: number;
  trend: FormTrendLabel;
  next_7_games: number | null;
  next_14_games: number | null;
}
export type WaiverSampleLabel = "EXCELLENT" | "GOOD" | "LIMITED" | "VERY LIMITED" | "INSUFFICIENT FOR STRONG RECOMMENDATION" | "NO CURRENT-SEASON EVIDENCE";
export type WaiverActionType = "ADD_ONLY" | "MOVE_TO_IL_THEN_ADD" | "ADD_DROP" | "WATCH" | "HOLD" | "INSUFFICIENT_EVIDENCE";
export type TransactionShape = "ADD_ONLY" | "MOVE_TO_IL_THEN_ADD" | "ADD_DROP" | "UNDETERMINED";
export type SlotKind = "starting" | "bench" | "injury" | "unsupported";
export type QualityState = "available" | "partial" | "missing" | "stale" | "unknown" | "unsupported" | "unavailable";
export type DecisionSupportClass = "SUPPORTED_ACTION" | "BEST_MEASURED_OPTION" | "WATCH" | "MEASURED" | "POTENTIAL_TARGET" | "UNAVAILABLE";
export type DecisionSupportState = "SUPPORTED_ACTION" | "BEST_MEASURED_OPTION" | "WATCH" | "POTENTIAL_TARGETS" | "UNAVAILABLE";
export type AvailabilityClass =
  | "CONFIRMED_FA"
  | "CONFIRMED_WAIVER"
  | "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT"
  | "ROSTERED_BY_OTHER_TEAM"
  | "ROSTERED_BY_MANAGER"
  | "AVAILABILITY_UNVERIFIED"
  | "EXCLUDED_STATUS"
  | "SOURCE_STALE";

export interface AvailabilityEvidence {
  classification: AvailabilityClass;
  label: string;
  actionable: boolean;
  source: string;
  imported_at: string | null;
  roster_snapshot_complete: boolean;
  roster_snapshots_current: number;
  roster_snapshots_expected: number;
  yahoo_ownership_state: "FA" | "W" | null;
  waiver_clear_date: string | null;
  eligibility_reason: string | null;
  blockers: string[];
  detail: string;
}

export interface AvailabilitySummary {
  state: QualityState;
  roster_snapshot_complete: boolean;
  roster_snapshots_current: number;
  roster_snapshots_expected: number;
  oldest_roster_snapshot: string | null;
  player_pool_imported_at: string | null;
  counts: Partial<Record<AvailabilityClass, number>>;
  explicit_state_supplied: boolean;
  source_gap: string | null;
  detail: string;
}

export interface AcquisitionContext {
  rules: string[];
  data_quality: WaiverEvidence;
  current_priority: number | null;
  weekly_adds_used: number | null;
  weekly_adds_remaining: number | null;
  weekly_add_limit?: number | null;
  yahoo_week?: number | null;
  claim_clear_at: string | null;
  state?: QualityState;
  source?: string | null;
  as_of?: string | null;
  detail: string;
}

export type RefreshStageName =
  | "LEAGUE_SETTINGS" | "PLAYER_POOL" | "LEAGUE_ROSTERS" | "ROSTER_SLOTS" | "YAHOO_AVAILABILITY_STATUS"
  | "NBA_TEAMS_PLAYERS" | "NBA_SCHEDULE" | "NBA_GAME_LOGS" | "NBA_SEASON_STATS" | "POST_REFRESH_VERIFICATION";
export type RefreshStageState = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "SKIPPED";

export interface RefreshCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface RefreshStage {
  stage: RefreshStageName;
  label: string;
  source: "YAHOO" | "NBA" | "VERIFICATION";
  state: RefreshStageState;
  started_at: string | null;
  completed_at: string | null;
  rows_fetched: number | null;
  rows_persisted: number | null;
  source_timestamp: string | null;
  verification: "PASSED" | "FAILED" | "NOT_RUN";
  checks: RefreshCheck[];
  summary: string;
  error_code: string | null;
  message: string;
}

export interface RefreshJob {
  job_id: string;
  state: "RUNNING" | "SUCCEEDED" | "PARTIAL_FAILURE" | "FAILED";
  active: boolean;
  scope: "ALL" | "FAILED_STAGES";
  retry_of: string | null;
  league_key: string;
  team_key: string;
  season: string | null;
  requested_at: string;
  started_at: string | null;
  completed_at: string | null;
  stages: RefreshStage[];
  message: string;
  yahoo_requests: number;
  practice_league_requests_blocked: number;
  yahoo_transactions_executed: number;
  board_reload_recommended: boolean;
}

export interface EvidenceStatus {
  stage: RefreshStageName;
  label: string;
  state: "current" | "stale" | "missing";
  as_of: string | null;
  summary: string;
  detail: string;
}

export interface WaiverRefreshStatus {
  job: RefreshJob | null;
  already_running: boolean;
  evidence: EvidenceStatus[];
  needs_refresh: boolean;
  stale_stages: RefreshStageName[];
  last_complete_refresh_at: string | null;
  last_complete_refresh_source: "refresh_job" | "persisted_evidence" | null;
  checked_at: string;
}
export type NeedLevel = "HIGH" | "MEDIUM" | "COVERED";
export type OptionGroupKey = "BEST_GUARD" | "BEST_WING_FORWARD" | "BEST_CENTER" | "BEST_MULTI_POSITION" | "BEST_SHORT_TERM" | "BEST_LONGER_TERM";

export interface MeasuredProduction {
  value: number | null;
  comparable: boolean;
  basis: "RECENT" | "CURRENT_SEASON" | "NONE";
  current_value: number | null;
  current_games: number;
  current_season: string | null;
  current_weight: number | null;
  prior_value: number | null;
  prior_games: number;
  prior_season: string | null;
  state: QualityState;
  as_of: string | null;
  sample_label: WaiverSampleLabel;
  detail: string;
}

export interface NeedSummary {
  priority: number;
  family: "GUARD" | "WING_FORWARD" | "CENTER";
  label: string;
  level: NeedLevel;
  slots: string[];
  positions: string[];
  reason: string;
  eligible_player_ids: number[];
}

export interface DecisionOption {
  player_id: number;
  player_name: string;
  positions: string | null;
  nba_team: string | null;
  decision_rank: number;
  classification: DecisionSupportClass;
  action_type: WaiverActionType;
  availability: "free_agent" | "waivers" | "unrostered" | "rostered" | "unknown";
  availability_confirmed: boolean;
  availability_label: string;
  availability_classification?: AvailabilityClass;
  availability_evidence?: AvailabilityEvidence | null;
  yahoo_player_id?: string | null;
  yahoo_status: string | null;
  status_label: string;
  status_detail: string;
  decision_status_state?: YahooStatusDecisionState;
  measured: MeasuredProduction;
  games_in_window: number | null;
  games_in_window_state: QualityState;
  fills: string[];
  fills_level: NeedLevel | null;
  fills_slots: string[];
  multi_position: boolean;
  evidence_level: WaiverSampleLabel;
  reason: string;
  why: string[];
  blockers: string[];
  confirm: string[];
  user_action: string;
  roster_rank_if_added: number | null;
  roster_measured_count: number;
  form?: OptionForm | null;
  move_intent?: MoveIntent | null;
}

export interface OptionGroupPick {
  key: OptionGroupKey;
  title: string;
  player_id: number | null;
  empty_reason: string | null;
}

export interface DecisionSupport {
  state: DecisionSupportState;
  headline: string;
  detail: string;
  availability_state: QualityState;
  availability_note: string;
  best_measured_ids: number[];
  groups: OptionGroupPick[];
  watch_ids: number[];
  potential_target_ids: number[];
  potential_target_count: number;
  options: DecisionOption[];
  supported_count: number;
  comparable_count: number;
  not_comparable_reasons: Record<string, number>;
  roster_floor_ppg: number | null;
  roster_floor_player_id: number | null;
  method: string;
  limitations: string[];
}

export interface FreshnessItem {
  source: string;
  state: QualityState;
  as_of: string | null;
  detail: string;
}

export interface WaiverEvidence {
  state: QualityState;
  source: string;
  as_of: string | null;
  detail: string;
  sample_count?: number | null;
}

export interface RosterSlot {
  position: string;
  count: number;
  kind: SlotKind;
  occupied: number | null;
  open: number | null;
}

export interface RosterAssignment {
  player_id: number;
  player_name: string;
  positions: string | null;
  roster_slot: string | null;
  slot_kind: SlotKind | null;
  yahoo_status: string | null;
  status_state: QualityState;
  status_label?: string | null;
  decision_status_state?: YahooStatusDecisionState;
  eligible_positions_known: boolean;
  eligible_injury_slots: string[];
  injured: boolean;
  lineup_eligible: boolean;
  injury_note: string | null;
  detail: string;
}

export interface InjuryMoveOption {
  player_id: number;
  player_name: string;
  from_slot: string;
  to_slot: string;
  released_slot: string;
  released_slot_kind: SlotKind;
  certainty: "conditional";
  detail: string;
}

export interface InjuryMoveBlocker {
  player_id: number;
  player_name: string;
  roster_slot: string | null;
  reason: string;
}

export interface RosterCapacity {
  state: "available" | "stale" | "missing" | "conflicting";
  transaction_shape: TransactionShape;
  slots: RosterSlot[];
  assignments: RosterAssignment[];
  total_capacity: number | null;
  non_injury_capacity: number | null;
  active_slot_capacity: number | null;
  bench_capacity: number | null;
  injury_slot_capacity: number | null;
  roster_count: number;
  occupied_roster_spots: number | null;
  occupied_active_slots: number | null;
  occupied_bench_slots: number | null;
  occupied_injury_slots: number | null;
  open_roster_spots: number | null;
  open_active_slots: string[];
  open_bench_slots: number | null;
  open_injury_slots: number | null;
  unassigned_player_ids: number[];
  injured_players: RosterAssignment[];
  injured_players_outside_injury_slots: number[];
  injured_players_in_injury_slots: number[];
  no_drop_additions_available: number | null;
  move_to_injury_slot_options: InjuryMoveOption[];
  injury_move_blockers: InjuryMoveBlocker[];
  additions_after_injury_moves: number | null;
  requires_drop: boolean | null;
  requires_roster_move: boolean | null;
  drop_requirement_reason: string;
  headline?: string;
  short_reason?: string;
  blockers: string[];
  warnings: string[];
  assignment_as_of: string | null;
  evidence: WaiverEvidence;
  status_evidence: WaiverEvidence;
  transaction_legality_quality: WaiverEvidence;
  limitations: string[];
}

export interface SlotCoverage {
  slot: string;
  kind: SlotKind;
  required: number;
  covered: number | null;
  uncovered: number | null;
  eligible_player_ids: number[];
  weakened_by_injury: boolean;
  injured_player_ids: number[];
  need_score: number | null;
  open_slot_days: number | null;
  detail: string;
}

export interface LineupDay {
  date: string;
  players_with_games: number;
  fillable_starting_slots: number;
  starting_slots_required: number;
  open_starting_slots: string[];
}

export interface TeamNeed {
  priority: number;
  slot: string;
  kind: "OPEN_STARTING_SLOT" | "INJURY_WEAKENED" | "LINEUP_DAY_GAP" | "BENCH_DEPTH";
  count: number;
  positions: string[];
  reason: string;
  compatible_candidate_ids: number[];
}

export interface NeedPlayer {
  player_id: number;
  player_name: string;
  positions: string | null;
  roster_slot: string | null;
  yahoo_status: string | null;
  lineup_eligible: boolean;
  injured: boolean;
  multi_position: boolean;
  games_in_window: number | null;
  schedule_state: QualityState;
  fantasy_ppg: number | null;
  production_state: QualityState;
  role_trend: string;
  minutes: number | null;
}

export interface TeamNeeds {
  state: QualityState;
  mode: WaiverMode;
  window_start: string;
  window_end: string;
  lineup_player_count: number;
  starting_slots_required: number | null;
  starting_slots_covered: number | null;
  open_starting_slots: string[];
  weakened_positions: string[];
  slot_coverage: SlotCoverage[];
  position_need_scores: Record<string, number>;
  needs: TeamNeed[];
  multi_position_player_ids: number[];
  redundancy: Record<string, number>;
  players: NeedPlayer[];
  lineup_days: LineupDay[];
  lineup_day_state: QualityState;
  lineup_day_detail: string;
  production: {
    state: QualityState;
    lineup_players: number;
    supported_players: number;
    lowest_supported_ppg: number | null;
    lowest_supported_player_id: number | null;
    median_supported_ppg: number | null;
    detail: string;
  };
  injured_player_ids: number[];
  uncertain_status_player_ids: number[];
  unknown_status_player_ids: number[];
  hold_guidance: string;
  summary?: NeedSummary[];
  depth_note?: string | null;
  basis?: string;
  limitations: string[];
}

export interface NeedOption {
  slot: string;
  candidate_id: number | null;
  action_type: WaiverActionType | null;
  reason: string;
}

export interface OptionGroups {
  by_need: NeedOption[];
  flexible_candidate_id: number | null;
  short_term_candidate_id: number | null;
  longer_term_candidate_id: number | null;
  watch_candidate_ids: number[];
  detail: string;
}

export interface RoleWindow {
  average: number | null;
  median: number | null;
  games: number;
  game_ids: string[];
  window_start: string | null;
  window_end: string | null;
  as_of: string | null;
  missing_game_ids: string[];
  stale_game_ids: string[];
}

export interface RoleMetric {
  quality: WaiverEvidence;
  recent: RoleWindow;
  comparison: RoleWindow;
  delta: number | null;
  median_delta: number | null;
  unit: string;
}

export interface CurrentRole {
  minutes: RoleMetric;
  usage: RoleMetric;
  starts: {
    quality: WaiverEvidence;
    season: string | null;
    season_starts: number | null;
    season_games: number | null;
    recent_starts: number | null;
    detail: string;
  };
  quality: WaiverEvidence;
  trend: "RISING" | "STABLE" | "FALLING" | "INSUFFICIENT EVIDENCE";
  season_usage: number | null;
  season_usage_quality: WaiverEvidence;
  method: string;
  limitations: string[];
}

export interface WaiverComponents {
  roster_fit: number | null;
  player_value: number | null;
  opportunity: number | null;
  schedule: number | null;
  acquisition_value: number | null;
}

export interface CoverageMetric {
  count: number;
  total: number;
  percentage: number;
}

export interface MappingWorklistItem {
  internal_id: number;
  yahoo_player_id: string;
  yahoo_name: string;
  yahoo_team: string | null;
  normalized_name: string;
  potential_nba_matches: { nba_player_id: string; player_name: string; team: string | null }[];
  conflict_reason: string;
  resolution_state: "EXACT_ID" | "EXACT_NAME_TEAM" | "NORMALIZED_NAME_TEAM" | "KNOWN_ALIAS_TEAM" | "TEAM_CHANGE_SUPPORTED" | "AMBIGUOUS" | "NO_MATCH" | "MISSING_MAPPING" | "NON_NBA_PLAYER";
}

export interface CoverageSlice {
  identity: { complete: CoverageMetric; unresolved: CoverageMetric; resolution_counts: Record<string, number> };
  production: {
    recent_supported: CoverageMetric;
    recent_missing: CoverageMetric;
    recent_stale: CoverageMetric;
    season_supported: CoverageMetric;
    season_missing: CoverageMetric;
    season_stale: CoverageMetric;
  };
  schedule: {
    supported: CoverageMetric;
    unknown: CoverageMetric;
    stale: CoverageMetric;
    source_incomplete: CoverageMetric;
  };
  status: { explicit: CoverageMetric; yahoo_blank: CoverageMetric; field_missing?: CoverageMetric; no_current_designation?: CoverageMetric; stale: CoverageMetric };
  role: {
    minutes_qualified: CoverageMetric;
    usage_supported: CoverageMetric;
    game_level_starts_supported: CoverageMetric;
    season_starts_supported: CoverageMetric;
    insufficient_sample: CoverageMetric;
    missing_inputs: CoverageMetric;
  };
}

export interface WaiverCoverage {
  population: { total: number; candidates: number; roster: number };
  pool: CoverageSlice;
  candidates: CoverageSlice;
  roster: CoverageSlice;
  acquisition: { supported: CoverageMetric; unsupported: CoverageMetric };
  mapping_worklist: MappingWorklistItem[];
}

export interface WaiverDataGap {
  category: "FIXABLE DATA ISSUE" | "WAITING FOR MORE GAMES" | "SOURCE DOES NOT SUPPLY" | "NEW SOURCE REQUIRED" | "UNVERIFIED YAHOO CONTEXT" | "SOURCE CONTRACT UNVERIFIED" | "INTENTIONALLY UNSUPPORTED";
  field: string;
  count: number;
  total: number;
  percentage: number;
  reason: string;
  root_cause: "RESOLVABLE_INTERNAL_DEFECT" | "STALE_EXISTING_SOURCE" | "MISSING_MAPPING" | "MISSING_EXISTING_SOURCE_FIELD" | "SOURCE_DOES_NOT_SUPPLY" | "SOURCE_CONTRACT_UNVERIFIED" | "REQUIRES_MORE_GAMES" | "REQUIRES_NEW_SOURCE" | "INTENTIONALLY_UNSUPPORTED";
}

export interface WaiverDrop {
  player_id: number | null;
  player_name: string;
  before_score: number | null;
  after_score: number | null;
  net_improvement: number | null;
  component_before: WaiverComponents;
  component_after: WaiverComponents;
  effective_weights: Record<string, number>;
  starting_slots_before: number | null;
  starting_slots_after: number | null;
  starting_slots_required: number | null;
  component_deltas: WaiverComponents;
  reasons: string[];
  comparison_type?: "ADD_DROP" | "ADD_ONLY" | "MOVE_TO_IL_THEN_ADD";
  moved_to_injury_slot_player_id?: number | null;
  moved_to_injury_slot_player_name?: string | null;
  target_roster_position?: string | null;
  roster_spots_basis?: number | null;
  open_roster_spots_before?: number | null;
  open_roster_spots_after?: number | null;
}

export type YahooStatusDecisionState = "EXCLUDED" | "UNCERTAIN" | "NO_CURRENT_YAHOO_DESIGNATION" | "UNKNOWN";

export interface WaiverCandidate {
  player_id: number;
  yahoo_player_id: string;
  player_name: string;
  position: string | null;
  yahoo_team: string | null;
  nba_team: string | null;
  raw_yahoo_status: string | null;
  yahoo_status: string | null;
  /** Backend-owned status interpretation; absent fields mean the response predates it (treated as UNKNOWN). */
  status_field_state?: "EXPLICIT_STATUS" | "UNRECOGNIZED_NONBLANK" | "YAHOO_SUPPLIED_BLANK" | "STATUS_FIELD_MISSING" | null;
  decision_status_state?: YahooStatusDecisionState;
  status_reason?: string | null;
  status_gate_supported?: boolean;
  status_label?: string | null;
  status_detail?: string | null;
  identity_mapping_state: MappingWorklistItem["resolution_state"];
  identity_mapping_reason: string;
  mapping_diagnostic: "YAHOO_ID_MISSING" | "NBA_ID_UNMAPPED" | "NBA_PLAYER_MISSING" | "TEAM_MAPPING_MISSING" | "GAME_LOGS_MISSING" | "SEASON_STATS_MISSING" | "SCHEDULE_ROWS_MISSING" | "SCHEDULE_STALE" | "COMPLETE_MAPPING";
  status_diagnostic: "YAHOO_SUPPLIED_BLANK" | "STATUS_FIELD_MISSING" | "STALE_PLAYER_POOL_IMPORT" | "NORMALIZATION_DEFECT" | "MISSING_PLAYER_OBSERVATION" | "MAPPING_ISSUE" | "UNRECOGNIZED_STATUS" | "STATUS_PRESENT";
  availability: "free_agent" | "waivers" | "unrostered" | "rostered" | "unknown";
  eligible: boolean;
  availability_classification?: AvailabilityClass | null;
  availability_evidence?: AvailabilityEvidence | null;
  recent: {
    value: number | null;
    games: number;
    season: string | null;
    label: string;
    sample_label: WaiverSampleLabel;
    per_game_stats: Record<string, number>;
    scoring_weights: Record<string, number>;
    scoring_contributions: Record<string, number>;
  };
  ros: {
    value: number | null;
    games: number;
    season: string | null;
    label: string;
    sample_label: WaiverSampleLabel;
    per_game_stats: Record<string, number>;
    scoring_weights: Record<string, number>;
    scoring_contributions: Record<string, number>;
  };
  ranking_value: {
    value: number | null;
    recent_weight: number | null;
    historical_value: number | null;
    historical_games: number;
    historical_season: string | null;
    label: string;
  };
  opportunity: {
    minutes: number | null;
    minutes_trend: number | null;
    usage_trend: number | null;
    historical_start_rate: number | null;
    role: string;
    score: number | null;
    score_parts: Record<string, number>;
    current_role: CurrentRole | null;
  };
  schedule: {
    games_remaining: number | null;
    off_day_games: number | null;
    back_to_backs: number | null;
    next_7_days_games: number | null;
    next_14_days_games?: number | null;
    rest_of_season_games?: number | null;
    persisted_window_games?: number | null;
    opponents: string[];
    game_dates?: string[];
    source_row_count: number;
    window_start: string;
    window_end: string;
    imported_at: string | null;
    freshness: "fresh" | "stale" | "unknown";
    coverage: "COMPLETE" | "PARTIAL" | "UNKNOWN" | "STALE";
    diagnostic_reason: "NBA_ID_UNMAPPED" | "TEAM_MAPPING_MISSING" | "NO_PLAYER_SCHEDULE_ROWS" | "NO_GAMES_IN_WINDOW" | "SCHEDULE_STALE" | "SCHEDULE_ROWS_PRESENT" | "SCHEDULE_SOURCE_INCOMPLETE";
  };
  components: WaiverComponents;
  overall_score: number | null;
  effective_weights: Record<string, number>;
  recommended_action: "MUST ADD" | "ADD" | "STREAM" | "WATCH" | "PASS" | "INSUFFICIENT EVIDENCE";
  current_season_games: number;
  evidence_quality: WaiverSampleLabel;
  hold_type: "streamer" | "longer_term_hold" | "undetermined";
  comparison: WaiverDrop | null;
  best_drop_options: WaiverDrop[];
  net_improvement: number | null;
  roster_decision: "review_replacement" | "keep_on_measured_model" | "unavailable";
  reasons: string[];
  limitations: string[];
  data_quality: Record<string, WaiverEvidence>;
  recommended_action_type?: WaiverActionType;
  action_label?: string;
  requires_drop?: boolean | null;
  requires_injury_slot_move?: boolean;
  suggested_injury_move?: InjuryMoveOption | null;
  target_roster_position?: string | null;
  fills_needs?: string[];
  add_only_impact?: WaiverDrop | null;
  evidence_blockers?: string[];
  decision_priority?: number | null;
  lineup_slot_days_gained?: number | null;
  measured?: MeasuredProduction;
  decision_support_class?: DecisionSupportClass | null;
  decision_rank?: number | null;
  form?: RecentForm | null;
  sample?: SampleAssessment | null;
  move_intent?: MoveIntent;
  move_intent_detail?: string;
}

export interface FillRecommendation {
  step: number;
  action_type: WaiverActionType;
  label: string;
  decision: WaiverCandidate["recommended_action"];
  add_player: WaiverCandidate;
  target_roster_position: string | null;
  fills_needs: string[];
  suggested_injury_move: InjuryMoveOption | null;
  requires_drop: boolean;
  comparison: WaiverDrop | null;
  reasons: string[];
  limitations: string[];
}

export interface WaiverBoard {
  league_key: string;
  team_key: string;
  team_name: string | null;
  mode: WaiverMode;
  generated_at: string;
  model_version: string;
  weights: Record<string, number>;
  best_overall_available_id: number | null;
  best_add_for_team_id: number | null;
  /** On a full roster: the supported pair's drop, always the optimizer's best transaction. */
  best_drop_for_team_id?: number | null;
  team_needs: string[];
  roster: WaiverCandidate[];
  selected_drop_player_id: number | null;
  top_measured_candidate_id: number | null;
  waiver_rules: string[];
  selected_player_result: string;
  candidates: WaiverCandidate[];
  excluded_count: number;
  unknown_availability_count: number;
  limitations: string[];
  data_quality: Record<string, WaiverEvidence>;
  coverage: WaiverCoverage;
  data_gaps: WaiverDataGap[];
  recommended_action_type?: WaiverActionType;
  roster_capacity?: RosterCapacity | null;
  team_needs_analysis?: TeamNeeds | null;
  option_groups?: OptionGroups | null;
  decision_support?: DecisionSupport | null;
  evidence_freshness?: FreshnessItem[];
  eligible_candidate_ids?: number[];
  candidate_count?: number;
  candidate_limit?: number;
  availability_summary?: AvailabilitySummary | null;
  acquisition_context?: AcquisitionContext | null;
  sample_policy?: string;
}

export interface WaiverImpact {
  league_key: string;
  team_key: string;
  mode: WaiverMode;
  model_version: string;
  candidate: WaiverCandidate;
  comparison: WaiverDrop | null;
  limitations: string[];
  roster_capacity?: RosterCapacity | null;
}

export interface SwapAnalysis {
  add_player: WaiverCandidate;
  drop_player: WaiverCandidate;
  mode: WaiverMode;
  decision: WaiverCandidate["recommended_action"];
  comparison: WaiverDrop;
  reasons: string[];
  limitations: string[];
}

export interface TransactionAnalysis {
  league_key: string;
  team_key: string;
  team_name: string | null;
  mode: WaiverMode;
  generated_at: string;
  model_version: string;
  decision: "MUST ADD" | "ADD" | "STREAM" | "HOLD" | "INSUFFICIENT EVIDENCE";
  decision_reasons: string[];
  best_transaction: SwapAnalysis | null;
  top_supported_transactions: SwapAnalysis[];
  watch_transactions: SwapAnalysis[];
  evaluated_pair_count: number;
  supported_pair_count: number;
  supported_move_count?: number;
  watch_pair_count: number;
  excluded_pair_count: number;
  excluded_pair_reasons: Record<string, number>;
  data_quality: Record<string, WaiverEvidence>;
  acquisition_context: AcquisitionContext;
  limitations: string[];
  recommended_action_type?: WaiverActionType;
  action_label?: string;
  roster_capacity?: RosterCapacity | null;
  team_needs_analysis?: TeamNeeds | null;
  best_addition?: FillRecommendation | null;
  add_only_recommendations?: FillRecommendation[];
  watch_additions?: FillRecommendation[];
  unfilled_needs?: string[];
  evaluated_addition_count?: number;
  supported_addition_count?: number;
  watch_addition_count?: number;
  excluded_addition_count?: number;
  excluded_addition_reasons?: Record<string, number>;
}

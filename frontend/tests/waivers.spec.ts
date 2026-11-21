import { expect, test, type Page, type Route } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const VERSION = "waiver-decision-integrity-phase7.1";
type Scenario = "add_only" | "move" | "two" | "full" | "hold_watch" | "undetermined" | "stale" | "unavailable";

const evidence = { state: "partial", source: "Persisted NBA", as_of: "2026-10-25T00:00:00Z", detail: "Partial schedule and coverage." };
const roleWindow = (average: number | null, games: number) => ({
  average, median: average, games, game_ids: games ? ["game-1", "game-2"] : [], window_start: games ? "2026-10-22" : null,
  window_end: games ? "2026-10-24" : null, as_of: evidence.as_of, missing_game_ids: [], stale_game_ids: [],
});
const currentRole = {
  minutes: { quality: { ...evidence, detail: "Recent 2/3; comparison 0/3: insufficient role sample." }, recent: roleWindow(30, 2), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "minutes" },
  usage: { quality: { ...evidence, state: "unavailable" }, recent: roleWindow(null, 0), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "fraction" },
  starts: { quality: { ...evidence, state: "unavailable" }, season: "2026-27", season_starts: null, season_games: null, recent_starts: null, detail: "Season starts do not establish the current lineup." },
  quality: evidence, trend: "INSUFFICIENT EVIDENCE", season_usage: .23, season_usage_quality: evidence,
  method: "Latest three vs preceding three games, each side needs three valid fresh games. No projection.",
  limitations: ["Game-level usage and starts are unavailable."],
};
const UNROSTERED = "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT";
const AVAILABILITY_LABELS: Record<string, string> = {
  CONFIRMED_FA: "FREE AGENT (YAHOO)", CONFIRMED_WAIVER: "ON WAIVERS (YAHOO)", [UNROSTERED]: "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO",
  ROSTERED_BY_OTHER_TEAM: "ROSTERED BY ANOTHER TEAM", ROSTERED_BY_MANAGER: "ON YOUR ROSTER", AVAILABILITY_UNVERIFIED: "AVAILABILITY UNVERIFIED",
  EXCLUDED_STATUS: "EXCLUDED (YAHOO O/OFS/NA)", SOURCE_STALE: "SAVED ROSTERS STALE — CHECK IN YAHOO",
};
const availability = (classification = UNROSTERED) => ({
  availability_classification: classification,
  availability_evidence: {
    classification, label: AVAILABILITY_LABELS[classification],
    actionable: ["CONFIRMED_FA", "CONFIRMED_WAIVER", UNROSTERED].includes(classification),
    source: "Yahoo league rosters and player pool", imported_at: "2026-11-14T05:00:00Z",
    roster_snapshot_complete: classification !== "SOURCE_STALE", roster_snapshots_current: classification === "SOURCE_STALE" ? 1 : 12,
    roster_snapshots_expected: 12, yahoo_ownership_state: null, waiver_clear_date: null, eligibility_reason: null, blockers: [],
    detail: "Persisted Yahoo availability evidence.",
  },
});
const components = { roster_fit: 72, player_value: 70, opportunity: 60, schedule: 80, acquisition_value: null };
const basis = (value: number) => ({
  value, basis: "RECENT_BLENDED", label: "Last 14 days blended with 2025-26 (83% previous season): mostly previous-season evidence",
  percentile: 80, window_value: value - 2, window_games: 2, window_weight: .1667, prior_value: value + .4, prior_games: 60,
  prior_season: "2025-26", prior_weight: .8333, current_season_value: value - 2, current_season_games: 2,
  math: `0.167 (2/12) x ${(value - 2).toFixed(2)} last 14 days (2 games) + 0.833 (10/12) x ${(value + .4).toFixed(2)} 2025-26 (60 games) = ${value.toFixed(2)}`,
});
// The backend explanation for one exact comparison; its single contribution reproduces the fixture net.
const explanation = (dropId: number | null, dropName: string | null, net: number, type = "ADD_DROP") => ({
  horizon: "Rest of Week", window_start: "2026-10-25", window_end: "2026-10-31", comparison_type: type,
  add_player_id: 1, add_name: "Available Center", drop_player_id: dropId, drop_name: dropName,
  add_production: basis(32), drop_production: dropId === null ? null : basis(24), production_gap: dropId === null ? null : 8,
  add_games: 2, drop_games: dropId === null ? null : 2, add_window_points: 64, drop_window_points: dropId === null ? null : 48,
  window_points_gap: dropId === null ? null : 16, starting_slots_before: 3, starting_slots_after: 3, starting_slots_required: 2,
  contributions: [{ component: "roster_fit", before: 72, after: 72 + net, delta: net, effective_weight: 1, weighted_contribution: net }],
  contribution_sum: net, net, favorable: net > 0 ? ["roster_fit"] : [], unfavorable: net < 0 ? ["roster_fit"] : [],
  omitted: { acquisition_value: "acquisition value is unavailable (current rolling priority and transaction evidence are unverified); it never affects ranking." },
  compensating: [], refuted: {}, net_without: {}, reconciled_net: net, near_tie: false, fragile: false, prior_season_driven: false,
  checks: [{ key: "ARITHMETIC", passed: true, detail: `Weighted contributions sum to ${net}; returned net ${net}.` }], consistent: true,
  statement: net > 0 ? `Roster fit: matched starting slots 3 to 3 of 2, +${net.toFixed(2)} index points. Net modeled change: +${net.toFixed(2)}.`
    : `No improvement: keeping ${dropName} is preferable under this model (net ${net.toFixed(2)} index points).`,
  primary_reason: net > 0 ? `Roster fit: +${net.toFixed(2)} index points` : "No component improves the roster index.",
  tradeoffs: [], primary_tradeoff: null, blocker: null,
});
const drop = (id: number, net = 15) => ({
  player_id: id, player_name: id === 2 ? "Weak Guard" : "Bench Forward", before_score: 66, after_score: 66 + net,
  net_improvement: net, component_before: components, component_after: { ...components, roster_fit: 72 + net },
  effective_weights: { roster_fit: .4 }, starting_slots_before: 3, starting_slots_after: 3,
  starting_slots_required: 2, component_deltas: { ...components, roster_fit: net }, reasons: ["Same measured model on both sides."],
  comparison_type: "ADD_DROP", target_roster_position: "C", explanation: explanation(id, id === 2 ? "Weak Guard" : "Bench Forward", net),
});
const noDrop = (type = "ADD_ONLY", moved: string | null = null) => ({
  ...drop(2, 12), player_id: null, player_name: moved ? `No drop (move ${moved} to IL)` : "No drop (open roster slot)",
  comparison_type: type, moved_to_injury_slot_player_id: moved ? 9 : null, moved_to_injury_slot_player_name: moved,
  target_roster_position: "C", roster_spots_basis: 13, open_roster_spots_before: 1, open_roster_spots_after: 0,
  reasons: ["No-drop comparison over the same 13 non-injury roster spots: nobody is removed."],
  explanation: { ...explanation(null, null, 12, type), statement: "Production: Available Center 32.0 Yahoo FP/G (last 14 days blended with the previous season), +12.00 index points. Net modeled change: +12.00." },
});
const formWindow = (key: string, label: string, games: number, ppg: number | null, tweaks: Record<string, unknown> = {}) => ({
  key, label, games, fantasy_ppg: ppg, minutes_average: games ? 28.4 : null, minutes_median: games ? 29 : null,
  starts: null, starts_detail: "Per-game starts are not persisted.", usage: null, usage_detail: "Game-level usage is not persisted.",
  sample_tier: games >= 7 ? "SUPPORTED" : games >= 5 ? "LIMITED" : "VERY_LOW", sample_label: `${games} games`,
  window_start: "2026-10-31", window_end: "2026-11-13", latest_game: "2026-11-13", season: null,
  as_of: "2026-11-14T08:31:50Z", state: "available", detail: "Persisted NBA game logs.", reason: null, reason_label: "", ...tweaks,
});
const SAMPLE_DETAIL = "6 games in the last 14 days (LIMITED SAMPLE), corroborated: 12 games in the last 30 days; 12 games this season; role STABLE (available)";
const formEvidence = {
  form: {
    windows: [
      formWindow("LAST_7_DAYS", "Last 7 Days", 3, 33.1), formWindow("LAST_14_DAYS", "Last 14 Days", 6, 31.2),
      formWindow("LAST_30_DAYS", "Last 30 Days", 12, 27.9),
      formWindow("CURRENT_SEASON", "Current Season", 12, 27.9, { season: "2026-27", starts: 9, usage: .231, window_start: null, window_end: null }),
      formWindow("PREVIOUS_SEASON", "Previous Season", 0, null, { season: "2025-26", state: "unavailable", window_start: null, window_end: null,
        reason: "NO_PREVIOUS_SEASON", reason_label: "No previous-season stats" }),
    ],
    trend: { trend: "IMPROVING", recent_games: 6, baseline_games: 6, recent_ppg: 31.2, baseline_ppg: 24.6, ppg_change: .268,
      recent_minutes: 30.1, baseline_minutes: 26.4, minutes_change: 3.7, detail: "Last 14 Days vs days 15-30: PPG +26.8%, minutes +3.7.",
      method: "Non-overlapping windows; descriptive only." },
    limitations: ["Form windows are historical Yahoo-rule production, not projections."],
  },
  sample: { mode: "this_week", window: "LAST_14_DAYS", relevant_games: 6, current_season_games: 12, tier: "LIMITED", passes: true,
    corroborated: true, required: [], corroborations: [], corroborations_passed: 3, detail: SAMPLE_DETAIL },
};
// Backend verdict semantics: every supported action type is SUPPORTED ADD; WATCH is WATCH ONLY; HOLD is DO NOT ADD.
const VERDICT_OF: Record<string, string> = { ADD_ONLY: "SUPPORTED_ADD", MOVE_TO_IL_THEN_ADD: "SUPPORTED_ADD", ADD_DROP: "SUPPORTED_ADD",
  WATCH: "WATCH_ONLY", HOLD: "DO_NOT_ADD" };
const VERDICT_WORDS: Record<string, string> = { SUPPORTED_ADD: "SUPPORTED ADD", WATCH_ONLY: "WATCH ONLY", NEAR_TIE: "NEAR TIE — NO STRONG PREFERENCE",
  DO_NOT_ADD: "DO NOT ADD", CANNOT_EVALUATE: "CANNOT EVALUATE" };
const withVerdict = <T extends { player_name: string; verdict?: unknown; verdict_text?: unknown }>(row: T, action: string) => {
  const verdict = (row.verdict as string | undefined) ?? VERDICT_OF[action] ?? "CANNOT_EVALUATE";
  return { ...row, verdict, verdict_text: (row.verdict_text as string | undefined) ?? `${VERDICT_WORDS[verdict]} — ${row.player_name}.` };
};
const player = (id: number, name: string, comparison: Record<string, unknown> | null, tweaks: Record<string, unknown> = {}) => {
  const row = playerRow(id, name, comparison, tweaks);
  return withVerdict(row, row.recommended_action_type as string);
};
const playerRow = (id: number, name: string, comparison: Record<string, unknown> | null, tweaks: Record<string, unknown> = {}) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, position: id === 3 ? "G" : "C", nba_team: "DEN",
  yahoo_status: id === 3 ? null : id === 1 ? "Q" : "P", availability: "free_agent", eligible: true,
  recent: { value: 52, games: 2, season: "2026-27",
    per_game_stats: { PTS: 20, REB: 10, AST: 6, BLK: 2, STL: 3, TOV: 4 },
    scoring_weights: { PTS: 1, REB: 1.2, AST: 1.5, BLK: 3, STL: 3, TOV: -1 },
    scoring_contributions: { PTS: 20, REB: 12, AST: 9, BLK: 6, STL: 9, TOV: -4 },
    label: "Recent", sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION" },
  ros: { value: 35, games: 60, season: "2025-26", per_game_stats: {}, label: "Historical", sample_label: "EXCELLENT" },
  ranking_value: { value: 32, recent_weight: .4, historical_value: 35, historical_games: 60, historical_season: "2025-26", label: "Recent / historical blend" },
  opportunity: { minutes: 30, minutes_trend: null, usage_trend: null, historical_start_rate: null, role: "INSUFFICIENT EVIDENCE", score: null, score_parts: {}, current_role: currentRole },
  identity_mapping_state: "EXACT_NAME_TEAM", identity_mapping_reason: "Yahoo and NBA identity evidence agrees.",
  mapping_diagnostic: "COMPLETE_MAPPING", status_diagnostic: id === 3 ? "YAHOO_SUPPLIED_BLANK" : "STATUS_PRESENT",
  schedule: { games_remaining: 2, off_day_games: 1, back_to_backs: 1, next_7_days_games: 2, next_14_days_games: 5, rest_of_season_games: 58, opponents: ["BOS"], window_start: "2026-10-25", window_end: "2026-10-31", coverage: "PARTIAL", freshness: "fresh", diagnostic_reason: "SCHEDULE_ROWS_PRESENT", imported_at: evidence.as_of, source_row_count: 4 },
  components, overall_score: 80, effective_weights: { roster_fit: .4 }, recommended_action: "WATCH", hold_type: "undetermined",
  current_season_games: 2, evidence_quality: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  comparison, best_drop_options: comparison && comparison.player_id !== null ? [comparison] : [],
  net_improvement: comparison ? comparison.net_improvement : null,
  roster_decision: "review_replacement", reasons: ["Fits an uncovered center slot"], limitations: ["Current rolling priority unavailable"],
  data_quality: { status: { ...evidence, state: id === 3 ? "unavailable" : "partial", detail: id === 3 ? "Blank status is unknown, not healthy." : "Q/P remains uncertain." }, schedule: evidence, recent: { ...evidence, state: "partial" } },
  recommended_action_type: "WATCH", action_label: "WATCH: The measured fit is positive, but the sample is too small for a supported move.",
  requires_drop: comparison ? comparison.player_id !== null : null, fills_needs: id === 3 ? [] : ["C"], target_roster_position: id === 3 ? "BN" : "C",
  evidence_blockers: ["Sample gate: Available Center 2 games this season and 2 in the last 14 days. A supported move needs 7 games this season and 7 in the last 14 days for every compared player; prior-season history cannot bypass this gate."], decision_priority: id,
  ...availability(),
  ...(id === 1 ? formEvidence : {}),
  ...tweaks,
});
// Backend-owned interpretation of a fresh, verified Yahoo record without a `status` key (2026-11-14 policy).
const NO_DESIGNATION_DETAIL = "Yahoo's current player record contains no explicit injury/status designation. This is not a medical-health guarantee.";
const noDesignation = {
  yahoo_status: null, raw_yahoo_status: null, status_diagnostic: "STATUS_FIELD_MISSING", status_field_state: "STATUS_FIELD_MISSING",
  decision_status_state: "NO_CURRENT_YAHOO_DESIGNATION", status_reason: "NO_CURRENT_YAHOO_DESIGNATION", status_gate_supported: true,
  status_label: "NO CURRENT YAHOO DESIGNATION", status_detail: NO_DESIGNATION_DETAIL,
};
const roster = [
  player(2, "Weak Guard", null, { availability: "rostered", ...availability("ROSTERED_BY_MANAGER") }),
  { ...player(4, "Bench Forward", null, { availability: "rostered", ...availability("ROSTERED_BY_MANAGER"), ...noDesignation,
    data_quality: { status: { ...evidence, state: "available", detail: NO_DESIGNATION_DETAIL }, schedule: evidence, recent: { ...evidence, state: "partial" } } }),
  position: "F" },
];
const injured = { player_id: 9, player_name: "Injured Center", positions: "C", roster_slot: "IL", slot_kind: "injury", yahoo_status: "O", status_state: "available", eligible_positions_known: true, eligible_injury_slots: ["IL"], injured: true, lineup_eligible: false, injury_note: "Knee", detail: "In IL." };
const shapes: Record<Scenario, string> = {
  add_only: "ADD_ONLY", two: "ADD_ONLY", hold_watch: "ADD_ONLY", move: "MOVE_TO_IL_THEN_ADD", full: "ADD_DROP",
  undetermined: "UNDETERMINED", stale: "UNDETERMINED", unavailable: "UNDETERMINED",
};
const headlines: Record<string, [string, string]> = {
  ADD_ONLY: ["OPEN ROSTER SPOT — NO DROP REQUIRED", "regular roster spots are used; players in IL do not use them."],
  MOVE_TO_IL_THEN_ADD: ["MOVE INJURED CENTER TO IL TO OPEN A ROSTER SPOT", "All 13 regular roster spots are used. An IL move keeps the player on your roster; it is not a drop."],
  ADD_DROP: ["ROSTER FULL — AN ADD REQUIRES A DROP", "All 13 regular roster spots are used and no injured player can move to an open IL slot."],
  UNDETERMINED: ["ROSTER CAPACITY NEEDS A YAHOO REFRESH", "Your saved roster is from 2026-10-25; Yahoo roster slots are not saved for 13 of 13 players."],
};
const moveOption = { player_id: 9, player_name: "Injured Center", from_slot: "C", to_slot: "IL", released_slot: "C", released_slot_kind: "starting", certainty: "conditional", detail: "Move Injured Center from C to IL. Conditional: Yahoo must currently allow the IL placement." };
const capacity = (current: Scenario) => {
  const shape = shapes[current];
  const open = current === "two" ? 2 : shape === "ADD_ONLY" ? 1 : 0;
  return {
    state: shape === "UNDETERMINED" ? "stale" : "available", transaction_shape: shape,
    headline: shape === "ADD_ONLY" ? `${open} ${headlines.ADD_ONLY[0].replace("SPOT", open === 1 ? "SPOT" : "SPOTS")}` : headlines[shape][0],
    short_reason: shape === "ADD_ONLY" ? `${13 - open} of 13 ${headlines.ADD_ONLY[1]}` : headlines[shape][1],
    slots: [{ position: "C", count: 2, kind: "starting", occupied: 1, open: 1 }, { position: "IL", count: 3, kind: "injury", occupied: 1, open: 2 }],
    assignments: [{ ...injured, roster_slot: current === "move" ? "C" : "IL", slot_kind: current === "move" ? "starting" : "injury" }],
    total_capacity: 16, non_injury_capacity: 13, active_slot_capacity: 10, bench_capacity: 3, injury_slot_capacity: 3,
    roster_count: 13, occupied_roster_spots: shape === "UNDETERMINED" ? null : 13 - open, occupied_active_slots: 9, occupied_bench_slots: 3,
    occupied_injury_slots: shape === "UNDETERMINED" ? null : 1, open_roster_spots: shape === "UNDETERMINED" ? null : open,
    open_active_slots: open ? ["C"] : [], open_bench_slots: 0, open_injury_slots: shape === "UNDETERMINED" ? null : 2, unassigned_player_ids: [],
    injured_players: [{ ...injured, roster_slot: current === "move" ? "C" : "IL", slot_kind: current === "move" ? "starting" : "injury" }],
    injured_players_outside_injury_slots: current === "move" ? [9] : [], injured_players_in_injury_slots: current === "move" ? [] : [9],
    no_drop_additions_available: shape === "UNDETERMINED" ? null : open,
    move_to_injury_slot_options: current === "move" ? [moveOption] : [], injury_move_blockers: [],
    additions_after_injury_moves: shape === "UNDETERMINED" ? null : open + (current === "move" ? 1 : 0),
    requires_drop: shape === "ADD_DROP" ? true : shape === "UNDETERMINED" ? null : false,
    requires_roster_move: shape === "MOVE_TO_IL_THEN_ADD",
    drop_requirement_reason: shape === "ADD_ONLY" ? `${open} of 13 non-injury roster spots are open. An add needs no drop.`
      : shape === "MOVE_TO_IL_THEN_ADD" ? "All 13 non-injury roster spots are occupied, but moving Injured Center to an open injury slot releases 1 spot(s)."
        : shape === "ADD_DROP" ? "All 13 non-injury roster spots are occupied and no injured player can move to an open injury slot. An add requires a drop."
          : "Roster capacity is undetermined, so no drop requirement is asserted and ADD + DROP is not used as a default.",
    blockers: shape === "UNDETERMINED" ? ["Yahoo slot assignments (selected_position) are not persisted for 13 of 13 roster players; use REFRESH WAIVER DATA."] : [],
    warnings: [], assignment_as_of: "2026-10-25",
    evidence: { ...evidence, state: shape === "UNDETERMINED" ? "stale" : "available" }, status_evidence: evidence,
    transaction_legality_quality: { ...evidence, detail: "Roster-capacity recommendation requiring Yahoo confirmation." },
    limitations: ["Moving a player to IL keeps that player on the roster; it is never treated as a drop."],
  };
};
const teamNeeds = () => ({
  state: "partial", mode: "this_week", window_start: "2026-10-25", window_end: "2026-10-31",
  lineup_player_count: 11, starting_slots_required: 10, starting_slots_covered: 9, open_starting_slots: ["C"], weakened_positions: ["C"],
  slot_coverage: [{ slot: "C", kind: "starting", required: 2, covered: 1, uncovered: 1, eligible_player_ids: [4], weakened_by_injury: true, injured_player_ids: [9], need_score: 50, open_slot_days: 3, detail: "1 of 2 C starting slots coverable." }],
  position_need_scores: { C: 50 },
  needs: [{ priority: 1, slot: "C", kind: "INJURY_WEAKENED", count: 1, positions: ["C"], reason: "1 of 2 C starting slot(s) cannot be filled by lineup-eligible roster players; weakened by Injured Center (O).", compatible_candidate_ids: [1] }],
  multi_position_player_ids: [], redundancy: { C: 1 }, players: [],
  lineup_days: [{ date: "2026-10-25", players_with_games: 6, fillable_starting_slots: 6, starting_slots_required: 10, open_starting_slots: ["C", "UTIL", "UTIL", "SF"] }],
  lineup_day_state: "partial", lineup_day_detail: "Uses persisted per-player schedule rows (coverage PARTIAL).",
  production: { state: "partial", lineup_players: 11, supported_players: 9, lowest_supported_ppg: 12, lowest_supported_player_id: 2, median_supported_ppg: 25, detail: "9 of 11 lineup-eligible players have supported Recent Yahoo-rule fantasy PPG." },
  injured_player_ids: [9], uncertain_status_player_ids: [], unknown_status_player_ids: [],
  hold_guidance: "Injury return timing is not forecast. Check Yahoo injury notes before choosing.", limitations: ["Eligibility is not player quality."],
  summary: [
    { priority: 1, family: "CENTER", label: "C", level: "HIGH", slots: ["C"], positions: ["C"], reason: "Injury coverage needed: Injured Center cannot play, leaving C open.", eligible_player_ids: [4] },
    { priority: 2, family: "GUARD", label: "PG / SG", level: "MEDIUM", slots: ["PG", "SG"], positions: ["PG", "SG"], reason: "Limited active coverage: only Weak Guard can fill PG / SG; one absence leaves it open.", eligible_player_ids: [2] },
    { priority: 3, family: "WING_FORWARD", label: "SF / PF / F", level: "COVERED", slots: ["SF", "PF", "F"], positions: ["SF", "PF"], reason: "Covered: 5 lineup-eligible players can fill these slots.", eligible_player_ids: [4] },
  ],
  depth_note: null, basis: "Based on the current saved Yahoo roster and league settings.",
});
const freshness = [
  { source: "Yahoo league settings", state: "available", as_of: "2026-10-25T00:00:00Z", detail: "Roster positions and scoring rules; fresh for 24 hours." },
  { source: "Your saved Yahoo roster", state: "stale", as_of: "2026-10-25T00:00:00Z", detail: "Yahoo slot assignments saved for 0 of 13 players." },
  { source: "League rosters (availability)", state: "partial", as_of: "2026-10-25T00:00:00Z", detail: "Saved rosters for 11 of 12 teams." },
  { source: "Yahoo player pool and statuses", state: "stale", as_of: "2026-10-25T00:00:00Z", detail: "Blank status is UNKNOWN." },
  { source: "NBA game logs", state: "stale", as_of: "2026-10-25T00:00:00Z", detail: "Latest persisted game 2026-10-24." },
  { source: "NBA season stats", state: "stale", as_of: "2026-10-25T00:00:00Z", detail: "Season rows imported with the game logs." },
  { source: "NBA schedule", state: "stale", as_of: "2026-10-25T00:00:00Z", detail: "Schedule counts are labeled stale." },
];
const BLANK = "Yahoo did not provide an explicit current status. Confirm the player in Yahoo before acting.";
const measured = (value: number | null) => ({
  value, comparable: value !== null, basis: value === null ? "NONE" : "CURRENT_SEASON", current_value: value, current_games: value === null ? 0 : 3,
  current_season: "2026-27", current_weight: 3 / 13, prior_value: value, prior_games: 70, prior_season: "2025-26", state: "stale",
  as_of: evidence.as_of, sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  detail: value === null ? "No current-season NBA games in persisted evidence." : `${value.toFixed(1)} measured Yahoo fantasy PPG. Imported 2026-10-25 (stale). Historical, not a projection.`,
});
const option = (id: number, name: string, tweaks: Record<string, unknown> = {}) => {
  const row = optionRow(id, name, tweaks);
  const verdict = withVerdict(row, row.action_type as string);
  return { ...verdict, headline: (tweaks.headline as string | undefined) ?? verdict.verdict_text };
};
const optionRow = (id: number, name: string, tweaks: Record<string, unknown> = {}) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, positions: "PG,SG", nba_team: "BOS", decision_rank: 1, classification: "MEASURED",
  action_type: "INSUFFICIENT_EVIDENCE", availability: "unrostered", availability_confirmed: true, availability_label: AVAILABILITY_LABELS[UNROSTERED],
  ...availability(),
  yahoo_status: null, status_label: "UNKNOWN", status_detail: BLANK, measured: measured(40 - id), games_in_window: 3,
  games_in_window_state: "partial", fills: [], fills_level: null, fills_slots: [], multi_position: true,
  evidence_level: "INSUFFICIENT FOR STRONG RECOMMENDATION", reason: `Measured ${(40 - id).toFixed(1)} Yahoo fantasy PPG.`,
  why: [`${(40 - id).toFixed(1)} measured Yahoo fantasy PPG from 3 current-season games, blended with 2025-26.`],
  blockers: ["Yahoo status is UNKNOWN (blank); blank is not treated as healthy.", "Current-season sample is 3 games; supported adds need at least 7."],
  confirm: ["Current Yahoo status", "Current role and minutes (small current-season sample)"], user_action: "CHECK IN YAHOO",
  roster_rank_if_added: 9, roster_measured_count: 14, current_season_games: 3, ...tweaks,
});
// Not on any saved roster, but the saved rosters are stale: a potential target only, never featured.
const unverified = (classification = "SOURCE_STALE") => ({
  classification: "POTENTIAL_TARGET", availability: "unknown", availability_confirmed: false,
  availability_label: AVAILABILITY_LABELS[classification], ...availability(classification),
  blockers: ["Yahoo availability is unverified: league rosters are from 2026-10-25 or incomplete."],
  confirm: ["Yahoo availability (free agent or waivers)", "Current Yahoo status"],
});
// Backend group titles: an empty group is "BEST AVAILABLE {noun}"; a pick's title is qualified by its verdict.
const GROUP_NOUNS = [["BEST_GUARD", "GUARD"], ["BEST_WING_FORWARD", "WING / FORWARD"], ["BEST_CENTER", "CENTER"],
  ["BEST_MULTI_POSITION", "MULTI-POSITION OPTION"], ["BEST_SHORT_TERM", "SHORT-TERM SCHEDULE OPTION"], ["BEST_LONGER_TERM", "LONGER-TERM OPTION"]];
const groupTitle = (noun: string, verdict: string) => verdict === "SUPPORTED_ADD" ? `BEST SUPPORTED ${noun} ADD`
  : verdict === "WATCH_ONLY" ? `BEST AVAILABLE ${noun} TO MONITOR — not a supported add`
    : verdict === "NEAR_TIE" ? `BEST AVAILABLE ${noun} — near tie, no strong preference`
      : verdict === "DO_NOT_ADD" ? `BEST AVAILABLE ${noun} — do not add: no supported positive swap` : `BEST AVAILABLE ${noun} — cannot evaluate yet`;
const groups = (picks: Record<string, number | null>, verdicts: Record<number, string> = {}) => GROUP_NOUNS.map(([key, noun]) => {
  const id = picks[key] ?? null;
  const verdict = id === null ? null : verdicts[id] ?? "CANNOT_EVALUATE";
  return { key, title: verdict ? groupTitle(noun, verdict) : `BEST AVAILABLE ${noun}`, player_id: id, verdict,
    empty_reason: id ? null : `No measurable ${noun.toLowerCase()}.` };
});
const decisionSupport = (current: Scenario) => {
  const base = {
    detail: "The strict evidence gates block a supported move, but persisted basketball evidence can still compare players.",
    availability_state: "available", availability_note: "League rosters are current, so listed players are confirmed available in Yahoo's saved data.",
    best_measured_ids: [] as number[], watch_ids: [] as number[], potential_target_ids: [] as number[], potential_target_count: 0,
    supported_count: 0, comparable_count: 2, not_comparable_reasons: { "Yahoo O/OFS/NA status": 2 },
    roster_floor_ppg: 12, roster_floor_player_id: 2, method: "Measured production is Yahoo-rule fantasy PPG from persisted NBA games.",
    limitations: ["Decision support never upgrades a player to ADD, STREAM or MUST ADD."],
  };
  if (current === "undetermined") {
    return { ...base, state: "BEST_MEASURED_OPTION", headline: "Best measured option: Measured Guard — not yet a supported add.",
      best_measured_ids: [21], comparable_count: 3, groups: groups({ BEST_WING_FORWARD: 22 }),
      options: [
        option(21, "Measured Guard", { decision_rank: 1, classification: "BEST_MEASURED_OPTION", fills: ["PG / SG"], fills_level: "MEDIUM",
          blockers: ["Roster capacity is undetermined: Your saved roster is from 2026-10-25.", "Yahoo status is UNKNOWN (blank); blank is not treated as healthy."],
          confirm: ["Free-agent or waiver state in Yahoo", "Current Yahoo status", "Whether you have an open roster spot"] }),
        option(22, "Group Wing", { decision_rank: 2, classification: "WATCH", positions: "SF,PF", reason: "Highest measured wing / forward production: 18.0 Yahoo fantasy PPG." }),
        option(24, "Watch Forward", { decision_rank: 3, positions: "PF", why: [], blockers: [], confirm: [] }),
      ] };
  }
  if (current === "stale") {
    return { ...base, state: "POTENTIAL_TARGETS", headline: "No player is confirmed available yet.",
      detail: "Saved Yahoo rosters are not all current, so no player can be confirmed available. 2 measurable players were not on any saved roster: refresh waiver data, or check the POTENTIAL TARGETS in Yahoo before acting.",
      availability_state: "stale",
      availability_note: "League rosters are from 2026-10-25 or incomplete, so availability is unverified. Players who were not on any saved league roster appear only as POTENTIAL TARGETS TO CHECK IN YAHOO; they may have been added since.",
      potential_target_ids: [41, 42, 43], potential_target_count: 2, comparable_count: 0, groups: groups({}),
      options: [
        option(41, "Potential Forward", { ...unverified(), decision_rank: 1, positions: "PF" }),
        option(42, "Unverified Guard", { ...unverified("AVAILABILITY_UNVERIFIED"), decision_rank: 2 }),
        // A malformed backend entry: a player rostered elsewhere must never be shown as any kind of target.
        option(43, "Rostered Elsewhere Guard", { ...unverified("ROSTERED_BY_OTHER_TEAM"), decision_rank: 3 }),
      ] };
  }
  if (current === "unavailable") {
    return { ...base, state: "UNAVAILABLE", headline: "No player can be compared yet.", availability_state: "partial",
      availability_note: "League rosters are from 2026-10-25 or incomplete, so availability is unverified.",
      detail: "Persisted evidence cannot support a measured comparison: No current-season NBA games: 82; Yahoo O/OFS/NA status: 270.",
      comparable_count: 0, groups: groups({}), options: [], not_comparable_reasons: { "No current-season NBA games": 82, "Yahoo O/OFS/NA status": 270 } };
  }
  const supported = current !== "hold_watch";
  const available = option(1, "Available Center", { decision_rank: 1, positions: "C", yahoo_status: "Q", status_label: "Q · Questionable",
    status_detail: "Yahoo lists the player as Questionable; status remains uncertain.", classification: supported ? "SUPPORTED_ACTION" : "WATCH",
    action_type: supported ? (current === "move" ? "MOVE_TO_IL_THEN_ADD" : current === "full" ? "ADD_DROP" : "ADD_ONLY") : "WATCH",
    fills: ["C"], fills_level: "HIGH", blockers: supported ? [] : ["Current-season sample is 2 games; supported adds need at least 7."],
    confirm: supported ? [] : ["Current role and minutes (small current-season sample)"], reason: supported ? "ADD ONLY: Add Available Center to cover C." : "Positive measured impact, but the sample is too small for a supported add." });
  const guard = option(3, "Overall Guard", { decision_rank: 2, classification: current === "two" ? "SUPPORTED_ACTION" : "WATCH", action_type: current === "two" ? "ADD_ONLY" : "INSUFFICIENT_EVIDENCE" });
  const wing = option(5, "Measured Wing", { decision_rank: 3, positions: "SF,PF", classification: "WATCH", reason: "Highest measured wing / forward production: 35.0 Yahoo fantasy PPG." });
  return { ...base, state: supported ? "SUPPORTED_ACTION" : "WATCH",
    headline: supported ? "1 supported move available." : "No measured option is strong enough to feature; watch the players below.",
    supported_count: supported ? (current === "two" ? 2 : 1) : 0, groups: groups({ BEST_GUARD: current === "two" ? null : 3, BEST_WING_FORWARD: 5 }),
    watch_ids: supported ? [] : [1], options: [available, guard, wing] };
};

let scenario: Scenario = "add_only";
type ReadFailure = "html504" | "network" | null;
let boardError: ReadFailure = null;
let transactionsError: ReadFailure = null;
let withheldEligibleId: number | null = null;
let failSelectedDrop: number | null = null;
let slowSelectedDrop: number | null = null;
let staleSurface: "board" | "transactions" | "replacements" | "impact" | null = null;
let structuredTransactionError = false;
let boardPair: [number, number] | null = null;

const candidatesFor = (mode: string, dropId: number | null, order = [1, 3]) => order.map((id) => {
  const name = id === 1 ? "Available Center" : "Overall Guard";
  if (dropId !== null) return player(id, name, drop(dropId, id === 1 ? (dropId === 2 ? 15 : -5) : 4), {
    recommended_action_type: "WATCH", add_only_impact: shapes[scenario] === "ADD_ONLY" ? noDrop() : null,
  });
  if (scenario === "full") return player(id, name, drop(4, 5));
  return player(id, name, noDrop(scenario === "move" ? "MOVE_TO_IL_THEN_ADD" : "ADD_ONLY", scenario === "move" ? "Injured Center" : null), { schedule: { ...player(id, name, null).schedule, window_end: mode === "next_7_days" ? "2026-10-31" : "2026-10-31" } });
});
const board = (mode = "this_week", dropId: number | null = null, order = [1, 3]) => ({
  league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
  mode, generated_at: "2026-10-25T00:00:00Z", model_version: VERSION,
  weights: { roster_fit: .35, player_value: .25, opportunity: .15, schedule: .15, acquisition_value: .1 },
  best_add_for_team_id: boardPair?.[0] ?? null, best_drop_for_team_id: boardPair?.[1] ?? null,
  best_overall_available_id: 1, top_measured_candidate_id: null,
  selected_drop_player_id: dropId, roster, team_needs: ["Uncovered center slot"],
  waiver_rules: ["Continual rolling list", "2-day waiver period", "4 adds/week", "Daily - Today deadline"],
  selected_player_result: "WATCH",
  candidates: shapes[scenario] === "UNDETERMINED" && dropId === null ? [] : candidatesFor(mode, dropId, order),
  // The backend's gated answer for an explicitly selected drop (null without one).
  drop_summary: dropId === null ? null : { drop_player_id: dropId, drop_player_name: dropId === 2 ? "Weak Guard" : "Bench Forward",
    decision: "watch_replacement", result: "WATCH", headline: `WATCH ONLY — ${order[0] === 1 ? "Available Center" : "Overall Guard"}.`,
    best_valid_replacement_id: null, watch_candidate_id: order[0], highest_raw_comparison: null },
  excluded_count: 2, unknown_availability_count: 1, limitations: ["No projections."],
  data_quality: { roster: { ...evidence, state: "available", detail: "Fresh roster." } },
  coverage, data_gaps: [], recommended_action_type: "WATCH",
  roster_capacity: capacity(scenario), team_needs_analysis: teamNeeds(), evidence_freshness: freshness,
  decision_support: dropId === null ? decisionSupport(scenario) : null,
  eligible_candidate_ids: scenario === "stale" ? [] : [1, 3, 5, 21, 22, 24].filter((id) => id !== withheldEligibleId),
  candidate_count: scenario === "stale" ? 0 : 6, candidate_limit: 12, acquisition_context: acquisition,
  availability_summary: {
    state: scenario === "stale" ? "stale" : "available", roster_snapshot_complete: scenario !== "stale",
    roster_snapshots_current: scenario === "stale" ? 1 : 12, roster_snapshots_expected: 12,
    oldest_roster_snapshot: "2026-10-25T00:00:00Z", player_pool_imported_at: "2026-10-25T00:00:00Z",
    counts: scenario === "stale" ? { SOURCE_STALE: 1, AVAILABILITY_UNVERIFIED: 1 } : { [UNROSTERED]: 6, ROSTERED_BY_OTHER_TEAM: 150 },
    explicit_state_supplied: false, source_gap: "The supported Yahoo player resource does not state free-agent vs waiver ownership.",
    detail: scenario === "stale" ? "1 of 12 league roster snapshots is current; availability is unverified." : "All 12 league roster snapshots are current and complete.",
  },
  option_groups: dropId === null ? { by_need: [{ slot: "C", candidate_id: 1, action_type: "WATCH", reason: "Best available option able to cover C." }],
    flexible_candidate_id: null, short_term_candidate_id: 1, longer_term_candidate_id: 3, watch_candidate_ids: [1], detail: "Backend-ranked alternatives." } : null,
});
const fill = (step: number, name: string, tweaks: Record<string, unknown> = {}) => {
  const move = scenario === "move" ? moveOption : null;
  const action = move ? "MOVE_TO_IL_THEN_ADD" : "ADD_ONLY";
  const label = move
    ? `MOVE Injured Center TO IL, THEN ADD ${name} to cover C. Injured Center stays on your roster; this is not a drop.`
    : `ADD ONLY: Add ${name}${step === 1 ? " to cover C" : ""}. You have an open roster spot. No player needs to be dropped.`;
  const comparison = noDrop(action, move ? "Injured Center" : null);
  return {
    step, action_type: action, label, decision: "ADD",
    add_player: player(step === 1 ? 1 : 3, name, comparison, { recommended_action: "ADD", recommended_action_type: action, current_season_games: 9, evidence_quality: "LIMITED", evidence_blockers: [], action_label: label }),
    target_roster_position: step === 1 ? "C" : "BN", fills_needs: step === 1 ? ["C"] : [], suggested_injury_move: move, requires_drop: false, comparison,
    reasons: [label, step === 1 ? "Fills the uncovered C starting slot measured for your lineup." : "Adds depth.", "Recent Yahoo-rule fantasy PPG 52 from 9 games.", "An add needs no drop."],
    limitations: ["Hypothetical analysis only."], ...tweaks,
  };
};
const swap = () => {
  const add = player(1, "Available Center", drop(4, 5));
  return { add_player: add, drop_player: roster[1], mode: "this_week", decision: "WATCH", comparison: add.comparison,
    reasons: ["Sample gate: Available Center 2 games this season and 2 in the last 14 days. A supported move needs 7 games this season and 7 in the last 14 days for every compared player; prior-season history cannot bypass this gate."], limitations: ["Partial schedule coverage; historical evidence is not a projection."] };
};
const transactions = (mode = "this_week") => {
  const base = {
    league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
    mode, generated_at: "2026-10-25T00:00:00Z", model_version: VERSION,
    decision: "HOLD", decision_reasons: ["No add/drop pair cleared all current evidence gates."], best_transaction: null as unknown,
    top_supported_transactions: [], watch_transactions: [] as unknown[],
    evaluated_pair_count: 0, supported_pair_count: 0, watch_pair_count: 0,
    excluded_pair_count: 0, excluded_pair_reasons: {}, data_quality: { settings: evidence },
    acquisition_context: acquisition,
    limitations: [], recommended_action_type: "HOLD", action_label: "HOLD: No sufficiently supported move currently improves the roster.",
    roster_capacity: capacity(scenario), team_needs_analysis: teamNeeds(),
    best_addition: null as unknown, add_only_recommendations: [] as unknown[], watch_additions: [] as unknown[], unfilled_needs: [],
    evaluated_addition_count: 0, supported_addition_count: 0, watch_addition_count: 0, excluded_addition_count: 0, excluded_addition_reasons: {},
  };
  if (scenario === "add_only" || scenario === "move" || scenario === "two") {
    const fills = (scenario === "two" ? [fill(1, "Available Center"), fill(2, "Overall Guard")] : [fill(1, "Available Center")])
      .map((item) => ({ ...item, add_player: { ...item.add_player, move_intent: "STREAM", move_intent_detail: "STREAM: 2 games in Rest of Week cover the open C slot." } }));
    return { ...base, decision: "ADD", recommended_action_type: fills[0].action_type, action_label: fills[0].label,
      best_addition: fills[0], add_only_recommendations: fills, evaluated_addition_count: 4, supported_addition_count: fills.length, excluded_addition_count: 4 - fills.length };
  }
  if (scenario === "hold_watch") {
    const watch = { ...fill(1, "Available Center"), action_type: "WATCH", decision: "WATCH", label: "WATCH: The measured fit is positive, but the sample is too small for a supported move." };
    watch.add_player = { ...watch.add_player, current_season_games: 2, recommended_action: "WATCH", recommended_action_type: "WATCH" };
    return { ...base, watch_additions: [watch], evaluated_addition_count: 4, excluded_addition_count: 4,
      decision_reasons: ["No available player cleared all evidence gates for the 1 no-drop roster spot(s)."] };
  }
  if (shapes[scenario] === "UNDETERMINED") {
    return { ...base, decision: "INSUFFICIENT EVIDENCE", recommended_action_type: "INSUFFICIENT_EVIDENCE",
      action_label: "INSUFFICIENT EVIDENCE: Roster capacity cannot be established from persisted Yahoo evidence, so no add, drop or IL move is recommended and no drop is assumed.",
      decision_reasons: capacity("undetermined").blockers };
  }
  return { ...base, watch_transactions: [{ ...swap(), mode }], evaluated_pair_count: 4, watch_pair_count: 1, excluded_pair_count: 4,
    excluded_pair_reasons: { "Insufficient current-season sample": 4 } };
};

const acquisition = {
  rules: ["Continual rolling list", "4 adds/week"], data_quality: { ...evidence, state: "available" },
  current_priority: 4, weekly_adds_used: 2, weekly_adds_remaining: 2, weekly_add_limit: 4, yahoo_week: 4, claim_clear_at: null,
  state: "available", source: "Yahoo league teams import", as_of: "2026-11-14T05:00:00Z",
  detail: "Waiver priority 4th and 2 of 4 weekly adds used in Yahoo week 4, from the supported Yahoo teams resource. Exact claim-clear times are not supplied.",
};
const metric = (count: number, total = 4) => ({ count, total, percentage: total ? count / total * 100 : 0 });
const coverageSlice = () => ({
  identity: { complete: metric(4), unresolved: metric(0), resolution_counts: { EXACT_NAME_TEAM: 4 } },
  production: { recent_supported: metric(3), recent_missing: metric(1), recent_stale: metric(0), season_supported: metric(4), season_missing: metric(0), season_stale: metric(0) },
  schedule: { supported: metric(3), unknown: metric(1), stale: metric(0), source_incomplete: metric(1) },
  status: { explicit: metric(3), yahoo_blank: metric(1), field_missing: metric(0), no_current_designation: metric(0), stale: metric(0) },
  role: { minutes_qualified: metric(3), usage_supported: metric(0), game_level_starts_supported: metric(0), season_starts_supported: metric(1), insufficient_sample: metric(1), missing_inputs: metric(4) },
});
const coverage = {
  population: { total: 4, candidates: 2, roster: 2 },
  pool: coverageSlice(), candidates: coverageSlice(), roster: coverageSlice(),
  acquisition: { supported: metric(0, 1), unsupported: metric(1, 1) },
  mapping_worklist: [],
};

type StageState = "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED" | "SKIPPED";
const STAGE_DEFS = [
  ["LEAGUE_SETTINGS", "Yahoo league/settings", "YAHOO"], ["PLAYER_POOL", "Yahoo player pool", "YAHOO"],
  ["LEAGUE_ROSTERS", "Yahoo rosters", "YAHOO"], ["ROSTER_SLOTS", "Roster slots", "YAHOO"],
  ["YAHOO_AVAILABILITY_STATUS", "Yahoo availability and status", "YAHOO"], ["NBA_TEAMS_PLAYERS", "NBA teams and players", "NBA"],
  ["NBA_SCHEDULE", "NBA schedule", "NBA"], ["NBA_GAME_LOGS", "NBA game logs", "NBA"], ["NBA_SEASON_STATS", "NBA season stats", "NBA"],
  ["POST_REFRESH_VERIFICATION", "Post-refresh verification", "VERIFICATION"],
] as const;
const STAGE_SUMMARY: Record<string, string> = {
  LEAGUE_SETTINGS: "Bully League · 12 teams", PLAYER_POOL: "612 players", LEAGUE_ROSTERS: "12 of 12 teams", ROSTER_SLOTS: "15 of 15 saved",
  YAHOO_AVAILABILITY_STATUS: "612 players", NBA_TEAMS_PLAYERS: "30 teams · 540 players", NBA_SCHEDULE: "1230 games · 18000 player rows",
  NBA_GAME_LOGS: "Latest game 2026-11-13", NBA_SEASON_STATS: "540 regular-season rows (2026-27)", POST_REFRESH_VERIFICATION: "9 of 9 checks passed",
};
const STALE_STAGES = ["LEAGUE_ROSTERS", "ROSTER_SLOTS", "YAHOO_AVAILABILITY_STATUS", "NBA_GAME_LOGS"];
const refreshJob = (states: StageState[], tweaks: Record<string, unknown> = {}) => ({
  job_id: "job-1", state: "RUNNING", active: true, scope: "ALL", retry_of: null as string | null, league_key: "478.l.50505",
  team_key: "478.l.50505.t.9", season: "2026-27", requested_at: "2026-11-14T03:40:00Z", started_at: "2026-11-14T03:40:00Z",
  completed_at: null as string | null,
  stages: STAGE_DEFS.map(([stage, label, source], index) => {
    const state = states[index] ?? "PENDING";
    return { stage, label, source, state, started_at: null, completed_at: null, rows_fetched: null, rows_persisted: null,
      source_timestamp: null, verification: state === "SUCCEEDED" ? "PASSED" : "NOT_RUN", checks: [], error_code: null as string | null,
      summary: state === "SUCCEEDED" ? STAGE_SUMMARY[stage] : state === "SKIPPED" ? "Not rerun: this source succeeded in the previous refresh." : "",
      message: "" };
  }),
  message: "", yahoo_requests: 14, practice_league_requests_blocked: 0, yahoo_transactions_executed: 0, board_reload_recommended: false,
  ...tweaks,
});
const finishedJob = (state: "SUCCEEDED" | "PARTIAL_FAILURE", tweaks: Record<string, unknown> = {}) => {
  const states: StageState[] = Array(10).fill("SUCCEEDED");
  if (state === "PARTIAL_FAILURE") [states[7], states[8]] = ["FAILED", "SKIPPED"];
  const job = refreshJob(states, { state, active: false, completed_at: "2026-11-14T03:42:00Z", board_reload_recommended: true, ...tweaks });
  if (state === "PARTIAL_FAILURE") {
    job.stages[7] = { ...job.stages[7], error_code: "NBA_SOURCE_FAILED",
      message: "The NBA statistics source did not return usable data. The previous NBA snapshot was kept." };
    job.stages[8] = { ...job.stages[8], summary: "Not run because NBA game logs failed; the previous NBA snapshot was kept." };
  }
  return job;
};
const refreshStatus = (stale: string[], job: unknown = null) => ({
  job, already_running: false,
  evidence: STAGE_DEFS.map(([stage, label]) => ({ stage, label, state: stale.includes(stage) ? "stale" : "current",
    as_of: "2026-11-14T03:42:00Z", summary: STAGE_SUMMARY[stage], detail: "Persisted evidence." })),
  needs_refresh: stale.length > 0, stale_stages: stale,
  last_complete_refresh_at: stale.length ? null : "2026-11-14T03:42:00Z",
  last_complete_refresh_source: stale.length ? null : "refresh_job", checked_at: "2026-11-14T03:45:00Z",
});
// Each refresh POST consumes one plan: its 202 body, then the statuses later progress polls return, in order.
type RefreshPlan = { post: unknown; polls: unknown[]; done?: () => void };
let refreshNow: unknown = refreshStatus([]);
let refreshPlans: RefreshPlan[] = [];
let refreshPolls: unknown[] = [];
let refreshDone: (() => void) | undefined;
const NGINX_504 = "<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n<body>\r\n<center><h1>504 Gateway Time-out</h1></center>\r\n"
  + "<hr><center>nginx/1.27.4</center>\r\n</body>\r\n</html>\r\n<!-- a padding to disable MSIE and Chrome friendly error page -->\r\n";
async function failRead(route: Route, kind: ReadFailure, requestId: string) {
  if (kind === "network") await route.abort("failed");
  else await route.fulfill({ status: 504, contentType: "text/html", body: NGINX_504, headers: { "X-Request-ID": requestId } });
}

const writes: string[] = [];
let expectedWrites: string[] = [];
test.beforeEach(async ({ page }) => {
  scenario = "add_only";
  boardError = null;
  transactionsError = null;
  withheldEligibleId = null;
  failSelectedDrop = null;
  slowSelectedDrop = null;
  staleSurface = null;
  structuredTransactionError = false;
  boardPair = null;
  refreshNow = refreshStatus([]);
  refreshPlans = [];
  refreshPolls = [];
  refreshDone = undefined;
  writes.length = 0;
  expectedWrites = [];
  page.on("request", (request) => {
    if (request.url().includes("/api/") && request.method() !== "GET") writes.push(`${request.method()} ${new URL(request.url()).pathname}`);
  });
  await page.route("**/api/**", async (route) => {
    const url = new URL(route.request().url());
    expect(url.searchParams.has("team_key")).toBe(false);
    expect(url.searchParams.has("league_key")).toBe(false);
    if (url.pathname === "/api/v1/waivers/refresh") {
      if (route.request().method() === "POST") {
        const plan = refreshPlans.shift();
        expect(plan, "an unplanned refresh POST").toBeTruthy();
        [refreshNow, refreshPolls, refreshDone] = [plan!.post, [...plan!.polls], plan!.done];
        await route.fulfill({ status: 202, json: refreshNow });
        return;
      }
      expect(route.request().method()).toBe("GET");
      if (refreshPolls.length) {
        refreshNow = refreshPolls.shift();
        if (!refreshPolls.length) {
          refreshDone?.();
          refreshDone = undefined;
        }
      }
      await route.fulfill({ json: refreshNow });
      return;
    }
    expect(route.request().method()).toBe("GET");
    const mode = url.searchParams.get("mode") ?? "this_week";
    if (url.pathname === "/api/v1/waivers/transactions") {
      if (transactionsError) {
        await failRead(route, transactionsError, "req-504-moves");
        return;
      }
      if (structuredTransactionError) {
        await route.fulfill({ status: 409, json: { detail: {
          message: "Persisted league contract mismatch; waiver analysis blocked",
          mismatches: ["scoring_type: persisted head, expected headpoint", "num_teams: persisted 10, expected 12"],
        } } });
        return;
      }
      const result = transactions(mode);
      if (staleSurface === "transactions") result.model_version = "waiver-availability-phase5";
      await route.fulfill({ json: result });
    } else if (url.pathname.endsWith("/impact")) {
      const dropParam = url.searchParams.get("drop_player_id");
      const selected = dropParam === null ? null : Number(dropParam);
      const comparison = shapes[scenario] === "UNDETERMINED" && selected === null ? null
        : selected === null ? noDrop(scenario === "move" ? "MOVE_TO_IL_THEN_ADD" : "ADD_ONLY", scenario === "move" ? "Injured Center" : null) : drop(selected);
      await route.fulfill({ json: {
        league_key: "478.l.50505", team_key: "478.l.50505.t.9", mode,
        model_version: staleSurface === "impact" ? "waiver-availability-phase5" : VERSION,
        candidate: player(1, "Available Center", comparison), comparison, limitations: [],
      } });
    } else if (url.pathname === "/api/v1/waivers/replacements") {
      const selected = Number(url.searchParams.get("drop_player_id"));
      if (slowSelectedDrop === selected) await new Promise((resolve) => setTimeout(resolve, 500));
      if (failSelectedDrop === selected) {
        await route.fulfill({ status: 503, json: { detail: "Replacement evidence unavailable" } });
        return;
      }
      const result = board(mode, selected, selected === 4 ? [3, 1] : [1, 3]);
      if (staleSurface === "replacements") result.model_version = "waiver-availability-phase5";
      await route.fulfill({ json: result });
    } else if (url.pathname === "/api/v1/waivers") {
      if (boardError) {
        await failRead(route, boardError, "req-504-board");
        return;
      }
      const result = board(mode);
      if (staleSurface === "board") result.model_version = "waiver-availability-phase5";
      await route.fulfill({ json: result });
    } else {
      await route.fulfill({ status: 404, json: { detail: "Unexpected API call" } });
    }
  });
});

test.afterEach(async () => {
  // Page reads are GET-only; the one deliberate mutation is the refresh POST, and only when a test clicks it.
  expect(writes).toEqual(expectedWrites);
});

async function expectNoBlockingOverflow(page: Page) {
  const width = page.viewportSize()!.width;
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
}

async function isOpen(page: Page, selector: string) {
  return page.locator(selector).evaluate((element) => (element as HTMLDetailsElement).open);
}

async function openDropPicker(page: Page) {
  if (!(await isOpen(page, "details.waiver-compare-picker"))) await page.locator("details.waiver-compare-picker > summary").click();
}

async function expectAccessible(page: Page) {
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
}

const section = (page: Page, name: string) => page.locator("section").filter({ has: page.getByRole("heading", { name, exact: true }) });
const HIERARCHY = ["WAIVER DATA IS CURRENT", "TEAM SITUATION", "BEST MOVES RIGHT NOW", "OTHER GOOD OPTIONS", "COMPARE A SPECIFIC DROP", "FULL WAIVER LIST", "ADVANCED EVIDENCE"];

test("ADD ONLY is the focal move, the page follows the decision hierarchy, and details return focus", async ({ page }) => {
  await page.goto("/waivers");
  await expect(page.getByRole("heading", { name: "Waiver Command Center" })).toBeVisible();
  await expect(page.locator(".waiver-heading")).toContainText("Box Score Bully");
  for (const name of HIERARCHY) await expect(page.getByRole("heading", { name, exact: true })).toBeVisible();
  const tops = await Promise.all(HIERARCHY.map((name) => page.getByRole("heading", { name, exact: true }).evaluate((element) => element.getBoundingClientRect().top)));
  expect([...tops].sort((left, right) => left - right)).toEqual(tops);
  const situation = section(page, "TEAM SITUATION");
  await expect(situation).toContainText("1 OPEN ROSTER SPOT — NO DROP REQUIRED");
  await expect(situation.locator(".waiver-need-summary li").first()).toContainText("HIGH");
  await expect(situation.locator(".waiver-need-summary")).not.toContainText("UTIL");
  await expect(situation).toContainText("Evidence freshness");
  await expect(situation.locator(".waiver-stat-grid")).toContainText("Weekly adds used2 of 4 · 2 left");
  await expect(situation.locator(".waiver-stat-grid")).toContainText("Waiver priority4th");
  await expect(page.getByRole("button", { name: "REFRESH WAIVER DATA" })).toHaveCount(1);
  expect(await isOpen(page, "details.waiver-refresh-details")).toBe(false);
  const visibleText = await page.locator("main").innerText();
  expect(visibleText).not.toMatch(/\/api\/|curl|swagger|docker|recent_days|league_key=/i);
  expect(visibleText).not.toMatch(/\bPOST\b/);
  const best = section(page, "BEST MOVES RIGHT NOW");
  const card = best.locator(".waiver-move-card.is-supported");
  await expect(card).toHaveCount(1);
  await expect(card.getByRole("heading", { name: "Available Center", exact: true })).toBeVisible();
  await expect(card.locator(".waiver-action")).toHaveText("ADD ONLY");
  await expect(card.locator(".waiver-move-availability")).toHaveText("UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO");
  await expect(card).toContainText("No drop required");
  await expect(best.getByRole("radio")).toHaveCount(0);
  await expect(best).not.toContainText("DROP:");
  await expect(best).not.toContainText(VERSION);
  if (page.viewportSize()!.width >= 1400) {
    const top = await card.getByRole("heading", { name: "Available Center", exact: true }).evaluate((element) => element.getBoundingClientRect().top);
    expect(top).toBeLessThan(page.viewportSize()!.height);
  }
  for (const selector of ["details.waiver-compare-picker", "details.waiver-full-list", "details.waiver-advanced"]) {
    expect(await isOpen(page, selector)).toBe(false);
  }
  await openDropPicker(page);
  await expect(page.getByRole("radio", { name: /Weak Guard/ })).not.toBeChecked();
  await expect(page.getByRole("radio", { name: /Bench Forward/ })).not.toBeChecked();
  await expect(page.getByRole("heading", { name: "Top 3 replacements" })).toHaveCount(0);
  await expectAccessible(page);
  const opener = card.getByRole("button", { name: "View details: Available Center" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Recommended addition analysis" });
  await expect(dialog.getByRole("button", { name: "Close addition analysis" })).toBeFocused();
  await expect(dialog).toContainText("ADD ONLY comparison (no drop)");
  await expect(dialog).toContainText("no player is dropped");
  await expect(card.locator(".waiver-intent")).toHaveText("STREAM");
  await expect(card).toContainText("Recent form (Yahoo FP/G, look-back): Last 7: 33.1 (3 g) · Last 14: 31.2 (6 g) · Last 30: 27.9 (12 g) · Season: 27.9 (12 g) · Trend: IMPROVING");
  await expect(card.locator(".waiver-verdict")).toHaveText("SUPPORTED ADD");
  const decision = dialog.getByRole("region", { name: "Roster decision for Available Center" });
  await expect(decision).toContainText("WHY: Production: Available Center 32.0 Yahoo FP/G (last 14 days blended with the previous season), +12.00 index points. Net modeled change: +12.00.");
  await expect(decision).toContainText("VERDICTSUPPORTED ADD");
  const formPanel = dialog.getByRole("region", { name: "Form and schedule evidence for Available Center" });
  for (const text of ["RECENT FORM", "LAST 14 DAYS", "6 games · 31.2 Yahoo FP/G · 28.4 MIN", "FORM: IMPROVING", "SEASON EVIDENCE",
    "9 starts · 23.1% usage", "UPCOMING SCHEDULE", "NEXT 14", "58 persisted games", `Recent-sample gate: ${SAMPLE_DETAIL}.`]) {
    await expect(formPanel).toContainText(text);
  }
  expect(await decision.evaluate((element) => element.getBoundingClientRect().top))
    .toBeLessThan(await formPanel.evaluate((element) => element.getBoundingClientRect().top));
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await expectNoBlockingOverflow(page);
});

test("MOVE TO IL, THEN ADD shows both steps and keeps the injured player on the roster", async ({ page }) => {
  scenario = "move";
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.locator(".waiver-move-card .waiver-action")).toHaveText("MOVE TO IL, THEN ADD");
  await expect(best.locator(".waiver-steps li")).toHaveText([
    "Move Injured Center from C to IL. Injured Center stays on your roster; this is not a drop.",
    "Add Available Center to cover C.",
  ]);
  await expect(section(page, "TEAM SITUATION")).toContainText("MOVE INJURED CENTER TO IL TO OPEN A ROSTER SPOT");
  await best.getByRole("button", { name: "View details: Available Center" }).click();
  const dialog = page.getByRole("dialog", { name: "Recommended addition analysis" });
  await expect(dialog).toContainText("MOVE TO IL, THEN ADD comparison");
  await expect(dialog).toContainText("Move Injured Center to IL (that player stays on your roster), then add Available Center. No player is dropped.");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expectNoBlockingOverflow(page);
});

test("two open spots show two distinct supported moves", async ({ page }) => {
  scenario = "two";
  await page.goto("/waivers");
  const cards = section(page, "BEST MOVES RIGHT NOW").locator(".waiver-move-card.is-supported");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0)).toContainText("Best move now");
  await expect(cards.nth(0).locator(".waiver-move-player")).toHaveText("Available Center");
  await expect(cards.nth(1)).toContainText("Also fill open spot 2 of 2");
  await expect(cards.nth(1).locator(".waiver-move-player")).toHaveText("Overall Guard");
  await expect(section(page, "TEAM SITUATION")).toContainText("2 OPEN ROSTER SPOTS — NO DROP REQUIRED");
  await expectNoBlockingOverflow(page);
});

test("optional drop comparison keeps the exact selected drop across modes and in analysis", async ({ page }) => {
  const replacementRequests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/waivers/replacements?")) replacementRequests.push(request.url());
  });
  await page.goto("/waivers");
  await expect(section(page, "COMPARE A SPECIFIC DROP")).toHaveClass(/is-muted/);
  expect(replacementRequests).toEqual([]);
  await openDropPicker(page);
  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByRole("heading", { name: "Top 3 replacements" })).toBeVisible();
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Bench Forward");
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Dropping is optional");
  expect(replacementRequests.some((request) => request.includes("drop_player_id=4"))).toBe(true);
  const nextWeekRequest = page.waitForRequest((request) =>
    request.url().includes("/waivers/replacements?") && request.url().includes("drop_player_id=4") && request.url().includes("mode=next_7_days"));
  await page.getByRole("radio", { name: "Next 7 Days", exact: true }).check();
  await nextWeekRequest;
  await expect(page.getByRole("radio", { name: /Bench Forward/ })).toBeChecked();
  const opener = page.getByRole("button", { name: "Analyze option: Overall Guard" }).first();
  const impactRequest = page.waitForRequest((request) =>
    request.url().includes("/impact?") && request.url().includes("drop_player_id=4") && request.url().includes("mode=next_7_days"));
  await opener.click();
  await impactRequest;
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await expect(dialog).toContainText("Selected drop comparison");
  await expect(dialog).toContainText("drop Bench Forward");
  await expect(dialog.getByRole("button", { name: /Compare dropping/ })).toHaveCount(0);
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await page.locator("details.waiver-full-list > summary").click();
  const region = page.getByRole("region", { name: /Waiver list/ });
  await expect(region).toBeVisible();
  const rows = region.locator("tbody tr");
  await expect(rows.first()).toContainText("Available Center");
  const noDropRequest = page.waitForRequest((request) => request.url().includes("/impact?") && !request.url().includes("drop_player_id"));
  await region.getByRole("button", { name: "Details: Available Center" }).click();
  await noDropRequest;
  await expect(page.getByRole("dialog", { name: "Player impact analysis" })).toContainText("ADD ONLY comparison (no drop)");
  await page.keyboard.press("Escape");
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
});

test("explicit drop: a supported replacement ranks before a higher-net WATCH, the drop stays fixed and details open the exact pair", async ({ page }) => {
  // Real-data regression (2026-11-14): WATCH DeMar DeRozan (+0.847) was listed above the supported Jerami Grant (+0.728).
  scenario = "full";
  const supported = player(3, "Overall Guard", drop(4, 0.728), { recommended_action: "ADD", recommended_action_type: "ADD_DROP",
    roster_decision: "review_replacement", evidence_blockers: [], action_label: "ADD Overall Guard + DROP Bench Forward: Your roster is full." });
  const watch = player(1, "Available Center", drop(4, 0.847));
  const replacementQueries: string[] = [];
  await page.route("**/api/v1/waivers/replacements?**", async (route) => {
    const url = new URL(route.request().url());
    expect(route.request().method()).toBe("GET");
    replacementQueries.push(url.search);
    // The backend's explicit-drop order: supported before WATCH even though the WATCH nets more.
    await route.fulfill({ json: { ...board(url.searchParams.get("mode") ?? "this_week", Number(url.searchParams.get("drop_player_id"))),
      candidates: [supported, watch], best_add_for_team_id: 3, top_measured_candidate_id: 1, selected_player_result: "ADD",
      drop_summary: { drop_player_id: 4, drop_player_name: "Bench Forward", decision: "review_replacement", result: "ADD",
        headline: "SUPPORTED ADD — ADD Overall Guard / DROP Bench Forward, net +0.73 roster-index points.",
        best_valid_replacement_id: 3, watch_candidate_id: null,
        highest_raw_comparison: { candidate_id: 1, player_name: "Available Center", verdict: "WATCH_ONLY", raw_net: 0.847, reconciled_net: 0.847,
          reason: "Sample gate: Available Center 2 games this season and 2 in the last 14 days." } } } });
  });
  await page.route("**/api/v1/waivers/*/impact?**", async (route) => {
    const url = new URL(route.request().url());
    const row = Number(url.pathname.split("/").at(-2)) === 3 ? supported : watch;
    const comparison = drop(Number(url.searchParams.get("drop_player_id")), row.net_improvement as number);
    await route.fulfill({ json: { league_key: "478.l.50505", team_key: "478.l.50505.t.9", mode: url.searchParams.get("mode"),
      model_version: VERSION, candidate: { ...row, comparison }, comparison, limitations: [] } });
  });
  await page.goto("/waivers");
  const compare = section(page, "COMPARE A SPECIFIC DROP");
  await expect(compare).toHaveClass(/is-promoted/);
  await expect(compare.locator('input[name="selected-drop"]:checked')).toHaveCount(0);
  await openDropPicker(page);
  await compare.getByRole("radio", { name: /Bench Forward/ }).check();
  const cards = compare.locator(".waiver-replacement-card");
  await expect(cards).toHaveCount(2);
  await expect(cards.nth(0).locator("h4")).toHaveText("Overall Guard");
  await expect(cards.nth(0).locator(".waiver-verdict")).toHaveText("SUPPORTED ADD");
  await expect(cards.nth(1).locator("h4")).toHaveText("Available Center");
  await expect(cards.nth(1).locator(".waiver-verdict")).toHaveText("WATCH ONLY");
  for (const card of await cards.all()) await expect(card).toContainText("Selected dropBench Forward");
  await expect(compare).toContainText("Each comparison uses only the selected drop: Bench Forward.");
  await expect(compare).toContainText("Ordered by the backend: supported moves first, then WATCH, HOLD and insufficient evidence");
  // The higher-net WATCH is subordinate raw evidence; the supported pair is the answer.
  await expect(compare.locator(".waiver-best-valid")).toHaveText("BEST VALID REPLACEMENT: Overall Guard SUPPORTED ADD");
  await expect(compare.locator(".waiver-raw-comparison .waiver-verdict")).toHaveText("WATCH ONLY");
  await expect(compare).not.toContainText("Top measured option");
  expect(replacementQueries.length).toBeGreaterThan(0);
  expect(replacementQueries.every((search) => search.includes("drop_player_id=4"))).toBe(true);
  const opener = cards.nth(0).getByRole("button", { name: "Analyze option: Overall Guard" });
  const impact = page.waitForRequest((request) => request.url().includes("/waivers/3/impact?") && request.url().includes("drop_player_id=4"));
  await opener.focus();
  await page.keyboard.press("Enter");
  await impact;
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await expect(dialog.getByRole("heading", { name: "Overall Guard: add/drop analysis" })).toBeVisible();
  await expect(dialog).toContainText("Selected drop comparison");
  await expect(dialog).toContainText("Add Overall Guard; drop Bench Forward.");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await expect(compare.getByRole("radio", { name: /Bench Forward/ })).toBeChecked();
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
});

test("compare a specific drop: a rejected raw leader is never the answer; HOLD the drop or name the best valid replacement", async ({ page }) => {
  // Deployed-acceptance regression (2026-11-21): the header named a DO NOT ADD pair "Top measured option" and answered
  // INSUFFICIENT EVIDENCE. Synthetic fixture; the numbers mirror the read-only trace.
  scenario = "full";
  const reason = "Explanation-consistency gate: schedule: Available Center scores 7.7 fewer Yahoo FP/G than the drop (22.6 vs 30.3); "
    + "66 x 22.6 = 1490.9 vs 63 x 30.3 = 1908.3 Yahoo fantasy points (-417.4), so 66 games vs 63 games does not offset the production loss. "
    + "Without the unsupported claim the net is -0.3880.";
  const nameOf = (dropId: number) => dropId === 2 ? "Weak Guard" : "Bench Forward";
  const refuted = (dropId: number) => {
    const comparison = drop(dropId, 1.025611);
    return player(1, "Available Center", { ...comparison,
      explanation: { ...comparison.explanation, consistent: false, reconciled_net: -0.388, blocker: reason } }, {
      recommended_action: "INSUFFICIENT EVIDENCE", recommended_action_type: "INSUFFICIENT_EVIDENCE", verdict: "DO_NOT_ADD",
      verdict_text: `DO NOT ADD — ADD Available Center / DROP ${nameOf(dropId)} shows +1.03 index points, but the schedule claim does not hold.`,
      evidence_blockers: [reason] });
  };
  const other = (dropId: number) => dropId === 2
    ? player(3, "Overall Guard", drop(dropId, 0.41), { recommended_action: "ADD", recommended_action_type: "ADD_DROP", evidence_blockers: [],
      verdict_text: "SUPPORTED ADD — ADD Overall Guard / DROP Weak Guard, net +0.41 roster-index points." })
    : player(3, "Overall Guard", drop(dropId, -1.2), { recommended_action: "PASS", recommended_action_type: "HOLD", evidence_blockers: [] });
  await page.route("**/api/v1/waivers/replacements?**", async (route) => {
    const url = new URL(route.request().url());
    expect(route.request().method()).toBe("GET");
    const dropId = Number(url.searchParams.get("drop_player_id"));
    const name = nameOf(dropId);
    const valid = dropId === 2;
    const rows = [other(dropId), refuted(dropId)];
    await route.fulfill({ json: { ...board(url.searchParams.get("mode") ?? "this_week", dropId), candidates: rows,
      best_add_for_team_id: valid ? 3 : null, top_measured_candidate_id: 1, selected_player_result: valid ? "ADD" : `HOLD ${name}`,
      drop_summary: { drop_player_id: dropId, drop_player_name: name, decision: valid ? "review_replacement" : "keep_on_measured_model",
        result: valid ? "ADD" : `HOLD ${name}`, best_valid_replacement_id: valid ? 3 : null, watch_candidate_id: null,
        headline: valid ? rows[0].verdict_text : `No supported or WATCH replacement exists for DROP ${name}; 1 positive raw model `
          + `comparison did not pass the decision gates (1 DO NOT ADD). Keep ${name} under this model.`,
        highest_raw_comparison: { candidate_id: 1, player_name: "Available Center", verdict: "DO_NOT_ADD", raw_net: 1.025611,
          reconciled_net: -0.388, reason } } } });
  });
  await page.route("**/api/v1/waivers/*/impact?**", async (route) => {
    const url = new URL(route.request().url());
    const dropId = Number(url.searchParams.get("drop_player_id"));
    const row = Number(url.pathname.split("/").at(-2)) === 1 ? refuted(dropId) : other(dropId);
    await route.fulfill({ json: { league_key: "478.l.50505", team_key: "478.l.50505.t.9", mode: url.searchParams.get("mode"),
      model_version: VERSION, candidate: row, comparison: row.comparison, limitations: [] } });
  });
  await page.goto("/waivers");
  const compare = section(page, "COMPARE A SPECIFIC DROP");
  await openDropPicker(page);
  await compare.getByRole("radio", { name: /Bench Forward/ }).check();
  // A: no favorable "top" wording for the rejected pair; the answer is HOLD the selected drop.
  const answer = compare.locator(".waiver-drop-answer");
  await expect(answer.locator(".waiver-outcome")).toHaveText("HOLD Bench Forward");
  await expect(answer).toContainText("No supported or WATCH replacement exists for DROP Bench Forward");
  await expect(compare).not.toContainText("Top measured option");
  await expect(answer.locator(".waiver-best-valid")).toHaveCount(0);
  // B: the rejected comparison stays visible below the answer, with its verdict, both nets and the rejection reason.
  const raw = answer.locator(".waiver-raw-comparison");
  await expect(raw).toContainText("HIGHEST RAW MODEL COMPARISON — not a recommendation");
  await expect(raw.locator(".waiver-verdict")).toHaveText("DO NOT ADD");
  await expect(raw).toContainText("Raw net+1.03 index points");
  await expect(raw).toContainText("Reconciled net-0.39 index points");
  await expect(raw).toContainText(`Why it is not the answer: ${reason}`);
  // D: the selected drop stays fixed on every card.
  const cards = compare.locator(".waiver-replacement-card");
  await expect(cards).toHaveCount(2);
  for (const card of await cards.all()) await expect(card).toContainText("Selected dropBench Forward");
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
  // E + F: Analyze opens exactly the displayed pair; closing returns keyboard focus to the same button.
  const opener = raw.getByRole("button", { name: "Analyze ADD Available Center / DROP Bench Forward" });
  const impact = page.waitForRequest((request) => request.url().includes("/waivers/1/impact?") && request.url().includes("drop_player_id=4"));
  await opener.focus();
  await page.keyboard.press("Enter");
  await impact;
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await expect(dialog).toContainText("Add Available Center; drop Bench Forward.");
  await expect(dialog.locator(".waiver-verdict").first()).toHaveText("DO NOT ADD");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(opener).toBeFocused();
  await expect(compare.getByRole("radio", { name: /Bench Forward/ })).toBeChecked();
  // C: when a supported pair exists for the selected drop it is the BEST VALID REPLACEMENT, above the raw comparison.
  await compare.getByRole("radio", { name: /Weak Guard/ }).check();
  await expect(answer.locator(".waiver-outcome")).toHaveText("ADD");
  await expect(answer.locator(".waiver-best-valid")).toHaveText("BEST VALID REPLACEMENT: Overall Guard SUPPORTED ADD");
  await expect(raw.locator("p strong").first()).toHaveText("Available Center");
  await expect(raw.getByRole("button", { name: "Analyze ADD Available Center / DROP Weak Guard" })).toBeVisible();
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
});

test("a pending older drop selection cannot replace the newer selection result", async ({ page }) => {
  await page.goto("/waivers");
  slowSelectedDrop = 4;
  await openDropPicker(page);
  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByRole("status").filter({ hasText: "Loading replacements" })).toBeVisible();
  await page.getByRole("radio", { name: /Weak Guard/ }).check();
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Weak Guard");
  await expect(page.locator(".waiver-replacement-card").first()).not.toContainText("Bench Forward");
});

test("full roster promotes the exact ADD + DROP pair and read errors never become HOLD", async ({ page }) => {
  scenario = "full";
  boardPair = [1, 4];
  await page.route("**/api/v1/waivers/transactions?**", (route) => route.fulfill({ json: {
    ...transactions(), decision: "ADD", recommended_action_type: "ADD_DROP",
    action_label: "ADD Available Center + DROP Bench Forward: Your roster is full.",
    // The backend attaches the pair-specific add row to a supported transaction (decision ADD, verdict SUPPORTED ADD).
    best_transaction: { ...swap(), decision: "ADD", add_player: { ...swap().add_player, verdict: "SUPPORTED_ADD", recommended_action: "ADD",
      recommended_action_type: "ADD_DROP", evidence_blockers: [] } },
  } }));
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("heading", { name: "ADD: Available Center", exact: true })).toBeVisible();
  await expect(best).toContainText("DROP: Bench Forward");
  await expect(best.locator(".waiver-verdict")).toHaveText("SUPPORTED ADD");
  await best.locator("details").filter({ hasText: "Exact calculation, risks and role evidence" }).locator("summary").first().click();
  await expect(best.locator(".waiver-contrib-table")).toContainText("roster fit");
  await expect(best).toContainText("Add Yahoo status: Q · drop status: NO CURRENT YAHOO DESIGNATION. Q/P remains uncertain.");
  await expect(best).toContainText(NO_DESIGNATION_DETAIL);
  await expect(best).not.toContainText(/HEALTHY|\bhealthy\b|CLEARED|NO INJURY/);
  await expectNoBlockingOverflow(page);
  await expect(section(page, "TEAM SITUATION")).toContainText("ROSTER FULL — AN ADD REQUIRES A DROP");
  await expect(section(page, "COMPARE A SPECIFIC DROP")).toHaveClass(/is-promoted/);
  expect(await isOpen(page, "details.waiver-compare-picker")).toBe(true);
  await expect(page.getByRole("radio", { name: /Weak Guard/ })).not.toBeChecked();
  await best.getByRole("button", { name: "View details: ADD Available Center / DROP Bench Forward" }).click();
  const dialog = page.getByRole("dialog", { name: "Supported transaction analysis" });
  await expect(dialog).toContainText("hypothetical ADD Available Center / DROP Bench Forward");
  await expect(dialog).toContainText("drop Bench Forward");
  await expect(dialog.getByRole("region", { name: "Form and schedule evidence for Bench Forward" })).toContainText("Form windows were not returned for this player.");
  expect(await dialog.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  // Real-data regression (Next 7 Days): the board named a different pair than the optimizer; now it fails closed.
  boardPair = [1, 2];
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(best.getByText("the waiver board and the best-move analysis name different supported ADD + DROP pairs", { exact: false })).toBeVisible();
  await expect(best.getByRole("heading", { name: "ADD: Available Center", exact: true })).toHaveCount(0);
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  boardPair = [1, 4];
  await page.route("**/api/v1/waivers/transactions?**", (route) => route.fulfill({ status: 409, json: { detail: "Persisted contract mismatch" } }));
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByText("Persisted contract mismatch", { exact: false })).toBeVisible();
  await expect(page.getByText(/this error is not a HOLD decision/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
});

test("expanded team-situation details scroll their tables inside the panel instead of widening the page", async ({ page }) => {
  // Real deployed-page finding (2026-11-14): at 390 px, opening "Why? Roster capacity details" widened the page to 589 px.
  scenario = "full";
  await page.goto("/waivers");
  const situation = section(page, "TEAM SITUATION");
  await expect(situation).toContainText("ROSTER FULL — AN ADD REQUIRES A DROP");
  for (const summary of await situation.locator(".waiver-situation-more > details > summary").all()) await summary.click();
  await expect(situation.locator(".waiver-situation-more > details[open]")).toHaveCount(2);
  await expect(situation.locator(".waiver-table-scroll").first()).toBeVisible();
  await expectNoBlockingOverflow(page);
});

test("WATCH stays separate from a HOLD with open capacity", async ({ page }) => {
  scenario = "hold_watch";
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toBeVisible();
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  const options = section(page, "OTHER GOOD OPTIONS");
  await expect(options.getByRole("heading", { name: "WATCHLIST" })).toBeVisible();
  // Titles are the backend's, qualified by each pick's verdict: "best" never implies a supported add.
  for (const title of ["BEST AVAILABLE GUARD — cannot evaluate yet", "BEST AVAILABLE WING / FORWARD — cannot evaluate yet", "BEST AVAILABLE CENTER",
    "BEST AVAILABLE MULTI-POSITION OPTION", "BEST AVAILABLE SHORT-TERM SCHEDULE OPTION", "BEST AVAILABLE LONGER-TERM OPTION"]) {
    await expect(options.getByRole("heading", { name: title, exact: true })).toBeVisible();
  }
  const watch = options.locator(".waiver-option-list");
  await expect(watch).toContainText("Available Center");
  await expect(watch).toContainText("Positive measured impact, but the sample is too small");
  await expect(watch.locator(".waiver-verdict")).toHaveText("WATCH ONLY");
  await watch.getByRole("button", { name: "View details: Available Center" }).click();
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await expect(dialog).toContainText("Positive measured impact, but the sample is too small");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expectNoBlockingOverflow(page);
});

test("undetermined capacity names a best measured option, never a supported add", async ({ page }) => {
  scenario = "undetermined";
  await page.goto("/waivers");
  const situation = section(page, "TEAM SITUATION");
  await expect(situation).toContainText("ROSTER CAPACITY NEEDS A YAHOO REFRESH");
  await expect(situation).toContainText("Yahoo roster slots are not saved for 13 of 13 players");
  expect(await situation.locator("details.waiver-details").first().evaluate((element) => (element as HTMLDetailsElement).open)).toBe(false);
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best).toContainText("No supported move yet: Your saved roster is from 2026-10-25");
  const card = best.locator(".waiver-move-card.is-measured");
  await expect(card.getByRole("heading", { name: "Measured Guard", exact: true })).toBeVisible();
  if (page.viewportSize()!.width >= 1400) {
    const top = await card.getByRole("heading", { name: "Measured Guard", exact: true }).evaluate((element) => element.getBoundingClientRect().top);
    expect(top).toBeLessThan(page.viewportSize()!.height);
  }
  for (const text of ["BEST MEASURED OPTION", "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO", "NOT YET A SUPPORTED ADD", `Yahoo status: UNKNOWN. ${BLANK}`,
    "Free-agent or waiver state in Yahoo", "Whether you have an open roster spot", "CHECK IN YAHOO", "PG / SG"]) {
    await expect(card).toContainText(text);
  }
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expect(best.locator(".waiver-move-card.is-supported")).toHaveCount(0);
  await expect(best).not.toContainText("DROP:");
  const options = section(page, "OTHER GOOD OPTIONS");
  await expect(options.locator("section.waiver-potential")).toHaveCount(0);
  await expect(options.locator(".waiver-option-grid")).toContainText("Group Wing");
  await expectAccessible(page);
  const opener = card.getByRole("button", { name: "View details: Measured Guard" });
  await opener.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("button", { name: "Close analysis" })).toBeFocused();
  await expect(dialog).toContainText("Why this is not a supported add");
  await expect(dialog).toContainText("Measured production");
  await expectAccessible(page);
  await page.keyboard.press("Escape");
  await expect(opener).toBeFocused();
  await expectNoBlockingOverflow(page);
});

test("when nothing can be compared the page explains exactly why instead of showing HOLD", async ({ page }) => {
  scenario = "unavailable";
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("heading", { name: "INSUFFICIENT EVIDENCE", exact: true })).toBeVisible();
  await expect(best).toContainText("No player can be compared yet.");
  await expect(best).toContainText("No current-season NBA games: 82");
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  await page.locator("details.waiver-full-list > summary").click();
  await expect(section(page, "FULL WAIVER LIST")).toContainText("No available or availability-unverified players can be listed");
  await expectAccessible(page);
  await expectNoBlockingOverflow(page);
});

test("model-version mismatch blocks only the affected decision surface", async ({ page }) => {
  staleSurface = "transactions";
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("alert")).toContainText("does not match this page version");
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "TEAM SITUATION" })).toBeVisible();
  staleSurface = "board";
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.getByText(/Stale deployed version: waiver-availability-phase5/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "TEAM SITUATION" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "OTHER GOOD OPTIONS" })).toHaveCount(0);
});

test("stale replacement and impact responses cannot expose decision-ready advice", async ({ page }) => {
  staleSurface = "replacements";
  await page.goto("/waivers");
  await openDropPicker(page);
  await page.getByRole("radio", { name: /Weak Guard/ }).check();
  await expect(page.locator(".waiver-compare").getByRole("alert")).toContainText("incompatible model waiver-availability-phase5");
  await expect(page.locator(".waiver-replacement-card")).toHaveCount(0);
  staleSurface = "impact";
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await section(page, "OTHER GOOD OPTIONS").getByRole("button", { name: "View details: Measured Wing" }).click();
  const dialog = page.getByRole("dialog", { name: "Player impact analysis" });
  await expect(dialog.getByRole("alert")).toContainText("incompatible model waiver-availability-phase5");
  await expect(dialog.getByText("Available Center: add analysis")).toHaveCount(0);
});

test("structured 409 settings mismatch stays an accessible error, never HOLD", async ({ page }) => {
  structuredTransactionError = true;
  await page.goto("/waivers");
  const alert = page.getByRole("alert").filter({ hasText: "Persisted league contract mismatch" });
  await expect(alert).toContainText("Persisted league contract mismatch; waiver analysis blocked");
  await expect(alert).toContainText("scoring_type: persisted head, expected headpoint");
  await expect(alert).toContainText("num_teams: persisted 10, expected 12");
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
});

test("replacement errors and base errors are accessible and recover on reload", async ({ page }) => {
  await page.goto("/waivers");
  failSelectedDrop = 4;
  await openDropPicker(page);
  await page.getByRole("radio", { name: /Bench Forward/ }).check();
  await expect(page.getByText("Replacement evidence unavailable", { exact: false })).toBeVisible();
  await expect(page.locator(".waiver-replacement-card")).toHaveCount(0);
  failSelectedDrop = null;
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(page.locator(".waiver-replacement-card").first()).toContainText("Bench Forward");
  await page.route("**/api/v1/waivers?**", (route) => route.fulfill({ status: 503, json: { detail: "Persisted evidence unavailable" } }));
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  const situation = section(page, "TEAM SITUATION");
  await expect(situation.getByRole("alert")).toContainText("WAIVER ANALYSIS UNAVAILABLE");
  await expect(situation).toContainText("Persisted evidence unavailable");
  await expect(situation).not.toContainText("OPEN ROSTER SPOT");
  await expect(section(page, "BEST MOVES RIGHT NOW")).toContainText("Best moves are withheld");
  await expect(page.locator(".waiver-move-card")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "OTHER GOOD OPTIONS" })).toHaveCount(0);
});

test("mode controls stay available, Pacific window is explicit, and saved targets cannot override manager", async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem("team_key", "478.l.50505.t.1");
    localStorage.setItem("league_key", "other.league");
  });
  const responsePromise = page.waitForResponse((response) => response.url().includes("/api/v1/waivers?"));
  await page.goto("/waivers?league_key=other.league&team_key=478.l.50505.t.1");
  const response = await responsePromise;
  expect(new URL(response.url()).searchParams.get("mode")).toBe("this_week");
  expect(await response.json()).toMatchObject({ league_key: "478.l.50505", team_key: "478.l.50505.t.9" });
  await expect(page.getByText(/Rest of Week · limited days remaining/)).toBeVisible();
  await expect(page.getByText(/today through today \+ 6/)).toHaveCount(0);
  const horizons = page.getByRole("group", { name: "Analysis window" }).getByRole("radio");
  await expect(horizons).toHaveCount(4);
  for (const name of ["Rest of Week", "Next 7 Days", "Next 14 Days", "Rest of Season Outlook"]) {
    await expect(page.getByRole("radio", { name, exact: true })).toBeVisible();
  }
  const next14 = page.waitForRequest((request) => request.url().includes("/api/v1/waivers?") && request.url().includes("mode=next_14_days"));
  const next14Moves = page.waitForRequest((request) => request.url().includes("/waivers/transactions?") && request.url().includes("mode=next_14_days"));
  await page.getByRole("radio", { name: "Next 14 Days", exact: true }).check();
  await Promise.all([next14, next14Moves]);
  await expect(page.getByText(/today through today \+ 13 in Pacific Time \(a forward schedule window, not Last 14 Days form\)/)).toBeVisible();
  await expect(section(page, "BEST MOVES RIGHT NOW")).toContainText("Next 14 Days · analysis only");
  await expect(page.locator(".waiver-heading")).not.toContainText("My Team");
});

test("one REFRESH WAIVER DATA click runs the whole refresh with stage progress, then reloads the board", async ({ page }) => {
  scenario = "stale";
  refreshNow = refreshStatus(STALE_STAGES);
  refreshPlans = [{
    post: refreshStatus(STALE_STAGES, refreshJob(["RUNNING"])),
    polls: [refreshStatus(STALE_STAGES, refreshJob(["SUCCEEDED", "SUCCEEDED", "SUCCEEDED", "SUCCEEDED", "SUCCEEDED", "RUNNING"])),
      refreshStatus([], finishedJob("SUCCEEDED"))],
    done: () => { scenario = "add_only"; },
  }];
  expectedWrites = ["POST /api/v1/waivers/refresh"];
  let boardReads = 0;
  page.on("request", (request) => { if (new URL(request.url()).pathname === "/api/v1/waivers") boardReads += 1; });
  await page.goto("/waivers");
  const panel = page.locator("section.waiver-refresh");
  await expect(panel.getByRole("heading", { name: "WAIVER DATA NEEDS A REFRESH" })).toBeVisible();
  await expect(panel).toContainText("Stale or missing: Yahoo rosters, Roster slots, Yahoo availability and status, NBA game logs.");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("heading", { name: "NO CONFIRMED AVAILABLE PLAYER" })).toBeVisible();
  await expect(page.getByRole("button", { name: "REFRESH WAIVER DATA" })).toHaveCount(1);
  await expectAccessible(page);
  const readsBefore = boardReads;
  const button = panel.getByRole("button", { name: "REFRESH WAIVER DATA" });
  await button.focus();
  const post = page.waitForRequest((request) => request.method() === "POST");
  await page.keyboard.press("Enter");
  expect((await post).postDataJSON()).toEqual({ retry_failed: false });
  await expect(panel.getByRole("heading", { name: "REFRESHING WAIVER DATA" })).toBeVisible();
  await expect(panel.getByRole("button", { name: "REFRESHING…" })).toBeDisabled();
  await expect(panel.getByRole("group", { name: "Refresh progress by source" })).toBeFocused();
  await expect(panel.locator(".waiver-refresh-stages li")).toHaveCount(10);
  await expect(panel.locator(".waiver-refresh-stages li.is-running")).toContainText("Yahoo league/settings");
  await expectAccessible(page);
  await expectNoBlockingOverflow(page);
  await expect(panel.locator(".waiver-refresh-stages li.is-running")).toContainText("NBA teams and players");
  await expect(panel.locator(".waiver-refresh-stages li.is-succeeded").first()).toContainText("Updated — Bully League · 12 teams");
  await expect(panel.getByRole("button", { name: "REFRESHING…" })).toBeDisabled();
  await expect(panel.getByRole("heading", { name: "WAIVER DATA IS CURRENT" })).toBeVisible({ timeout: 15_000 });
  await expect(panel.getByRole("status")).toHaveText("Waiver data refreshed and verified. The waiver board was reloaded.");
  await expect(best.locator(".waiver-move-card.is-supported .waiver-move-player")).toHaveText("Available Center");
  expect(boardReads).toBeGreaterThan(readsBefore);
  await expect(panel.getByRole("button", { name: "REFRESH WAIVER DATA" })).toBeFocused();
  await expect(panel).toContainText(/Last successful complete refresh: November 13, 2026(,| at) 7:42\sPM PST/);
  await expectAccessible(page);
});

test("a partial failure names the failed NBA stage, keeps the Yahoo update, and RETRY FAILED STAGE reruns only that source", async ({ page }) => {
  scenario = "stale";
  refreshNow = refreshStatus(STALE_STAGES);
  const nbaStale = ["NBA_GAME_LOGS", "NBA_SEASON_STATS"];
  const skipped: StageState[] = ["SKIPPED", "SKIPPED", "SKIPPED", "SKIPPED", "SKIPPED", "RUNNING"];
  refreshPlans = [
    { post: refreshStatus(STALE_STAGES, refreshJob(["RUNNING"])), polls: [refreshStatus(nbaStale, finishedJob("PARTIAL_FAILURE"))],
      done: () => { scenario = "full"; } },
    { post: refreshStatus(nbaStale, refreshJob(skipped, { job_id: "job-2", scope: "FAILED_STAGES", retry_of: "job-1" })),
      polls: [refreshStatus([], finishedJob("SUCCEEDED", { job_id: "job-2", scope: "FAILED_STAGES", retry_of: "job-1" }))],
      done: () => { scenario = "add_only"; } },
  ];
  expectedWrites = ["POST /api/v1/waivers/refresh", "POST /api/v1/waivers/refresh"];
  await page.goto("/waivers");
  const panel = page.locator("section.waiver-refresh");
  await panel.getByRole("button", { name: "REFRESH WAIVER DATA" }).click();
  await expect(panel.getByRole("heading", { name: "REFRESH PARTIALLY COMPLETED" })).toBeVisible({ timeout: 15_000 });
  await expect(panel).toContainText("Yahoo roster data updated successfully.");
  await expect(panel).toContainText("NBA game logs failed. The NBA statistics source did not return usable data. The previous NBA snapshot was kept.");
  await expect(panel).not.toContainText("NBA data updated successfully");
  await expect(panel.locator(".waiver-refresh-stages li.is-failed")).toHaveCount(1);
  await expect(panel.locator(".waiver-refresh-stages li.is-failed")).toContainText("NBA game logs");
  await expect(panel.getByRole("status")).toHaveText("Refresh partially completed. Successful sources were saved; failed sources are listed.");
  await expect(section(page, "TEAM SITUATION")).toContainText("ROSTER FULL — AN ADD REQUIRES A DROP");
  await expectAccessible(page);
  await expectNoBlockingOverflow(page);
  const post = page.waitForRequest((request) => request.method() === "POST");
  await panel.getByRole("button", { name: "RETRY FAILED STAGE" }).click();
  expect((await post).postDataJSON()).toEqual({ retry_failed: true });
  await expect(panel.locator(".waiver-refresh-stages li.is-skipped").first()).toContainText("Not rerun: this source succeeded in the previous refresh.");
  await expect(panel.getByRole("button", { name: "RETRY FAILED STAGE" })).toHaveCount(0);
  await expect(panel.getByRole("heading", { name: "WAIVER DATA IS CURRENT" })).toBeVisible({ timeout: 15_000 });
  await expect(section(page, "BEST MOVES RIGHT NOW").locator(".waiver-move-card.is-supported")).toHaveCount(1);
});

test("an nginx HTML 504 shows WAIVER ANALYSIS TIMED OUT with retry and refresh actions, never the HTML, and RETRY ANALYSIS recovers", async ({ page }) => {
  boardError = "html504";
  transactionsError = "html504";
  await page.goto("/waivers");
  const situation = section(page, "TEAM SITUATION");
  const best = section(page, "BEST MOVES RIGHT NOW");
  for (const [surface, requestId] of [[situation, "req-504-board"], [best, "req-504-moves"]] as const) {
    await expect(surface.getByRole("alert")).toContainText("WAIVER ANALYSIS TIMED OUT");
    await expect(surface).toContainText("The saved data was not changed. Retry the analysis, or refresh the evidence if its timestamps are stale.");
    await expect(surface).toContainText(`this error is not a HOLD decision. Request ID: ${requestId}.`);
    await expect(surface.getByRole("button", { name: "RETRY ANALYSIS" })).toBeVisible();
    await expect(surface.getByRole("button", { name: "REFRESH WAIVER DATA" })).toBeVisible();
  }
  expect(await page.locator("main").innerText()).not.toMatch(/nginx|Gateway Time-out|<center>|<html|MSIE|padding to disable/i);
  expect(await page.locator("main").innerHTML()).not.toMatch(/<center>|<hr>|nginx\//);
  await expect(page.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expect(page.locator(".waiver-move-card")).toHaveCount(0);
  await expectAccessible(page);
  await expectNoBlockingOverflow(page);
  boardError = null;
  transactionsError = null;
  const retry = situation.getByRole("button", { name: "RETRY ANALYSIS" });
  await retry.focus();
  await page.keyboard.press("Enter");
  await expect(best.locator(".waiver-move-card.is-supported .waiver-move-player")).toHaveText("Available Center");
  await expect(page.getByText("WAIVER ANALYSIS TIMED OUT")).toHaveCount(0);
  await expect(section(page, "TEAM SITUATION")).toContainText("1 OPEN ROSTER SPOT — NO DROP REQUIRED");
});

test("a read error removes the earlier supported move, and the error's REFRESH WAIVER DATA starts the single refresh", async ({ page }) => {
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.locator(".waiver-move-card.is-supported")).toHaveCount(1);
  transactionsError = "network";
  await page.getByRole("button", { name: "Reload persisted evidence" }).click();
  await expect(best.getByRole("alert")).toContainText("WAIVER ANALYSIS UNAVAILABLE");
  await expect(best).toContainText("Could not reach the server. Check the connection, then retry.");
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  await expect(best).not.toContainText("Available Center");
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  refreshPlans = [{ post: refreshStatus([], refreshJob(["RUNNING"])), polls: [refreshStatus([], finishedJob("SUCCEEDED"))],
    done: () => { transactionsError = null; } }];
  expectedWrites = ["POST /api/v1/waivers/refresh"];
  const post = page.waitForRequest((request) => request.method() === "POST");
  await best.getByRole("button", { name: "REFRESH WAIVER DATA" }).click();
  expect((await post).postDataJSON()).toEqual({ retry_failed: false });
  const panel = page.locator("section.waiver-refresh");
  await expect(panel.getByRole("heading", { name: "REFRESHING WAIVER DATA" })).toBeVisible();
  await expect(panel.getByRole("heading", { name: "WAIVER DATA IS CURRENT" })).toBeVisible({ timeout: 15_000 });
  await expect(best.locator(".waiver-move-card.is-supported")).toHaveCount(1);
});

test("with stale league rosters nobody is featured: unverified players are a separate potential-target list and rostered players never appear", async ({ page }) => {
  scenario = "stale";
  refreshNow = refreshStatus(STALE_STAGES);
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("heading", { name: "NO CONFIRMED AVAILABLE PLAYER" })).toBeVisible();
  await expect(best).toContainText("No player is confirmed available yet.");
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  const options = section(page, "OTHER GOOD OPTIONS");
  const potential = options.locator("section.waiver-potential");
  await expect(potential.getByRole("heading", { name: "POTENTIAL TARGETS TO CHECK IN YAHOO" })).toBeVisible();
  await expect(potential).toContainText("Potential Forward");
  await expect(potential).toContainText("SAVED ROSTERS STALE — CHECK IN YAHOO");
  expect(await potential.evaluate((element) => getComputedStyle(element).borderTopStyle)).toBe("dashed");
  await expect(options.locator(".waiver-option-grid")).not.toContainText("Potential Forward");
  await expect(options.locator(".waiver-option-list")).toHaveCount(0);
  await expect(page.locator("main")).not.toContainText("Rostered Elsewhere Guard");
  await page.locator("details.waiver-full-list > summary").click();
  const list = section(page, "FULL WAIVER LIST");
  await expect(list).toContainText("Show all 2 players (0 unrostered in every current league roster · 2 availability unverified)");
  await expect(list.locator("tbody tr").first()).toContainText("List group: POTENTIAL TARGET");
  await expect(list).not.toContainText("Rostered Elsewhere Guard");
  await expectAccessible(page);
  await expectNoBlockingOverflow(page);
});

test("a featured move missing from the eligible-candidate map shows a contract error instead of the card", async ({ page }) => {
  withheldEligibleId = 1;
  await page.goto("/waivers");
  const best = section(page, "BEST MOVES RIGHT NOW");
  await expect(best.getByRole("alert")).toContainText("WAIVER MODEL CONTRACT ERROR");
  await expect(best).toContainText("A recommendation for Available Center was withheld because the player is not in the current waiver-eligible candidate set.");
  await expect(best.locator(".waiver-move-card")).toHaveCount(0);
  await expect(best.getByRole("heading", { name: "HOLD", exact: true })).toHaveCount(0);
  await expectAccessible(page);
});

test("full-roster OTHER GOOD OPTIONS give every pick a verdict and its exact drop, and fit the desktop page", async ({ page }) => {
  // 2026-11-21 audit (WC-07/WC-08/WC-12): full-roster options named no drop, and "best" read as a recommendation.
  scenario = "full";
  const refuted = "Explanation gate: schedule: 4 x 20.0 = 80.0 vs 3 x 30.0 = 90.0 window Yahoo fantasy points; the extra game does not offset the lower production.";
  const pair = (dropId: number, dropName: string, net: number, tweaks: Record<string, unknown> = {}) => ({
    comparison_type: "ADD_DROP", drop_player_id: dropId, drop_player_name: dropName, net, add_ppg: 20, drop_ppg: 18,
    basis_label: "Last 14 days blended with 2025-26 (83% previous season): mostly previous-season evidence",
    add_games: 3, drop_games: 2, window_points_gap: 24, starting_slots_before: 3, starting_slots_after: 3, starting_slots_required: 2,
    statement: "", primary_reason: "Production: 20.0 vs 18.0 Yahoo FP/G, +0.41 index points", primary_tradeoff: null, blocker: null,
    consistent: true, near_tie: false, alternatives: [], drop_choice: "", ...tweaks,
  });
  const support = { ...decisionSupport("full"), state: "WATCH", supported_count: 0,
    headline: "No supported move; each option below carries its own verdict.",
    groups: groups({ BEST_GUARD: 3, BEST_WING_FORWARD: 5, BEST_CENTER: 1 }, { 1: "WATCH_ONLY", 3: "DO_NOT_ADD", 5: "CANNOT_EVALUATE" }),
    options: [
      option(1, "Available Center", { positions: "C", classification: "WATCH", action_type: "WATCH", current_season_games: 2,
        pair: pair(4, "Bench Forward", .41, { blocker: "Sample gate: Available Center 2 games in the last 14 days.",
          alternatives: [{ player_id: 2, player_name: "Weak Guard", net: .2, margin: .21, consistent: true, near_tie: false, note: "" }],
          drop_choice: "Bench Forward gives the highest measured net (+0.41); next best drop Weak Guard +0.20 (+0.21 behind)." }) }),
      option(3, "Overall Guard", { verdict: "DO_NOT_ADD", headline: "DO NOT ADD — Overall Guard / drop Weak Guard shows +1.03 index points, but its schedule edge does not hold.",
        pair: pair(2, "Weak Guard", 1.03, { add_ppg: 20, drop_ppg: 30, add_games: 4, drop_games: 3, window_points_gap: -10, consistent: false,
          blocker: refuted, primary_reason: "No component improves the roster index." }) }),
      option(5, "Measured Wing", { positions: "SF,PF", blockers: ["Current-season sample is 3 games; supported adds need at least 7."] }),
    ] };
  await page.route((url) => url.pathname === "/api/v1/waivers", async (route) => {
    const mode = new URL(route.request().url()).searchParams.get("mode") ?? "this_week";
    await route.fulfill({ json: { ...board(mode), decision_support: support } });
  });
  await page.goto("/waivers");
  const options = section(page, "OTHER GOOD OPTIONS");
  const card = (title: string) => options.locator(".waiver-option-card").filter({ has: page.getByRole("heading", { name: title, exact: true }) });
  const center = card("BEST AVAILABLE CENTER TO MONITOR — not a supported add");
  await expect(center.locator(".waiver-verdict")).toHaveText("WATCH ONLY");
  await expect(center).toContainText("Best compatible drop (comparison only)Bench Forward");
  await expect(center).toContainText("Net (exact pair)+0.41 index points");
  await expect(center).toContainText("Yahoo FP/G (same basis)Add 20.0 · drop 18.0");
  await expect(center).toContainText("Primary blocker: Sample gate: Available Center 2 games in the last 14 days.");
  await expect(center).toContainText("2-GAME SAMPLE — WATCH ONLY");
  await center.locator("details.waiver-why-drop > summary").click();
  await expect(center.locator("details.waiver-why-drop")).toContainText("Weak Guard: +0.20 index points (0.21 behind)");
  const guard = card("BEST AVAILABLE GUARD — do not add: no supported positive swap");
  await expect(guard.locator(".waiver-verdict")).toHaveText("DO NOT ADD");
  await expect(guard).toContainText("Best compatible drop (comparison only)Weak Guard");
  await expect(guard).toContainText(`Primary blocker: ${refuted}`);
  const wing = card("BEST AVAILABLE WING / FORWARD — cannot evaluate yet");
  await expect(wing.locator(".waiver-verdict")).toHaveText("CANNOT EVALUATE");
  await expect(wing).toContainText("No supported drop: Current-season sample is 3 games; supported adds need at least 7.");
  await expect(options).not.toContainText("Which roster player you would drop");
  const badge = (locator: ReturnType<typeof page.locator>) => locator.locator(".waiver-verdict").evaluate((element) => {
    const style = getComputedStyle(element);
    return `${style.backgroundColor} ${style.borderTopStyle}`;
  });
  const styles = [await badge(center), await badge(guard), await badge(wing)];
  expect(new Set(styles).size).toBe(3);
  for (const style of styles) expect(style).not.toContain("rgb(31, 107, 79)");
  await options.locator("details").filter({ hasText: "Measured index and blockers" }).locator("summary").first().click();
  await expect(options.locator(".waiver-contrib-table").first()).toContainText("Sum = net");
  for (const item of await options.locator(".waiver-option-card").all()) {
    expect(await item.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
  }
  await expectNoBlockingOverflow(page);
  await expectAccessible(page);
});

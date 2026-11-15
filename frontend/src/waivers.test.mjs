import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ts from "typescript";

const require = createRequire(import.meta.url);
const source = readFileSync(new URL("./WaiverCenter.tsx", import.meta.url), "utf8");
const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const api = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const apiOutput = ts.transpileModule(api, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const output = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022 },
}).outputText;
const VERSION = "waiver-horizon-evidence-phase6";
const TWO_WEEK = "Two-week move supported by current production, role, roster impact, and persisted Next 14 Days schedule evidence.";

function load(states = []) {
  let index = 0;
  const exports = {};
  const loader = (name) => name === "./api" ? { api: {} } : name === "react" && states.length
    ? { ...React, useState: (initial) => [index < states.length ? states[index++] : initial, () => {}], useEffect: () => {} }
    : name === "react-router-dom" ? { Link: ({ to, children }) => React.createElement("a", { href: to }, children) }
      : require(name);
  new Function("require", "exports", output)(loader, exports);
  return exports;
}

function loadApi() {
  const exports = {};
  new Function("require", "exports", apiOutput)(require, exports);
  return exports;
}

const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const escaped = (text) => text.replaceAll("'", "&#x27;");
const components = { roster_fit: 72, player_value: 70, opportunity: 60, schedule: 80, acquisition_value: null };
const evidence = { state: "partial", source: "Persisted NBA", as_of: "2026-10-25T00:00:00Z", detail: "Partial schedule and coverage." };
const UNROSTERED = "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT";
const LABELS = {
  CONFIRMED_FA: "FREE AGENT (YAHOO)", CONFIRMED_WAIVER: "ON WAIVERS (YAHOO)",
  [UNROSTERED]: "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO",
  ROSTERED_BY_OTHER_TEAM: "ROSTERED BY ANOTHER TEAM", ROSTERED_BY_MANAGER: "ON YOUR ROSTER",
  AVAILABILITY_UNVERIFIED: "AVAILABILITY UNVERIFIED", EXCLUDED_STATUS: "EXCLUDED (YAHOO O/OFS/NA)",
  SOURCE_STALE: "SAVED ROSTERS STALE — CHECK IN YAHOO",
};
const ACTIONABLE = new Set(["CONFIRMED_FA", "CONFIRMED_WAIVER", UNROSTERED]);
const availabilityEvidence = (classification = UNROSTERED, tweaks = {}) => ({
  classification, label: LABELS[classification], actionable: ACTIONABLE.has(classification),
  source: "Yahoo league rosters and player pool", imported_at: "2026-11-14T05:00:00Z",
  roster_snapshot_complete: classification !== "SOURCE_STALE", roster_snapshots_current: classification === "SOURCE_STALE" ? 1 : 12,
  roster_snapshots_expected: 12, yahoo_ownership_state: classification === "CONFIRMED_FA" ? "FA" : classification === "CONFIRMED_WAIVER" ? "W" : null,
  waiver_clear_date: classification === "CONFIRMED_WAIVER" ? "2026-11-15" : null,
  eligibility_reason: ACTIONABLE.has(classification) ? "Absent from all 12 current league rosters." : null,
  blockers: [], detail: "Persisted Yahoo availability evidence.", ...tweaks,
});
const roleWindow = (average, games = 3) => ({ average, median: average, games, game_ids: [], window_start: "2026-10-20", window_end: "2026-10-24", as_of: evidence.as_of, missing_game_ids: [], stale_game_ids: [] });
const currentRole = {
  minutes: { quality: { ...evidence, state: "available", detail: "Three fresh valid games on each side." }, recent: roleWindow(30), comparison: roleWindow(23), delta: 7, median_delta: 7, unit: "minutes" },
  usage: { quality: { ...evidence, state: "unavailable" }, recent: roleWindow(null, 0), comparison: roleWindow(null, 0), delta: null, median_delta: null, unit: "fraction" },
  starts: { quality: { ...evidence, state: "unavailable" }, season: "2026-27", season_starts: null, season_games: null, recent_starts: null, detail: "Season starts do not prove the current lineup." },
  quality: { ...evidence, state: "available" }, trend: "RISING",
  season_usage: .231, season_usage_quality: evidence,
  method: "Latest three vs preceding three games; not a projection.", limitations: ["Game-level usage is unavailable."],
};
const drop = (id, net = 10) => ({
  player_id: id, player_name: id === 2 ? "Weak Guard" : "Bench Forward", before_score: 66, after_score: 66 + net,
  net_improvement: net, component_before: components, component_after: { ...components, roster_fit: 72 + net },
  effective_weights: { roster_fit: .4 }, starting_slots_before: 3, starting_slots_after: 3,
  starting_slots_required: 2, component_deltas: { ...components, roster_fit: net }, reasons: ["Same measured model on both sides."],
  comparison_type: "ADD_DROP", target_roster_position: "C",
});
const noDrop = (type = "ADD_ONLY", moved = null) => ({
  ...drop(2, 12), player_id: null, player_name: moved ? `No drop (move ${moved} to IL)` : "No drop (open roster slot)",
  comparison_type: type, moved_to_injury_slot_player_id: moved ? 9 : null, moved_to_injury_slot_player_name: moved,
  target_roster_position: "C", roster_spots_basis: 13, open_roster_spots_before: 1, open_roster_spots_after: 0,
  reasons: ["No-drop comparison over the same 13 non-injury roster spots: nobody is removed."],
});
const candidate = (id, name, comparison = drop(2), tweaks = {}) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, position: "C",
  yahoo_team: "DEN", nba_team: "DEN", raw_yahoo_status: id === 3 ? "" : "Q",
  yahoo_status: id === 3 ? null : "Q", identity_mapping_state: "EXACT_NAME_TEAM",
  identity_mapping_reason: "Yahoo and NBA names and team abbreviations match.",
  availability: "free_agent", eligible: true,
  recent: { value: 30, games: 2, season: "2026-27", label: "Recent", sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION", per_game_stats: {} },
  ros: { value: 35, games: 60, season: "2025-26", label: "History", sample_label: "EXCELLENT", per_game_stats: {} },
  ranking_value: { value: 32, recent_weight: .4, historical_value: 35, historical_games: 60, historical_season: "2025-26", label: "Recent / historical blend" },
  opportunity: { minutes: 30, minutes_trend: 2, usage_trend: null, historical_start_rate: .5, role: "Current role unverified" },
  schedule: { games_remaining: 2, off_day_games: 1, back_to_backs: 1, next_7_days_games: 2, opponents: ["BOS"], source_row_count: 4, window_start: "2026-10-25", window_end: "2026-10-31", imported_at: evidence.as_of, freshness: "fresh", coverage: "PARTIAL", diagnostic_reason: "SCHEDULE_ROWS_PRESENT" },
  components, overall_score: 80, effective_weights: { roster_fit: .4 }, recommended_action: "WATCH",
  current_season_games: 2, evidence_quality: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  hold_type: "streamer", comparison, best_drop_options: comparison ? [comparison] : [], net_improvement: comparison?.net_improvement ?? null,
  roster_decision: "review_replacement", reasons: ["Fits an uncovered center slot"], limitations: ["Current rolling priority unavailable"],
  data_quality: { status: { ...evidence, state: id === 3 ? "unknown" : "available" }, schedule: evidence, recent: { ...evidence, state: "partial" } },
  recommended_action_type: "WATCH", action_label: "WATCH: The measured fit is positive, but the sample is too small for a supported move.",
  requires_drop: false, fills_needs: ["C"], target_roster_position: "C", evidence_blockers: ["Sample gate: Available Center 2 games this season and 2 in the last 14 days. A supported move needs 7 games this season and 7 in the last 14 days for every compared player; prior-season history cannot bypass this gate."],
  decision_priority: id,
  availability_classification: UNROSTERED, availability_evidence: availabilityEvidence(),
  ...tweaks,
});
const MANAGER = { availability: "rostered", availability_classification: "ROSTERED_BY_MANAGER", availability_evidence: availabilityEvidence("ROSTERED_BY_MANAGER") };
const roster = [
  candidate(2, "Weak Guard", null, { ...MANAGER, roster_decision: "keep_on_measured_model", position: "G", recent: { value: 12, games: 10, season: "2026-27", label: "Recent", sample_label: "EXCELLENT", per_game_stats: {} }, ros: { value: 14, games: 60, season: "2025-26", label: "History", sample_label: "EXCELLENT", per_game_stats: {} } }),
  candidate(4, "Bench Forward", null, { ...MANAGER, roster_decision: "review_replacement", position: "F" }),
];
const metric = (count, total = 4) => ({ count, total, percentage: total ? count / total * 100 : 0 });
const coverageSlice = () => ({
  identity: { complete: metric(4), unresolved: metric(0), resolution_counts: { EXACT_NAME_TEAM: 4 } },
  production: { recent_supported: metric(3), recent_missing: metric(1), recent_stale: metric(0), season_supported: metric(4), season_missing: metric(0), season_stale: metric(0) },
  schedule: { supported: metric(3), unknown: metric(1), stale: metric(0), source_incomplete: metric(1) },
  status: { explicit: metric(3), yahoo_blank: metric(1), field_missing: metric(0), stale: metric(0) },
  role: { minutes_qualified: metric(3), usage_supported: metric(0), game_level_starts_supported: metric(0), season_starts_supported: metric(1), insufficient_sample: metric(1), missing_inputs: metric(4) },
});
const coverage = {
  population: { total: 4, candidates: 2, roster: 2 },
  pool: coverageSlice(), candidates: coverageSlice(), roster: coverageSlice(),
  acquisition: { supported: metric(0, 1), unsupported: metric(1, 1) },
  mapping_worklist: [],
};
const injured = { player_id: 9, player_name: "Injured Center", positions: "C", roster_slot: "IL", slot_kind: "injury", yahoo_status: "O", status_state: "available", eligible_positions_known: true, eligible_injury_slots: ["IL"], injured: true, lineup_eligible: false, injury_note: "Knee", detail: "In IL." };
const capacity = (shape = "ADD_ONLY", tweaks = {}) => ({
  state: shape === "UNDETERMINED" ? "stale" : "available", transaction_shape: shape,
  slots: [{ position: "C", count: 2, kind: "starting", occupied: 1, open: 1 }, { position: "IL", count: 3, kind: "injury", occupied: 1, open: 2 }],
  assignments: [injured], total_capacity: 16, non_injury_capacity: 13, active_slot_capacity: 10, bench_capacity: 3, injury_slot_capacity: 3,
  roster_count: 13, occupied_roster_spots: shape === "ADD_ONLY" ? 12 : 13, occupied_active_slots: 9, occupied_bench_slots: 3, occupied_injury_slots: 1,
  open_roster_spots: shape === "ADD_ONLY" ? 1 : 0, open_active_slots: shape === "ADD_ONLY" ? ["C"] : [], open_bench_slots: 0, open_injury_slots: 2,
  unassigned_player_ids: [], injured_players: [injured], injured_players_outside_injury_slots: [], injured_players_in_injury_slots: [9],
  no_drop_additions_available: shape === "ADD_ONLY" ? 1 : 0, move_to_injury_slot_options: [], injury_move_blockers: [],
  additions_after_injury_moves: shape === "ADD_ONLY" ? 1 : 0,
  requires_drop: shape === "ADD_DROP" ? true : shape === "UNDETERMINED" ? null : false,
  requires_roster_move: shape === "MOVE_TO_IL_THEN_ADD",
  drop_requirement_reason: shape === "ADD_ONLY" ? "1 of 13 non-injury roster spots are open. An add needs no drop." : "All 13 non-injury roster spots are occupied. An add requires a drop.",
  blockers: shape === "UNDETERMINED" ? ["Yahoo slot assignments (selected_position) are not persisted for 13 of 13 roster players."] : [],
  warnings: [], assignment_as_of: "2026-10-25",
  evidence: { ...evidence, state: shape === "UNDETERMINED" ? "stale" : "available" }, status_evidence: { ...evidence },
  transaction_legality_quality: { ...evidence, detail: "Roster-capacity recommendation requiring Yahoo confirmation." },
  limitations: ["Moving a player to IL keeps that player on the roster; it is never treated as a drop."],
  headline: HEADLINES[shape][0], short_reason: HEADLINES[shape][1],
  ...tweaks,
});
const teamNeeds = () => ({
  state: "partial", mode: "this_week", window_start: "2026-10-25", window_end: "2026-10-31",
  lineup_player_count: 11, starting_slots_required: 10, starting_slots_covered: 9,
  open_starting_slots: ["C"], weakened_positions: ["C"],
  slot_coverage: [{ slot: "C", kind: "starting", required: 2, covered: 1, uncovered: 1, eligible_player_ids: [4], weakened_by_injury: true, injured_player_ids: [9], need_score: 50, open_slot_days: 3, detail: "1 of 2 C starting slot(s) coverable." }],
  position_need_scores: { C: 50 },
  needs: [{ priority: 1, slot: "C", kind: "INJURY_WEAKENED", count: 1, positions: ["C"], reason: "1 of 2 C starting slot(s) cannot be filled by lineup-eligible roster players; weakened by Injured Center (O).", compatible_candidate_ids: [1] }],
  multi_position_player_ids: [4], redundancy: { C: 1 }, players: [],
  lineup_days: [{ date: "2026-10-25", players_with_games: 6, fillable_starting_slots: 6, starting_slots_required: 10, open_starting_slots: ["C", "UTIL"] }],
  lineup_day_state: "partial", lineup_day_detail: "Uses persisted per-player schedule rows (coverage PARTIAL).",
  production: { state: "partial", lineup_players: 11, supported_players: 9, lowest_supported_ppg: 12, lowest_supported_player_id: 2, median_supported_ppg: 25, detail: "9 of 11 lineup-eligible players have supported Recent Yahoo-rule fantasy PPG." },
  injured_player_ids: [9], uncertain_status_player_ids: [], unknown_status_player_ids: [4],
  hold_guidance: "Injury return timing is not forecast.", limitations: ["Eligibility is not player quality."],
});
const optionGroups = () => ({
  by_need: [{ slot: "C", candidate_id: 1, action_type: "WATCH", reason: "Best available option able to cover C." }],
  flexible_candidate_id: null, short_term_candidate_id: 1, longer_term_candidate_id: 3, watch_candidate_ids: [1],
  detail: "Backend-ranked alternatives.",
});
const HEADLINES = {
  ADD_ONLY: ["1 OPEN ROSTER SPOT — NO DROP REQUIRED", "12 of 13 regular roster spots are used; players in IL do not use them."],
  MOVE_TO_IL_THEN_ADD: ["MOVE INJURED CENTER TO IL TO OPEN A ROSTER SPOT", "All 13 regular roster spots are used. An IL move keeps the player on your roster; it is not a drop."],
  ADD_DROP: ["ROSTER FULL — AN ADD REQUIRES A DROP", "All 13 regular roster spots are used and no injured player can move to an open IL slot."],
  UNDETERMINED: ["ROSTER CAPACITY NEEDS A YAHOO REFRESH", "Your saved roster is from 2026-10-25; Yahoo roster slots are not saved for 13 of 13 players."],
};
const BLANK = "Yahoo did not provide an explicit current status. Confirm the player in Yahoo before acting.";
const measured = (value, tweaks = {}) => ({
  value, comparable: true, basis: "CURRENT_SEASON", current_value: value + 2, current_games: 3, current_season: "2026-27",
  current_weight: 3 / 13, prior_value: value - 1, prior_games: 70, prior_season: "2025-26", state: "stale",
  as_of: "2026-10-25T19:04:00Z", sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION",
  detail: "Measured Yahoo fantasy PPG shrunk toward 2025-26. Imported 2026-10-25 (stale). Historical, not a projection.", ...tweaks,
});
const option = (id, name, tweaks = {}) => ({
  player_id: id, yahoo_player_id: `y${id}`, player_name: name, positions: "PG,SG", nba_team: "BOS", decision_rank: id - 20, classification: "MEASURED",
  action_type: "INSUFFICIENT_EVIDENCE", availability: "unrostered", availability_confirmed: true, availability_label: LABELS[UNROSTERED],
  availability_classification: UNROSTERED, availability_evidence: availabilityEvidence(),
  yahoo_status: null, status_label: "UNKNOWN", status_detail: BLANK,
  measured: measured(50 - id), games_in_window: 4, games_in_window_state: "stale",
  fills: ["PG / SG"], fills_level: "HIGH", fills_slots: ["PG", "SG"], multi_position: true,
  evidence_level: "INSUFFICIENT FOR STRONG RECOMMENDATION", reason: `Measured ${(50 - id).toFixed(1)} Yahoo fantasy PPG.`,
  why: ["Fills the PG / SG need (high priority).", `${(50 - id).toFixed(1)} measured Yahoo fantasy PPG from 3 current-season games, blended with 2025-26.`],
  blockers: [
    "Roster capacity is undetermined: Your saved roster is from 2026-10-25; Yahoo roster slots are not saved for 13 of 13 players.",
    "Yahoo status is UNKNOWN (blank); blank is not treated as healthy.",
  ],
  confirm: ["Free-agent or waiver state in Yahoo", "Current Yahoo status", "Whether you have an open roster spot"],
  user_action: "CHECK IN YAHOO", roster_rank_if_added: 10, roster_measured_count: 14, ...tweaks,
});
// Unrostered in a stale or incomplete saved snapshot: never featured, only a potential target.
const potential = (id, name, classification = "SOURCE_STALE", tweaks = {}) => option(id, name, {
  classification: "POTENTIAL_TARGET", availability: "unknown", availability_classification: classification,
  availability_confirmed: false, availability_label: LABELS[classification], availability_evidence: availabilityEvidence(classification),
  reason: `Measured ${(50 - id).toFixed(1)} Yahoo fantasy PPG; ${LABELS[classification].toLowerCase()} — check in Yahoo before acting.`,
  blockers: ["Yahoo availability is unverified: league rosters are from 2026-10-25 or incomplete, so this player may have been added since."],
  confirm: ["Yahoo availability (free agent or waivers)", "Current Yahoo status"], ...tweaks,
});
const decisionSupport = (tweaks = {}) => ({
  state: "BEST_MEASURED_OPTION", headline: "Best measured option: Measured Guard — not yet a supported add.",
  detail: "The strict evidence gates block a supported move, but persisted basketball evidence can still compare players.",
  availability_state: "available",
  availability_note: "League rosters are current: featured players were absent from every current league roster. Yahoo does not state free-agent vs waiver status in this import, so confirm it in Yahoo.",
  best_measured_ids: [21],
  groups: [
    { key: "BEST_GUARD", title: "BEST GUARD", player_id: null, empty_reason: "The best option here is already shown above: Measured Guard." },
    { key: "BEST_WING_FORWARD", title: "BEST WING / FORWARD", player_id: 22, empty_reason: null },
    { key: "BEST_CENTER", title: "BEST CENTER", player_id: 23, empty_reason: null },
    { key: "BEST_MULTI_POSITION", title: "BEST MULTI-POSITION OPTION", player_id: null, empty_reason: "No measurable multi-position option." },
    { key: "BEST_SHORT_TERM", title: "BEST SHORT-TERM SCHEDULE", player_id: null, empty_reason: "No measurable option has persisted schedule rows in this window." },
    { key: "BEST_LONGER_TERM", title: "BEST LONGER-TERM OPTION", player_id: null, empty_reason: "No measurable option has at least 20 games across this season and last season." },
  ],
  watch_ids: [], potential_target_ids: [], potential_target_count: 0,
  options: [
    option(21, "Measured Guard", { classification: "BEST_MEASURED_OPTION" }),
    option(22, "Group Wing", { classification: "WATCH", positions: "SF,PF", fills: [], fills_level: null, reason: "Highest measured wing / forward production: 28.0 Yahoo fantasy PPG. Would rank 12 of 14 on your roster." }),
    option(23, "Watch Center", { classification: "WATCH", positions: "C", fills: [], fills_level: null }),
    option(24, "Watch Forward", { positions: "PF", fills: [], fills_level: null }),
    option(25, "Unmeasured Rookie", { classification: "UNAVAILABLE", fills: [], fills_level: null, why: [],
      measured: measured(0, { value: null, comparable: false, state: "missing", prior_value: null, prior_season: null }),
      reason: "No current-season NBA games; this player cannot be compared.", user_action: "VIEW DETAILS" }),
  ],
  supported_count: 0, comparable_count: 4,
  not_comparable_reasons: { "On another team's saved roster (not a target)": 152, "Yahoo O/OFS/NA status": 270 },
  roster_floor_ppg: 27.2, roster_floor_player_id: 2,
  method: "Measured production is Yahoo-rule fantasy points per game from persisted NBA games.",
  limitations: ["Decision support never upgrades a player to ADD, STREAM or MUST ADD; supported actions use the strict evidence gates."],
  ...tweaks,
});
const staleSupport = (tweaks = {}) => decisionSupport({
  state: "POTENTIAL_TARGETS", headline: "No player is confirmed available yet.",
  detail: "Saved Yahoo rosters are not all current, so no player can be confirmed available. 2 measurable players were not on any saved roster: refresh waiver data, or check the POTENTIAL TARGETS in Yahoo before acting.",
  availability_state: "stale",
  availability_note: "League rosters are from 2026-10-25 or incomplete, so availability is unverified. Players who were not on any saved league roster appear only as POTENTIAL TARGETS TO CHECK IN YAHOO; they may have been added since.",
  best_measured_ids: [], watch_ids: [], potential_target_ids: [41, 42], potential_target_count: 2,
  groups: decisionSupport().groups.map((group) => ({ ...group, player_id: null, empty_reason: group.empty_reason ?? "No confirmed-available player in this group." })),
  options: [potential(41, "Potential Forward", "SOURCE_STALE", { positions: "PF", fills: [], fills_level: null }), potential(42, "Unverified Guard", "AVAILABILITY_UNVERIFIED")],
  supported_count: 0, comparable_count: 0,
  ...tweaks,
});
const acquisition = (tweaks = {}) => ({
  rules: ["Continual rolling list", "4 adds/week"], data_quality: { ...evidence, state: "available" },
  current_priority: 4, weekly_adds_used: 2, weekly_adds_remaining: 2, weekly_add_limit: 4, yahoo_week: 4, claim_clear_at: null,
  state: "available", source: "Yahoo league teams import", as_of: "2026-11-14T05:00:00Z",
  detail: "Waiver priority 4th and 2 of 4 weekly adds used in Yahoo week 4, from the supported Yahoo teams resource. Exact claim-clear times are not supplied.",
  ...tweaks,
});
const availabilitySummary = (state = "available") => ({
  state, roster_snapshot_complete: state === "available", roster_snapshots_current: state === "available" ? 12 : 1, roster_snapshots_expected: 12,
  oldest_roster_snapshot: state === "available" ? "2026-11-14T05:00:00Z" : "2026-10-25T18:20:50Z", player_pool_imported_at: "2026-11-14T05:00:00Z",
  counts: state === "available"
    ? { [UNROSTERED]: 8, ROSTERED_BY_OTHER_TEAM: 152, ROSTERED_BY_MANAGER: 15, EXCLUDED_STATUS: 270 }
    : { SOURCE_STALE: 1, AVAILABILITY_UNVERIFIED: 1, ROSTERED_BY_OTHER_TEAM: 152, ROSTERED_BY_MANAGER: 15 },
  explicit_state_supplied: false,
  source_gap: "The supported Yahoo player resource does not state free-agent vs waiver ownership; unrostered players are labeled UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO.",
  detail: state === "available" ? "All 12 league roster snapshots are current and complete." : "1 of 12 league roster snapshots is current; availability is unverified.",
});
const needSummary = () => [
  { priority: 1, family: "CENTER", label: "C", level: "HIGH", slots: ["C"], positions: ["C"], reason: "Injury coverage needed: Injured Center cannot play, leaving C open.", eligible_player_ids: [4] },
  { priority: 2, family: "GUARD", label: "PG / SG", level: "MEDIUM", slots: ["PG", "SG"], positions: ["PG", "SG"], reason: "Limited active coverage: only Weak Guard can fill PG / SG; one absence leaves it open.", eligible_player_ids: [2] },
  { priority: 3, family: "WING_FORWARD", label: "SF / PF / F", level: "COVERED", slots: ["SF", "PF", "F"], positions: ["SF", "PF"], reason: "Covered: 5 lineup-eligible players can fill these slots.", eligible_player_ids: [4] },
];
const freshness = [
  { source: "Yahoo league settings", state: "available", as_of: "2026-11-13T21:05:17Z", detail: "Roster positions and scoring rules; fresh for 24 hours." },
  { source: "Your saved Yahoo roster", state: "stale", as_of: "2026-10-25T18:20:50Z", detail: "Yahoo slot assignments saved for 0 of 13 players; fresh for 24 hours." },
  { source: "NBA game logs", state: "stale", as_of: "2026-10-25T19:04:00Z", detail: "Latest persisted game 2026-10-24; Recent uses the last 14 days." },
];
const board = (dropId = 2, mode = "this_week", order = [1, 3], best_add_for_team_id = null) => ({
  league_key: "478.l.50505", team_key: "478.l.50505.t.9", team_name: "Box Score Bully",
  mode, generated_at: "2026-10-25T00:00:00Z", model_version: VERSION,
  weights: { roster_fit: .35, player_value: .25, opportunity: .15, schedule: .15, acquisition_value: .1 },
  best_add_for_team_id, best_overall_available_id: 1, top_measured_candidate_id: null,
  selected_drop_player_id: dropId, roster, team_needs: ["Uncovered center slot"],
  waiver_rules: ["Continual rolling list", "2-day waiver period", "4 adds/week", "Daily - Today deadline"],
  selected_player_result: "WATCH",
  candidates: order.map((id) => candidate(id, id === 1 ? "Available Center" : "Overall Guard", drop(dropId, id === 1 ? (dropId === 2 ? 15 : -5) : 4))),
  excluded_count: 2, unknown_availability_count: 1, limitations: ["No projections."],
  data_quality: { roster: { ...evidence, state: "stale", detail: "Stale roster." } },
  coverage, data_gaps: [],
  recommended_action_type: "WATCH", roster_capacity: capacity(), option_groups: optionGroups(),
  team_needs_analysis: { ...teamNeeds(), summary: needSummary(), depth_note: null,
    basis: "Based on the saved Yahoo roster from 2026-10-25 (stale); refresh Yahoo before relying on these needs." },
  decision_support: decisionSupport(), evidence_freshness: freshness,
  eligible_candidate_ids: [1, 3, 21, 22, 23, 24, 25, 32], candidate_count: 8, candidate_limit: 12,
  availability_summary: availabilitySummary(), acquisition_context: acquisition(),
});
const staleBoard = (tweaks = {}) => ({ ...board(null), candidates: [], eligible_candidate_ids: [], candidate_count: 0,
  roster_capacity: capacity("UNDETERMINED"), decision_support: staleSupport(), availability_summary: availabilitySummary("stale"), ...tweaks });
const fill = (step = 1, name = "Available Center", tweaks = {}) => ({
  step, action_type: "ADD_ONLY", decision: "ADD",
  label: `ADD ONLY: Add ${name} to cover C. You have an open roster spot. No player needs to be dropped.`,
  add_player: candidate(step === 1 ? 1 : 30 + step, name, noDrop(), { recommended_action: "ADD", recommended_action_type: "ADD_ONLY", current_season_games: 9, evidence_quality: "LIMITED", evidence_blockers: [] }),
  target_roster_position: "C", fills_needs: ["C"], suggested_injury_move: null, requires_drop: false, comparison: noDrop(),
  reasons: ["label", "Fills the uncovered C starting slot measured for your lineup.", "Recent Yahoo-rule fantasy PPG 30 from 9 games.", "1 of 13 non-injury roster spots are open. An add needs no drop."],
  limitations: [], ...tweaks,
});
const transactionAnalysis = (best = null, tweaks = {}) => {
  const add = candidate(1, "Available Center", drop(4, 5), { recommended_action: "WATCH" });
  const swap = {
    add_player: add, drop_player: roster[1], mode: "this_week", decision: "WATCH",
    comparison: add.comparison, reasons: ["Limited current-season evidence"], limitations: ["Partial schedule"],
  };
  return {
    team_name: "Box Score Bully", mode: "this_week", model_version: VERSION, decision: best ? "ADD" : "HOLD",
    best_transaction: best ? { ...swap, decision: "ADD" } : null,
    watch_transactions: [swap], top_supported_transactions: [],
    evaluated_pair_count: 20, supported_pair_count: 0, watch_pair_count: 1, excluded_pair_count: 20,
    excluded_pair_reasons: { "Limited sample": 20 }, data_quality: {}, decision_reasons: ["No add/drop pair cleared all current evidence gates."],
    acquisition_context: { rules: ["Continual rolling list"], detail: "Weekly adds unverified." },
    recommended_action_type: best ? "ADD_DROP" : "HOLD",
    action_label: best ? "ADD Available Center + DROP Bench Forward: Your roster is full." : "HOLD: No sufficiently supported move currently improves the roster.",
    roster_capacity: capacity("ADD_DROP"), add_only_recommendations: [], watch_additions: [],
    ...tweaks,
  };
};
const fillAnalysis = (fills, tweaks = {}) => transactionAnalysis(null, {
  decision: fills.length ? "ADD" : "HOLD", recommended_action_type: fills.length ? fills[0].action_type : "HOLD",
  action_label: fills.length ? fills[0].label : "HOLD: No sufficiently supported move currently improves the roster.",
  roster_capacity: capacity("ADD_ONLY"), add_only_recommendations: fills, best_addition: fills[0] ?? null,
  evaluated_pair_count: 0, watch_transactions: [], evaluated_addition_count: 3, supported_addition_count: fills.length,
  excluded_addition_count: 3 - fills.length, watch_additions: [], ...tweaks,
});
const supportedBoard = (tweaks = {}) => ({ ...board(null), decision_support: decisionSupport({
  state: "SUPPORTED_ACTION", best_measured_ids: [], supported_count: 1, ...tweaks }) });
// On a full roster the board names the same supported pair as the best-move analysis (backend invariant).
const pairBoard = (analysis, tweaks = {}) => ({ ...supportedBoard(), roster_capacity: capacity("ADD_DROP"),
  best_add_for_team_id: analysis.best_transaction?.add_player.player_id ?? null,
  best_drop_for_team_id: analysis.best_transaction?.drop_player.player_id ?? null, ...tweaks });
function moves(analysis, result = supportedBoard(), failure = null, extra = {}) {
  const { BestMoves } = load();
  return render(BestMoves, { board: result, analysis, failure, mode: "this_week", onAnalyzeFill() {}, onAnalyzePair() {}, onDetails() {},
    onRetry() {}, onRefresh() {}, ...extra });
}
const apiFailure = (status, code, message, tweaks = {}) => ({ status, code, message, retryable: true, requestId: null, ...tweaks });
// WaiverCenter useState order: mode, board, replacement, drop, impact, loading, replacementLoading, failure,
// replacementError, retry, pair, fill, transactions, transactionsFailure, then the refresh hook's status.
const NO_STATE = ["this_week", null, null, null, null, false, false, null, "", 0, null, null, null, null];
const STAGE_DEFS = [
  ["LEAGUE_SETTINGS", "Yahoo league/settings", "YAHOO"], ["PLAYER_POOL", "Yahoo player pool", "YAHOO"],
  ["LEAGUE_ROSTERS", "Yahoo rosters", "YAHOO"], ["ROSTER_SLOTS", "Roster slots", "YAHOO"],
  ["YAHOO_AVAILABILITY_STATUS", "Yahoo availability and status", "YAHOO"], ["NBA_TEAMS_PLAYERS", "NBA teams and players", "NBA"],
  ["NBA_SCHEDULE", "NBA schedule", "NBA"], ["NBA_GAME_LOGS", "NBA game logs", "NBA"], ["NBA_SEASON_STATS", "NBA season stats", "NBA"],
  ["POST_REFRESH_VERIFICATION", "Post-refresh verification", "VERIFICATION"],
];
const STAGE_SUMMARY = {
  LEAGUE_SETTINGS: "Bully League · 12 teams", PLAYER_POOL: "612 players", LEAGUE_ROSTERS: "12 of 12 teams", ROSTER_SLOTS: "15 of 15 saved",
  YAHOO_AVAILABILITY_STATUS: "612 players", NBA_TEAMS_PLAYERS: "30 teams · 540 players", NBA_SCHEDULE: "1230 games · 18000 player rows",
  NBA_GAME_LOGS: "Latest game 2026-11-13", NBA_SEASON_STATS: "540 regular-season rows (2026-27)", POST_REFRESH_VERIFICATION: "9 of 9 checks passed",
};
const STALE_STAGES = ["LEAGUE_ROSTERS", "ROSTER_SLOTS", "YAHOO_AVAILABILITY_STATUS", "NBA_GAME_LOGS"];
const refreshJob = (states, tweaks = {}) => ({
  job_id: "job-1", state: "RUNNING", active: true, scope: "ALL", retry_of: null, league_key: "478.l.50505", team_key: "478.l.50505.t.9",
  season: "2026-27", requested_at: "2026-11-14T03:40:00Z", started_at: "2026-11-14T03:40:00Z", completed_at: null,
  stages: STAGE_DEFS.map(([stage, label, source], index) => ({
    stage, label, source, state: states[index] ?? "PENDING", started_at: null, completed_at: null, rows_fetched: null, rows_persisted: null,
    source_timestamp: null, verification: states[index] === "SUCCEEDED" ? "PASSED" : "NOT_RUN", checks: [],
    summary: states[index] === "SUCCEEDED" ? STAGE_SUMMARY[stage] : "", error_code: null, message: "",
  })),
  message: "", yahoo_requests: 0, practice_league_requests_blocked: 0, yahoo_transactions_executed: 0, board_reload_recommended: false,
  ...tweaks,
});
const refreshStatus = (kind = "current", job = null) => ({
  job, already_running: false,
  evidence: STAGE_DEFS.map(([stage, label]) => ({ stage, label, state: kind === "stale" && STALE_STAGES.includes(stage) ? "stale" : "current",
    as_of: "2026-11-14T03:42:00Z", summary: STAGE_SUMMARY[stage], detail: "Persisted evidence." })),
  needs_refresh: kind === "stale", stale_stages: kind === "stale" ? STALE_STAGES : [],
  last_complete_refresh_at: kind === "stale" ? null : "2026-11-14T03:42:00Z",
  last_complete_refresh_source: kind === "stale" ? null : "refresh_job", checked_at: "2026-11-14T03:45:00Z",
});
const refreshController = (status, tweaks = {}) => ({
  status, failure: null, requesting: false, running: Boolean(status?.job?.active), announcement: "", start() {},
  buttonRef: { current: null }, progressRef: { current: null }, ...tweaks,
});

test("replacement cards show a single measured drop, evidence, ranking blend and risks", () => {
  const { Replacements } = load();
  const html = render(Replacements, { board: board(), loading: false, error: "", selectedDropId: 2, onAnalyze() {} });
  assert.match(html, /Top 3 replacements/);
  assert.match(html, /Recent evidence: insufficient for strong recommendation/);
  assert.match(html, /INSUFFICIENT FOR STRONG RECOMMENDATION/);
  assert.match(html, /historical, not a projection/);
  assert.match(html, /Recent \/ historical blend/);
  assert.match(html, /Roster before/);
  assert.match(html, /Roster after/);
  assert.match(html, /Net improvement/);
  assert.match(html, /Starting-slot compatibility/);
  assert.match(html, /Effective comparison weights/);
  assert.match(html, /recent evidence is partial/);
  assert.match(html, /Yahoo status is unknown/);
  assert.match(html, /Top measured option: not established · limited evidence/);
});

test("current role shows measured deltas, independent missing inputs, status and schedule coverage", () => {
  const { RoleEvidence } = load();
  const row = candidate(1, "Role Player", null, {
    opportunity: { current_role: currentRole, score_parts: { minutes_level: 83.333 } },
    schedule: { ...candidate(1, "").schedule, coverage: "PARTIAL", imported_at: evidence.as_of },
  });
  const html = render(RoleEvidence, { candidate: row });
  for (const text of ["CURRENT ROLE", "RISING", "+7.0", "23.1", "percentage points", "Recent starts: Unavailable",
    "Unavailable", "PARTIAL", "Opponent identity is not matchup difficulty", "Game-level usage is unavailable",
    "Yahoo team DEN vs NBA team DEN", "4 persisted source rows"]) {
    assert.ok(html.includes(text), text);
  }
  assert.match(html, /Yahoo raw status:<\/strong> Q/);
  assert.doesNotMatch(html, /Expected minutes|Projected role|Usage will increase|Breakout probability/);
  for (const status of ["Q", "P", null]) {
    row.yahoo_status = status;
    const text = render(RoleEvidence, { candidate: row });
    assert.match(text, new RegExp(`normalized status: ${status ?? "UNKNOWN"}`));
    assert.match(text, /No injury-return date is inferred/);
  }
  row.opportunity.current_role = { ...currentRole, trend: "INSUFFICIENT EVIDENCE", quality: { ...evidence, state: "partial" } };
  assert.match(render(RoleEvidence, { candidate: row }), /INSUFFICIENT EVIDENCE/);
});

test("a missing Yahoo status field that fails a condition shows the backend's UNKNOWN reason and is counted apart from a supplied blank", () => {
  // Real-data audit (2026-11-14): Yahoo omitted the status field for all 426 undesignated players. Only the backend
  // decides whether that absence qualifies; when a condition fails, the browser shows the backend's UNKNOWN reason.
  const { RoleEvidence, AdvancedEvidence } = load();
  const detail = "Yahoo's record has no status field, but the player-pool import is older than 24 hours, so the absence is not current evidence. Status is UNKNOWN, not healthy. Confirm the player in Yahoo before acting.";
  const row = candidate(1, "No Field", null, { raw_yahoo_status: null, yahoo_status: null, status_diagnostic: "STATUS_FIELD_MISSING",
    status_field_state: "STATUS_FIELD_MISSING", decision_status_state: "UNKNOWN", status_reason: "STALE_PLAYER_POOL_IMPORT",
    status_gate_supported: false, status_label: "UNKNOWN", status_detail: detail });
  row.data_quality = { ...row.data_quality, status: { ...evidence, state: "unknown", detail } };
  const html = render(RoleEvidence, { candidate: row });
  assert.ok(html.includes("Yahoo raw status:</strong> (not supplied) · normalized status: none · decision status: <strong>UNKNOWN</strong> (Yahoo status gate blocks strong actions) · unknown"), html);
  assert.ok(html.includes(escaped(detail)));
  assert.match(html, /Diagnostic: STATUS FIELD MISSING\./);
  assert.doesNotMatch(html, /Yahoo supplied a blank|NO CURRENT YAHOO DESIGNATION|HEALTHY|[Cc]leared/);
  const pool = { ...coverageSlice(), status: { explicit: metric(1), yahoo_blank: metric(0), field_missing: metric(3), no_current_designation: metric(2), stale: metric(0) } };
  const evidenceHtml = render(AdvancedEvidence, { board: { ...board(), coverage: { ...coverage, pool } }, analysis: transactionAnalysis() });
  assert.ok(evidenceHtml.includes("1/4 (25.0%) explicit · 0/4 (0.0%) Yahoo blank · 3/4 (75.0%) status field missing · 2/4 (50.0%) no current Yahoo designation"), "status coverage");
});

test("NO CURRENT YAHOO DESIGNATION is rendered only from backend fields, with its limitation, and never as health", () => {
  const { RoleEvidence, FullWaiverList } = load();
  const label = "NO CURRENT YAHOO DESIGNATION";
  const detail = "Yahoo's current player record contains no explicit injury/status designation. This is not a medical-health guarantee.";
  const designation = { raw_yahoo_status: null, yahoo_status: null, status_diagnostic: "STATUS_FIELD_MISSING",
    status_field_state: "STATUS_FIELD_MISSING", decision_status_state: "NO_CURRENT_YAHOO_DESIGNATION",
    status_reason: "NO_CURRENT_YAHOO_DESIGNATION", status_gate_supported: true, status_label: label, status_detail: detail };
  const row = candidate(1, "Available Center", drop(4, 5), designation);
  row.data_quality = { ...row.data_quality, status: { ...evidence, state: "available", detail } };
  const role = render(RoleEvidence, { candidate: row });
  assert.ok(role.includes(`normalized status: none · decision status: <strong>${label}</strong> (Yahoo status gate passes) · available`), role);
  assert.ok(role.includes(escaped(detail)));
  const analysis = transactionAnalysis(true);
  analysis.best_transaction = { ...analysis.best_transaction, add_player: { ...analysis.best_transaction.add_player, ...designation },
    drop_player: { ...analysis.best_transaction.drop_player, ...designation } };
  const pair = moves(analysis, pairBoard(analysis));
  assert.ok(pair.includes(`Add Yahoo status: ${label} · drop status: ${label}. Q/P remains uncertain.`), pair);
  assert.ok(pair.includes(`<p>${escaped(detail)}</p>`));
  for (const html of [role, pair]) {
    assert.doesNotMatch(html, /HEALTHY|\bhealthy\b|\bACTIVE\b|CLEARED|NO INJURY|Yahoo status: Unknown|Yahoo status is unknown/);
  }
  const options = [option(21, "Designation Guard", { decision_status_state: "NO_CURRENT_YAHOO_DESIGNATION", status_label: label, status_detail: detail }),
    option(22, "Blank Guard")];
  const result = { ...board(null), decision_support: decisionSupport({ options }) };
  const all = render(FullWaiverList, { board: result, onDetails() {} });
  assert.match(all, /<option value="no_designation">No current Yahoo designation<\/option>/);
  assert.ok(all.includes(`<td>${label}</td>`), "the list shows the backend label");
  const designated = render(load(["", "all", "all", "all", "all", "no_designation"]).FullWaiverList, { board: result, onDetails() {} });
  assert.match(designated, /Designation Guard/);
  assert.doesNotMatch(designated, /Blank Guard/);
  const unknown = render(load(["", "all", "all", "all", "all", "unknown"]).FullWaiverList, { board: result, onDetails() {} });
  assert.match(unknown, /Blank Guard/);
  assert.doesNotMatch(unknown, /Designation Guard/, "NO CURRENT YAHOO DESIGNATION is not filtered as unknown / blank");
});

test("negative net remains signed and is explicitly not presented as an improvement", () => {
  const { Replacements } = load();
  const html = render(Replacements, { board: board(4, "this_week", [1, 3]), loading: false, error: "", selectedDropId: 4, onAnalyze() {} });
  assert.match(html, /Net improvement<\/dt><dd>-5\.0/);
  assert.match(html, /No measured improvement/);
  assert.match(html, /not a recommendation to replace the selected player/);
  assert.match(html, /roster fit: 72\.0 → 67\.0 \(-5\.0\)/);
});

test("full waiver list starts collapsed, keeps backend rank order and filters by need, sample and availability", () => {
  const { FullWaiverList } = load();
  const result = board(null);
  result.decision_support = decisionSupport({ options: [...decisionSupport().options].reverse() });
  const html = render(FullWaiverList, { board: result, onDetails() {} });
  assert.match(html, /<h2 id="waiver-ranked">FULL WAIVER LIST<\/h2><details class="waiver-full-list"><summary>Show all 5 players \(5 confirmed available · 0 availability unverified\)<\/summary>/);
  for (const text of ["Search players", "Position", "Roster need", "Fills a HIGH need", "Action type", "Evidence level", "Yahoo status",
    "Schedule", "3+ games in window", "Production sample", "7+ current-season games", "Availability", "Confirmed available",
    "Availability unverified", "Decision priority (backend)", LABELS[UNROSTERED], "BEST MEASURED OPTION", "NOT COMPARABLE",
    "POTENTIAL TARGET", "neither creates a recommendation or changes BEST MOVES or the backend rank", "272 Yahoo O/OFS/NA players excluded"]) {
    assert.ok(html.includes(text), text);
  }
  const order = ["Measured Guard", "Group Wing", "Watch Center", "Watch Forward", "Unmeasured Rookie"].map((name) => html.indexOf(name));
  assert.deepEqual([...order].sort((left, right) => left - right), order, "backend decision_rank order wins over payload order");
  assert.doesNotMatch(html, /Best Overall Available|Best Fit for Box Score Bully/);
  const empty = render(FullWaiverList, { board: { ...board(null), decision_support: decisionSupport({ options: [] }) }, onDetails() {} });
  assert.match(empty, /No available or availability-unverified players can be listed/);
  const stale = render(FullWaiverList, { board: staleBoard(), onDetails() {} });
  assert.match(stale, /Show all 2 players \(0 confirmed available · 2 availability unverified\)/);
  assert.match(stale, /<span class="waiver-action is-potential_target">POTENTIAL TARGET<\/span>/);
  assert.match(stale, /<span class="waiver-availability is-unverified">SAVED ROSTERS STALE — CHECK IN YAHOO<\/span>/);
  const rostered = render(FullWaiverList, { board: { ...board(null), decision_support: decisionSupport({ options: [
    ...decisionSupport().options, potential(43, "Rostered Elsewhere Guard", "ROSTERED_BY_OTHER_TEAM")] }) }, onDetails() {} });
  assert.doesNotMatch(rostered, /Rostered Elsewhere Guard/, "a rostered player is never listed as a waiver option");
});

test("advanced evidence starts collapsed and holds model version, timestamps, coverage, data gaps and mapping worklist", () => {
  const { AdvancedEvidence } = load();
  const result = board();
  result.data_gaps = [{
    category: "SOURCE CONTRACT UNVERIFIED", field: "Game-level usage",
    count: 4, total: 4, percentage: 100,
    reason: "Persisted game logs do not provide supported usage values.",
    root_cause: "SOURCE_CONTRACT_UNVERIFIED",
  }];
  result.coverage.mapping_worklist = [{
    internal_id: 101, yahoo_player_id: "y101", yahoo_name: "Unmapped Center",
    yahoo_team: "DEN", normalized_name: "unmapped center",
    potential_nba_matches: [], conflict_reason: "No same-name NBA player exists.",
    resolution_state: "NO_MATCH",
  }];
  const html = render(AdvancedEvidence, { board: result, analysis: transactionAnalysis() });
  assert.match(html, /<h2 id="waiver-quality">ADVANCED EVIDENCE<\/h2><details class="waiver-advanced"><summary>/);
  for (const text of [`Model version ${VERSION}`, "Source timestamps", "NBA game logs: stale", "Decision-support method",
    "Yahoo O/OFS/NA status: 270", "On another team&#x27;s saved roster (not a target): 152", "Supported-action evidence counts",
    "20 add/drop pairs evaluated", "Limited sample: 20 pairs", "Acquisition context", "Persisted evidence coverage",
    "4 Yahoo-pool observations", "Full persisted Yahoo pool", "Eligible candidates", "Configured roster", "DATA GAPS",
    "SOURCE DOES NOT SUPPLY", "Game-level usage: 4/4 (100.0%)", "NEW SOURCE REQUIRED", "No additional source is selected",
    "Identity mapping worklist · 1 unresolved records", "Unmapped Center", "NO MATCH", "Yahoo availability evidence",
    "All 12 league roster snapshots are current and complete.", "does not state free-agent vs waiver ownership",
    "UNROSTERED FROM COMPLETE ROSTER SNAPSHOT: 8", "ROSTERED BY OTHER TEAM: 152",
    "8 waiver-eligible candidates; full evidence is returned for the top 12", "Waiver priority 4th and 2 of 4 weekly adds used",
    "does not supply exact waiver claim-clear times"]) {
    assert.ok(html.includes(text), text);
  }
});

test("backend-owned HOLD and Yahoo calculation evidence are rendered without a fake winner", () => {
  const { Replacements } = load();
  const result = board();
  result.selected_player_result = "HOLD Weak Guard";
  result.candidates = [candidate(1, "Available Center", drop(2, -5), {
    recommended_action: "PASS", recommended_action_type: "HOLD", action_label: "HOLD: No sufficiently supported move currently improves the roster.",
    recent: {
      value: 52, games: 2, season: "2026-27", label: "Yahoo fantasy PPG",
      sample_label: "INSUFFICIENT FOR STRONG RECOMMENDATION",
      per_game_stats: { PTS: 20, REB: 10, AST: 6, BLK: 2, STL: 3, TOV: 4 },
      scoring_weights: { PTS: 1, REB: 1.2, AST: 1.5, BLK: 3, STL: 3, TOV: -1 },
      scoring_contributions: { PTS: 20, REB: 12, AST: 9, BLK: 6, STL: 9, TOV: -4 },
    },
  })];
  const html = render(Replacements, { board: result, loading: false, error: "", selectedDropId: 2, onAnalyze() {} });
  assert.match(html, /HOLD Weak Guard/);
  assert.match(html, /Exact Fantasy PPG inputs and contributions/);
  assert.match(html, /REB 10 × 1.2 = 12/);
  assert.match(html, /TO \(NBA TOV\) 4 × -1 = -4/);
  assert.match(html, /Total 52 fantasy PPG/);
  assert.doesNotMatch(html, /Best Add|MUST ADD|ROS Projection|confidence/);
});

test("compare a specific drop renders the backend order: a supported move before a higher-net WATCH, each with its own decision", () => {
  // Real-data regression (2026-11-14): WATCH DeMar DeRozan (+0.847) was listed above the supported Jerami Grant (+0.728).
  const { Replacements } = load();
  const supported = candidate(3, "Supported Guard", drop(4, .728), { recommended_action: "ADD", recommended_action_type: "ADD_DROP",
    action_label: "ADD Supported Guard + DROP Bench Forward: Your roster is full.", evidence_blockers: [] });
  const watch = candidate(1, "Watch Center", drop(4, .847));
  const replacement = { ...board(4), candidates: [supported, watch], best_add_for_team_id: 3, top_measured_candidate_id: 1, selected_player_result: "ADD" };
  const cards = (html) => [...html.matchAll(/<p class="waiver-kicker">Replacement option (\d)<\/p><h4>([^<]+)<\/h4><\/div><span class="waiver-decision[^"]*">([^<]+)<\/span>/g)]
    .map(([, rank, name, decision]) => `${rank}. ${name}: ${decision}`);
  const html = render(Replacements, { board: replacement, loading: false, error: "", selectedDropId: 4, onAnalyze() {} });
  assert.deepEqual(cards(html), ["1. Supported Guard: ADD", "2. Watch Center: WATCH"]);
  assert.match(html, /Each comparison uses only the selected drop: Bench Forward\./);
  assert.equal(html.match(/<dt>Selected drop<\/dt><dd>Bench Forward<\/dd>/g).length, 2, "every card compares the same selected drop");
  assert.match(html, /Ordered by the backend: supported moves first, then WATCH, HOLD and insufficient evidence; within each group by measured net improvement\./);
  assert.match(html, /Top measured option: Watch Center/);
  // The page renders the backend order as received and never re-sorts by net.
  const asReceived = render(Replacements, { board: { ...replacement, candidates: [watch, supported] }, loading: false, error: "", selectedDropId: 4, onAnalyze() {} });
  assert.deepEqual(cards(asReceived), ["1. Watch Center: WATCH", "2. Supported Guard: ADD"]);
  const stale = render(Replacements, { board: { ...replacement, model_version: "waiver-availability-phase5" }, loading: false, error: "", selectedDropId: 4, onAnalyze() {} });
  assert.match(stale, /Replacement evidence uses incompatible model waiver-availability-phase5/);
  assert.deepEqual(cards(stale), [], "a stale replacement response shows no option");
});

test("rest-of-week uses the board timestamp's Pacific calendar date", () => {
  const { WindowNote } = load();
  const html = (generated_at) => render(WindowNote, { board: { ...board(), generated_at } });
  assert.match(html("2026-10-25T00:00:00Z"), /Rest of Week · limited days remaining/);
  assert.match(html("2026-10-22T00:00:00Z"), /persisted games through Sunday Pacific Time/);
});

test("ADD + DROP impact stays fixed to the exact selected drop and never offers alternate-drop controls", () => {
  const { ImpactContent } = load();
  const html = render(ImpactContent, {
    impact: { model_version: VERSION, candidate: candidate(1, "Available Center", drop(2)), comparison: drop(2), limitations: [] },
    selectedDropId: 2,
  });
  assert.match(html, /Available Center: add\/drop analysis/);
  assert.match(html, /Selected drop comparison/);
  assert.match(html, /drop Weak Guard/);
  assert.match(html, /starting-slot compatibility/i);
  assert.doesNotMatch(html, /Compare dropping|selected-drop/);
  assert.match(source, /comparison: swap\.comparison/);
  assert.match(source, /selectedDropId=\{swap\.drop_player\.player_id\}/);
  const modelDrop = render(ImpactContent, {
    impact: { model_version: VERSION, candidate: candidate(1, "Available Center", drop(4)), comparison: drop(4), limitations: [] },
    selectedDropId: null,
  });
  assert.match(modelDrop, /Best measured drop for this add \(roster full\)/);
  assert.match(modelDrop, /best measured drop for this add; use Compare a specific drop to fix a different drop/);
  assert.doesNotMatch(modelDrop, /Selected drop comparison/);
});

test("ADD ONLY best move is a focal card with no drop selector, fake drop or model version", () => {
  const { ImpactContent } = load();
  const html = moves(fillAnalysis([fill()]));
  assert.match(html, /BEST MOVES RIGHT NOW/);
  assert.match(html, /<span class="waiver-action is-add_only">ADD ONLY<\/span><h3 class="waiver-move-player">Available Center<\/h3>/);
  assert.match(html, /Fills<\/dt><dd>C<\/dd>/);
  assert.match(html, /Drop<\/dt><dd>No drop required<\/dd>/);
  assert.match(html, /Evidence<\/dt><dd>LIMITED<\/dd>/);
  assert.match(html, /Fills the uncovered C starting slot/);
  assert.match(html, /CONFIRM IN YAHOO BEFORE ACTING/);
  assert.match(html, /View details: Available Center/);
  assert.match(html, /<p class="waiver-move-availability"><span class="waiver-availability is-confirmed">UNROSTERED — CONFIRM FA\/WAIVER STATE IN YAHOO<\/span><\/p>/);
  assert.doesNotMatch(html, /DROP:|selected-drop|Choose one roster player|Selected drop comparison|BEST MEASURED OPTION|WAIVER MODEL CONTRACT ERROR/);
  assert.doesNotMatch(html, new RegExp(VERSION), "the model version is not prominent user-facing content");
  const impact = render(ImpactContent, {
    impact: { model_version: VERSION, candidate: fill().add_player, comparison: noDrop(), limitations: [] }, selectedDropId: null,
  });
  assert.match(impact, /ADD ONLY comparison \(no drop\)/);
  assert.match(impact, /no player is dropped/);
  assert.match(impact, /Open roster spots 1 → 0/);
  assert.doesNotMatch(impact, /Selected drop comparison|drop Weak Guard/);
});

test("MOVE TO IL, THEN ADD shows both steps and never calls the IL move a drop", () => {
  const move = { player_id: 9, player_name: "Injured Center", from_slot: "C", to_slot: "IL", released_slot: "C", released_slot_kind: "starting", certainty: "conditional", detail: "Conditional on Yahoo allowing the IL placement." };
  const moveFill = fill(1, "Available Center", {
    action_type: "MOVE_TO_IL_THEN_ADD", suggested_injury_move: move, comparison: noDrop("MOVE_TO_IL_THEN_ADD", "Injured Center"),
    label: "MOVE Injured Center TO IL, THEN ADD Available Center to cover C. Injured Center stays on your roster; this is not a drop.",
  });
  const html = moves(fillAnalysis([moveFill], { roster_capacity: capacity("MOVE_TO_IL_THEN_ADD") }));
  assert.match(html, /<span class="waiver-action is-move_to_il_then_add">MOVE TO IL, THEN ADD<\/span><h3 class="waiver-move-player">Available Center<\/h3>/);
  assert.match(html, /<ol class="waiver-steps"><li>Move Injured Center from C to IL\. Injured Center stays on your roster; this is not a drop\.<\/li><li>Add Available Center to cover C\.<\/li><\/ol>/);
  assert.match(html, /Drop<\/dt><dd>No drop required/);
  assert.doesNotMatch(html, /DROP: Injured Center|drop Injured Center/);
});

test("two open spots show two distinct supported cards, or a best measured card for the unsupported spot", () => {
  const second = fill(2, "Bench Guard", { target_roster_position: "BN", fills_needs: [], label: "ADD ONLY: Add Bench Guard. You have an open roster spot. No player needs to be dropped." });
  const html = moves(fillAnalysis([fill(), second]));
  assert.equal(html.match(/class="waiver-move-card is-supported"/g).length, 2);
  assert.ok(html.indexOf("Best move now") < html.indexOf("Also fill open spot 2 of 2"));
  assert.ok(html.indexOf(">Available Center<") < html.indexOf(">Bench Guard<"));
  assert.match(html, /Fills<\/dt><dd>Depth \(bench\)<\/dd>/);
  const mixed = moves(fillAnalysis([fill()]), supportedBoard({ best_measured_ids: [21] }));
  assert.equal(mixed.match(/class="waiver-move-card is-supported"/g).length, 1);
  assert.equal(mixed.match(/class="waiver-move-card is-measured"/g).length, 1);
  assert.ok(mixed.indexOf(">Available Center<") < mixed.indexOf(">Measured Guard<"), "supported moves stay first");
  assert.match(mixed, /Next open spot: no supported add yet/);
});

test("team situation is a compact plain-language summary with prioritized needs, freshness and expandable details", () => {
  const { TeamSituation } = load();
  const situation = render(TeamSituation, { board: board(null) });
  for (const text of ["TEAM SITUATION", "1 OPEN ROSTER SPOT — NO DROP REQUIRED", "12 of 13 regular roster spots are used",
    "Roster spots used", "12 of 13", "Open regular spots", "Open IL spots", "2 of 3", "Adds without a drop", "Injured players",
    "IL spots used</dt><dd>1 of 3", "Could move to IL", "Weekly adds used</dt><dd>2 of 4 · 2 left", "Waiver priority</dt><dd>4th",
    "Source: Yahoo league import", "Positional needs", "Injury coverage needed", "Evidence freshness",
    "<strong>STALE</strong> (2026-10-25): Your saved Yahoo roster, NBA game logs",
    "<strong>CURRENT</strong> (2026-11-13): Yahoo league settings", "Why? Roster capacity details", "Team needs details",
    "Injured Center", "already in an injury slot", "Yahoo note: Knee", "Transaction legality", "Roster occupancy by slot",
    "Schedule gaps by date", "6 of 10", "C, UTIL", "Injury return timing is not forecast",
    "9 of 10 starting slots can be covered by 11 lineup-eligible players", "Needs evidence is <strong>partial</strong>"]) {
    assert.ok(situation.includes(text), text);
  }
  const needs = situation.slice(situation.indexOf('<ol class="waiver-need-summary">'), situation.indexOf("</ol>", situation.indexOf('<ol class="waiver-need-summary">')));
  assert.ok(needs.indexOf(">HIGH<") < needs.indexOf(">MEDIUM<") && needs.indexOf(">MEDIUM<") < needs.indexOf(">COVERED<"));
  assert.doesNotMatch(needs, /UTIL|BN/, "UTIL and bench are not positional needs");
  assert.doesNotMatch(situation, /Need score|<details class="waiver-details" open/);
});

test("WATCH and HOLD stay separate from actionable additions", () => {
  const { OtherGoodOptions } = load();
  const watchBoard = supportedBoard({ state: "WATCH", supported_count: 0, watch_ids: [24],
    headline: "No measured option is strong enough to feature; watch the players below." });
  const html = moves(fillAnalysis([]), watchBoard);
  assert.match(html, /<h3>HOLD<\/h3>/);
  assert.match(html, /No measured option is strong enough to feature/);
  assert.doesNotMatch(html, /waiver-move-card|ADD ONLY<\/span>/);
  const options = render(OtherGoodOptions, { board: watchBoard, analysis: fillAnalysis([]), onDetails() {}, onAnalyzePair() {} });
  assert.match(options, /OTHER GOOD OPTIONS/);
  for (const title of ["BEST GUARD", "BEST WING / FORWARD", "BEST CENTER", "BEST MULTI-POSITION OPTION", "BEST SHORT-TERM SCHEDULE", "BEST LONGER-TERM OPTION"]) {
    assert.ok(options.includes(`<h3>${title}</h3>`), title);
  }
  assert.match(options, /<h3>WATCHLIST<\/h3>/);
  assert.match(options, /These are not add recommendations/);
  assert.match(options, /The best option here is already shown above: Measured Guard\./);
  const watchList = options.slice(options.indexOf("<h3>WATCHLIST</h3>"));
  assert.match(watchList, /Watch Forward/);
  assert.doesNotMatch(watchList, /is-add_only|ADD ONLY</);
  assert.equal(options.match(/>Group Wing</g).length, 1, "a featured player is shown once");
});

test("undetermined capacity with measurable players shows a BEST MEASURED OPTION, never a supported add", () => {
  const { TeamSituation } = load();
  const stale = { ...board(null), candidates: [], roster_capacity: capacity("UNDETERMINED") };
  const situation = render(TeamSituation, { board: stale });
  assert.match(situation, /ROSTER CAPACITY NEEDS A YAHOO REFRESH/);
  assert.match(situation, /Yahoo roster slots are not saved for 13 of 13 players/);
  assert.match(situation, /Capacity is not decision-ready\. No drop is assumed and ADD \+ DROP is not used as a default\./);
  const blocked = transactionAnalysis(null, {
    decision: "INSUFFICIENT EVIDENCE", recommended_action_type: "INSUFFICIENT_EVIDENCE", roster_capacity: capacity("UNDETERMINED"),
    decision_reasons: ["Yahoo slot assignments (selected_position) are not persisted for 13 of 13 roster players."],
    evaluated_pair_count: 0, watch_transactions: [],
  });
  const html = moves(blocked, stale);
  assert.match(html, /No supported move yet: Your saved roster is from 2026-10-25/);
  assert.match(html, /<span class="waiver-action is-best_measured_option">BEST MEASURED OPTION<\/span><h3 class="waiver-move-player">Measured Guard<\/h3>/);
  for (const text of [LABELS[UNROSTERED], "NOT YET A SUPPORTED ADD", `Yahoo status: <strong>UNKNOWN</strong>. ${BLANK}`,
    "Confirm in Yahoo:", "Free-agent or waiver state in Yahoo", "Current Yahoo status", "Whether you have an open roster spot",
    "CHECK IN YAHOO", "Best measurable fit for", "PG / SG", "Why this is not a supported add (2)", "4 games in Rest of Week (stale schedule)"]) {
    assert.ok(html.includes(text), text);
  }
  assert.doesNotMatch(html, /is-add_only|ADD ONLY<|MUST ADD|STREAM|<h3>HOLD<\/h3>/);
  const failed = moves(null, stale, apiFailure(502, "BAD_GATEWAY", "The server is temporarily unavailable."));
  assert.match(failed, /<p class="waiver-failure-title">WAIVER ANALYSIS UNAVAILABLE<\/p><p>The server is temporarily unavailable\.<\/p>/);
  assert.match(failed, /The best-move analysis is unavailable; this error is not a HOLD decision\./);
  assert.doesNotMatch(failed, /<h3>HOLD<\/h3>|BEST MEASURED OPTION|Loading best move analysis/);
  const none = moves(blocked, { ...stale, decision_support: decisionSupport({ state: "UNAVAILABLE", best_measured_ids: [],
    headline: "No player can be compared yet.", detail: "Persisted evidence cannot support a measured comparison: No current-season NBA games: 82." }) });
  assert.match(none, /<h3>INSUFFICIENT EVIDENCE<\/h3>/);
  assert.match(none, /No player can be compared yet\./);
  assert.match(none, /No current-season NBA games: 82/);
});

test("stale league rosters feature nobody: unverified players are separate potential targets, never moves", () => {
  const { OtherGoodOptions } = load();
  const html = render(OtherGoodOptions, { board: staleBoard(), analysis: null, onDetails() {}, onAnalyzePair() {} });
  assert.match(html, /Players who were not on any saved league roster appear only as POTENTIAL TARGETS TO CHECK IN YAHOO/);
  assert.match(html, /<section class="waiver-potential" aria-labelledby="waiver-potential-title"><h3 id="waiver-potential-title">POTENTIAL TARGETS TO CHECK IN YAHOO<\/h3>/);
  assert.match(html, /2 measurable players were not on any saved league roster/);
  const featured = html.slice(0, html.indexOf('<section class="waiver-potential"'));
  assert.doesNotMatch(featured, /Potential Forward|Unverified Guard|waiver-option-name/, "unverified players are never featured");
  const list = html.slice(html.indexOf('<ol class="waiver-potential-list">'));
  assert.match(list, /Potential Forward/);
  assert.match(list, /Unverified Guard/);
  assert.match(list, /Yahoo status: UNKNOWN · Availability: <span class="waiver-availability is-unverified">SAVED ROSTERS STALE — CHECK IN YAHOO<\/span>/);
  assert.match(list, /<span class="waiver-availability is-unverified">AVAILABILITY UNVERIFIED<\/span>/);
  assert.match(list, /CHECK IN YAHOO/);
  const best = moves(transactionAnalysis(null, { recommended_action_type: "INSUFFICIENT_EVIDENCE", roster_capacity: capacity("UNDETERMINED"),
    watch_transactions: [], decision_reasons: ["Saved Yahoo rosters are stale."] }), staleBoard());
  assert.match(best, /<h3>NO CONFIRMED AVAILABLE PLAYER<\/h3><p>No player is confirmed available yet\.<\/p>/);
  assert.doesNotMatch(best, /waiver-move-card|Potential Forward|Unverified Guard|ADD ONLY<|ADD \+ DROP<|BEST MEASURED OPTION/);
  const rosteredTarget = render(OtherGoodOptions, { board: staleBoard({ decision_support: staleSupport({
    potential_target_ids: [41, 43], options: [...staleSupport().options, potential(43, "Rostered Elsewhere Guard", "ROSTERED_BY_OTHER_TEAM")] }) }),
  analysis: null, onDetails() {}, onAnalyzePair() {} });
  assert.doesNotMatch(rosteredTarget, /Rostered Elsewhere Guard/, "a player on another team is not even a potential target");
  const confirmed = render(OtherGoodOptions, {
    board: { ...board(null), decision_support: decisionSupport({ availability_state: "available", potential_target_ids: [] }) },
    analysis: null, onDetails() {}, onAnalyzePair() {},
  });
  assert.doesNotMatch(confirmed, /POTENTIAL TARGETS TO CHECK IN YAHOO/);
});

test("compare a specific drop is collapsed and de-emphasized unless the roster is full, and never preselected", () => {
  const { CompareDropSection } = load();
  const props = { selectedDropId: null, onSelect() {}, replacementBoard: null, loading: false, error: "", onAnalyze() {} };
  const open = render(CompareDropSection, { ...props, board: board(null) });
  assert.match(open, /class="panel waiver-panel waiver-compare is-muted"/);
  assert.match(open, /<details class="waiver-compare-picker"><summary>Show the optional drop comparison<\/summary>/);
  assert.match(open, /Optional: no drop is required for your next add/);
  assert.match(open, /name="selected-drop"/);
  assert.doesNotMatch(open, /checked=""/);
  const undetermined = render(CompareDropSection, { ...props, board: { ...board(null), roster_capacity: capacity("UNDETERMINED") } });
  assert.match(undetermined, /is-muted/);
  assert.match(undetermined, /no drop is assumed/);
  assert.doesNotMatch(undetermined, /<details class="waiver-compare-picker" open/);
  const full = render(CompareDropSection, { ...props, board: { ...board(null), roster_capacity: capacity("ADD_DROP") } });
  assert.match(full, /class="panel waiver-panel waiver-compare is-promoted"/);
  assert.match(full, /<details class="waiver-compare-picker" open="">/);
  assert.doesNotMatch(full, /checked=""/);
});

test("page order puts recommendations before diagnostics, and list, evidence and compare start collapsed", () => {
  const analysis = { mode: "this_week", reload: 0, analysis: fillAnalysis([fill()]) };
  const states = ["this_week", board(null), null, null, null, false, false, null, "", 0, null, null, analysis, null, refreshStatus("stale")];
  const html = renderToStaticMarkup(React.createElement(load(states).WaiverCenter));
  assert.match(html, /<h1>Waiver Command Center<\/h1><p class="waiver-team">Box Score Bully<\/p>/);
  assert.equal(html.match(/>REFRESH WAIVER DATA<\/button>/g).length, 1, "one refresh action on the page");
  assert.doesNotMatch(html, /\/api\/v1|curl|Swagger|players\/import|nba\/import|leagues\/import|recent_days|docker/i,
    "no endpoint, curl, Swagger or Docker instructions in the normal UI");
  assert.doesNotMatch(html, /\bPOST\b/);
  const order = ["WAIVER DATA NEEDS A REFRESH", "TEAM SITUATION", "BEST MOVES RIGHT NOW", "OTHER GOOD OPTIONS", "COMPARE A SPECIFIC DROP", "FULL WAIVER LIST", "ADVANCED EVIDENCE"]
    .map((text) => html.indexOf(`>${text}</h2>`));
  assert.ok(order.every((index) => index >= 0), String(order));
  assert.deepEqual([...order].sort((left, right) => left - right), order);
  assert.ok(html.indexOf(">Available Center<") < html.indexOf("Persisted evidence coverage"), "recommendations precede diagnostics");
  assert.equal(html.split(VERSION).length - 1, 1, "the model version appears once");
  assert.ok(html.indexOf(`Model version ${VERSION}`) > html.indexOf(">ADVANCED EVIDENCE</h2>"));
  for (const pattern of [/<details class="waiver-full-list" open/, /<details class="waiver-advanced" open/, /<details class="waiver-compare-picker" open/]) {
    assert.doesNotMatch(html, pattern);
  }
  assert.match(html, /name="selected-drop"/);
  assert.doesNotMatch(html, /name="selected-drop" value="\d+" checked=""/);
  assert.doesNotMatch(html, /Top 3 replacements/);
  assert.match(html, /name="waiver-mode" checked=""\/>Rest of Week/);
  assert.match(html, /Rest of Week · limited days remaining/);
  assert.doesNotMatch(html, /Stale deployed version|ROS Projection|FAAB|confidence|My Team|Selected Team/);
  const loading = renderToStaticMarkup(React.createElement(load(NO_STATE.map((value, index) => index === 5 ? true : value)).WaiverCenter));
  assert.match(loading, /Loading persisted waiver evidence/);
  assert.match(loading, /Loading best move analysis/);
  assert.doesNotMatch(loading, /TEAM SITUATION/);
  const timeout = apiFailure(504, "GATEWAY_TIMEOUT", "The server took too long to respond.", { requestId: "req-504" });
  const failed = renderToStaticMarkup(React.createElement(load(NO_STATE.map((value, index) => index === 7 ? timeout : value)).WaiverCenter));
  assert.match(failed, /<h2 id="waiver-situation">TEAM SITUATION<\/h2><div class="waiver-failure" role="alert"><p class="waiver-failure-title">WAIVER ANALYSIS TIMED OUT<\/p>/);
  assert.match(failed, /The saved data was not changed\. Retry the analysis, or refresh the evidence if its timestamps are stale\./);
  assert.match(failed, /Request ID: req-504\./);
  assert.match(failed, />RETRY ANALYSIS<\/button>/);
  assert.match(failed, /Best moves are withheld/);
  assert.doesNotMatch(failed, /<h3>HOLD<\/h3>|Loading best move analysis|waiver-move-card|<html|nginx/);
  const mismatch = renderToStaticMarkup(React.createElement(load(NO_STATE.map((value, index) => index === 1 ? { ...board(null), model_version: "waiver-availability-phase5" } : value)).WaiverCenter));
  assert.match(mismatch, /Stale deployed version: waiver-availability-phase5/);
  assert.doesNotMatch(mismatch, /TEAM SITUATION|OTHER GOOD OPTIONS/);
});

test("routes, GET-only waiver API, Pacific time, responsive overflow and modal focus are wired", () => {
  assert.match(app, /path="\/waivers" element={<WaiverCenter/);
  assert.match(api, /getWaiverReplacements/);
  assert.match(api, /\/waivers\/replacements/);
  assert.match(api, /drop_player_id/);
  const waiverApi = api.slice(api.indexOf("getWaivers:"), api.indexOf("getLeagues:"));
  assert.deepEqual(waiverApi.match(/method: "[A-Z]+"/g), ['method: "POST"'], "page reads are GET-only; one deliberate mutation");
  assert.match(waiverApi, /startWaiverRefresh: \(retryFailed = false\) =>\s*request<WaiverRefreshStatus>\("\/api\/v1\/waivers\/refresh", \{\s*method: "POST"/);
  assert.equal(source.match(/api\.startWaiverRefresh\(/g).length, 1, "one frontend call starts the whole refresh");
  assert.doesNotMatch(source, /importLeagues|importPlayers|\/(leagues|players|nba)\/import/, "the page never chains provider imports");
  assert.match(source, /api\.getWaiverImpact\(playerId, mode, dropPlayerId \?\? undefined/);
  assert.match(source, /controller\.abort\(\)/);
  assert.match(source, /element\?\.showModal\(\)/);
  assert.match(source, /previousFocus\.focus\(\)/);
  assert.match(source, /onCancel={onClose}/);
  assert.match(source, /autoFocus/);
  assert.doesNotMatch(source, /api\.(addPlayer|dropPlayer|executeTransaction)|method: "(POST|PUT|DELETE)"/);
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.waiver-center/);
  assert.match(css, /\.waiver-table-scroll[^}]*overflow-x: auto/);
  assert.match(css, /\.waiver-center :focus-visible/);
});

test("global HOLD is first class and positive WATCH swaps stay in the watchlist, not promoted", () => {
  const { OtherGoodOptions } = load();
  const holdBoard = { ...board(null), roster_capacity: capacity("ADD_DROP"), decision_support: decisionSupport({
    state: "WATCH", best_measured_ids: [], headline: "No measured option out-produces your lowest-producing roster player." }) };
  const html = moves(transactionAnalysis(), holdBoard);
  assert.match(html, /BEST MOVES RIGHT NOW/);
  assert.match(html, /<span class="waiver-action is-hold">HOLD<\/span> <span class="waiver-strict-text">No supported move currently improves Box Score Bully\.<\/span>/);
  assert.match(html, /<h3>HOLD<\/h3>/);
  assert.match(html, /No measured option out-produces your lowest-producing roster player/);
  assert.doesNotMatch(html, /waiver-move-card|Best Add|confidence|ROS Projection/);
  const options = render(OtherGoodOptions, { board: holdBoard, analysis: transactionAnalysis(), onDetails() {}, onAnalyzePair() {} });
  assert.match(options, /Measured swaps to watch/);
  assert.match(options, /WATCH: Available Center \/ drop Bench Forward/);
});

test("WATCH swaps show the backend-named sample and status gates instead of a reconstructed reason", () => {
  // Real-data regression (2026-11-14): a 12-game add was told "current role, status, schedule, or replacement
  // evidence remains insufficient" while the failing count was the drop's 6 games in the last 14 days.
  const { OtherGoodOptions } = load();
  const base = transactionAnalysis();
  const [swap] = base.watch_transactions;
  const blockers = [
    "Sample gate: Bench Forward 6 games in the last 14 days. A supported move needs 7 games this season and 7 in the last 14 days for every compared player; prior-season history cannot bypass this gate.",
    "Yahoo status gate: Available Center blank (UNKNOWN); Bench Forward blank (UNKNOWN). Blank, unrecognized or stale Yahoo status is UNKNOWN, not healthy, so strong recommendations are blocked.",
  ];
  const analysis = { ...base, watch_transactions: [{ ...swap,
    add_player: { ...swap.add_player, current_season_games: 12, evidence_blockers: blockers } }] };
  const holdBoard = { ...board(null), roster_capacity: capacity("ADD_DROP"),
    decision_support: decisionSupport({ state: "WATCH", best_measured_ids: [] }) };
  const html = render(OtherGoodOptions, { board: holdBoard, analysis, onDetails() {}, onAnalyzePair() {} });
  assert.match(html, /Why not add:<\/strong> Sample gate: Bench Forward 6 games in the last 14 days\./);
  assert.match(html, /Yahoo status gate: Available Center blank \(UNKNOWN\); Bench Forward blank \(UNKNOWN\)\./);
  assert.doesNotMatch(html, /seven-game eligibility gate|replacement evidence remains insufficient/);
});

test("full-roster supported transaction renders the exact add/drop pair with GET-only API", () => {
  const analysis = transactionAnalysis(true);
  const html = moves(analysis, pairBoard(analysis));
  assert.match(html, /<span class="waiver-action is-add_drop">ADD \+ DROP<\/span><h3 class="waiver-move-player">ADD: Available Center<\/h3>/);
  assert.match(html, /DROP: <strong>Bench Forward<\/strong>/);
  assert.match(html, /Drop<\/dt><dd>Required: your roster is full<\/dd>/);
  assert.match(html, /\(\+5\)/);
  assert.match(html, /Starting-slot coverage/);
  assert.match(html, /Why a drop is required: All 13 non-injury roster spots are occupied/);
  assert.match(html, /View details: ADD Available Center \/ DROP Bench Forward/);
  assert.match(html, /CONFIRM IN YAHOO BEFORE ACTING/);
  assert.match(api, /getWaiverTransactions/);
  assert.match(api, /\/waivers\/transactions/);
});

test("incompatible model versions fail closed for board, replacement and transaction surfaces", () => {
  const { FullWaiverList, Replacements } = load();
  const staleBoard = { ...board(), model_version: "waiver-availability-phase5" };
  const boardHtml = render(FullWaiverList, { board: staleBoard, onDetails() {} });
  const replacementHtml = render(Replacements, { board: staleBoard, loading: false, error: "", selectedDropId: 2, onAnalyze() {} });
  for (const html of [boardHtml, replacementHtml]) {
    assert.match(html, /role="alert"/);
    assert.match(html, /incompatible model waiver-availability-phase5/);
    assert.doesNotMatch(html, /ADD: Available Center|WATCH: Available Center|ADD ONLY:/);
  }
  const transactionHtml = moves({ ...transactionAnalysis(true), model_version: "waiver-availability-phase5" }, board(null));
  assert.match(transactionHtml, /role="alert"/);
  assert.match(transactionHtml, /does not match this page version/);
  assert.doesNotMatch(transactionHtml, /ADD: Available Center|BEST MEASURED OPTION|is-add_only/);
});

test("impact surfaces reject stale model responses instead of rendering player recommendations", () => {
  const { ImpactContent } = load();
  const html = render(ImpactContent, {
    impact: {
      league_key: "league", team_key: "team", mode: "this_week",
      model_version: "waiver-availability-phase5", candidate: candidate(1, "Available Center"),
      comparison: drop(2), limitations: [],
    },
    selectedDropId: 2,
  });
  assert.match(html, /role="alert"/);
  assert.match(html, /Impact evidence uses incompatible model waiver-availability-phase5/);
  assert.doesNotMatch(html, /Available Center: add\/drop analysis/);
});

test("API failures are normalized: HTML/JSON 504, plain text, timeout, abort, network and retry never expose bodies", async () => {
  const originalFetch = globalThis.fetch;
  const originalSetTimeout = globalThis.setTimeout;
  const { ApiError, api: client, isTimeoutError } = loadApi();
  const nginx = "<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n<body>\r\n<center><h1>504 Gateway Time-out</h1></center>\r\n"
    + "<hr><center>nginx/1.27.4</center>\r\n</body>\r\n</html>\r\n<!-- a padding to disable MSIE and Chrome friendly error page -->\r\n";
  const rejects = (call, check) => assert.rejects(call, (error) => {
    assert.ok(error instanceof ApiError);
    check(error);
    return true;
  });
  const json = (body, status, headers = {}) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json", ...headers } });
  try {
    globalThis.fetch = async () => new Response(nginx, { status: 504, headers: { "Content-Type": "text/html", "X-Request-ID": "nginx-req-1" } });
    await rejects(client.getWaivers("this_week"), (error) => {
      assert.deepEqual([error.status, error.code, error.retryable, error.requestId], [504, "GATEWAY_TIMEOUT", true, "nginx-req-1"]);
      assert.equal(error.message, "The server took too long to respond.");
      assert.ok(isTimeoutError(error));
      assert.doesNotMatch(error.message, /<|nginx|Gateway Time-out|MSIE/);
    });

    globalThis.fetch = async () => json({ detail: "Waiver analysis exceeded the server time limit." }, 504);
    await rejects(client.getWaiverTransactions("this_week"), (error) => {
      assert.deepEqual([error.code, error.message], ["GATEWAY_TIMEOUT", "Waiver analysis exceeded the server time limit."]);
      assert.ok(isTimeoutError(error));
    });

    globalThis.fetch = async () => json({ detail: "<html><body>proxy page</body></html>" }, 502);
    await rejects(client.getWaivers("this_week"), (error) => assert.deepEqual([error.code, error.message], ["BAD_GATEWAY", "The server is temporarily unavailable."]));
    globalThis.fetch = async () => new Response("upstream returned plain text", { status: 502 });
    await rejects(client.getWaivers("this_week"), (error) => assert.equal(error.message, "The server is temporarily unavailable."));
    globalThis.fetch = async () => json({ detail: "x".repeat(2000) }, 400);
    await rejects(client.getWaivers("this_week"), (error) => assert.equal(error.message.length, 401, "long messages are capped"));
    globalThis.fetch = async () => json({ detail: { unknown: "server detail" } }, 400);
    await rejects(client.getWaivers("this_week"), (error) => assert.equal(error.message, "The request failed (HTTP 400)."));

    globalThis.fetch = async () => json({ detail: "String API error" }, 400);
    await rejects(client.getWaivers("this_week"), (error) => assert.deepEqual([error.status, error.message, error.retryable], [400, "String API error", false]));
    globalThis.fetch = async () => json({ detail: { message: "Persisted league contract mismatch; waiver analysis blocked",
      mismatches: ["scoring_type: persisted 'head', expected 'headpoint'", "num_teams: persisted '10', expected '12'"] } }, 409);
    await rejects(client.getWaiverTransactions("this_week"), (error) => {
      assert.equal(error.message, "Persisted league contract mismatch; waiver analysis blocked · scoring_type: persisted 'head', expected 'headpoint' · num_teams: persisted '10', expected '12'");
      assert.equal(error.mismatches.length, 2);
    });
    globalThis.fetch = async () => json({ detail: [{ loc: ["query", "mode"], msg: "Input should be 'this_week', 'next_7_days' or 'ros'", type: "literal_error" }] }, 422);
    await rejects(client.getWaivers("this_week"), (error) => assert.equal(error.message, "Input should be 'this_week', 'next_7_days' or 'ros'"));
    globalThis.fetch = async () => json({ detail: { code: "RECOMMENDATION_CONTRACT_VIOLATION",
      message: "The waiver board named players outside the current waiver-eligible candidate set; the result was withheld.",
      violations: ["best_measured: player 9 is not waiver-eligible"] } }, 500, { "X-Request-ID": "req-contract" });
    await rejects(client.getWaivers("this_week"), (error) => {
      assert.deepEqual([error.code, error.retryable, error.requestId], ["RECOMMENDATION_CONTRACT_VIOLATION", false, "req-contract"]);
      assert.doesNotMatch(error.message, /player 9/);
    });
    globalThis.fetch = async () => json({ detail: { code: "PROVIDER_IMPORT_IN_PROGRESS",
      message: "A waiver data refresh or another Yahoo/NBA import is already running. Wait for it to finish, then retry." } }, 409);
    await rejects(client.startWaiverRefresh(), (error) => assert.deepEqual([error.status, error.code], [409, "PROVIDER_IMPORT_IN_PROGRESS"]));

    globalThis.setTimeout = (callback) => { queueMicrotask(callback); return 0; };
    globalThis.fetch = (_path, init) => new Promise((_resolve, reject) =>
      init.signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError"))));
    await rejects(client.getWaivers("this_week"), (error) => {
      assert.deepEqual([error.status, error.code, error.retryable], [0, "TIMEOUT", true]);
      assert.ok(isTimeoutError(error));
    });
    globalThis.setTimeout = originalSetTimeout;
    const caller = new AbortController();
    const pending = client.getWaivers("this_week", caller.signal);
    caller.abort();
    await rejects(pending, (error) => assert.deepEqual([error.code, error.retryable], ["ABORTED", false]));
    globalThis.fetch = async () => { throw new TypeError("synthetic network failure"); };
    await rejects(client.getWaivers("this_week"), (error) => {
      assert.deepEqual([error.code, error.retryable], ["NETWORK_ERROR", true]);
      assert.doesNotMatch(error.message, /synthetic/);
    });

    let calls = 0;
    globalThis.fetch = async () => ++calls === 1 ? new Response(nginx, { status: 504 }) : json({ recovered: true }, 200);
    await rejects(client.getWaivers("this_week"), (error) => assert.equal(error.code, "GATEWAY_TIMEOUT"));
    assert.deepEqual(await client.getWaivers("this_week"), { recovered: true }, "a retry after a 504 recovers");

    const seen = [];
    globalThis.fetch = async (path, init = {}) => {
      seen.push({ path, method: init.method ?? "GET", body: init.body ?? null, type: init.headers?.["Content-Type"] ?? null });
      return json(refreshStatus("stale"), init.method === "POST" ? 202 : 200);
    };
    await client.getWaiverRefresh();
    await client.startWaiverRefresh(true);
    assert.deepEqual(seen, [
      { path: "/api/v1/waivers/refresh", method: "GET", body: null, type: null },
      { path: "/api/v1/waivers/refresh", method: "POST", body: '{"retry_failed":true}', type: "application/json" },
    ]);
  } finally {
    globalThis.fetch = originalFetch;
    globalThis.setTimeout = originalSetTimeout;
  }
});

test("display failures are built from normalized fields only", () => {
  const { toFailure } = load();
  assert.deepEqual(toFailure({ status: 504, code: "GATEWAY_TIMEOUT", message: "The server took too long to respond.", retryable: true, requestId: "abc" }, "fallback"),
    { status: 504, code: "GATEWAY_TIMEOUT", message: "The server took too long to respond.", retryable: true, requestId: "abc" });
  assert.deepEqual(toFailure(new TypeError("<html><center>nginx</center></html>"), "Could not load waiver evidence."),
    { status: 0, code: "UNKNOWN", message: "Could not load waiver evidence.", retryable: true, requestId: null });
});

test("refresh panel offers one action, names stale sources, keeps details collapsed and shows no endpoint instructions", () => {
  const { WaiverRefreshPanel } = load();
  const html = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("stale")) });
  assert.match(html, /<section class="panel waiver-refresh is-stale" aria-labelledby="waiver-refresh-title">/);
  assert.match(html, /<h2 id="waiver-refresh-title">WAIVER DATA NEEDS A REFRESH<\/h2>/);
  assert.match(html, /Stale or missing: Yahoo rosters, Roster slots, Yahoo availability and status, NBA game logs\./);
  assert.equal(html.match(/<button/g).length, 1, "a single refresh action");
  assert.match(html, /<button type="button" class="button button-primary">REFRESH WAIVER DATA<\/button>/);
  assert.match(html, /<details class="waiver-refresh-details"><summary>Source details<\/summary>/);
  assert.match(html, /Yahoo rosters<\/span><span class="waiver-refresh-state">Stale — 12 of 12 teams<\/span>/);
  assert.match(html, /No complete refresh recorded yet\./);
  assert.doesNotMatch(html, /\/api\/|curl|Swagger|docker|query param/i);
  assert.doesNotMatch(html, /\bPOST\b/);
  const current = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("current")) });
  assert.match(current, /<h2 id="waiver-refresh-title">WAIVER DATA IS CURRENT<\/h2>/);
  assert.match(current, /All 10 sources are current\./);
  assert.match(current, /class="button button-quiet">REFRESH WAIVER DATA<\/button>/);
  for (const row of ["Yahoo league/settings</span><span class=\"waiver-refresh-state\">Current — Bully League · 12 teams",
    "Yahoo player pool</span><span class=\"waiver-refresh-state\">Current — 612 players",
    "Yahoo rosters</span><span class=\"waiver-refresh-state\">Current — 12 of 12 teams",
    "Roster slots</span><span class=\"waiver-refresh-state\">Current — 15 of 15 saved",
    "NBA game logs</span><span class=\"waiver-refresh-state\">Current — Latest game 2026-11-13",
    "NBA schedule</span><span class=\"waiver-refresh-state\">Current", "NBA season stats</span><span class=\"waiver-refresh-state\">Current"]) {
    assert.ok(current.includes(row), row);
  }
  assert.match(current, /Last successful complete refresh: November 13, 2026(,| at) 7:42\sPM PST/);
  const unreadable = render(WaiverRefreshPanel, { refresh: refreshController(null, {
    failure: apiFailure(503, "SERVICE_UNAVAILABLE", "The server is temporarily unavailable.", { requestId: "req-9" }) }) });
  assert.match(unreadable, /Saved-evidence freshness could not be read/);
  assert.match(unreadable, /role="alert">The server is temporarily unavailable\. Request ID: req-9\.<\/p>/);
  assert.match(unreadable, /class="button button-primary">REFRESH WAIVER DATA<\/button>/);
});

test("refresh progress renders stage states, disables the button while running and announces progress", () => {
  const { WaiverRefreshPanel } = load();
  const job = refreshJob(["SUCCEEDED", "SUCCEEDED", "RUNNING"]);
  const html = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("stale", job), { announcement: "Refreshing waiver data." }) });
  assert.match(html, /<h2 id="waiver-refresh-title">REFRESHING WAIVER DATA<\/h2>/);
  assert.match(html, /2 of 10 steps finished · Yahoo rosters: running\./);
  assert.match(html, /<button type="button" class="button button-primary" disabled="">REFRESHING…<\/button>/);
  assert.doesNotMatch(html, /RETRY FAILED STAGE|<details class="waiver-refresh-details">/);
  assert.match(html, /<div tabindex="-1" role="group" class="waiver-refresh-progress" aria-label="Refresh progress by source">/);
  assert.match(html, /<li class="is-succeeded"><span class="waiver-refresh-stage">Yahoo league\/settings<\/span><span class="waiver-refresh-state">Updated — Bully League · 12 teams<\/span><\/li>/);
  assert.match(html, /<li class="is-running"><span class="waiver-refresh-stage">Yahoo rosters<\/span><span class="waiver-refresh-state">Running<\/span><\/li>/);
  assert.match(html, /<li class="is-pending"><span class="waiver-refresh-stage">NBA game logs<\/span><span class="waiver-refresh-state">Waiting<\/span><\/li>/);
  assert.match(html, /<p class="sr-only" role="status" aria-live="polite">Refreshing waiver data\.<\/p>/);
  const requesting = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("stale"), { requesting: true }) });
  assert.match(requesting, /disabled="">REFRESHING…<\/button>/);
});

test("partial and failed refreshes name the exact failed stage, keep successful sources and offer RETRY FAILED STAGE", () => {
  const { WaiverRefreshPanel } = load();
  const done = Array(10).fill("SUCCEEDED");
  done[7] = "FAILED";
  done[8] = "SKIPPED";
  const job = refreshJob(done, { state: "PARTIAL_FAILURE", active: false, completed_at: "2026-11-14T03:44:00Z", board_reload_recommended: true });
  job.stages[7] = { ...job.stages[7], error_code: "NBA_SOURCE_FAILED",
    message: "The NBA statistics source did not return usable data. The previous NBA snapshot was kept." };
  job.stages[8] = { ...job.stages[8], summary: "Not run because NBA game logs failed; the previous NBA snapshot was kept." };
  const html = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("stale", job)) });
  assert.match(html, /<section class="panel waiver-refresh is-failed"/);
  assert.match(html, /<h2 id="waiver-refresh-title">REFRESH PARTIALLY COMPLETED<\/h2>/);
  assert.match(html, /Successful sources were saved\. Failed sources kept their previous data and remain stale\./);
  assert.match(html, /<li>Yahoo roster data updated successfully\.<\/li>/);
  assert.doesNotMatch(html, /NBA data updated successfully/);
  assert.match(html, /<li><strong>NBA game logs failed\.<\/strong> The NBA statistics source did not return usable data\. The previous NBA snapshot was kept\.<\/li>/);
  assert.match(html, /<button class="button button-primary" type="button">RETRY FAILED STAGE<\/button><button type="button" class="button button-quiet">REFRESH WAIVER DATA<\/button>/);
  assert.match(html, /<details class="waiver-refresh-details"><summary>Stage details<\/summary>/);
  assert.match(html, /<li class="is-failed"><span class="waiver-refresh-stage">NBA game logs<\/span><span class="waiver-refresh-state">Failed — The NBA statistics source/);
  assert.match(html, /<li class="is-skipped"><span class="waiver-refresh-stage">NBA season stats<\/span><span class="waiver-refresh-state">Skipped — Not run because NBA game logs failed/);
  const failedJob = refreshJob(["FAILED", "SKIPPED", "SKIPPED", "SKIPPED", "SKIPPED"], { state: "FAILED", active: false,
    message: "Yahoo rejected the saved authorization. Reconnect Yahoo, then refresh again." });
  failedJob.stages[0].message = "Yahoo rejected the saved authorization. Reconnect Yahoo, then refresh again.";
  const failed = render(WaiverRefreshPanel, { refresh: refreshController(refreshStatus("stale", failedJob)) });
  assert.match(failed, /<h2 id="waiver-refresh-title">REFRESH FAILED<\/h2>/);
  assert.match(failed, /<strong>Yahoo league\/settings failed\.<\/strong> Yahoo rejected the saved authorization/);
  assert.match(failed, /RETRY FAILED STAGE/);
  assert.doesNotMatch(failed, /updated successfully/);
});

test("supported cards require an eligible, actionable candidate; otherwise BEST MOVES fails closed with a contract error", () => {
  const notEligible = moves(fillAnalysis([fill()]), { ...supportedBoard(), eligible_candidate_ids: [3, 21] });
  assert.match(notEligible, /<div class="waiver-contract-error" role="alert"><p><strong>WAIVER MODEL CONTRACT ERROR<\/strong><\/p><p>A recommendation for Available Center was withheld because the player is not in the current waiver-eligible candidate set\./);
  assert.doesNotMatch(notEligible, /waiver-move-card|ADD ONLY<\/span>|<h3>HOLD<\/h3>|waiver-strict-status/);
  const rosteredPair = transactionAnalysis(true);
  rosteredPair.best_transaction = { ...rosteredPair.best_transaction,
    add_player: { ...rosteredPair.best_transaction.add_player, availability_classification: "ROSTERED_BY_OTHER_TEAM" } };
  const pair = moves(rosteredPair, pairBoard(rosteredPair));
  assert.match(pair, /A recommendation for Available Center was withheld because the player&#x27;s Yahoo availability is not confirmed\./);
  assert.doesNotMatch(pair, /ADD: Available Center|ADD \+ DROP<\/span>/);
  const unverified = supportedBoard({ state: "BEST_MEASURED_OPTION", supported_count: 0, best_measured_ids: [41],
    options: [potential(41, "Unverified Wing", "AVAILABILITY_UNVERIFIED", { classification: "BEST_MEASURED_OPTION" })] });
  const measuredHtml = moves(fillAnalysis([]), unverified);
  assert.match(measuredHtml, /A recommendation for Unverified Wing was withheld/);
  assert.doesNotMatch(measuredHtml, /waiver-move-card|BEST MEASURED OPTION<\/span>/);
  const confirmed = moves(fillAnalysis([fill()]), supportedBoard());
  assert.match(confirmed, /waiver-move-card is-supported/);
  assert.doesNotMatch(confirmed, /WAIVER MODEL CONTRACT ERROR/);
  const waiverClaim = fill(1, "Waiver Center");
  waiverClaim.add_player = { ...waiverClaim.add_player, availability_classification: "CONFIRMED_WAIVER",
    availability_evidence: availabilityEvidence("CONFIRMED_WAIVER") };
  assert.match(moves(fillAnalysis([waiverClaim]), supportedBoard()), /ON WAIVERS \(YAHOO\)<\/span> · clears 2026-11-15/);
});

test("featured OTHER GOOD OPTIONS must be eligible too; a failed check withholds the player", () => {
  const { OtherGoodOptions } = load();
  const result = { ...board(null), eligible_candidate_ids: [1, 3, 21, 23, 24, 25] };
  const html = render(OtherGoodOptions, { board: result, analysis: null, onDetails() {}, onAnalyzePair() {} });
  assert.match(html, /A recommendation for Group Wing was withheld because the player is not in the current waiver-eligible candidate set/);
  const wing = html.slice(html.indexOf("<h3>BEST WING / FORWARD</h3>"), html.indexOf("<h3>BEST CENTER</h3>"));
  assert.match(wing, /Withheld: this option failed the waiver-eligibility check\./);
  assert.doesNotMatch(wing, /Group Wing/);
  assert.match(html, /Watch Center/);
});

test("after an API error nothing from an earlier analysis stays actionable", () => {
  const timeout = apiFailure(504, "GATEWAY_TIMEOUT", "The server took too long to respond.", { requestId: "req-1" });
  const html = moves(fillAnalysis([fill()]), supportedBoard(), timeout);
  assert.match(html, /<p class="waiver-failure-title">WAIVER ANALYSIS TIMED OUT<\/p><p>The saved data was not changed\. Retry the analysis, or refresh the evidence if its timestamps are stale\.<\/p>/);
  assert.match(html, /<button class="button button-primary" type="button">RETRY ANALYSIS<\/button><button class="button button-quiet" type="button">REFRESH WAIVER DATA<\/button>/);
  assert.match(html, /this error is not a HOLD decision\. Request ID: req-1\./);
  assert.doesNotMatch(html, /waiver-move-card|ADD ONLY<|Available Center|<h3>HOLD<\/h3>|Loading best move/);
  const clientTimeout = moves(null, supportedBoard(), apiFailure(0, "TIMEOUT", "The request timed out before the server answered."));
  assert.match(clientTimeout, /WAIVER ANALYSIS TIMED OUT/);
  const withheld = moves(fillAnalysis([fill()]), null, null, { boardFailed: true });
  assert.match(withheld, /Best moves are withheld/);
  assert.doesNotMatch(withheld, /waiver-move-card|Loading best move/);
  const contract = moves(null, supportedBoard(), apiFailure(500, "RECOMMENDATION_CONTRACT_VIOLATION",
    "The best-move analysis named players outside the current waiver-eligible candidate set; the result was withheld.", { retryable: false }));
  assert.match(contract, /<p class="waiver-failure-title">WAIVER MODEL CONTRACT ERROR<\/p>/);
  assert.match(contract, /No recommendation from this response is shown\./);
});

const formWindow = (key, label, games, ppg, tweaks = {}) => ({
  key, label, games, fantasy_ppg: ppg, minutes_average: games ? 28.4 : null, minutes_median: games ? 29 : null,
  starts: null, starts_detail: "Per-game starts are not persisted.", usage: null, usage_detail: "Game-level usage is not persisted.",
  sample_tier: games >= 7 ? "SUPPORTED" : games >= 5 ? "LIMITED" : "VERY_LOW", sample_label: `${games} games`,
  window_start: "2026-10-31", window_end: "2026-11-13", latest_game: "2026-11-13", season: null,
  as_of: "2026-11-14T08:31:50Z", state: "available", detail: "Persisted NBA game logs.", ...tweaks,
});
const recentForm = () => ({
  windows: [
    formWindow("LAST_7_DAYS", "Last 7 Days", 3, 33.1), formWindow("LAST_14_DAYS", "Last 14 Days", 6, 31.2),
    formWindow("LAST_30_DAYS", "Last 30 Days", 12, 27.9),
    formWindow("CURRENT_SEASON", "Current Season", 12, 27.9, { season: "2026-27", starts: 9, usage: .231, window_start: null, window_end: null }),
    formWindow("PREVIOUS_SEASON", "Previous Season", 0, null, { season: "2025-26", state: "unavailable", window_start: null, window_end: null }),
  ],
  trend: { trend: "IMPROVING", recent_games: 6, baseline_games: 6, recent_ppg: 31.2, baseline_ppg: 24.6, ppg_change: .268,
    recent_minutes: 30.1, baseline_minutes: 26.4, minutes_change: 3.7, detail: "Last 14 Days vs days 15-30: PPG +26.8%, minutes +3.7.",
    method: "Non-overlapping windows; descriptive only." },
  limitations: ["Form windows are historical Yahoo-rule production, not projections."],
});
const SAMPLE_DETAIL = "6 games in the last 14 days (LIMITED SAMPLE), corroborated: 12 games in the last 30 days; 12 games this season; role STABLE (available)";
const formed = (tweaks = {}) => ({
  form: recentForm(), move_intent: "STREAM", move_intent_detail: "STREAM: 4 games in Next 7 Days with a corroborated recent sample.",
  sample: { mode: "next_7_days", window: "LAST_14_DAYS", relevant_games: 6, current_season_games: 12, tier: "LIMITED", passes: true,
    corroborated: true, required: [], corroborations: [], corroborations_passed: 3, detail: SAMPLE_DETAIL },
  ...tweaks,
});

test("a full-roster board/analysis pair mismatch fails closed, and a full roster never offers a next open spot", () => {
  const analysis = transactionAnalysis(true);
  const reason = /the waiver board and the best-move analysis name different supported ADD \+ DROP pairs/;
  for (const result of [pairBoard(analysis, { best_drop_for_team_id: 2 }), pairBoard(analysis, { best_add_for_team_id: null, best_drop_for_team_id: null })]) {
    const html = moves(analysis, result);
    assert.match(html, /WAIVER MODEL CONTRACT ERROR/);
    assert.match(html, /A recommendation for Available Center \/ Bench Forward was withheld because /);
    assert.match(html, reason);
    assert.doesNotMatch(html, /waiver-move-card|<h3>HOLD<\/h3>|waiver-strict-status/, "no contradictory answer is shown");
  }
  const boardOnly = moves(transactionAnalysis(), pairBoard(analysis));
  assert.match(boardOnly, /A recommendation for the board&#x27;s supported move was withheld because /);
  assert.doesNotMatch(boardOnly, /<span class="waiver-action is-hold">HOLD<\/span>/);
  // Real-data regression: a full roster with a supported pair also showed a measured card as "Next open spot".
  const pairAndMeasured = moves(analysis, pairBoard(analysis, { decision_support: decisionSupport({
    state: "SUPPORTED_ACTION", supported_count: 1, best_measured_ids: [21, 22] }) }));
  assert.match(pairAndMeasured, /<h3 class="waiver-move-player">ADD: Available Center<\/h3>/);
  assert.doesNotMatch(pairAndMeasured, /WAIVER MODEL CONTRACT ERROR|Next open spot|Second open spot|Measured Guard|Group Wing/);
  const measuredHold = moves(transactionAnalysis(), { ...board(null), roster_capacity: capacity("ADD_DROP"),
    decision_support: decisionSupport({ best_measured_ids: [21, 22] }) });
  assert.match(measuredHold, /<span class="waiver-action is-hold">HOLD<\/span>/);
  assert.equal(measuredHold.match(/Top target to check/g)?.length, 2);
  assert.doesNotMatch(measuredHold, /Next open spot|Second open spot|WAIVER MODEL CONTRACT ERROR/);
});

test("supported cards carry the backend horizon intent and form lines; other actions get no intent badge", () => {
  const analysis = transactionAnalysis(true);
  analysis.best_transaction = { ...analysis.best_transaction, add_player: { ...analysis.best_transaction.add_player,
    ...formed({ move_intent: "TWO_WEEK_STREAM", move_intent_detail: "Two-week move supported by current production, role, roster impact, and persisted Next 14 Days schedule evidence." }) } };
  const html = moves(analysis, pairBoard(analysis), null, { mode: "next_14_days" });
  assert.match(html, /Next 14 Days · analysis only/);
  assert.match(html, /<span class="waiver-action is-add_drop">ADD \+ DROP<\/span> <span class="waiver-intent is-two_week_stream">TWO-WEEK STREAM<\/span><h3/);
  assert.ok(html.includes(`<li>${TWO_WEEK}</li>`), "the backend Next 14 Days wording is rendered verbatim");
  assert.match(html, /Add form \(Yahoo FP\/G\):<\/strong> L7 33\.1 \(3 g\) · L14 31\.2 \(6 g\) · L30 27\.9 \(12 g\) · Season 27\.9 \(12 g\) · IMPROVING/);
  assert.doesNotMatch(html, /Drop form/, "no form line is invented for a drop without backend form");
  const watch = { ...analysis, best_transaction: { ...analysis.best_transaction,
    add_player: { ...analysis.best_transaction.add_player, move_intent: "WATCH" } } };
  assert.doesNotMatch(moves(watch, pairBoard(watch)), /waiver-intent/);
  const { AdvancedEvidence } = load();
  const policy = "Recent sample tiers: SUPPORTED 7+ games; LIMITED 5-6 games needs a qualified role and 2 corroborations.";
  const evidence = render(AdvancedEvidence, { board: { ...board(), sample_policy: policy }, analysis: { ...transactionAnalysis(), supported_move_count: 40 } });
  assert.ok(evidence.includes(`<h4>Recent-sample policy</h4><p>${policy}</p>`), "the backend policy text is shown verbatim");
  assert.match(evidence, /40 supported moves \(positive ADD or STREAM; the best is featured\)/);
});

test("details lead with the roster decision and show only backend form, season and schedule evidence", () => {
  const { ImpactContent } = load();
  const player = candidate(1, "Available Center", drop(4, .728), { recommended_action_type: "ADD_DROP", action_label: "ADD Available Center + DROP Bench Forward.",
    evidence_blockers: [], schedule: { ...candidate(1, "x").schedule, next_14_days_games: 7, rest_of_season_games: 58 }, ...formed() });
  const html = render(ImpactContent, { impact: { model_version: VERSION, candidate: player, comparison: player.comparison, limitations: [] }, selectedDropId: null });
  assert.match(html, /<span class="waiver-intent is-stream">STREAM<\/span>/);
  assert.match(html, /<h3>ROSTER DECISION<\/h3><dl class="waiver-move-facts"><div><dt>ADD<\/dt><dd>Available Center<\/dd><\/div><div><dt>DROP<\/dt><dd>Bench Forward<\/dd><\/div><div><dt>NET<\/dt><dd>\+0\.728 roster-index points<\/dd><\/div><\/dl><p><strong>WHY:<\/strong> STREAM: 4 games in Next 7 Days with a corroborated recent sample\.<\/p>/);
  const sections = ["ROSTER DECISION", "RECENT FORM", "SEASON EVIDENCE", "UPCOMING SCHEDULE", "Best supported drop for this add (roster full)"].map((text) => html.indexOf(text));
  assert.ok(sections.every((index) => index >= 0), String(sections));
  assert.deepEqual([...sections].sort((left, right) => left - right), sections, "the decision precedes the evidence");
  const recent = html.slice(html.indexOf("RECENT FORM"), html.indexOf("SEASON EVIDENCE"));
  assert.match(recent, /<dt>LAST 14 DAYS<\/dt><dd>6 games · 31\.2 Yahoo FP\/G · 28\.4 MIN · median 29\.0<small>6 games · 2026-10-31 to 2026-11-13/);
  assert.doesNotMatch(recent, /starts|usage/, "log windows never invent starts or usage");
  assert.match(html, /<strong>FORM: IMPROVING<\/strong> · Last 14 Days vs days 15-30: PPG \+26\.8%, minutes \+3\.7\./);
  assert.match(html, /<dt>CURRENT SEASON 2026-27<\/dt><dd>12 games · 27\.9 Yahoo FP\/G · 28\.4 MIN · median 29\.0 · 9 starts · 23\.1% usage<small>/);
  assert.match(html, /<dt>PREVIOUS SEASON 2025-26<\/dt><dd>0 games · n\/a Yahoo FP\/G<small>/);
  assert.match(html, /<dt>NEXT 14<\/dt><dd>7 games<\/dd>/);
  assert.match(html, /<dt>REST OF SEASON<\/dt><dd>58 persisted games<small>PARTIAL COVERAGE<\/small>/);
  assert.match(html, new RegExp(`<strong>Recent-sample gate:</strong> ${SAMPLE_DETAIL.replace(/[()]/g, "\\$&")}\\.`));
  assert.match(html, /Form windows are historical Yahoo-rule production, not projections\./);
  assert.doesNotMatch(html, /projected fantasy points:|ROS Projection/);
  const bare = render(ImpactContent, { impact: { model_version: VERSION, candidate: candidate(1, "Available Center"), comparison: null, limitations: [] }, selectedDropId: null });
  assert.match(bare, /Form windows were not returned for this player\./);
  assert.match(bare, /<dt>DROP<\/dt><dd>Not measured<\/dd><\/div><div><dt>NET<\/dt><dd>Unavailable<\/dd>/);
  assert.match(bare, /<dt>NEXT 14<\/dt><dd>Unknown games<\/dd>/);
  assert.doesNotMatch(bare, /Recent-sample gate|waiver-intent|FORM: /);
});

test("Next 14 Days is a fourth forward horizon and the season horizon is the Rest of Season Outlook", () => {
  const states = ["next_14_days", board(null, "next_14_days"), null, null, null, false, false, null, "", 0, null, null, null, null, refreshStatus("current")];
  const html = renderToStaticMarkup(React.createElement(load(states).WaiverCenter));
  const radios = [...html.matchAll(/name="waiver-mode"( checked="")?\/>([^<]+)</g)].map(([, checked, title]) => `${title}${checked ? " *" : ""}`);
  assert.deepEqual(radios, ["Rest of Week", "Next 7 Days", "Next 14 Days *", "Rest of Season Outlook"]);
  assert.match(html, /Next 14 Days: today through today \+ 13 in Pacific Time \(a forward schedule window, not Last 14 Days form\)/);
  const { WindowNote } = load();
  const outlook = render(WindowNote, { board: board(null, "ros") });
  assert.match(outlook, /Rest of Season Outlook: a current roster decision from Season Evidence/);
  assert.match(outlook, /No projected fantasy totals\./);
  assert.doesNotMatch(outlook + html, /ROS Projection|Rest of Season<\/label>/);
});

test("full-list exploratory sorts reorder by backend form numbers only and keep the backend rank", () => {
  const optionForm = (l14, next14) => ({ last_7_ppg: l14 + 1, last_7_games: 3, last_14_ppg: l14, last_14_games: 6, last_30_ppg: l14 - 1,
    last_30_games: 12, season_ppg: l14 - 2, season_games: 12, trend: "STABLE", next_7_games: 3, next_14_games: next14 });
  const forms = { 21: optionForm(20, 6), 22: optionForm(35, 8), 24: optionForm(30, 7) };
  const result = board(null);
  result.decision_support = decisionSupport({ options: decisionSupport().options.map((item) => ({ ...item, form: forms[item.player_id] ?? null })) });
  const names = ["Measured Guard", "Group Wing", "Watch Center", "Watch Forward", "Unmeasured Rookie"];
  const sorted = (sortBy) => {
    const html = render(load(["", "all", "all", "all", "all", "all", "all", "all", "all", sortBy]).FullWaiverList, { board: result, onDetails() {} });
    return [html, names.map((name) => [name, html.indexOf(`<th scope="row">${name}<`)]).sort((left, right) => left[1] - right[1]).map(([name]) => name)];
  };
  const [byL14, l14Order] = sorted("last14");
  assert.deepEqual(l14Order, ["Group Wing", "Watch Forward", "Measured Guard", "Watch Center", "Unmeasured Rookie"], "missing form sorts last, then backend rank");
  assert.match(byL14, /<tr><td>2<\/td><th scope="row">Group Wing</, "the backend decision rank is still shown");
  assert.match(byL14, /<td>36\.0 · 35\.0 · 34\.0 · 33\.0<small>STABLE<\/small><\/td>/);
  assert.match(byL14, /<td>3 \/ 8<\/td>/);
  assert.match(byL14, /<td>Unavailable<small>No form evidence<\/small><\/td>/);
  assert.deepEqual(sorted("next14")[1], ["Group Wing", "Watch Forward", "Measured Guard", "Watch Center", "Unmeasured Rookie"]);
  assert.deepEqual(sorted("decision")[1], names, "default order is the backend decision_rank");
});

import { type RefObject, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import type {
  AcquisitionContext,
  AvailabilityClass,
  CoverageMetric,
  CoverageSlice,
  DecisionOption,
  DecisionSupport,
  DecisionSupportClass,
  DropAlternative,
  EvidenceDimension,
  FillRecommendation,
  FormWindow,
  FreshnessItem,
  MeasuredProduction,
  ProductionBucket,
  MoveIntent,
  OptionForm,
  OptionPair,
  PairExplanation,
  QualityState,
  RecentForm,
  RosterCapacity,
  SwapAnalysis,
  TeamNeed,
  TransactionAnalysis,
  TransactionVerdict,
  WaiverActionType,
  WaiverBoard,
  WaiverCandidate,
  WaiverDataGap,
  WaiverEvidence,
  WaiverImpact,
  WaiverMode,
  WaiverRefreshStatus,
  WaiverSampleLabel,
} from "./waiverTypes";

const CURRENT_WAIVER_MODEL_VERSION = "waiver-season-blend-phase8";
// Only these Yahoo availability classes may back a supported move or a featured recommendation.
const ACTIONABLE_AVAILABILITY = new Set<AvailabilityClass>([
  "CONFIRMED_FA", "CONFIRMED_WAIVER", "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT",
]);
// Unrostered in the saved snapshot but unconfirmed: listed only as potential targets to check in Yahoo.
const CHECKABLE_AVAILABILITY = new Set<AvailabilityClass>(["AVAILABILITY_UNVERIFIED", "SOURCE_STALE"]);
const ROSTERED_AVAILABILITY = new Set<AvailabilityClass>(["ROSTERED_BY_OTHER_TEAM", "ROSTERED_BY_MANAGER"]);
const REFRESH_POLL_MS = 2000;

/** A display-safe failure: built only from normalized API error fields, never a response body. */
export interface WaiverFailure {
  status: number;
  code: string;
  message: string;
  retryable: boolean;
  requestId: string | null;
}

export function toFailure(cause: unknown, fallback: string): WaiverFailure {
  if (cause && typeof cause === "object" && "code" in cause && "status" in cause) {
    const error = cause as { status: number; code: unknown; message?: unknown; retryable?: unknown; requestId?: unknown };
    return {
      status: Number(error.status) || 0,
      code: String(error.code),
      message: typeof error.message === "string" && error.message ? error.message : fallback,
      retryable: error.retryable === true,
      requestId: typeof error.requestId === "string" ? error.requestId : null,
    };
  }
  return { status: 0, code: "UNKNOWN", message: fallback, retryable: true, requestId: null };
}

function isTimedOut(failure: WaiverFailure): boolean {
  return failure.code === "GATEWAY_TIMEOUT" || failure.code === "TIMEOUT";
}

function isAborted(cause: unknown, signal?: AbortSignal): boolean {
  return Boolean(signal?.aborted) || (typeof cause === "object" && cause !== null && "code" in cause
    && (cause as { code: unknown }).code === "ABORTED");
}

function number(value: number | null | undefined): string {
  return value == null ? "Unavailable" : value.toFixed(1);
}

function exact(value: number | null | undefined): string {
  return value == null ? "Unavailable" : String(value);
}

function label(value: string): string {
  return value.replaceAll("_", " ");
}

/** The Yahoo token when Yahoo supplied one, else the backend's status label; the browser never infers a status. */
function yahooStatusText(row: { yahoo_status: string | null; status_label?: string | null }): string {
  return row.yahoo_status ?? row.status_label ?? "UNKNOWN";
}

function noDesignation(row: { decision_status_state?: string }): boolean {
  return row.decision_status_state === "NO_CURRENT_YAHOO_DESIGNATION";
}

function timestamp(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "America/Los_Angeles",
    timeZoneName: "short",
  });
}

function longTimestamp(value: string): string {
  return new Date(value).toLocaleString("en-US", {
    timeZone: "America/Los_Angeles", month: "long", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

function ordinal(value: number): string {
  const tens = value % 100;
  const suffix = tens >= 11 && tens <= 13 ? "th" : ({ 1: "st", 2: "nd", 3: "rd" } as Record<number, string>)[value % 10] ?? "th";
  return `${value}${suffix}`;
}

function pacificDate(value: string): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Los_Angeles",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date(value));
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function daysUntilPacificSunday(value: string): number {
  const [year, month, day] = pacificDate(value).split("-").map(Number);
  return (7 - new Date(Date.UTC(year, month - 1, day)).getUTCDay()) % 7;
}

function Quality({ fields }: { fields: Record<string, WaiverEvidence> }) {
  return <dl className="waiver-quality">{Object.entries(fields).map(([name, field]) =>
    <div key={name} className={`waiver-evidence is-${field.state}`}>
      <dt>{label(name)}: <strong>{field.state}</strong></dt>
      <dd>{field.detail}<br />{field.source} · {field.as_of ? timestamp(field.as_of) : "Source timestamp unavailable"}{field.sample_count != null && <> · {field.sample_count} observations</>}</dd>
    </div>,
  )}</dl>;
}

function coverageLabel(name: string, metric: CoverageMetric): string {
  return `${metric.count}/${metric.total} (${metric.percentage.toFixed(1)}%) ${label(name)}`;
}

function CoverageScopeDetails({ title, scope }: { title: string; scope: CoverageSlice }) {
  return <section aria-label={`${title} coverage`}>
    <h4>{title}</h4>
    <dl className="waiver-quality">
      <div><dt>Identity</dt><dd>{coverageLabel("complete mappings", scope.identity.complete)} · {coverageLabel("unresolved mappings", scope.identity.unresolved)} · states: {Object.entries(scope.identity.resolution_counts).map(([state, count]) => `${label(state)} ${count}`).join(", ") || "none"}</dd></div>
      <div><dt>Production</dt><dd>{coverageLabel("recent supported", scope.production.recent_supported)} · {coverageLabel("recent missing", scope.production.recent_missing)} · {coverageLabel("recent stale", scope.production.recent_stale)} · {coverageLabel("season supported", scope.production.season_supported)} · {coverageLabel("season missing", scope.production.season_missing)} · {coverageLabel("season stale", scope.production.season_stale)}</dd></div>
      <div><dt>Schedule</dt><dd>{coverageLabel("in-window rows", scope.schedule.supported)} · {coverageLabel("unknown", scope.schedule.unknown)} · {coverageLabel("stale", scope.schedule.stale)} · {coverageLabel("source incomplete", scope.schedule.source_incomplete)}</dd></div>
      <div><dt>Status</dt><dd>{coverageLabel("explicit", scope.status.explicit)} · {coverageLabel("Yahoo blank", scope.status.yahoo_blank)}{scope.status.field_missing ? ` · ${coverageLabel("status field missing", scope.status.field_missing)}` : ""}{scope.status.no_current_designation ? ` · ${coverageLabel("no current Yahoo designation", scope.status.no_current_designation)}` : ""} · {coverageLabel("stale", scope.status.stale)}</dd></div>
      <div><dt>Role</dt><dd>{coverageLabel("qualified minutes", scope.role.minutes_qualified)} · {coverageLabel("supported game-level usage", scope.role.usage_supported)} · {coverageLabel("recent game-level starts", scope.role.game_level_starts_supported)} · {coverageLabel("season starts", scope.role.season_starts_supported)} · {coverageLabel("insufficient sample", scope.role.insufficient_sample)} · {coverageLabel("missing role inputs", scope.role.missing_inputs)}</dd></div>
    </dl>
  </section>;
}

function CoverageSummary({ board }: { board: WaiverBoard }) {
  const { coverage } = board;
  const scopes: { title: string; value: CoverageSlice }[] = [
    { title: "Full persisted Yahoo pool", value: coverage.pool },
    { title: "Eligible candidates", value: coverage.candidates },
    { title: "Configured roster", value: coverage.roster },
  ];
  const categories: WaiverDataGap["category"][] = [
    "FIXABLE DATA ISSUE",
    "WAITING FOR MORE GAMES",
    "SOURCE DOES NOT SUPPLY",
    "NEW SOURCE REQUIRED",
    "UNVERIFIED YAHOO CONTEXT",
    "SOURCE CONTRACT UNVERIFIED",
    "INTENTIONALLY UNSUPPORTED",
  ];
  return <section aria-labelledby="waiver-coverage">
    <h3 id="waiver-coverage">Persisted evidence coverage</h3>
    <p>Population: {coverage.population.total} Yahoo-pool observations · {coverage.population.candidates} eligible candidates · {coverage.population.roster} configured-roster players. Percentages below use the full persisted pool unless identified as a different scope.</p>
    {scopes.map(({ title, value }) => <CoverageScopeDetails key={title} title={title} scope={value} />)}
    <p><strong>Acquisition context:</strong> {coverageLabel("supported", coverage.acquisition.supported)} · {coverageLabel("unsupported", coverage.acquisition.unsupported)}</p>
    <h3>DATA GAPS</h3>
    {categories.map((category) => {
      const gaps = board.data_gaps.filter((gap) => gap.category === category);
      return <section key={category} aria-label={category}>
        <h4>{category}</h4>
        {gaps.length
          ? <ul>{gaps.map((gap) => <li key={`${gap.category}-${gap.field}`}><strong>{gap.field}: {gap.count}/{gap.total} ({gap.percentage.toFixed(1)}%).</strong> {gap.reason}</li>)}</ul>
          : <p>{category === "NEW SOURCE REQUIRED"
            ? "No additional source is selected: current evidence and verified source terms did not establish a suitable free/legal replacement."
            : "No persisted gap is currently counted in this category."}</p>}
      </section>;
    })}
    {coverage.mapping_worklist.length > 0 && <details>
      <summary>Identity mapping worklist · {coverage.mapping_worklist.length} unresolved records</summary>
      <ul>{coverage.mapping_worklist.map((item) => <li key={`${item.internal_id}-${item.yahoo_player_id}`}>
        <strong>{item.yahoo_name}</strong> · Yahoo ID {item.yahoo_player_id} · Yahoo team {item.yahoo_team ?? "unknown"} · {label(item.resolution_state)}.
        {" "}{item.conflict_reason}
        {" "}Potential normalized-name NBA matches: {item.potential_nba_matches.length
          ? item.potential_nba_matches.map((match) => `${match.player_name} (${match.nba_player_id}, ${match.team ?? "team unknown"})`).join("; ")
          : "none in the persisted NBA player table"}.
      </li>)}</ul>
    </details>}
  </section>;
}

function sampleClass(sample: string): string {
  return `waiver-sample waiver-sample-${sample.toLowerCase().replaceAll(" ", "-")}`;
}

function sampleRisk(candidate: WaiverCandidate): string[] {
  return [
    ...(candidate.recent.games < 7
      ? [`Last 14 days sample: ${candidate.recent.games} game${candidate.recent.games === 1 ? "" : "s"} (${SAMPLE_BAND_TEXT[candidate.recent.sample_label]}).`] : []),
    ...(candidate.ros.games < 7
      ? [`Season Evidence sample: ${candidate.ros.games} game${candidate.ros.games === 1 ? "" : "s"} (${SAMPLE_BAND_TEXT[candidate.ros.sample_label]}).`] : []),
    ...(noDesignation(candidate) && candidate.status_detail ? [`${candidate.status_label}: ${candidate.status_detail}`]
      : !candidate.yahoo_status ? ["Yahoo status is unknown."] : []),
    ...Object.entries(candidate.data_quality)
      .filter(([, evidence]) => ["partial", "missing", "stale", "unknown"].includes(evidence.state))
      .map(([name, evidence]) => `${label(name)} evidence is ${evidence.state}.`),
    ...candidate.limitations,
  ];
}

function CandidateSamples({ candidate }: { candidate: WaiverCandidate }) {
  const windows: [string, WaiverCandidate["recent"]][] = [["Recent", candidate.recent], ["Season Evidence", candidate.ros]];
  return <div className="waiver-samples">
    <p><strong>{seasonSampleText(candidate.evidence_quality, candidate.current_season_games)}</strong>. A game-count band, not probability.</p>
    <div><strong>Last 14 days {number(candidate.recent.value)} fantasy PPG</strong><span className={sampleClass(candidate.recent.sample_label)}>{SAMPLE_BAND_TEXT[candidate.recent.sample_label]}</span>
      <small>{candidate.recent.games} games · {candidate.recent.season ?? "season unavailable"} · raw window, before any blending</small></div>
    <div><strong>Season Evidence {number(candidate.ros.value)} fantasy PPG</strong><span className={sampleClass(candidate.ros.sample_label)}>{SAMPLE_BAND_TEXT[candidate.ros.sample_label]}</span>
      <small>{candidate.ros.games} games · {candidate.ros.season ?? "no historical season"} · historical, not a projection</small></div>
    <details><summary>Exact Fantasy PPG inputs and contributions</summary>
      {windows.map(([title, value]) =>
        <p key={title}><strong>{title}:</strong> {Object.entries(value.scoring_weights ?? {})
          .map(([field, weight]) => `${field === "TOV" ? "TO (NBA TOV)" : field} ${exact(value.per_game_stats[field])} × ${exact(weight)} = ${exact(value.scoring_contributions?.[field])}`).join(" + ") || "Unavailable: complete persisted scoring/stat inputs required."}
          {value.value !== null && <> · Total {exact(value.value)} fantasy PPG</>}</p>,
      )}
    </details>
  </div>;
}

export function RoleEvidence({ candidate }: { candidate: WaiverCandidate }) {
  const role = candidate.opportunity.current_role;
  const status = candidate.data_quality.status;
  return <div className="waiver-role">
    <p><strong>CURRENT ROLE</strong></p>
    <p><strong>Role evidence: {role?.trend ?? "INSUFFICIENT EVIDENCE"}</strong> · {role?.quality.state ?? "unavailable"}. Descriptive observations, not a projection.</p>
    {role ? <>
      <dl className="waiver-comparison">
        {([["Minutes", role.minutes, 1], ["Usage", role.usage, 100]] as const).map(([title, metric, multiplier]) =>
          <div key={title}><dt>{title}</dt><dd>
            Recent {number(metric.recent.average == null ? null : metric.recent.average * multiplier)}{title === "Usage" ? "%" : ""} ({metric.recent.games} games)
            {" · "}comparison {number(metric.comparison.average == null ? null : metric.comparison.average * multiplier)} ({metric.comparison.games} games)
            {" · "}delta {metric.delta != null && metric.delta > 0 ? "+" : ""}{number(metric.delta == null ? null : metric.delta * multiplier)}{title === "Usage" ? " percentage points" : " minutes"}
            <br />{metric.quality.state} · {metric.recent.window_start ?? "No dates"}–{metric.recent.window_end ?? "No dates"} vs {metric.comparison.window_start ?? "No comparison dates"}–{metric.comparison.window_end ?? "No comparison dates"}
          </dd></div>,
        )}
        <div><dt>Starts</dt><dd>{role.starts.season_starts ?? "Unavailable"} season starts / {role.starts.season_games ?? "unknown"} games · {role.starts.quality.state}<br />Recent starts: {role.starts.recent_starts ?? "Unavailable"}. {role.starts.detail}</dd></div>
        <div><dt>Season usage context</dt><dd>{number(role.season_usage == null ? null : role.season_usage * 100)}% · {role.season_usage_quality.state}. Not recent usage or trend.</dd></div>
      </dl>
      <details><summary>Role calculation and source evidence</summary>
        <p>{role.method}</p>
        {([["Minutes", role.minutes, 1], ["Usage", role.usage, 100]] as const).map(([title, metric, multiplier]) =>
          <p key={title}>{title} median corroboration: {number(metric.recent.median == null ? null : metric.recent.median * multiplier)} vs {number(metric.comparison.median == null ? null : metric.comparison.median * multiplier)} · delta {number(metric.median_delta == null ? null : metric.median_delta * multiplier)}{title === "Usage" ? " percentage points" : " minutes"}.
            <br />Recent game IDs: {metric.recent.game_ids.join(", ") || "Unavailable"} · comparison game IDs: {metric.comparison.game_ids.join(", ") || "Unavailable"}.
            <br />Missing/invalid IDs: {[...metric.recent.missing_game_ids, ...metric.comparison.missing_game_ids].join(", ") || "None observed"} · stale import IDs: {[...metric.recent.stale_game_ids, ...metric.comparison.stale_game_ids].join(", ") || "None observed"}.
          </p>,
        )}
        <p>Opportunity parts (each counted once): {Object.entries(candidate.opportunity.score_parts).map(([key, value]) => `${label(key)} ${number(value)}`).join(" · ") || "Unavailable: qualified role evidence required."}</p>
        <Quality fields={{ role: role.quality, minutes: role.minutes.quality, usage: role.usage.quality, starts: role.starts.quality, season_usage: role.season_usage_quality }} />
        <ul>{role.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </> : <p>Role inputs unavailable; no neutral opportunity or role assumption is made.</p>}
    <p><strong>Yahoo raw status:</strong> {candidate.raw_yahoo_status ?? "(not supplied)"} · normalized status: {candidate.yahoo_status ?? (candidate.status_label ? "none" : "UNKNOWN")}
      {candidate.status_label ? <> · decision status: <strong>{candidate.status_label}</strong></> : null}
      {candidate.status_gate_supported !== undefined ? ` (Yahoo status gate ${candidate.status_gate_supported ? "passes" : "blocks strong actions"})` : ""}
      {" · "}{status?.state ?? "unavailable"} · {status?.as_of ? timestamp(status.as_of) : "Timestamp unavailable"}.
      {" "}{status?.detail ?? "Blank status is unknown, not healthy."} Diagnostic: {candidate.status_diagnostic ? label(candidate.status_diagnostic) : "unknown"}. No injury-return date is inferred.</p>
    <p><strong>Identity mapping:</strong> {label(candidate.identity_mapping_state)} · Yahoo team {candidate.yahoo_team ?? "unknown"} vs NBA team {candidate.nba_team ?? "unknown"} · {candidate.identity_mapping_reason}</p>
    <p><strong>SCHEDULE</strong></p>
    <p>{candidate.schedule.window_start}–{candidate.schedule.window_end} Pacific · {candidate.schedule.games_remaining ?? "Unknown"} persisted games · {candidate.schedule.off_day_games ?? "Unknown"} off-days · {candidate.schedule.back_to_backs ?? "Unknown"} back-to-back pairs.
      {" "}Coverage: {candidate.schedule.coverage ?? "UNKNOWN"} · {candidate.data_quality.schedule?.state ?? "unavailable"} · {label(candidate.schedule.diagnostic_reason ?? "unknown")} · {candidate.schedule.source_row_count} persisted source rows · {candidate.schedule.imported_at ? timestamp(candidate.schedule.imported_at) : "Import timestamp unavailable"}.
      {" "}Opponents: {candidate.schedule.opponents.join(", ") || "Unavailable"}. Opponent identity is not matchup difficulty.</p>
    <details><summary>Identity-chain diagnostic</summary>
      <p>{label(candidate.mapping_diagnostic ?? "unknown")} · {candidate.data_quality.identity?.detail ?? "Identity evidence unavailable"}.</p>
      <p>Yahoo player → internal identity → NBA player → current team → game logs → season stats → player schedule.</p>
    </details>
  </div>;
}

const ACTION_TEXT: Record<WaiverActionType, string> = {
  ADD_ONLY: "ADD ONLY",
  MOVE_TO_IL_THEN_ADD: "MOVE TO IL, THEN ADD",
  ADD_DROP: "ADD + DROP",
  WATCH: "WATCH",
  HOLD: "HOLD",
  INSUFFICIENT_EVIDENCE: "INSUFFICIENT EVIDENCE",
};

const SHAPE_TEXT: Record<RosterCapacity["transaction_shape"], string> = {
  ADD_ONLY: "OPEN ROSTER SPOT — NO DROP REQUIRED",
  MOVE_TO_IL_THEN_ADD: "MOVE A PLAYER TO IL TO OPEN A ROSTER SPOT",
  ADD_DROP: "ROSTER FULL — AN ADD REQUIRES A DROP",
  UNDETERMINED: "ROSTER CAPACITY NEEDS A YAHOO REFRESH",
};

const NEED_KIND_TEXT: Record<TeamNeed["kind"], string> = {
  OPEN_STARTING_SLOT: "Open starting slot",
  INJURY_WEAKENED: "Weakened by injury",
  LINEUP_DAY_GAP: "Schedule gap",
  BENCH_DEPTH: "Bench depth",
};

const CLASS_TEXT: Record<DecisionSupportClass, string> = {
  SUPPORTED_ACTION: "SUPPORTED ACTION",
  BEST_MEASURED_OPTION: "BEST MEASURED OPTION",
  WATCH: "WATCH",
  MEASURED: "MEASURED",
  POTENTIAL_TARGET: "POTENTIAL TARGET",
  UNAVAILABLE: "NOT COMPARABLE",
};

const STATE_TEXT: Record<QualityState, string> = {
  available: "current",
  partial: "partial",
  missing: "missing",
  stale: "stale",
  unknown: "unknown",
  unsupported: "unsupported",
  unavailable: "unavailable",
};

const NON_POSITIONAL_SLOTS = new Set(["UTIL", "UT", "BN"]);

function actionOf(candidate: WaiverCandidate): WaiverActionType {
  return candidate.recommended_action_type ?? "INSUFFICIENT_EVIDENCE";
}

function ActionBadge({ action }: { action: WaiverActionType }) {
  return <span className={`waiver-action is-${action.toLowerCase()}`}>{ACTION_TEXT[action]}</span>;
}

export function decisionText(option: DecisionOption): string {
  return option.classification === "SUPPORTED_ACTION" ? ACTION_TEXT[option.action_type] : CLASS_TEXT[option.classification];
}

function ClassBadge({ option }: { option: DecisionOption }) {
  const key = option.classification === "SUPPORTED_ACTION" ? option.action_type : option.classification;
  return <span className={`waiver-action is-${key.toLowerCase()}`}>{decisionText(option)}</span>;
}

function actionableClass(value: AvailabilityClass | null | undefined): boolean {
  return value != null && ACTIONABLE_AVAILABILITY.has(value);
}

/** Why a featured player must be withheld (null when it may be shown), using only backend-supplied fields. */
function featuredCheck(board: WaiverBoard) {
  const eligible = new Set(board.eligible_candidate_ids ?? []);
  return (playerId: number, availability: AvailabilityClass | null | undefined): string | null =>
    !eligible.has(playerId) ? "the player is not in the current waiver-eligible candidate set"
      : !actionableClass(availability) ? "the player's Yahoo availability is not confirmed" : null;
}

function AvailabilityBadge({ option }: { option: DecisionOption }) {
  const confirmed = option.availability_confirmed && actionableClass(option.availability_classification);
  return <span className={`waiver-availability is-${confirmed ? "confirmed" : "unverified"}`}>{option.availability_label}</span>;
}

function CandidateAvailability({ candidate }: { candidate: WaiverCandidate }) {
  const evidence = candidate.availability_evidence;
  if (!evidence) return null;
  return <p className="waiver-move-availability"><span className={`waiver-availability is-${evidence.actionable ? "confirmed" : "unverified"}`}>{evidence.label}</span>
    {evidence.waiver_clear_date ? <> · clears {evidence.waiver_clear_date}</> : null}</p>;
}

function signed(value: number | null | undefined): string {
  return value == null ? "Unavailable" : netDigits(value);
}

// Roster-index nets are shown with two decimals on every surface; the backend calls any |net| below half of that
// unit (0.005) a NEAR TIE, so a displayed preference is never just rounding. A non-zero net that would print as
// 0.00 keeps four decimals so its sign and size stay visible.
function netDigits(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(value !== 0 && Math.abs(value) < .005 ? 4 : 2)}`;
}

function indexNet(value: number | null | undefined): string {
  return value == null ? "Unavailable" : `${netDigits(value)} index points`;
}

const VERDICT_TEXT: Record<TransactionVerdict, string> = {
  SUPPORTED_ADD: "SUPPORTED ADD", WATCH_ONLY: "WATCH ONLY", NEAR_TIE: "NEAR TIE — NO STRONG PREFERENCE",
  DO_NOT_ADD: "DO NOT ADD", CANNOT_EVALUATE: "CANNOT EVALUATE",
};

/** The backend verdict; WATCH, DO NOT ADD and NEAR TIE never share the supported-add styling. */
function VerdictBadge({ verdict }: { verdict: TransactionVerdict | null | undefined }) {
  const value = verdict ?? "CANNOT_EVALUATE";
  return <span className={`waiver-verdict is-${value.toLowerCase()}`}>{VERDICT_TEXT[value]}</span>;
}

/** Every evidence label with its dimension, so labels from different systems are never shown unlabeled together. */
function EvidenceDimensions({ dimensions }: { dimensions: EvidenceDimension[] | null | undefined }) {
  if (!dimensions?.length) return null;
  return <dl className="waiver-dimensions" aria-label="Evidence by dimension">{dimensions.map((item) =>
    <div key={item.key} className={`is-${item.state.toLowerCase()}`}><dt>{item.label}</dt><dd>{item.text}</dd></div>)}</dl>;
}

// Season-game bands (current-season game counts); never the bare "INSUFFICIENT FOR STRONG RECOMMENDATION".
const SAMPLE_BAND_TEXT: Record<WaiverSampleLabel, string> = {
  EXCELLENT: "20+ games", GOOD: "10–19 games", LIMITED: "7–9 games",
  "VERY LIMITED": "4–6 games: below the 7-game requirement",
  "INSUFFICIENT FOR STRONG RECOMMENDATION": "1–3 games: below the 7-game requirement",
  "NO CURRENT-SEASON EVIDENCE": "no current-season games",
};

function seasonSampleText(label: WaiverSampleLabel, games?: number | null): string {
  if (games == null) return `Current-season sample: ${SAMPLE_BAND_TEXT[label]}`;
  return `Current-season sample: ${games} game${games === 1 ? "" : "s"}${games < 7 ? " (below the 7-game requirement)" : ""}`;
}

/** "1-GAME SAMPLE — WATCH ONLY" (or 2-game) is shown prominently; such a sample never supports a move. */
function tinySample(games: number | null | undefined): string | null {
  return games === 1 || games === 2 ? `${games}-GAME SAMPLE — WATCH ONLY` : null;
}

/** The backend's basis line for the model production value (this season's games, the prior season's share). */
function measuredBasisLabel(measured: MeasuredProduction): string {
  return measured.value == null ? "Unavailable" : measured.label || "Model production value";
}

/** The backend's exact arithmetic for the model production value; no weight is computed here. */
function measuredMath(measured: MeasuredProduction): string {
  if (measured.value == null) return measured.detail || "Production unavailable.";
  return measured.math ? `${measured.math} Yahoo FP/G.` : `${measured.value.toFixed(1)} Yahoo FP/G.`;
}

function gameSpan(bucket: ProductionBucket): string {
  if (!bucket.first_game || !bucket.last_game) return "";
  return bucket.first_game === bucket.last_game ? `, ${bucket.first_game}` : `, ${bucket.first_game} to ${bucket.last_game}`;
}

/** "Recent current season (last 14 days): 7 games at 16.5 FP/G, … · 47%": one line per bucket, backend numbers only. */
function bucketText(bucket: ProductionBucket): string {
  const share = `${Math.round(bucket.share * 100)}%`;
  const games = `${bucket.games} game${bucket.games === 1 ? "" : "s"}`;
  if (bucket.key === "PRIOR") {
    const name = `Prior season${bucket.season ? ` ${bucket.season}` : ""}`;
    return bucket.share > 0 && bucket.value != null
      ? `${name}: ${games} at ${bucket.value.toFixed(1)} FP/G, counted as ${bucket.weight_games} games · ${share}`
      : `${name}: not used (no supported prior-season history)`;
  }
  return bucket.games && bucket.value != null
    ? `${bucket.label}: ${games} at ${bucket.value.toFixed(1)} FP/G${gameSpan(bucket)} · ${share}`
    : `${bucket.label}: no games`;
}

/** Every bucket behind a production value: each current-season game counts once; the prior season counts as a fixed
 * number of games. */
export function ProductionBuckets({ buckets }: { buckets: ProductionBucket[] | null | undefined }) {
  if (!buckets?.length) return null;
  return <ul className="waiver-buckets" aria-label="Production basis: each game counted once">
    {buckets.map((bucket) => <li key={bucket.key}>{bucketText(bucket)}</li>)}
  </ul>;
}

// Decision horizons look forward; form windows (Last 7 / 14 / 30 Days) look back. They are never interchangeable.
const HORIZON_TEXT: Record<WaiverMode, string> = {
  this_week: "Rest of Week", next_7_days: "Next 7 Days", next_14_days: "Next 14 Days", ros: "Rest of Season Outlook",
};
const INTENT_TEXT: Record<MoveIntent, string> = {
  STREAM: "STREAM", TWO_WEEK_STREAM: "TWO-WEEK STREAM", LONGER_TERM_ADD: "LONGER-TERM ADD",
  WATCH: "WATCH", HOLD: "HOLD", INSUFFICIENT_EVIDENCE: "INSUFFICIENT EVIDENCE",
};

function modeWindow(mode: WaiverMode): string {
  return HORIZON_TEXT[mode];
}

/** Supported-move intent; renders nothing (not even spacing) for other actions. */
function IntentBadge({ intent }: { intent: MoveIntent | null | undefined }) {
  if (!intent || !["STREAM", "TWO_WEEK_STREAM", "LONGER_TERM_ADD"].includes(intent)) return null;
  return <>{" "}<span className={`waiver-intent is-${intent.toLowerCase()}`}>{INTENT_TEXT[intent]}</span></>;
}

function ppgText(value: number | null | undefined, reason?: string | null): string {
  return value == null ? (reason || "Unavailable") : `${value.toFixed(1)}${reason ? ` (${reason})` : ""}`;
}

const FORM_SHORT: [FormWindow["key"], string][] = [
  ["LAST_7_DAYS", "Last 7"], ["LAST_14_DAYS", "Last 14"], ["LAST_30_DAYS", "Last 30"], ["CURRENT_SEASON", "Season"],
];

function trendText(trend: RecentForm["trend"]["trend"]): string {
  return trend === "INSUFFICIENT EVIDENCE" ? "Trend: not enough games (3+ on each side of the 14-day split)" : `Trend: ${trend}`;
}

/** One backend form line (look-back windows, never a forecast); a missing value shows its backend reason. */
function FormLine({ form, name }: { form: RecentForm | null | undefined; name?: string }) {
  if (!form) return null;
  const windows = new Map(form.windows.map((window) => [window.key, window]));
  const parts = FORM_SHORT.map(([key, short]) => {
    const window = windows.get(key);
    return window ? `${short}: ${ppgText(window.fantasy_ppg, window.reason_label)} (${window.games} g)` : null;
  }).filter((part): part is string => part !== null);
  return <p className="waiver-form-line"><strong>{name ? `${name} recent form` : "Recent form"} (Yahoo FP/G, look-back):</strong> {parts.join(" · ")} · {trendText(form.trend.trend)}</p>;
}

function OptionFormLine({ form }: { form: OptionForm | null | undefined }) {
  if (!form) return null;
  return <p className="waiver-form-line"><strong>Recent form (Yahoo FP/G, look-back):</strong> Last 7: {ppgText(form.last_7_ppg, form.last_7_reason)} ({form.last_7_games} g) · Last 14: {ppgText(form.last_14_ppg, form.last_14_reason)} ({form.last_14_games} g) · Last 30: {ppgText(form.last_30_ppg, form.last_30_reason)} ({form.last_30_games} g) · {trendText(form.trend)}</p>;
}

/** "24.1 Yahoo FP/G · 12 games", or the backend reason when the value is missing (never "n/a"). */
function seasonFacts(value: number | null | undefined, reason: string | null | undefined, games: number): string {
  const count = `${games} game${games === 1 ? "" : "s"}`;
  return value == null ? `${reason || "Unavailable"} · ${count}` : `${ppgText(value, reason)} Yahoo FP/G · ${count}`;
}

/** RECENT FORM, CURRENT-SEASON PRODUCTION, PREVIOUS-SEASON BASELINE and the MODEL VALUE USED, kept apart. */
function ProductionBlock({ option }: { option: DecisionOption }) {
  const form = option.form;
  const pair = option.pair;
  return <dl className="waiver-production" aria-label={`Production evidence for ${option.player_name}`}>
    <div><dt>RECENT FORM</dt><dd>{form ? <OptionFormLine form={form} /> : "Form windows were not returned"}</dd></div>
    <div><dt>CURRENT-SEASON PRODUCTION</dt><dd>{form ? seasonFacts(form.season_ppg, form.season_reason, form.season_games) : "Form windows were not returned"}</dd></div>
    <div><dt>PREVIOUS-SEASON BASELINE</dt><dd>{form ? seasonFacts(form.previous_season_ppg, form.previous_season_reason, form.previous_season_games) : "Form windows were not returned"}</dd></div>
    <div><dt>MODEL VALUE USED</dt><dd>{pair?.add_ppg != null
      ? <>{pair.add_ppg.toFixed(1)} Yahoo FP/G in the exact comparison <small>{pair.basis_label}</small></>
      : <>{measuredBasisLabel(option.measured)}: {measuredMath(option.measured)}</>}</dd></div>
    {option.measured.value != null && <div><dt>MODEL PRODUCTION VALUE</dt><dd>{option.measured.value.toFixed(1)} Yahoo FP/G · {measuredBasisLabel(option.measured)}<small>Based on: {measuredMath(option.measured)}</small>
      <ProductionBuckets buckets={option.measured.buckets} /></dd></div>}
  </dl>;
}

/** Exact component arithmetic: weighted contribution = effective weight x (after - before); the sum is the net. */
function ContributionTable({ explanation }: { explanation: PairExplanation }) {
  return <div className="waiver-table-scroll" role="region" aria-label="Exact roster-index arithmetic, scroll horizontally for all columns" tabIndex={0}>
    <table className="waiver-contrib-table">
      <caption>Roster index: weighted contribution = effective weight × (after − before). Components outside the common mask are listed below, never filled.</caption>
      <thead><tr>{["Component", "Before", "After", "Delta", "Effective weight", "Weighted contribution"].map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
      <tbody>
        {explanation.contributions.map((row) => <tr key={row.component} className={row.weighted_contribution > 0 ? "is-gain" : row.weighted_contribution < 0 ? "is-cost" : ""}>
          <th scope="row">{label(row.component)}</th><td>{row.before.toFixed(4)}</td><td>{row.after.toFixed(4)}</td>
          <td>{row.delta > 0 ? "+" : ""}{row.delta.toFixed(4)}</td><td>{(row.effective_weight * 100).toFixed(2)}%</td>
          <td>{row.weighted_contribution > 0 ? "+" : ""}{row.weighted_contribution.toFixed(6)}</td>
        </tr>)}
        <tr><th scope="row">Sum = net</th><td colSpan={4}>Returned net {explanation.net == null ? "unavailable" : `${explanation.net > 0 ? "+" : ""}${explanation.net.toFixed(6)}`}</td>
          <td>{explanation.contribution_sum == null ? "Unavailable" : `${explanation.contribution_sum > 0 ? "+" : ""}${explanation.contribution_sum.toFixed(6)}`}</td></tr>
      </tbody>
    </table>
  </div>;
}

/** The full backend explanation: statement, arithmetic, provenance, window points, checks and sensitivity. */
function ExplanationDetails({ explanation }: { explanation: PairExplanation }) {
  const omitted = Object.entries(explanation.omitted);
  const without = Object.entries(explanation.net_without);
  return <div className="waiver-explanation">
    <ContributionTable explanation={explanation} />
    <h5>Production values used (same basis for both players)</h5>
    <ul>
      <li><strong>{explanation.add_name}:</strong> {explanation.add_production.value == null ? "Unavailable" : `${explanation.add_production.value.toFixed(2)} Yahoo FP/G`} · {explanation.add_production.label}{explanation.add_production.math ? ` · ${explanation.add_production.math}` : ""}{explanation.add_production.percentile != null ? ` · production percentile ${explanation.add_production.percentile.toFixed(1)}` : ""}
        <ProductionBuckets buckets={explanation.add_production.buckets} /></li>
      {explanation.drop_production && <li><strong>{explanation.drop_name}:</strong> {explanation.drop_production.value == null ? "Unavailable" : `${explanation.drop_production.value.toFixed(2)} Yahoo FP/G`} · {explanation.drop_production.label}{explanation.drop_production.math ? ` · ${explanation.drop_production.math}` : ""}{explanation.drop_production.percentile != null ? ` · production percentile ${explanation.drop_production.percentile.toFixed(1)}` : ""}
        <ProductionBuckets buckets={explanation.drop_production.buckets} /></li>}
    </ul>
    <p><strong>Schedule in {explanation.horizon}</strong> ({explanation.window_start ?? "?"} to {explanation.window_end ?? "?"}, persisted schedule rows):{" "}
      {explanation.add_name} {explanation.add_games ?? "unknown"} games{explanation.drop_name ? ` · ${explanation.drop_name} ${explanation.drop_games ?? "unknown"} games` : ""}.
      {explanation.window_points_gap != null && ` Window Yahoo fantasy points (games × FP/G, before daily lineup limits): ${explanation.add_window_points?.toFixed(1)} vs ${explanation.drop_window_points?.toFixed(1)} (${explanation.window_points_gap > 0 ? "+" : ""}${explanation.window_points_gap.toFixed(1)}).`}</p>
    <p><strong>Starting slots:</strong> {explanation.starting_slots_before ?? "?"} → {explanation.starting_slots_after ?? "?"} of {explanation.starting_slots_required ?? "?"}{explanation.starting_slots_after != null && explanation.starting_slots_before != null && explanation.starting_slots_after > explanation.starting_slots_before ? " (fills a starting slot)" : " (no fit change)"}.</p>
    {without.length > 0 && <p><strong>Would it still win without…</strong> {without.map(([key, value]) => `${label(key)}: ${value == null ? "unavailable" : `${value > 0 ? "+" : ""}${value.toFixed(4)}`}`).join(" · ")}.</p>}
    {omitted.length > 0 && <><h5>Not in this comparison</h5><ul>{omitted.map(([key, reason]) => <li key={key}>{label(key)}: {reason}</li>)}</ul></>}
    <h5>Consistency checks</h5>
    <ul className="waiver-checks">{explanation.checks.map((check) => <li key={check.key} className={check.passed ? "is-passed" : "is-failed"}>
      <strong>{check.passed ? "PASS" : "FAIL"} · {label(check.key)}:</strong> {check.detail}</li>)}</ul>
    {explanation.tradeoffs.length > 0 && <><h5>Tradeoffs</h5><ul>{explanation.tradeoffs.map((item) => <li key={item}>{item}</li>)}</ul></>}
  </div>;
}

/** Every backend tradeoff for a featured move (drop permanence, fragile window edge, prior-season reliance, costs). */
function Tradeoffs({ explanation }: { explanation: PairExplanation | null }) {
  if (!explanation?.tradeoffs.length) return null;
  return <div className="waiver-tradeoff"><strong>{explanation.tradeoffs.length === 1 ? "Tradeoff" : "Tradeoffs"}:</strong>
    <ul>{explanation.tradeoffs.map((item) => <li key={item}>{item}</li>)}</ul></div>;
}

/** "Why this drop?": the chosen drop against the next measured drops for the same add. */
function WhyThisDrop({ choice, alternatives }: { choice: string | null | undefined; alternatives: DropAlternative[] | null | undefined }) {
  if (!choice && !alternatives?.length) return null;
  return <details className="waiver-why-drop"><summary>Why this drop?</summary>
    {choice && <p>{choice}</p>}
    {alternatives?.length ? <ul>{alternatives.map((row) => <li key={row.player_id}>{row.player_name}: {indexNet(row.net)}
      {row.margin != null ? ` (${row.margin >= 0 ? `${row.margin.toFixed(2)} behind` : `${Math.abs(row.margin).toFixed(2)} ahead on the index`})` : ""}{row.note ? ` — not used: ${row.note}` : ""}</li>)}</ul> : null}
  </details>;
}

/** The exact pair behind an option card: who to drop (or no drop), the net and why, on one basis. */
function PairFacts({ option, mode, onDetails }: { option: DecisionOption; mode: WaiverMode; onDetails: (option: DecisionOption) => void }) {
  const pair = option.pair as OptionPair;
  const drop = pair.drop_player_name ?? (pair.comparison_type === "MOVE_TO_IL_THEN_ADD" ? "No drop: conditional IL move"
    : pair.comparison_type === "ADD_ONLY" ? "No drop: open roster spot" : "No supported drop");
  const slotsChanged = pair.starting_slots_after != null && pair.starting_slots_before != null && pair.starting_slots_after > pair.starting_slots_before;
  const blocker = pair.blocker ?? (option.verdict === "SUPPORTED_ADD" ? null : option.blockers[0] ?? null);
  return <>
    <dl className="waiver-move-facts waiver-pair-facts">
      <div><dt>{pair.drop_player_name ? `Best compatible drop${option.verdict === "SUPPORTED_ADD" ? "" : " (comparison only)"}` : "Drop"}</dt><dd>{drop}</dd></div>
      <div><dt>Net (exact pair)</dt><dd>{indexNet(pair.net)}</dd></div>
      <div><dt>Yahoo FP/G (same basis)</dt><dd>Add {pair.add_ppg?.toFixed(1) ?? "?"}{pair.drop_player_name ? ` · drop ${pair.drop_ppg?.toFixed(1) ?? "?"}` : ""}<small>{pair.basis_label}</small></dd></div>
      <div><dt>Games in {modeWindow(mode)}</dt><dd>{pair.add_games ?? "Unknown"}{pair.drop_player_name ? ` vs ${pair.drop_games ?? "unknown"}` : ""}{pair.window_points_gap != null ? ` · window FP ${pair.window_points_gap > 0 ? "+" : ""}${pair.window_points_gap.toFixed(1)}` : ""}</dd></div>
      <div><dt>Need / fit change</dt><dd>Starting slots {pair.starting_slots_before ?? "?"} → {pair.starting_slots_after ?? "?"} of {pair.starting_slots_required ?? "?"}{slotsChanged ? " (fills a slot)" : " (no fit change)"}</dd></div>
      <div><dt>Primary reason</dt><dd>{pair.primary_reason || "No component improves the roster index."}</dd></div>
    </dl>
    <p className={`waiver-tradeoff${blocker ? " is-blocker" : ""}`}><strong>{blocker ? "Primary blocker" : "Primary tradeoff"}:</strong> {blocker ?? pair.primary_tradeoff ?? "None reported by the backend."}</p>
    <WhyThisDrop choice={pair.drop_choice} alternatives={pair.alternatives} />
    {pair.drop_player_name && <button className="button button-quiet" onClick={() => onDetails(option)}>Compare other drops: {option.player_name}</button>}
  </>;
}

/** An option card that always answers the transaction question with the backend verdict and exact pair. */
function OptionCard({ option, mode, fullRoster, onDetails }: { option: DecisionOption; mode: WaiverMode; fullRoster: boolean; onDetails: (option: DecisionOption) => void }) {
  const verdict = option.verdict ?? "CANNOT_EVALUATE";
  const sample = tinySample(option.current_season_games);
  return <div className={`waiver-option is-${verdict.toLowerCase()}`}>
    <p className="waiver-option-head"><strong className="waiver-option-name">{option.player_name}</strong> <span>{positionText(option.positions)}</span> <VerdictBadge verdict={verdict} /> <AvailabilityBadge option={option} /></p>
    <p className="waiver-option-headline">{option.headline || option.verdict_text || option.reason}</p>
    {option.reason && option.reason !== option.headline && <p className="waiver-option-reason"><strong>Why listed:</strong> {option.reason}</p>}
    {sample && <p className="waiver-sample-alert">{sample}</p>}
    {option.pair ? <PairFacts option={option} mode={mode} onDetails={onDetails} />
      : <p className="waiver-tradeoff is-blocker"><strong>{fullRoster ? "No supported drop:" : "No comparison:"}</strong> {option.blockers[0] ?? "no measured comparison is available for this player."}</p>}
    <ProductionBlock option={option} />
    <EvidenceDimensions dimensions={option.evidence_dimensions} />
    <button className="button button-quiet" onClick={() => onDetails(option)}>View details: {option.player_name}</button>
  </div>;
}

function windowFacts(window: FormWindow): string {
  return [`${window.games} game${window.games === 1 ? "" : "s"}`,
    window.fantasy_ppg == null ? (window.reason_label || "Yahoo FP/G unavailable") : `${ppgText(window.fantasy_ppg, window.reason_label)} Yahoo FP/G`,
    window.minutes_average != null ? `${window.minutes_average.toFixed(1)} MIN` : null,
    window.minutes_median != null ? `median ${window.minutes_median.toFixed(1)}` : null,
    window.starts != null ? `${window.starts} starts` : null,
    window.usage != null ? `${(window.usage * 100).toFixed(1)}% usage` : null].filter(Boolean).join(" · ");
}

/** RECENT FORM, SEASON EVIDENCE and UPCOMING SCHEDULE exactly as the backend measured them. */
export function FormPanel({ candidate }: { candidate: WaiverCandidate }) {
  const form = candidate.form;
  const schedule = candidate.schedule;
  const recent = (form?.windows ?? []).filter((window) => window.key.startsWith("LAST_"));
  const seasons = (form?.windows ?? []).filter((window) => !window.key.startsWith("LAST_"));
  return <section className="waiver-form-panel" aria-label={`Form and schedule evidence for ${candidate.player_name}`}>
    <h3>RECENT FORM</h3>
    {form ? <dl className="waiver-form-grid">{recent.map((window) => <div key={window.key}>
      <dt>{window.label.toUpperCase()}</dt>
      <dd>{windowFacts(window)}<small>{window.sample_label} · {window.window_start ?? "?"} to {window.window_end ?? "?"} · {STATE_TEXT[window.state]}</small></dd>
    </div>)}</dl> : <p>Form windows were not returned for this player.</p>}
    {form && <p><strong>FORM: {form.trend.trend}</strong> · {form.trend.detail}</p>}
    <h3>SEASON EVIDENCE</h3>
    {seasons.length ? <dl className="waiver-form-grid">{seasons.map((window) => <div key={window.key}>
      <dt>{window.label.toUpperCase()}{window.season ? ` ${window.season}` : ""}</dt>
      <dd>{windowFacts(window)}<small>{STATE_TEXT[window.state]} · historical, not a projection</small></dd>
    </div>)}</dl> : <p>Season evidence was not returned.</p>}
    <h3>UPCOMING SCHEDULE</h3>
    <dl className="waiver-form-grid">
      <div><dt>NEXT 7</dt><dd>{schedule.next_7_days_games ?? "Unknown"} games</dd></div>
      <div><dt>NEXT 14</dt><dd>{schedule.next_14_days_games ?? "Unknown"} games</dd></div>
      <div><dt>REST OF SEASON</dt><dd>{schedule.rest_of_season_games ?? "Unknown"} persisted games<small>{schedule.coverage} COVERAGE</small></dd></div>
    </dl>
    {candidate.sample && <p><strong>Recent-sample gate:</strong> {candidate.sample.detail}.</p>}
    {form && <ul className="waiver-form-limits">{form.limitations.map((item) => <li key={item}>{item}</li>)}</ul>}
  </section>;
}

function measuredPpg(option: DecisionOption): string {
  return option.measured.value == null ? "Production unavailable" : `${option.measured.value.toFixed(1)} Yahoo FP/G model value`;
}

function gamesText(option: DecisionOption, mode: WaiverMode): string {
  const window = mode === "ros" ? "rest of season" : modeWindow(mode);
  if (option.games_in_window == null) return `Games in ${window} unknown`;
  return `${option.games_in_window} game${option.games_in_window === 1 ? "" : "s"} in ${window}${option.games_in_window_state === "stale" ? " (stale schedule)" : ""}`;
}

function fillsText(option: DecisionOption): string {
  return option.fills.length ? option.fills.join(", ") : "Depth (no open positional need)";
}

function positionText(positions: string | null | undefined, fallback = "Position unknown"): string {
  const list = (positions ?? "").split(",").map((position) => position.trim()).filter(Boolean);
  return list.length ? list.join(" / ") : fallback;
}

function CapacityDetails({ capacity }: { capacity: RosterCapacity }) {
  return <>
    <p>{capacity.drop_requirement_reason}</p>
    {capacity.blockers.length
      ? <div className="waiver-blocker-box"><p><strong>Capacity is not decision-ready. No drop is assumed and ADD + DROP is not used as a default.</strong></p>
        <ul className="waiver-blockers">{capacity.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div>
      : <p>No capacity blockers: persisted Yahoo slot assignments, roster positions and the roster import are fresh and consistent.</p>}
    <h3>Injured players</h3>
    {capacity.injured_players.length ? <ul>{capacity.injured_players.map((row) =>
      <li key={row.player_id}><strong>{row.player_name}</strong> · Yahoo status {row.yahoo_status ?? row.status_label ?? "blank (UNKNOWN)"} · {row.roster_slot ? `in ${row.roster_slot}` : "slot not persisted"} · {row.slot_kind === "injury"
        ? "already in an injury slot"
        : row.eligible_injury_slots.length ? `IL-eligible (${row.eligible_injury_slots.join(", ")})` : "not IL-eligible in persisted Yahoo eligibility"}{row.injury_note ? ` · Yahoo note: ${row.injury_note}` : ""}</li>)}</ul>
      : <p>No injured players are identified in the persisted roster evidence. Neither NO CURRENT YAHOO DESIGNATION nor a blank status means healthy.</p>}
    {capacity.move_to_injury_slot_options.length > 0 && <><h3>Conditional IL moves</h3>
      <ul>{capacity.move_to_injury_slot_options.map((move) => <li key={move.player_id}>{move.detail}</li>)}</ul></>}
    {capacity.injury_move_blockers.length > 0 && <><h3>IL moves not available</h3>
      <ul>{capacity.injury_move_blockers.map((blocker) => <li key={blocker.player_id}>{blocker.reason}</li>)}</ul></>}
    {capacity.warnings.length > 0 && <ul>{capacity.warnings.map((item) => <li key={item}>{item}</li>)}</ul>}
    <p>Roster evidence: {capacity.evidence.state} · imported {capacity.evidence.as_of ? timestamp(capacity.evidence.as_of) : "unknown"} · Yahoo slot date {capacity.assignment_as_of ?? "not persisted"}. Status evidence: {capacity.status_evidence.state}. {capacity.status_evidence.detail}</p>
    <p><strong>Transaction legality: {capacity.transaction_legality_quality.state}.</strong> {capacity.transaction_legality_quality.detail}</p>
    <div className="waiver-table-scroll" role="region" aria-label="Roster occupancy by slot, scroll horizontally for all columns" tabIndex={0}>
      <table className="waiver-slot-table"><caption>Persisted Yahoo slot assignments for the configured roster.</caption>
        <thead><tr>{["Slot", "Player", "Positions", "Yahoo status", "Lineup eligible", "Detail"].map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
        <tbody>{capacity.assignments.map((row) => <tr key={row.player_id}>
          <td>{row.roster_slot ?? "Unknown"}</td><th scope="row">{row.player_name}</th><td>{row.positions ?? "Unknown"}</td>
          <td>{row.yahoo_status ?? row.status_label ?? "UNKNOWN"}</td><td>{row.lineup_eligible ? "Yes" : "No"}</td><td>{row.detail}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <ul>{capacity.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
  </>;
}

function NeedsDetails({ board }: { board: WaiverBoard }) {
  const needs = board.team_needs_analysis;
  if (!needs) return <p role="status">Team needs were not returned for this response.</p>;
  // Need options can name any eligible player, not only the bounded set returned with full evidence.
  const names = new Map([...(board.decision_support?.options ?? []), ...board.roster, ...board.candidates]
    .map((row) => [row.player_id, row.player_name]));
  const nameOf = (id: number) => names.get(id) ?? `Player ${id}`;
  const eligible = new Set(board.eligible_candidate_ids ?? []);
  const positional = needs.needs.filter((need) => !NON_POSITIONAL_SLOTS.has(need.slot));
  return <>
    {needs.state !== "available" && <p className={`waiver-capacity is-${needs.state === "partial" ? "partial" : "stale"}`}>
      Needs evidence is <strong>{needs.state}</strong>: {needs.state === "partial"
        ? "some supporting evidence below is missing or unverified."
        : "refresh the Yahoo baseline before relying on these needs."}</p>}
    <p>{needs.starting_slots_required
      ? `${needs.starting_slots_covered ?? "Unknown"} of ${needs.starting_slots_required} starting slots can be covered by ${needs.lineup_player_count} lineup-eligible players.`
      : "Starting slots are unavailable: no valid persisted Yahoo roster positions."} {modeWindow(needs.mode)}: {needs.window_start} to {needs.window_end} Pacific.</p>
    {positional.length > 0 && <><h3>Open slots and schedule gaps</h3><ol className="waiver-need-list">{positional.map((need) =>
      <li key={`${need.kind}-${need.slot}`}><strong>{need.slot}</strong> · {NEED_KIND_TEXT[need.kind]}{need.kind !== "LINEUP_DAY_GAP" && need.count > 1 ? ` ×${need.count}` : ""}: {need.reason}
        {need.compatible_candidate_ids.some((id) => eligible.has(id)) && <> Options: {need.compatible_candidate_ids.filter((id) => eligible.has(id)).map(nameOf).join(", ")}.</>}</li>)}</ol></>}
    <h3>Schedule gaps by date</h3>
    {needs.lineup_day_state === "partial" && <div className="waiver-table-scroll" role="region" aria-label="Lineup coverage by date, scroll horizontally for all columns" tabIndex={0}>
      <table className="waiver-days"><caption>Starting slots fillable by lineup-eligible players with a persisted game.</caption>
        <thead><tr>{["Date", "Players with games", "Fillable starting slots", "Open starting slots"].map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
        <tbody>{needs.lineup_days.map((day) => <tr key={day.date}>
          <th scope="row">{day.date}</th><td>{day.players_with_games}</td>
          <td>{day.fillable_starting_slots} of {day.starting_slots_required}</td><td>{day.open_starting_slots.join(", ") || "None"}</td>
        </tr>)}</tbody>
      </table>
    </div>}
    <p>{needs.lineup_day_detail}</p>
    <h3>Position coverage</h3>
    <div className="waiver-table-scroll" role="region" aria-label="Position coverage, scroll horizontally for all columns" tabIndex={0}>
      <table className="waiver-slot-table"><caption>How many starting slots each slot type needs and how many lineup-eligible players can fill them. Eligibility is not player quality.</caption>
        <thead><tr>{["Slot", "Required", "Covered", "Uncovered", "Open dates (slot-games)", "Eligible players"].map((column) => <th key={column} scope="col">{column}</th>)}</tr></thead>
        <tbody>{needs.slot_coverage.map((row) => <tr key={row.slot}>
          <th scope="row">{row.slot}{row.weakened_by_injury ? " (injury)" : ""}</th><td>{row.required}</td>
          <td>{row.covered ?? "Unknown"}</td><td>{row.uncovered ?? "Unknown"}</td>
          <td>{row.open_slot_days == null ? "Unavailable" : `${row.open_slot_days}${row.open_slot_games != null && row.open_slot_games !== row.open_slot_days ? ` (${row.open_slot_games})` : ""}`}</td>
          <td>{row.eligible_player_ids.map(nameOf).join(", ") || "None"}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p><strong>Production:</strong> {needs.production.detail}{needs.production.lowest_supported_ppg != null && needs.production.lowest_supported_player_id != null
      ? ` Lowest supported lineup player: ${nameOf(needs.production.lowest_supported_player_id)} at ${needs.production.lowest_supported_ppg.toFixed(1)} fantasy PPG; median ${number(needs.production.median_supported_ppg)}.`
      : ""}</p>
    <p><strong>Short-term streamer or longer-term hold?</strong> {needs.hold_guidance}</p>
    <p><strong>Multi-position lineup players:</strong> {needs.multi_position_player_ids.map(nameOf).join(", ") || "None"}. <strong>Uncertain Yahoo status (Q/P):</strong> {needs.uncertain_status_player_ids.map(nameOf).join(", ") || "None"}. <strong>Unknown status:</strong> {needs.unknown_status_player_ids.length} lineup players (blank is not healthy).</p>
    <ul>{needs.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
  </>;
}

function FreshnessLine({ items }: { items: FreshnessItem[] }) {
  if (!items.length) return null;
  // Sources sharing a state and Pacific date are grouped; ADVANCED EVIDENCE keeps the per-source list.
  const groups = new Map<string, { state: FreshnessItem["state"]; day: string | null; sources: string[] }>();
  for (const item of items) {
    const day = item.as_of ? pacificDate(item.as_of) : null;
    const key = `${item.state}|${day ?? ""}`;
    const group = groups.get(key) ?? { state: item.state, day, sources: [] };
    group.sources.push(item.source);
    groups.set(key, group);
  }
  return <div className="waiver-freshness">
    <p className="waiver-freshness-title"><strong>Evidence freshness</strong></p>
    <ul>{[...groups.entries()].map(([key, group]) => <li key={key} className={`is-${group.state}`}>
      <strong>{STATE_TEXT[group.state].toUpperCase()}</strong> ({group.day ?? "no import recorded"}): {group.sources.join(", ")}
    </li>)}</ul>
  </div>;
}

function weeklyAddsText(context: AcquisitionContext | null | undefined): string {
  if (!context || context.weekly_adds_used == null || context.weekly_add_limit == null) return "Not supplied by Yahoo";
  return `${context.weekly_adds_used} of ${context.weekly_add_limit} · ${context.weekly_adds_remaining ?? "?"} left`
    + (context.state === "stale" ? " (stale)" : "");
}

function priorityText(context: AcquisitionContext | null | undefined): string {
  if (!context || context.current_priority == null) return "Not supplied by Yahoo";
  return `${ordinal(context.current_priority)}${context.state === "stale" ? " (stale)" : ""}`;
}

export function TeamSituation({ board }: { board: WaiverBoard }) {
  const capacity = board.roster_capacity;
  const needs = board.team_needs_analysis;
  const summary = needs?.summary ?? [];
  const acquisition = board.acquisition_context;
  return <section className="panel waiver-panel waiver-situation" aria-labelledby="waiver-situation">
    <h2 id="waiver-situation">TEAM SITUATION</h2>
    {!capacity ? <p role="status">Roster capacity evidence was not returned; no drop requirement is assumed.</p> : <>
      <div className="waiver-situation-grid">
        <div>
          <p className={`waiver-headline is-${capacity.transaction_shape.toLowerCase()}`}>{capacity.headline || SHAPE_TEXT[capacity.transaction_shape]}</p>
          <p className="waiver-short-reason">{capacity.short_reason || capacity.drop_requirement_reason}</p>
          <FreshnessLine items={board.evidence_freshness ?? []} />
        </div>
        <div>
          <h3 className="waiver-subhead">Positional needs</h3>
          {summary.length
            ? <ol className="waiver-need-summary">{summary.map((need) => <li key={need.family}>
              <span className={`waiver-need-level is-${need.level.toLowerCase()}`}>{need.level}</span>
              <strong>{need.label}</strong> <span>{need.reason}</span>
            </li>)}</ol>
            : <p>{needs?.basis || "Positional needs are unavailable for this response."}</p>}
          {needs?.depth_note && <p className="waiver-depth">{needs.depth_note}</p>}
          {summary.length > 0 && needs?.basis && <p className="waiver-basis">{needs.basis}</p>}
        </div>
      </div>
      <dl className="waiver-stat-grid">
        <div><dt>Roster spots used</dt><dd>{capacity.occupied_roster_spots ?? "Unknown"} of {capacity.non_injury_capacity ?? "?"}</dd></div>
        <div><dt>Open regular spots</dt><dd>{capacity.open_roster_spots ?? "Unknown"}</dd></div>
        <div><dt>Open IL spots</dt><dd>{capacity.open_injury_slots ?? "Unknown"} of {capacity.injury_slot_capacity ?? "?"}</dd></div>
        <div><dt>Adds without a drop</dt><dd>{capacity.additions_after_injury_moves ?? capacity.no_drop_additions_available ?? "Unknown"}</dd></div>
        <div><dt>IL spots used</dt><dd>{capacity.occupied_injury_slots ?? "Unknown"} of {capacity.injury_slot_capacity ?? "?"}</dd></div>
        <div><dt>Injured players</dt><dd>{capacity.injured_players.length}</dd></div>
        <div><dt>Could move to IL</dt><dd>{capacity.transaction_shape === "UNDETERMINED" ? "Unknown" : capacity.move_to_injury_slot_options.length}</dd></div>
        <div><dt>Weekly adds used</dt><dd>{weeklyAddsText(acquisition)}</dd></div>
        <div><dt>Waiver priority</dt><dd>{priorityText(acquisition)}</dd></div>
      </dl>
      <div className="waiver-situation-more">
        <details className="waiver-details">
          <summary>Why? Roster capacity details{capacity.blockers.length ? ` (${capacity.blockers.length} blocking issue${capacity.blockers.length === 1 ? "" : "s"})` : ""}</summary>
          {acquisition && <p className="waiver-acquisition-note"><strong>Weekly adds and waiver priority:</strong> {acquisition.detail}{acquisition.as_of ? ` Source: Yahoo league import ${timestamp(acquisition.as_of)}.` : ""}</p>}
          <CapacityDetails capacity={capacity} />
        </details>
        <details className="waiver-details"><summary>Team needs details: schedule gaps, coverage and production</summary><NeedsDetails board={board} /></details>
      </div>
    </>}
  </section>;
}

function MoveCard({ fill, mode, kicker, onAnalyze }: {
  fill: FillRecommendation;
  mode: WaiverMode;
  kicker: string;
  onAnalyze: (fill: FillRecommendation) => void;
}) {
  const player = fill.add_player;
  const move = fill.suggested_injury_move;
  const target = fill.target_roster_position;
  const explanation = fill.comparison?.explanation ?? null;
  const warnings = (player.evidence_blockers ?? []).length ? player.evidence_blockers ?? [] : sampleRisk(player).slice(0, 3);
  return <article className="waiver-move-card is-supported">
    <header>
      <p className="waiver-kicker">{kicker}</p>
      <div className="waiver-badges"><ActionBadge action={fill.action_type} /><IntentBadge intent={player.move_intent} /> <VerdictBadge verdict={player.verdict} /></div>
      <h3 className="waiver-move-player">{player.player_name}</h3>
      <p className="waiver-move-meta">{positionText(player.position)} · {player.nba_team ?? "NBA team unknown"}</p>
      <CandidateAvailability candidate={player} />
    </header>
    {move && <ol className="waiver-steps">
      <li>Move {move.player_name} from {move.from_slot} to {move.to_slot}. {move.player_name} stays on your roster; this is not a drop.</li>
      <li>Add {player.player_name}{target && target !== "BN" ? ` to cover ${target}` : ""}.</li>
    </ol>}
    <dl className="waiver-move-facts">
      <div><dt>Fills</dt><dd>{fill.fills_needs.length ? fill.fills_needs.join(" / ") : target && target !== "BN" ? target : "Depth (bench)"}</dd></div>
      <div><dt>Yahoo FP/G used</dt><dd>{explanation?.add_production.value != null ? explanation.add_production.value.toFixed(1) : "Unavailable"}<small>{explanation?.add_production.label ?? ""}</small></dd></div>
      <div><dt>Production sample</dt><dd>{seasonSampleText(player.evidence_quality, player.current_season_games)}</dd></div>
      <div><dt>Drop</dt><dd>{fill.requires_drop ? "Drop required" : "No drop required"}</dd></div>
      <div><dt>Games in {modeWindow(mode)}</dt><dd>{explanation?.add_games ?? player.schedule.games_remaining ?? "Unknown"}</dd></div>
      <div><dt>Net</dt><dd>{indexNet(fill.comparison?.net_improvement)}</dd></div>
    </dl>
    <FormLine form={player.form} />
    <h4>Why</h4>
    <ul>{explanation && <li>{explanation.statement}</li>}{player.move_intent_detail && <li>{player.move_intent_detail}</li>}{fill.reasons.slice(1, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul>
    <Tradeoffs explanation={explanation} />
    <details><summary>Exact calculation and evidence warnings ({warnings.length})</summary>
      {explanation && <ExplanationDetails explanation={explanation} />}
      {warnings.length
        ? <ul>{warnings.map((item) => <li key={item}>{item}</li>)}</ul>
        : <p>No additional evidence warnings. Live status, roster locks and claim timing still need Yahoo confirmation.</p>}
      <p>Roster index (no drop): {number(fill.comparison?.before_score)} → {number(fill.comparison?.after_score)} ({signed(fill.comparison?.net_improvement)}); a descriptive model index, not fantasy points.</p>
    </details>
    <EvidenceDimensions dimensions={player.evidence_dimensions} />
    <p className="waiver-user-action">CONFIRM IN YAHOO BEFORE ACTING</p>
    <button className="button button-primary" onClick={() => onAnalyze(fill)}>View details: {player.player_name}</button>
  </article>;
}

function PairCard({ swap, mode, capacity, onAnalyze }: {
  swap: SwapAnalysis;
  mode: WaiverMode;
  capacity: RosterCapacity | null | undefined;
  onAnalyze: (swap: SwapAnalysis) => void;
}) {
  const add = swap.add_player;
  const drop = swap.drop_player;
  const explanation = swap.comparison.explanation ?? null;
  const addValue = explanation?.add_production.value;
  const dropValue = explanation?.drop_production?.value;
  const slots = swap.comparison;
  return <article className="waiver-move-card is-supported">
    <header>
      <p className="waiver-kicker">Best move now</p>
      <div className="waiver-badges"><ActionBadge action="ADD_DROP" /><IntentBadge intent={add.move_intent} /> <VerdictBadge verdict={add.verdict} /></div>
      <h3 className="waiver-move-player">ADD: {add.player_name}</h3>
      <p className="waiver-move-drop">DROP: <strong>{drop.player_name}</strong> · Decision: {swap.decision}</p>
      <CandidateAvailability candidate={add} />
    </header>
    <dl className="waiver-move-facts">
      <div><dt>Net (exact pair)</dt><dd>{indexNet(swap.comparison.net_improvement)}</dd></div>
      <div><dt>Yahoo FP/G used (same basis)</dt><dd>Add {addValue != null ? addValue.toFixed(1) : number(null)} · drop {dropValue != null ? dropValue.toFixed(1) : number(null)}<small>{explanation?.add_production.label ?? "Production basis unavailable"}</small></dd></div>
      <div><dt>Games in {modeWindow(mode)}</dt><dd>{explanation ? `${explanation.add_games ?? "unknown"} vs ${explanation.drop_games ?? "unknown"}` : "Unknown"}{explanation?.window_points_gap != null ? ` · window FP ${explanation.window_points_gap > 0 ? "+" : ""}${explanation.window_points_gap.toFixed(1)}` : ""}</dd></div>
      <div><dt>Starting slots</dt><dd>{slots.starting_slots_before ?? "?"} → {slots.starting_slots_after ?? "?"} of {slots.starting_slots_required ?? "?"}{slots.starting_slots_after != null && slots.starting_slots_before != null && slots.starting_slots_after > slots.starting_slots_before ? " (fills a slot)" : " (no fit change)"}</dd></div>
      <div><dt>Drop</dt><dd>Required: your roster is full</dd></div>
    </dl>
    <FormLine form={add.form} name="Add" />
    <FormLine form={drop.form} name="Drop" />
    <h4>Why</h4>
    <ul>
      {add.move_intent_detail && <li>{add.move_intent_detail}</li>}
      <li>{explanation?.statement ?? "The backend returned no explanation for this pair; do not act on it."}</li>
      {capacity && <li>Why a drop is required: {capacity.drop_requirement_reason}</li>}
    </ul>
    <Tradeoffs explanation={explanation} />
    <WhyThisDrop choice={add.drop_choice} alternatives={add.drop_alternatives} />
    <details><summary>Exact calculation, risks and role evidence</summary>
      {explanation && <ExplanationDetails explanation={explanation} />}
      <p>Add Yahoo status: {yahooStatusText(add)} · drop status: {yahooStatusText(drop)}. Q/P remains uncertain.</p>
      {[add, drop].some(noDesignation) && <p>{[add, drop].find(noDesignation)?.status_detail}</p>}
      <p>Exact roster model index: {exact(swap.comparison.before_score)} → {exact(swap.comparison.after_score)} ({swap.comparison.net_improvement != null && swap.comparison.net_improvement > 0 ? "+" : ""}{exact(swap.comparison.net_improvement)}); descriptive, not projected fantasy points.</p>
      <ul>{swap.limitations.map((risk) => <li key={risk}>{risk}</li>)}</ul>
      <RoleEvidence candidate={add} />
    </details>
    <EvidenceDimensions dimensions={add.evidence_dimensions} />
    <p className="waiver-user-action">CONFIRM IN YAHOO BEFORE ACTING</p>
    <button className="button button-primary" onClick={() => onAnalyze(swap)}>View details: ADD {add.player_name} / DROP {drop.player_name}</button>
  </article>;
}

function MeasuredCard({ option, mode, kicker, fullRoster, onDetails }: {
  option: DecisionOption;
  mode: WaiverMode;
  kicker: string;
  fullRoster: boolean;
  onDetails: (option: DecisionOption) => void;
}) {
  return <article className={`waiver-move-card is-measured is-${(option.verdict ?? "CANNOT_EVALUATE").toLowerCase()}`}>
    <header>
      <p className="waiver-kicker">{kicker}</p>
      <div className="waiver-badges"><span className="waiver-action is-best_measured_option">BEST MEASURED OPTION</span> <VerdictBadge verdict={option.verdict} /></div>
      <h3 className="waiver-move-player">{option.player_name}</h3>
      <p className="waiver-move-meta">{positionText(option.positions)} · {option.nba_team ?? "NBA team unknown"} · <AvailabilityBadge option={option} /></p>
    </header>
    <p className="waiver-option-headline">{option.headline || option.verdict_text}</p>
    {option.pair && <PairFacts option={option} mode={mode} onDetails={onDetails} />}
    {!option.pair && fullRoster && <p className="waiver-tradeoff is-blocker"><strong>No supported drop:</strong> {option.blockers[0] ?? "no measured comparison is available."}</p>}
    <dl className="waiver-move-facts">
      <div><dt>Position-eligible for</dt><dd>{fillsText(option)}</dd></div>
      <div><dt>Schedule</dt><dd>{gamesText(option, mode)}</dd></div>
    </dl>
    <ProductionBlock option={option} />
    <h4>Why</h4>
    <ul>{option.why.map((item) => <li key={item}>{item}</li>)}</ul>
    <div className="waiver-not-supported">
      <p><strong>NOT YET A SUPPORTED ADD</strong></p>
      <p>Yahoo status: <strong>{option.status_label}</strong>. {option.status_detail}</p>
      {option.confirm.length > 0 && <><p><strong>Confirm in Yahoo:</strong></p><ul>{option.confirm.map((item) => <li key={item}>{item}</li>)}</ul></>}
      <details><summary>Why this is not a supported add ({option.blockers.length})</summary>
        <ul>{option.blockers.map((item) => <li key={item}>{item}</li>)}</ul>
      </details>
    </div>
    <EvidenceDimensions dimensions={option.evidence_dimensions} />
    <p className="waiver-user-action">{option.user_action}</p>
    <button className="button button-quiet" onClick={() => onDetails(option)}>View details: {option.player_name}</button>
  </article>;
}

export function OtherGoodOptions({ board, analysis, onDetails, onAnalyzePair }: {
  board: WaiverBoard;
  analysis: TransactionAnalysis | null;
  onDetails: (option: DecisionOption) => void;
  onAnalyzePair: (swap: SwapAnalysis) => void;
}) {
  const support = board.decision_support;
  if (!support) {
    return <section className="panel waiver-panel" aria-labelledby="waiver-options">
      <h2 id="waiver-options">OTHER GOOD OPTIONS</h2>
      <p role="status">Decision support was not returned for this response.</p>
    </section>;
  }
  const byId = new Map(support.options.map((option) => [option.player_id, option]));
  const pick = (ids: number[]) => ids.map((id) => byId.get(id)).filter((option): option is DecisionOption => option !== undefined);
  // Featured options must be eligible with confirmed availability; unconfirmed players are only potential targets.
  const check = featuredCheck(board);
  const withheld: { name: string; reason: string }[] = [];
  const allowed = (option: DecisionOption) => {
    const reason = check(option.player_id, option.availability_classification);
    if (reason) withheld.push({ name: option.player_name, reason });
    return reason === null;
  };
  const groupOptions = new Map(support.groups.map((group) => {
    const candidate = group.player_id != null ? byId.get(group.player_id) : undefined;
    return [group.key, candidate && allowed(candidate) ? candidate : undefined];
  }));
  const watch = pick(support.watch_ids).filter(allowed);
  const potential = pick(support.potential_target_ids).filter((option) => option.classification === "POTENTIAL_TARGET"
    && option.availability_classification != null && CHECKABLE_AVAILABILITY.has(option.availability_classification));
  const unverified = support.availability_state !== "available";
  const fullRoster = board.roster_capacity?.transaction_shape === "ADD_DROP";
  const swaps = analysis?.roster_capacity?.transaction_shape === "ADD_DROP" ? analysis.watch_transactions : [];
  return <section className="panel waiver-panel" aria-labelledby="waiver-options">
    <h2 id="waiver-options">OTHER GOOD OPTIONS</h2>
    <p className="waiver-window-note">Each card answers the transaction question for its exact best comparison: SUPPORTED ADD, WATCH ONLY, NEAR TIE, DO NOT ADD or CANNOT EVALUATE{fullRoster ? ", with the exact drop" : ""}. "Best" never means supported unless the card says SUPPORTED ADD.</p>
    {withheld.map((item) => <ContractError key={`${item.name}-${item.reason}`} name={item.name} reason={item.reason} />)}
    {unverified && <p className="waiver-availability-note">{support.availability_note}</p>}
    <ul className="waiver-option-grid">{support.groups.map((group) => {
      const option = groupOptions.get(group.key);
      return <li key={group.key} className={`waiver-option-card is-${(option?.verdict ?? "empty").toLowerCase()}`}>
        <h3>{group.title}</h3>
        {option ? <OptionCard option={option} mode={board.mode} fullRoster={fullRoster} onDetails={onDetails} />
          : <p>{group.player_id != null ? "Withheld: this option failed the waiver-eligibility check." : group.empty_reason}</p>}
      </li>;
    })}</ul>
    <h3>WATCHLIST</h3>
    <p className="waiver-window-note">Measurable players worth monitoring, each with its own verdict. These are not add recommendations.</p>
    {watch.length
      ? <ul className="waiver-option-list">{watch.map((option) => <li key={option.player_id}><OptionCard option={option} mode={board.mode} fullRoster={fullRoster} onDetails={onDetails} /></li>)}</ul>
      : <p>No additional WATCH players: nobody else out-produces your lowest-producing roster player{support.roster_floor_ppg != null ? ` (${support.roster_floor_ppg.toFixed(1)} Yahoo FP/G model production value)` : ""}.</p>}
    {swaps.length > 0 && <><h4>Measured swaps to watch</h4><WatchSwapList analysis={analysis as TransactionAnalysis} onAnalyze={onAnalyzePair} /></>}
    {unverified && <section className="waiver-potential" aria-labelledby="waiver-potential-title">
      <h3 id="waiver-potential-title">POTENTIAL TARGETS TO CHECK IN YAHOO</h3>
      <p>{support.potential_target_count} measurable player{support.potential_target_count === 1 ? " was" : "s were"} not on any saved league roster, but the saved rosters are not all current. Availability is UNVERIFIED for every player below: they are not supported adds and may already be rostered. Refresh waiver data, or check each one in Yahoo.</p>
      {potential.length
        ? <ol className="waiver-potential-list">{potential.map((option) => <li key={option.player_id}>
          <p><strong className="waiver-option-name">{option.player_name}</strong> · {positionText(option.positions)} · {measuredPpg(option)} · {gamesText(option, board.mode)}</p>
          <p>Fits: {fillsText(option)} · Yahoo status: {option.status_label} · Availability: <AvailabilityBadge option={option} /></p>
          <p className="waiver-user-action">{option.user_action}</p>
          <button className="button button-quiet" onClick={() => onDetails(option)}>View details: {option.player_name}</button>
        </li>)}</ol>
        : <p>No availability-unverified players to list.</p>}
    </section>}
  </section>;
}

function ReplacementCard({ candidate, rank, onAnalyze }: {
  candidate: WaiverCandidate;
  rank: number;
  onAnalyze: (id: number) => void;
}) {
  const comparison = candidate.comparison;
  const explanation = comparison?.explanation ?? null;
  const risks = sampleRisk(candidate);
  return <article className={`waiver-replacement-card is-${(candidate.verdict ?? "CANNOT_EVALUATE").toLowerCase()}`}>
    <header><div><p className="waiver-kicker">Replacement option {rank}</p><h4>{candidate.player_name}</h4></div>
      <VerdictBadge verdict={candidate.verdict} /></header>
    <p>{candidate.position ?? "Position unknown"} · {candidate.nba_team ?? "NBA team unknown"} · Yahoo status: {yahooStatusText(candidate)}</p>
    <p className="waiver-option-headline">{candidate.verdict_text || candidate.action_label}</p>
    {candidate.action_label && <p><ActionBadge action={actionOf(candidate)} /> {candidate.action_label}</p>}
    {explanation && <p><strong>Why:</strong> {explanation.statement}</p>}
    {explanation?.primary_tradeoff && <p className="waiver-tradeoff"><strong>Primary tradeoff:</strong> {explanation.primary_tradeoff}</p>}
    <CandidateSamples candidate={candidate} />
    <RoleEvidence candidate={candidate} />
    <p><strong>Ranking blend:</strong> {candidate.ranking_value.label} · blended value {number(candidate.ranking_value.value)} · recent weight {candidate.ranking_value.recent_weight === null ? "Unavailable" : `${(candidate.ranking_value.recent_weight * 100).toFixed(0)}%`} · historical {number(candidate.ranking_value.historical_value)} ({candidate.ranking_value.historical_games} games, {candidate.ranking_value.historical_season ?? "season unavailable"}). Historical value is not a projection.</p>
    <dl className="waiver-comparison">
      <div><dt>Selected drop</dt><dd>{comparison?.player_name ?? "No measured comparison for this roster player"}</dd></div>
      <div><dt>Roster before</dt><dd>{number(comparison?.before_score)}</dd></div>
      <div><dt>Roster after</dt><dd>{number(comparison?.after_score)}</dd></div>
      <div><dt>Net improvement</dt><dd>{indexNet(comparison?.net_improvement)}</dd></div>
    </dl>
    {comparison && (comparison.net_improvement === null || comparison.net_improvement <= 0
      ? <p className="waiver-outcome is-no-improvement"><strong>No measured improvement.</strong> This swap is a tradeoff, not a recommendation to replace the selected player.</p>
      : explanation && !explanation.consistent
        ? <p className="waiver-outcome is-no-improvement"><strong>{explanation.near_tie ? "Near tie — no strong preference." : "Positive index change not supported."}</strong> {explanation.blocker ?? explanation.statement}</p>
        : <p className="waiver-outcome"><strong>Positive measured roster-index change.</strong> This is descriptive evidence, not a projection or guarantee.</p>)}
    {candidate.add_only_impact && <p className="waiver-outcome"><strong>Dropping is optional.</strong> Without a drop: {number(candidate.add_only_impact.before_score)} → {number(candidate.add_only_impact.after_score)} ({signed(candidate.add_only_impact.net_improvement)}) using an open roster spot.</p>}
    {comparison && (explanation
      ? <details><summary>Exact calculation for this drop</summary><ExplanationDetails explanation={explanation} /></details>
      : <p><strong>Starting-slot compatibility:</strong> {comparison.starting_slots_before ?? "?"} before → {comparison.starting_slots_after ?? "?"} after; {comparison.starting_slots_required ?? "?"} starting slots required.</p>)}
    <p><strong>Schedule:</strong> {candidate.schedule.games_remaining ?? "Unknown"} games, {candidate.schedule.off_day_games ?? "unknown"} off-day games, {candidate.schedule.back_to_backs ?? "unknown"} back-to-back pairs · {candidate.schedule.window_start}–{candidate.schedule.window_end} Pacific · {candidate.schedule.opponents.join(", ") || "opponents unavailable"}.</p>
    <p><strong>Opportunity:</strong> {candidate.opportunity.role}; {number(candidate.opportunity.minutes)} minutes · opportunity index {number(candidate.components.opportunity)}.</p>
    <h5>Reasons and tradeoffs</h5>
    {candidate.reasons.length ? <ul>{candidate.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul> : <p>No supported reason recorded.</p>}
    <h5>Risks and limitations</h5>
    {risks.length ? <ul>{risks.map((risk) => <li key={risk}>{risk}</li>)}</ul> : <p>No additional limitations reported.</p>}
    <button className="button button-quiet" onClick={() => onAnalyze(candidate.player_id)}>Analyze option: {candidate.player_name}</button>
  </article>;
}

// Derived from the same gated exact-pair decisions the optimizer uses.
const ROSTER_DECISION_TEXT: Record<WaiverCandidate["roster_decision"], string> = {
  review_replacement: "Supported replacement exists",
  watch_replacement: "Watch only: positive but unsupported replacements",
  keep_on_measured_model: "Keep: no supported replacement",
  unavailable: "Cannot evaluate: no measured comparison",
};

function RosterPicker({ roster, selectedId, onSelect }: {
  roster: WaiverCandidate[];
  selectedId: number | null;
  onSelect: (id: number) => void;
}) {
  const [search, setSearch] = useState("");
  const matchingRoster = roster.filter((candidate) =>
    `${candidate.player_name} ${candidate.position ?? ""}`.toLowerCase().includes(search.trim().toLowerCase()),
  );
  if (!roster.length) return <p role="status">No imported manager roster is available for drop comparisons.</p>;
  return <>
    <label className="waiver-filter">Search roster players
      <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
    </label>
    <fieldset className="waiver-roster-picker"><legend>Choose one roster player to compare as the drop</legend>
      {!matchingRoster.length && <p role="status">No roster players match this search.</p>}
      {matchingRoster.map((candidate) => <label className={`waiver-roster-card${candidate.player_id === selectedId ? " is-selected" : ""}`} key={candidate.player_id}>
        <input type="radio" name="selected-drop" value={candidate.player_id} checked={candidate.player_id === selectedId} onChange={() => onSelect(candidate.player_id)} />
        <span className="waiver-roster-main"><strong>{candidate.player_name}</strong><span>{candidate.position ?? "Position unknown"} · {yahooStatusText(candidate)} · {candidate.schedule.games_remaining ?? "?"} schedule games</span></span>
        <span className="waiver-roster-evidence">{ROSTER_DECISION_TEXT[candidate.roster_decision] ?? label(candidate.roster_decision)}<br />Recent {number(candidate.recent.value)} fantasy PPG · {candidate.recent.games} games<br />Season Evidence {number(candidate.ros.value)} fantasy PPG · {candidate.ros.games} games</span>
      </label>)}
    </fieldset>
  </>;
}

/** The backend's answer for the exact selected drop. Players are only looked up by ID: the page never ranks or
 * promotes a card itself, and a missing or inconsistent answer names nobody. */
export function SelectedDropAnswer({ board, selectedDropId, onAnalyze }: {
  board: WaiverBoard;
  selectedDropId: number | null;
  onAnalyze: (id: number) => void;
}) {
  const summary = board.drop_summary;
  if (!summary || summary.drop_player_id !== selectedDropId) {
    return <p className="notice notice-error" role="alert">The selected-drop answer is missing from this response; no replacement is named.</p>;
  }
  const best = summary.best_valid_replacement_id === null ? null
    : board.candidates.find((candidate) => candidate.player_id === summary.best_valid_replacement_id);
  if (best !== null && best?.verdict !== "SUPPORTED_ADD") {
    return <p className="notice notice-error" role="alert">The selected-drop answer was withheld: its best valid replacement is not a SUPPORTED ADD card in this response.</p>;
  }
  const raw = summary.highest_raw_comparison;
  return <div className="waiver-drop-answer">
    <p className="waiver-outcome"><strong>{summary.result}</strong></p>
    {best && <p className="waiver-best-valid"><span className="waiver-kicker">BEST VALID REPLACEMENT:</span> <strong>{best.player_name}</strong> <VerdictBadge verdict={best.verdict} /></p>}
    <p className="waiver-option-headline">{summary.headline}</p>
    {raw && <div className="waiver-raw-comparison">
      <p className="waiver-kicker">HIGHEST RAW MODEL COMPARISON — not a recommendation</p>
      <p><strong>{raw.player_name}</strong> <VerdictBadge verdict={raw.verdict} /></p>
      <dl className="waiver-comparison">
        <div><dt>Raw net</dt><dd>{indexNet(raw.raw_net)}</dd></div>
        <div><dt>Reconciled net</dt><dd>{indexNet(raw.reconciled_net)}</dd></div>
      </dl>
      <p><strong>Why it is not the answer:</strong> {raw.reason}</p>
      <button className="button button-quiet" onClick={() => onAnalyze(raw.candidate_id)}>Analyze ADD {raw.player_name} / DROP {summary.drop_player_name}</button>
    </div>}
  </div>;
}

export function Replacements({ board, loading, error, selectedDropId, onAnalyze }: {
  board: WaiverBoard | null;
  loading: boolean;
  error: string;
  selectedDropId: number | null;
  onAnalyze: (id: number) => void;
}) {
  if (board && board.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <div aria-labelledby="waiver-replacements">
      <h3 id="waiver-replacements">Top 3 replacements</h3>
      <p className="notice notice-error" role="alert">Replacement evidence uses incompatible model {board.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Do not use these results.</p>
    </div>;
  }
  return <div className="waiver-replacements">
    <h3 id="waiver-replacements">Top 3 replacements</h3>
    <p>Each comparison uses only the selected drop: {board?.roster.find((candidate) => candidate.player_id === selectedDropId)?.player_name ?? "select a roster player"}.</p>
    <p className="waiver-window-note">Ordered by the backend: supported moves first, then WATCH, HOLD and insufficient evidence; within each group by measured net improvement.</p>
    {loading && <p role="status">Loading replacements for the selected player...</p>}
    {error && <p role="alert">{error} Select the roster player again or reload to retry.</p>}
    {!loading && !error && !board && selectedDropId === null && <p>No comparison is available without a roster player selection.</p>}
    {!loading && !error && board && <SelectedDropAnswer board={board} selectedDropId={selectedDropId} onAnalyze={onAnalyze} />}
    {!loading && !error && board && !board.candidates.length && <p role="status">No replacement candidates are supported for this selected player.</p>}
    {!loading && !error && board && <div className="waiver-replacement-list">
      {board.candidates.slice(0, 3).map((candidate, index) =>
        <ReplacementCard key={candidate.player_id} candidate={candidate} rank={index + 1} onAnalyze={onAnalyze} />)}
    </div>}
  </div>;
}

export function CompareDropSection({ board, selectedDropId, onSelect, replacementBoard, loading, error, onAnalyze }: {
  board: WaiverBoard;
  selectedDropId: number | null;
  onSelect: (id: number) => void;
  replacementBoard: WaiverBoard | null;
  loading: boolean;
  error: string;
  onAnalyze: (id: number) => void;
}) {
  const capacity = board.roster_capacity;
  const full = capacity?.requires_drop === true;
  const optional = capacity?.requires_drop === false;
  return <section className={`panel waiver-panel waiver-compare ${full ? "is-promoted" : "is-muted"}`} aria-labelledby="waiver-compare">
    <h2 id="waiver-compare">COMPARE A SPECIFIC DROP</h2>
    <p>{full
      ? "Your roster is full, so an add needs a drop. Choose one roster player to compare every replacement against."
      : optional
        ? "Optional: no drop is required for your next add."
        : "Optional what-if: roster capacity is undetermined, so no drop is assumed."} The chosen drop stays fixed in every comparison; nobody is preselected.</p>
    <details className="waiver-compare-picker" open={full || selectedDropId !== null}>
      <summary>{full ? "Choose a roster player to compare as the drop" : "Show the optional drop comparison"}</summary>
      {capacity && !full && <p>{capacity.drop_requirement_reason}</p>}
      <RosterPicker roster={board.roster} selectedId={selectedDropId} onSelect={onSelect} />
      {selectedDropId !== null && <Replacements board={replacementBoard} loading={loading} error={error} selectedDropId={selectedDropId} onAnalyze={onAnalyze} />}
    </details>
  </section>;
}

const DECISION_FILTERS = ["ADD ONLY", "MOVE TO IL, THEN ADD", "ADD + DROP", "BEST MEASURED OPTION", "WATCH", "MEASURED", "POTENTIAL TARGET", "NOT COMPARABLE"];
const VERDICT_FILTERS = Object.keys(VERDICT_TEXT) as TransactionVerdict[];
const EVIDENCE_ORDER = ["EXCELLENT", "GOOD", "LIMITED", "VERY LIMITED", "INSUFFICIENT FOR STRONG RECOMMENDATION", "NO CURRENT-SEASON EVIDENCE"];
// Backend not-comparable reason key for O/OFS/NA players whose availability is unverified.
const ONA_REASON = "Yahoo O/OFS/NA status";
// Exploratory client sorts over backend-supplied numbers only; they never change BEST MOVES or decision_rank.
const SORT_VALUES: Record<string, (option: DecisionOption) => number | null | undefined> = {
  ppg: (option) => option.measured.value,
  games: (option) => option.games_in_window,
  evidence: (option) => -EVIDENCE_ORDER.indexOf(option.evidence_level),
  last7: (option) => option.form?.last_7_ppg,
  last14: (option) => option.form?.last_14_ppg,
  last30: (option) => option.form?.last_30_ppg,
  season: (option) => option.form?.season_ppg,
  next7: (option) => option.form?.next_7_games,
  next14: (option) => option.form?.next_14_games,
};

export function FullWaiverList({ board, onDetails }: { board: WaiverBoard; onDetails: (option: DecisionOption) => void }) {
  const [search, setSearch] = useState("");
  const [positionFilter, setPositionFilter] = useState("all");
  const [needFilter, setNeedFilter] = useState("all");
  const [decisionFilter, setDecisionFilter] = useState("all");
  const [evidenceFilter, setEvidenceFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [scheduleFilter, setScheduleFilter] = useState("all");
  const [sampleFilter, setSampleFilter] = useState("all");
  const [availabilityFilter, setAvailabilityFilter] = useState("all");
  const [sortBy, setSortBy] = useState("decision");
  const [verdictFilter, setVerdictFilter] = useState("all");
  const support = board.decision_support;
  if (board.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <p className="notice notice-error" role="alert">Board results use incompatible model {board.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Decision, ranking, and analysis actions are disabled.</p>;
  }
  // Rostered players are never waiver options, whatever else the response contains.
  const options = (support?.options ?? []).filter((option) =>
    option.availability_classification == null || !ROSTERED_AVAILABILITY.has(option.availability_classification));
  const isConfirmed = (option: DecisionOption) => option.availability_confirmed && actionableClass(option.availability_classification);
  const confirmed = options.filter(isConfirmed).length;
  const onaExcluded = board.excluded_count + (support?.not_comparable_reasons?.[ONA_REASON] ?? 0);
  const statuses = [...new Set(options.map((option) => option.yahoo_status).filter((status): status is string => status !== null))].sort();
  const rows = options.filter((option) => {
    const positions = (option.positions ?? "").split(",").map((position) => position.trim().toUpperCase());
    return `${option.player_name} ${option.nba_team ?? ""}`.toLowerCase().includes(search.trim().toLowerCase())
      && (positionFilter === "all" || positions.includes(positionFilter))
      && (needFilter === "all" || (needFilter === "HIGH" ? option.fills_level === "HIGH" : option.fills.length > 0))
      && (decisionFilter === "all" || decisionText(option) === decisionFilter)
      && (verdictFilter === "all" || (option.verdict ?? "CANNOT_EVALUATE") === verdictFilter)
      && (evidenceFilter === "all" || option.evidence_level === evidenceFilter)
      && (statusFilter === "all" || (statusFilter === "unknown" ? option.yahoo_status === null && !noDesignation(option)
        : statusFilter === "no_designation" ? noDesignation(option) : option.yahoo_status === statusFilter))
      && (scheduleFilter === "all" || (scheduleFilter === "known" ? option.games_in_window !== null : (option.games_in_window ?? 0) >= 3))
      && (sampleFilter === "all" || (sampleFilter === "comparable" ? option.measured.comparable : option.measured.current_games >= 7))
      && (availabilityFilter === "all" || (availabilityFilter === "confirmed") === isConfirmed(option));
  }).sort((left, right) => {
    // Backend-owned decision order; the frontend never re-ranks decisions.
    if (sortBy === "decision" || !SORT_VALUES[sortBy]) return left.decision_rank - right.decision_rank;
    const value = SORT_VALUES[sortBy];
    return (value(right) ?? -Infinity) - (value(left) ?? -Infinity) || left.decision_rank - right.decision_rank;
  });
  return <section className="panel waiver-panel" aria-labelledby="waiver-ranked">
    <h2 id="waiver-ranked">FULL WAIVER LIST</h2>
    <details className="waiver-full-list">
      <summary>Show all {options.length} players ({confirmed} unrostered in every current league roster · {options.length - confirmed} availability unverified)</summary>
      <p>Ranked by the backend: supported moves first, then the best measured option, WATCH, measured players, potential targets whose availability is unverified, and players who cannot be compared. Each row shows the backend verdict for its exact best comparison. "Unrostered" means absent from every current league roster; Yahoo FA/waiver state must still be confirmed in Yahoo. Fantasy PPG is historical Yahoo-rule production, not a projection. Filters only narrow the list and sorting is exploratory: neither creates a recommendation or changes BEST MOVES or the backend rank.</p>
      <p>{onaExcluded} Yahoo O/OFS/NA players excluded. Players on another team's saved roster are not listed.</p>
      {!options.length ? <p role="status">No available or availability-unverified players can be listed. Review ADVANCED EVIDENCE for the exact reasons.</p> : <>
        <div className="waiver-filters" aria-label="Waiver list filters">
          <label className="waiver-filter">Search players
            <input type="search" value={search} onChange={(event) => setSearch(event.target.value)} />
          </label>
          <label className="waiver-filter">Position
            <select value={positionFilter} onChange={(event) => setPositionFilter(event.target.value)}>
              <option value="all">All positions</option>
              {["PG", "SG", "SF", "PF", "C"].map((position) => <option key={position} value={position}>{position}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Roster need
            <select value={needFilter} onChange={(event) => setNeedFilter(event.target.value)}>
              <option value="all">Any</option><option value="need">Fills a need</option><option value="HIGH">Fills a HIGH need</option>
            </select>
          </label>
          <label className="waiver-filter">Verdict
            <select value={verdictFilter} onChange={(event) => setVerdictFilter(event.target.value)}>
              <option value="all">All verdicts</option>
              {VERDICT_FILTERS.map((item) => <option key={item} value={item}>{VERDICT_TEXT[item]}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Action type
            <select value={decisionFilter} onChange={(event) => setDecisionFilter(event.target.value)}>
              <option value="all">All action types</option>
              {DECISION_FILTERS.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Current-season sample
            <select value={evidenceFilter} onChange={(event) => setEvidenceFilter(event.target.value)}>
              <option value="all">Any current-season sample</option>
              {EVIDENCE_ORDER.map((item) => <option key={item} value={item}>{SAMPLE_BAND_TEXT[item as WaiverSampleLabel]}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Yahoo status
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option><option value="unknown">Unknown / blank</option>
              {options.some(noDesignation) && <option value="no_designation">No current Yahoo designation</option>}
              {statuses.map((status) => <option key={status} value={status}>{status}</option>)}
            </select>
          </label>
          <label className="waiver-filter">Schedule
            <select value={scheduleFilter} onChange={(event) => setScheduleFilter(event.target.value)}>
              <option value="all">Any schedule</option><option value="known">Games known</option><option value="3plus">3+ games in window</option>
            </select>
          </label>
          <label className="waiver-filter">Production sample
            <select value={sampleFilter} onChange={(event) => setSampleFilter(event.target.value)}>
              <option value="all">Any sample</option><option value="comparable">Comparable</option><option value="7plus">7+ current-season games</option>
            </select>
          </label>
          <label className="waiver-filter">Availability
            <select value={availabilityFilter} onChange={(event) => setAvailabilityFilter(event.target.value)}>
              <option value="all">All</option><option value="confirmed">Unrostered in every current league roster</option><option value="unverified">Availability unverified</option>
            </select>
          </label>
          <label className="waiver-filter">Sort by
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              <option value="decision">Decision priority (backend)</option><option value="ppg">Model production value</option>
              <option value="last7">Last 7 Days FP/G</option><option value="last14">Last 14 Days FP/G</option>
              <option value="last30">Last 30 Days FP/G</option><option value="season">Season FP/G</option>
              <option value="next7">Next 7 Days games</option><option value="next14">Next 14 Days games</option>
              <option value="games">Games in window</option><option value="evidence">Evidence level</option>
            </select>
          </label>
        </div>
        {!rows.length ? <p role="status">No players match the current filters.</p> :
          <div className="waiver-table-scroll" role="region" aria-label="Waiver list, scroll horizontally for all columns" tabIndex={0}>
            <table className="waiver-table">
              <caption>Backend-ranked players. Details open evidence only; no Yahoo transaction is executed.</caption>
              <thead><tr>{["Rank", "Player", "Pos", "Availability", "Yahoo status", "Verdict", "Fills need", "Model production value (Yahoo FP/G)", "Form FP/G (Last 7 · 14 · 30 · Season)", "Games", "Next 7 / 14", "Current-season sample", "Details"].map((column) =>
                <th key={column} scope="col">{column}</th>)}</tr></thead>
              <tbody>{rows.map((option) => <tr key={option.player_id}>
                <td>{option.decision_rank}</td>
                <th scope="row">{option.player_name}<small>{option.nba_team ?? "NBA team unknown"}</small></th>
                <td>{positionText(option.positions, "Unknown")}</td>
                <td><AvailabilityBadge option={option} /></td>
                <td>{option.status_label}</td>
                <td><VerdictBadge verdict={option.verdict} /><small>{option.headline || option.reason}</small><small>List group: {decisionText(option)}</small></td>
                <td>{option.fills.join(", ") || "None"}{option.fills_level && <small>{option.fills_level} priority</small>}</td>
                <td>{number(option.measured.value)}<small>{measuredBasisLabel(option.measured)}{option.measured.state === "stale" ? " · stale" : ""}</small></td>
                <td>{option.form ? `${ppgText(option.form.last_7_ppg, option.form.last_7_reason)} · ${ppgText(option.form.last_14_ppg, option.form.last_14_reason)} · ${ppgText(option.form.last_30_ppg, option.form.last_30_reason)} · ${ppgText(option.form.season_ppg, option.form.season_reason)}` : "Unavailable"}<small>{option.form ? trendText(option.form.trend) : "No form evidence"}</small></td>
                <td>{option.games_in_window ?? "Unknown"}<small>{option.games_in_window_state}</small></td>
                <td>{option.form ? `${option.form.next_7_games ?? "?"} / ${option.form.next_14_games ?? "?"}` : "Unknown"}</td>
                <td>{option.current_season_games ?? "?"} games<small>{SAMPLE_BAND_TEXT[option.evidence_level]}</small></td>
                <td><button className="button button-quiet" onClick={() => onDetails(option)}>Details: {option.player_name}</button></td>
              </tr>)}</tbody>
            </table>
          </div>}
      </>}
    </details>
  </section>;
}

export function WindowNote({ board }: { board: WaiverBoard }) {
  const restOfWeek = board.mode === "this_week" && daysUntilPacificSunday(board.generated_at) < 2;
  return <p className="waiver-window-note">{board.mode === "this_week"
    ? `Rest of Week${restOfWeek ? " · limited days remaining" : ""}: persisted games through Sunday Pacific Time, not a verified Yahoo matchup week.`
    : board.mode === "next_7_days"
      ? "Next 7 Days: today through today + 6 in Pacific Time; this is not the Yahoo matchup week."
      : board.mode === "next_14_days"
        ? "Next 14 Days: today through today + 13 in Pacific Time (a forward schedule window, not Last 14 Days form); not two Yahoo matchup weeks."
        : "Rest of Season Outlook: a current roster decision from Season Evidence (historical production), current role, the persisted remaining schedule and roster fit. No projected fantasy totals."}</p>;
}

export function AdvancedEvidence({ board, analysis }: { board: WaiverBoard; analysis: TransactionAnalysis | null }) {
  const support = board.decision_support;
  const fillShape = analysis?.roster_capacity?.transaction_shape === "ADD_ONLY" || analysis?.roster_capacity?.transaction_shape === "MOVE_TO_IL_THEN_ADD";
  const blockerCounts = analysis ? Object.entries(fillShape ? analysis.excluded_addition_reasons ?? {} : analysis.excluded_pair_reasons) : [];
  return <section className="panel waiver-panel" aria-labelledby="waiver-quality">
    <h2 id="waiver-quality">ADVANCED EVIDENCE</h2>
    <details className="waiver-advanced">
      <summary>Show data quality, source timestamps, coverage, DATA GAPS and model details</summary>
      <p>Model version {board.model_version} · calculated {timestamp(board.generated_at)} · read from persisted data only.</p>
      <h3>Source timestamps</h3>
      {(board.evidence_freshness ?? []).length
        ? <ul>{(board.evidence_freshness ?? []).map((item) => <li key={item.source}><strong>{item.source}: {STATE_TEXT[item.state]}</strong> · {item.as_of ? timestamp(item.as_of) : "no import recorded"} · {item.detail}</li>)}</ul>
        : <p>Source timestamps were not returned.</p>}
      {support && <>
        <h3>Decision-support method</h3>
        <p>{support.headline} {support.detail}</p>
        <p>{support.method}</p>
        <p>{support.comparable_count} comparable players · {support.potential_target_count} availability unverified · {support.supported_count} featured supported move{support.supported_count === 1 ? "" : "s"}.</p>
        {board.sample_policy && <><h4>Recent-sample policy</h4><p>{board.sample_policy}</p></>}
        <h4>Players that cannot be compared or targeted</h4>
        {Object.keys(support.not_comparable_reasons).length
          ? <ul>{Object.entries(support.not_comparable_reasons).map(([reason, count]) => <li key={reason}>{reason}: {count}</li>)}</ul>
          : <p>None.</p>}
        <ul>{support.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
      </>}
      {analysis && <>
        <h3>Supported-action evidence counts</h3>
        <p>{fillShape
          ? `${analysis.evaluated_addition_count ?? 0} no-drop additions evaluated · ${analysis.supported_addition_count ?? 0} supported · ${analysis.excluded_addition_count ?? 0} excluded. ADD + DROP pairs are not evaluated while no-drop capacity exists.`
          : `${analysis.evaluated_pair_count} add/drop pairs evaluated · ${analysis.supported_move_count ?? 0} supported moves (positive ADD or STREAM; the best is featured) · ${analysis.supported_pair_count} supported pairs including PASS · ${analysis.excluded_pair_count} excluded from the supported pool.`}</p>
        {blockerCounts.length > 0 && <ul>{blockerCounts.map(([reason, count]) => <li key={reason}>{reason}: {count} {fillShape ? "players" : "pairs"}</li>)}</ul>}
        <h4>Acquisition context</h4>
        <ul>{analysis.acquisition_context.rules.map((rule) => <li key={rule}>{rule}</li>)}</ul>
        <p>{analysis.acquisition_context.detail}</p>
      </>}
      <h3>Weights and identifiers</h3>
      <p>Default configured weights: {Object.entries(board.weights).map(([key, value]) => `${label(key)} ${(value * 100).toFixed(0)}%`).join(" · ")}. Missing components are omitted and measured weights renormalized, never filled with invented values.</p>
      <p>Best overall available ID: {board.best_overall_available_id ?? "Unavailable"} · best team-fit ID: {board.best_add_for_team_id ?? "Unavailable"} · top measured candidate ID: {board.top_measured_candidate_id ?? "Unavailable"}.</p>
      <ul>{board.team_needs.map((need) => <li key={need}>{need}</li>)}</ul>
      {board.waiver_rules?.length
        ? <><h3>Persisted waiver rules</h3><ul>{board.waiver_rules.map((rule) => <li key={rule}>{rule}</li>)}</ul></>
        : <p>Fresh persisted waiver rules are unavailable.</p>}
      <h3>Acquisition context</h3>
      <p>{board.acquisition_context?.detail ?? "Waiver priority and weekly adds were not returned for this response."} The existing Yahoo import does not supply exact waiver claim-clear times.</p>
      {board.availability_summary && <>
        <h3>Yahoo availability evidence</h3>
        <p>{board.availability_summary.detail}</p>
        {board.availability_summary.source_gap && <p>{board.availability_summary.source_gap}</p>}
        <ul>{Object.entries(board.availability_summary.counts).map(([key, count]) => <li key={key}>{label(key)}: {count}</li>)}</ul>
        <p>{board.candidate_count ?? board.candidates.length} waiver-eligible candidates; full evidence is returned for the top {board.candidate_limit ?? board.candidates.length}, and every player is listed in FULL WAIVER LIST.</p>
      </>}
      <Quality fields={board.data_quality} />
      <CoverageSummary board={board} />
      <h3>Unsupported analytics and limitations</h3>
      <ul>{board.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul>
    </details>
  </section>;
}

export function ImpactContent({ impact, selectedDropId }: { impact: WaiverImpact; selectedDropId: number | null }) {
  if (impact.model_version !== CURRENT_WAIVER_MODEL_VERSION) {
    return <p className="notice notice-error" role="alert">Impact evidence uses incompatible model {impact.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. Do not use this analysis.</p>;
  }
  const player = impact.candidate;
  const comparison = impact.comparison;
  const type = comparison?.comparison_type ?? (comparison && comparison.player_id === null ? "ADD_ONLY" : "ADD_DROP");
  // Without a chosen drop, a full-roster comparison is the model's best measured drop, not a user selection.
  const modelDrop = type === "ADD_DROP" && selectedDropId === null;
  // On a full roster the backend pairs each add with its best supported drop (else its best measured drop).
  const supportedDrop = modelDrop && player.recommended_action_type === "ADD_DROP";
  const heading = type === "ADD_DROP" ? (modelDrop ? `Best ${supportedDrop ? "supported" : "measured"} drop for this add (roster full)` : "Selected drop comparison")
    : type === "MOVE_TO_IL_THEN_ADD" ? "MOVE TO IL, THEN ADD comparison" : "ADD ONLY comparison (no drop)";
  return <>
    <h2 id="waiver-impact-title">{player.player_name}: {type === "ADD_DROP" ? "add/drop analysis" : "add analysis"}</h2>
    <p>{player.position ?? "Unknown position"} · {player.nba_team ?? "Unknown NBA team"} · Yahoo {yahooStatusText(player)} · {label(player.availability)} · {label(player.hold_type)}</p>
    {player.action_label && <p className="waiver-action-label"><ActionBadge action={actionOf(player)} /><IntentBadge intent={player.move_intent} /> <span>{player.action_label}</span></p>}
    <RosterDecision player={player} comparison={comparison} />
    <EvidenceDimensions dimensions={player.evidence_dimensions} />
    <FormPanel candidate={player} />
    <CandidateSamples candidate={player} />
    <RoleEvidence candidate={player} />
    <p>Ranking blend: {player.ranking_value.label} · recent weight {player.ranking_value.recent_weight === null ? "Unavailable" : `${(player.ranking_value.recent_weight * 100).toFixed(0)}%`} · historical evidence, not a projection.</p>
    <h3>Why this player?</h3>
    <ul>{player.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
    <p>Minutes {number(player.opportunity.minutes)}; minutes trend {number(player.opportunity.minutes_trend)}; usage trend {number(player.opportunity.usage_trend)}; historical start rate {number(player.opportunity.historical_start_rate)}. No inferred injury opportunity.</p>
    <p>Persisted schedule {player.schedule.window_start} through {player.schedule.window_end} (Pacific Time): {player.schedule.games_remaining ?? "unknown"} games, {player.schedule.off_day_games ?? "unknown"} off-day games, {player.schedule.back_to_backs ?? "unknown"} back-to-back pairs. Opponents: {player.schedule.opponents.join(", ") || "Unavailable"}.</p>
    <h3>{heading}</h3>
    {comparison ? <>
      <p>{type === "ADD_DROP"
        ? `Add ${player.player_name}; drop ${comparison.player_name}.${modelDrop ? ` This is the model's best ${supportedDrop ? "supported" : "measured"} drop for this add; use Compare a specific drop to fix a different drop.` : ""}`
        : type === "MOVE_TO_IL_THEN_ADD"
          ? `Move ${comparison.moved_to_injury_slot_player_name ?? "the injured player"} to IL (that player stays on your roster), then add ${player.player_name}. No player is dropped.`
          : `Add ${player.player_name}; no player is dropped.`}
        {comparison.target_roster_position ? (comparison.starting_slots_after != null && comparison.starting_slots_before != null
          && comparison.starting_slots_after > comparison.starting_slots_before
          ? ` Fills the ${comparison.target_roster_position} starting slot.`
          : ` Takes the ${comparison.target_roster_position} slot (no change in matched starting slots).`) : ""}
        {comparison.open_roster_spots_before != null ? ` Open roster spots ${comparison.open_roster_spots_before} → ${comparison.open_roster_spots_after}.` : ""}</p>
      <dl className="waiver-comparison"><div><dt>Roster before</dt><dd>{number(comparison.before_score)}</dd></div>
        <div><dt>Roster after</dt><dd>{number(comparison.after_score)}</dd></div>
        <div><dt>Net model improvement</dt><dd>{indexNet(comparison.net_improvement)}</dd></div></dl>
      <p>This is a descriptive roster-index difference, not expected fantasy points or a prediction.</p>
      {comparison.explanation && <p className="waiver-option-headline"><strong>Why:</strong> {comparison.explanation.statement}</p>}
      {modelDrop && <WhyThisDrop choice={player.drop_choice} alternatives={player.drop_alternatives} />}
      <ul>{comparison.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
      <h4>Exact calculation</h4>
      {comparison.explanation ? <ExplanationDetails explanation={comparison.explanation} />
        : <dl className="waiver-quality">{Object.entries(comparison.component_deltas).map(([key, value]) =>
          <div key={key}><dt>{label(key)}</dt><dd>{number(value)}</dd></div>)}</dl>}
    </> : <p>{selectedDropId !== null
      ? `No measured comparison is available for selected roster player ID ${selectedDropId}. The selected drop will not be changed automatically.`
      : `No comparison is available: ${(player.evidence_blockers ?? [])[0] ?? "required roster-capacity or production evidence is missing."} No drop is assumed.`}</p>}
    <details><summary>Advanced Evidence · components, weights, and source quality</summary>
      <h3>Per-player component scores</h3>
      <p>This player's own available components and renormalized weights (used only for list ordering). Every pair comparison above uses the request's common component mask.</p>
      <dl className="waiver-quality">{Object.entries(player.components).map(([key, value]) =>
        <div key={key}><dt>{label(key)}</dt><dd>{exact(value)} / 100 · {((player.effective_weights[key] ?? 0) * 100).toFixed(1)}%</dd></div>)}</dl>
      <Quality fields={player.data_quality} />
      <ul>{impact.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
    </details>
    <p>Analysis only. Complete any transaction yourself in Yahoo after checking current availability.</p>
  </>;
}

function netText(value: number | null | undefined): string {
  return value == null ? "Unavailable" : `${netDigits(value)} roster-index points`;
}

/** The decision first: who to add, who to drop, the measured net, why, and what still blocks it. */
function RosterDecision({ player, comparison }: { player: WaiverCandidate; comparison: WaiverImpact["comparison"] }) {
  const blockers = player.evidence_blockers ?? [];
  return <section className="waiver-roster-decision" aria-label={`Roster decision for ${player.player_name}`}>
    <h3>ROSTER DECISION</h3>
    <dl className="waiver-move-facts">
      <div><dt>ADD</dt><dd>{player.player_name}</dd></div>
      <div><dt>DROP</dt><dd>{comparison ? (comparison.player_id != null ? comparison.player_name : "No drop needed") : "Not measured"}</dd></div>
      <div><dt>NET</dt><dd>{netText(comparison?.net_improvement)}</dd></div>
      <div><dt>VERDICT</dt><dd><VerdictBadge verdict={player.verdict} /></dd></div>
    </dl>
    {player.verdict_text && <p className="waiver-option-headline">{player.verdict_text}</p>}
    <p><strong>WHY:</strong> {comparison?.explanation?.statement || player.move_intent_detail || player.action_label || "No supported move is established."}</p>
    {comparison?.explanation?.primary_tradeoff && <p className="waiver-tradeoff"><strong>Primary tradeoff:</strong> {comparison.explanation.primary_tradeoff}</p>}
    {blockers.length > 0 && <><p><strong>BLOCKERS:</strong></p><ul>{blockers.map((item) => <li key={item}>{item}</li>)}</ul></>}
  </section>;
}

function useModalDialog() {
  const dialog = useRef<HTMLDialogElement>(null);
  useLayoutEffect(() => {
    const element = dialog.current;
    const previousFocus = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (previousFocus instanceof HTMLElement) previousFocus.focus();
    };
  }, []);
  return dialog;
}

function DecisionOptionSummary({ option }: { option: DecisionOption }) {
  return <section className="waiver-option-detail" aria-label={`Decision support for ${option.player_name}`}>
    <p className="waiver-action-label"><ClassBadge option={option} /> <AvailabilityBadge option={option} /> <span>{option.reason}</span></p>
    <p><strong>Model production value:</strong> {option.measured.detail}</p>
    <ProductionBuckets buckets={option.measured.buckets} />
    <p><strong>Yahoo status:</strong> {option.status_label}. {option.status_detail}</p>
    {option.blockers.length > 0 && <><h3>Why this is not a supported add</h3><ul>{option.blockers.map((item) => <li key={item}>{item}</li>)}</ul></>}
    {option.confirm.length > 0 && <><h3>Confirm in Yahoo</h3><ul>{option.confirm.map((item) => <li key={item}>{item}</li>)}</ul></>}
  </section>;
}

function ImpactDialog({ playerId, mode, dropPlayerId, option, onClose }: {
  playerId: number;
  mode: WaiverMode;
  dropPlayerId: number | null;
  option?: DecisionOption | null;
  onClose: () => void;
}) {
  const dialog = useModalDialog();
  const [impact, setImpact] = useState<WaiverImpact | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setImpact(null);
    setError("");
    api.getWaiverImpact(playerId, mode, dropPlayerId ?? undefined, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setImpact(data); })
      .catch((cause: unknown) => { if (!controller.signal.aborted) setError(cause instanceof Error ? cause.message : "Impact analysis failed."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [playerId, mode, dropPlayerId]);
  return <dialog ref={dialog} className="waiver-dialog" aria-label="Player impact analysis" onCancel={onClose}>
    <button className="button button-quiet waiver-close" autoFocus onClick={onClose}>Close analysis</button>
    {option && <DecisionOptionSummary option={option} />}
    {loading && <p role="status">Loading persisted player impact...</p>}
    {error && <p role="alert">{error}</p>}
    {impact && impact.model_version !== CURRENT_WAIVER_MODEL_VERSION &&
      <p className="notice notice-error" role="alert">Impact response uses incompatible model {impact.model_version}; expected {CURRENT_WAIVER_MODEL_VERSION}. The analysis is blocked.</p>}
    {impact?.model_version === CURRENT_WAIVER_MODEL_VERSION && <ImpactContent impact={impact} selectedDropId={dropPlayerId} />}
  </dialog>;
}

function WatchSwapList({ analysis, onAnalyze }: { analysis: TransactionAnalysis; onAnalyze: (swap: SwapAnalysis) => void }) {
  return analysis.watch_transactions.length ? <ul>{analysis.watch_transactions.map((swap) =>
    <li key={`${swap.add_player.player_id}-${swap.drop_player.player_id}`}>
      WATCH: {swap.add_player.player_name} / drop {swap.drop_player.player_name}.
      <p>Model production value: {number(swap.comparison.explanation?.add_production.value ?? null)} Yahoo FP/G{swap.comparison.explanation ? ` (${swap.comparison.explanation.add_production.label})` : ""} · {swap.add_player.current_season_games} current-season games · {swap.add_player.schedule.games_remaining ?? "Unknown"} games in {modeWindow(analysis.mode)} · Yahoo status {yahooStatusText(swap.add_player)}.</p>
      <FormLine form={swap.add_player.form} name="Add" />
      <p><strong>Why watch:</strong> {swap.comparison.explanation?.statement ?? "positive measured roster-index change with observed comparison evidence."}</p>
      {/* The backend names the exact gate, player and window that block this pair. */}
      <p><strong>Why not add:</strong> {swap.add_player.evidence_blockers?.length
        ? swap.add_player.evidence_blockers.join(" ")
        : "The supported-move evidence gates are not met."}</p>
      <p>Role trend {swap.add_player.opportunity.current_role?.trend ?? "INSUFFICIENT EVIDENCE"} · schedule {swap.add_player.schedule.diagnostic_reason}.</p>
      <details><summary>Measured index and blockers</summary>
        <p>{indexNet(swap.comparison.net_improvement)} (exact {exact(swap.comparison.net_improvement)}); a descriptive model index, not projected fantasy points, wins, or probability.</p>
        {swap.comparison.explanation && <ExplanationDetails explanation={swap.comparison.explanation} />}
        <ul>{swap.reasons.slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
      </details>
      <details><summary>Current role and schedule evidence: {swap.add_player.player_name}</summary><RoleEvidence candidate={swap.add_player} /></details>
      <button className="button button-quiet" onClick={() => onAnalyze(swap)}>View watch analysis: {swap.add_player.player_name} / {swap.drop_player.player_name}</button>
    </li>,
  )}</ul> : <p>No positive measured WATCH swaps are available.</p>;
}

function NoMove({ analysis, support }: { analysis: TransactionAnalysis; support: DecisionSupport | null }) {
  const hold = analysis.recommended_action_type === "HOLD";
  const title = hold ? "HOLD" : support?.state === "WATCH" ? "WATCH"
    : support?.state === "POTENTIAL_TARGETS" ? "NO CONFIRMED AVAILABLE PLAYER" : "INSUFFICIENT EVIDENCE";
  return <div className="waiver-no-move">
    <h3>{title}</h3>
    <p>{support?.headline ?? (hold
      ? "No supported waiver move currently clears the evidence threshold."
      : "Roster capacity or required evidence could not be established, so no add, drop or IL move is recommended.")}</p>
    {support?.detail && <p>{support.detail}</p>}
    <ul>{(analysis.decision_reasons ?? []).slice(0, 4).map((reason) => <li key={reason}>{reason}</li>)}</ul>
  </div>;
}

export function WaiverFailureNotice({ failure, surface, onRetry, onRefresh }: {
  failure: WaiverFailure;
  surface: string;
  onRetry: () => void;
  onRefresh?: () => void;
}) {
  const timedOut = isTimedOut(failure);
  const contract = failure.code === "RECOMMENDATION_CONTRACT_VIOLATION";
  return <div className="waiver-failure" role="alert">
    <p className="waiver-failure-title">{timedOut ? "WAIVER ANALYSIS TIMED OUT" : contract ? "WAIVER MODEL CONTRACT ERROR" : "WAIVER ANALYSIS UNAVAILABLE"}</p>
    <p>{timedOut
      ? "The saved data was not changed. Retry the analysis, or refresh the evidence if its timestamps are stale."
      : contract ? `${failure.message} No recommendation from this response is shown.` : failure.message}</p>
    <p className="waiver-failure-note">The {surface} is unavailable; this error is not a HOLD decision.{failure.requestId ? ` Request ID: ${failure.requestId}.` : ""}</p>
    <div className="waiver-failure-actions">
      <button className="button button-primary" type="button" onClick={onRetry}>RETRY ANALYSIS</button>
      {onRefresh && <button className="button button-quiet" type="button" onClick={onRefresh}>REFRESH WAIVER DATA</button>}
    </div>
  </div>;
}

function ContractError({ name, reason }: { name: string; reason: string }) {
  return <div className="waiver-contract-error" role="alert">
    <p><strong>WAIVER MODEL CONTRACT ERROR</strong></p>
    <p>A recommendation for {name} was withheld because {reason}. Reload persisted evidence; if it repeats, do not act on this analysis.</p>
  </div>;
}

export function BestMoves({ board, analysis, failure, boardFailed = false, mode, onAnalyzeFill, onAnalyzePair, onDetails, onRetry, onRefresh }: {
  board: WaiverBoard | null;
  analysis: TransactionAnalysis | null;
  failure: WaiverFailure | null;
  boardFailed?: boolean;
  mode: WaiverMode;
  onAnalyzeFill: (fill: FillRecommendation) => void;
  onAnalyzePair: (swap: SwapAnalysis) => void;
  onDetails: (option: DecisionOption) => void;
  onRetry: () => void;
  onRefresh?: () => void;
}) {
  const incompatible = analysis !== null && analysis.model_version !== CURRENT_WAIVER_MODEL_VERSION;
  // A move is only rendered against the board's eligible-candidate map, so both must be loaded; after any
  // failure nothing from an earlier analysis stays actionable.
  const usable = failure !== null || incompatible || board === null ? null : analysis;
  const support = board?.decision_support ?? null;
  const byId = new Map((support?.options ?? []).map((option) => [option.player_id, option]));
  const check = board ? featuredCheck(board) : () => "the waiver board is not loaded";
  const withheld: { name: string; reason: string }[] = [];
  const allowed = (playerId: number, name: string, availability: AvailabilityClass | null | undefined) => {
    const reason = check(playerId, availability);
    if (reason) withheld.push({ name, reason });
    return reason === null;
  };
  // A supported card must carry the backend's SUPPORTED ADD verdict; any other verdict is a contradiction.
  const supportedVerdict = (name: string, verdict: TransactionVerdict | null | undefined) => {
    if (verdict === "SUPPORTED_ADD") return true;
    withheld.push({ name, reason: `its backend verdict is ${verdict ? VERDICT_TEXT[verdict] : "missing"}, not SUPPORTED ADD` });
    return false;
  };
  const fills = (usable?.add_only_recommendations ?? []).filter((fill) =>
    allowed(fill.add_player.player_id, fill.add_player.player_name, fill.add_player.availability_classification)
    && supportedVerdict(fill.add_player.player_name, fill.add_player.verdict));
  const rawPair = usable?.best_transaction ?? null;
  const pair = rawPair && allowed(rawPair.add_player.player_id, rawPair.add_player.player_name,
    rawPair.add_player.availability_classification)
    && supportedVerdict(`${rawPair.add_player.player_name} / ${rawPair.drop_player.player_name}`, rawPair.add_player.verdict) ? rawPair : null;
  const fullRoster = board?.roster_capacity?.transaction_shape === "ADD_DROP";
  // On a full roster the board and the best-move analysis must name the same supported pair (or both none);
  // otherwise nothing is shown rather than two contradictory answers.
  if (usable && board && fullRoster) {
    const boardPair = `${board.best_add_for_team_id ?? "none"}/${board.best_drop_for_team_id ?? "none"}`;
    const analysisPair = rawPair ? `${rawPair.add_player.player_id}/${rawPair.drop_player.player_id}` : "none/none";
    if (boardPair !== analysisPair) {
      withheld.push({ name: rawPair ? `${rawPair.add_player.player_name} / ${rawPair.drop_player.player_name}` : "the board's supported move",
        reason: "the waiver board and the best-move analysis name different supported ADD + DROP pairs" });
    }
  }
  const measured = (usable && !(fullRoster && pair) ? (support?.best_measured_ids ?? []) : []).map((id) => byId.get(id))
    .filter((option): option is DecisionOption => option !== undefined)
    .filter((option) => allowed(option.player_id, option.player_name, option.availability_classification));
  const supported = fills.length + (pair ? 1 : 0);
  // An inconsistent response fails closed: no card, HOLD or other decision is shown beside a contract error.
  const decided = usable !== null && withheld.length === 0;
  const strict: WaiverActionType = usable?.recommended_action_type ?? "INSUFFICIENT_EVIDENCE";
  const capacity = board?.roster_capacity;
  const strictText = strict === "HOLD"
    ? "No supported move currently improves Box Score Bully."
    : capacity?.transaction_shape === "UNDETERMINED"
      ? `No supported move yet: ${capacity.short_reason || "roster capacity needs a Yahoo refresh."}`
      : `No supported move yet: ${(usable?.decision_reasons ?? [])[0] ?? "required evidence is missing."}`;
  return <section className="panel waiver-panel waiver-best" aria-labelledby="waiver-transaction">
    <div className="waiver-section-head">
      <h2 id="waiver-transaction">BEST MOVES RIGHT NOW</h2>
      <p className="waiver-window-note">{modeWindow(mode)} · analysis only; complete any move yourself in Yahoo.</p>
    </div>
    {incompatible && <p className="notice notice-error" role="alert">The best-move response does not match this page version, so no decision is shown. Reload after the update finishes.</p>}
    {failure && <WaiverFailureNotice failure={failure} surface="best-move analysis" onRetry={onRetry} onRefresh={onRefresh} />}
    {!failure && boardFailed && <p className="waiver-strict-status" role="status">Best moves are withheld: every move is checked against the current waiver board&apos;s eligible players, and that board is unavailable. This is not a HOLD decision.</p>}
    {!failure && !boardFailed && (!analysis || (!board && !incompatible)) && <p role="status">Loading best move analysis...</p>}
    {withheld.map((item) => <ContractError key={`${item.name}-${item.reason}`} name={item.name} reason={item.reason} />)}
    {decided && !supported && <p className="waiver-strict-status"><ActionBadge action={strict} /> <span className="waiver-strict-text">{strictText}</span></p>}
    {decided && (supported > 0 || measured.length > 0) && <div className="waiver-move-grid">
      {fills.map((fill, index) => <MoveCard key={fill.add_player.player_id} fill={fill} mode={mode}
        kicker={index === 0 ? "Best move now" : `Also fill open spot ${fill.step} of ${fills.length}`} onAnalyze={onAnalyzeFill} />)}
      {pair && <PairCard swap={pair} mode={mode} capacity={usable?.roster_capacity} onAnalyze={onAnalyzePair} />}
      {measured.map((option, index) => <MeasuredCard key={option.player_id} option={option} mode={mode} fullRoster={fullRoster}
        kicker={fullRoster ? "Top target to check" : supported ? "Next open spot: no supported add yet"
          : index === 0 ? "Top target to check" : "Second open spot"} onDetails={onDetails} />)}
    </div>}
    {decided && usable && !supported && !measured.length && <NoMove analysis={usable} support={support} />}
    {decided && fills.length > 0 && (usable?.unfilled_needs ?? []).length > 0 &&
      <p>No supported available player covers {(usable?.unfilled_needs ?? []).join(", ")}; see OTHER GOOD OPTIONS.</p>}
  </section>;
}

export interface WaiverRefreshController {
  status: WaiverRefreshStatus | null;
  failure: WaiverFailure | null;
  requesting: boolean;
  running: boolean;
  announcement: string;
  start: (retryFailed?: boolean) => void;
  buttonRef: RefObject<HTMLButtonElement | null>;
  progressRef: RefObject<HTMLDivElement | null>;
}

/** Reads refresh status (database-only), starts the one backend refresh, and polls while it runs. */
export function useWaiverRefresh(onReload: () => void): WaiverRefreshController {
  const [status, setStatus] = useState<WaiverRefreshStatus | null>(null);
  const [failure, setFailure] = useState<WaiverFailure | null>(null);
  const [requesting, setRequesting] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const watched = useRef<string | null>(null);
  const focusProgress = useRef(false);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const progressRef = useRef<HTMLDivElement | null>(null);
  const job = status?.job ?? null;
  const running = Boolean(job?.active);

  useEffect(() => {
    const controller = new AbortController();
    api.getWaiverRefresh(controller.signal)
      .then((next) => {
        if (controller.signal.aborted) return;
        setStatus(next);
        if (next.job?.active) watched.current = next.job.job_id;
      })
      .catch((cause: unknown) => {
        if (!isAborted(cause, controller.signal)) setFailure(toFailure(cause, "Refresh status is unavailable."));
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const poll = () => {
      api.getWaiverRefresh()
        .then((next) => { if (!stopped) { setStatus(next); setFailure(null); } })
        .catch((cause: unknown) => {
          if (!stopped) setFailure(toFailure(cause, "Refresh progress could not be read; the refresh continues on the server."));
        })
        .finally(() => { if (!stopped) timer = setTimeout(poll, REFRESH_POLL_MS); });
    };
    timer = setTimeout(poll, REFRESH_POLL_MS);
    return () => { stopped = true; if (timer !== undefined) clearTimeout(timer); };
  }, [running]);

  useEffect(() => {
    if (running && focusProgress.current) {
      focusProgress.current = false;
      progressRef.current?.focus();
    }
  }, [running]);

  useEffect(() => {
    if (!job || job.active || watched.current !== job.job_id) return;
    watched.current = null;
    setAnnouncement(job.state === "SUCCEEDED" ? "Waiver data refreshed and verified. The waiver board was reloaded."
      : job.state === "PARTIAL_FAILURE" ? "Refresh partially completed. Successful sources were saved; failed sources are listed."
        : "Refresh failed. No data was changed.");
    if (job.board_reload_recommended) onReload();
    buttonRef.current?.focus();
  }, [job, onReload]);

  const start = useCallback((retryFailed = false) => {
    setRequesting(true);
    setFailure(null);
    setAnnouncement(retryFailed ? "Retrying the failed refresh stages." : "Refreshing waiver data.");
    focusProgress.current = true;
    api.startWaiverRefresh(retryFailed)
      .then((next) => {
        setStatus(next);
        if (next.job) watched.current = next.job.job_id;
      })
      .catch((cause: unknown) => {
        focusProgress.current = false;
        setFailure(toFailure(cause, "The refresh could not be started."));
      })
      .finally(() => setRequesting(false));
  }, []);

  return { status, failure, requesting, running, announcement, start, buttonRef, progressRef };
}

const STAGE_STATE_TEXT: Record<string, string> = {
  PENDING: "Waiting", RUNNING: "Running", SUCCEEDED: "Updated", FAILED: "Failed", SKIPPED: "Skipped",
  current: "Current", stale: "Stale", missing: "Missing",
};

export function WaiverRefreshPanel({ refresh, onReload }: { refresh: WaiverRefreshController; onReload?: () => void }) {
  const { status, failure, requesting, running, announcement, start, buttonRef, progressRef } = refresh;
  const job = status?.job ?? null;
  const evidence = status?.evidence ?? [];
  const finished = job && !job.active ? job : null;
  const partial = finished?.state === "PARTIAL_FAILURE";
  const failed = finished?.state === "FAILED";
  const busy = running || requesting;
  // Stage rows come from the job while it runs or after it failed; otherwise from persisted evidence.
  const showJob = Boolean(job) && (running || partial || failed);
  const stale = evidence.filter((item) => item.state !== "current");
  const tone = running ? "running" : partial || failed ? "failed" : status?.needs_refresh || (!status && failure) ? "stale" : "current";
  const title = running ? "REFRESHING WAIVER DATA" : partial ? "REFRESH PARTIALLY COMPLETED" : failed ? "REFRESH FAILED"
    : status?.needs_refresh ? "WAIVER DATA NEEDS A REFRESH" : status ? "WAIVER DATA IS CURRENT" : "WAIVER DATA";
  const done = (job?.stages ?? []).filter((stage) => stage.state !== "PENDING" && stage.state !== "RUNNING").length;
  const current = job?.stages.find((stage) => stage.state === "RUNNING");
  const summary = running
    ? `${done} of ${job?.stages.length ?? 0} steps finished${current ? ` · ${current.label}: running` : ""}.`
    : partial ? "Successful sources were saved. Failed sources kept their previous data and remain stale."
      : failed ? job?.message ?? "The refresh failed. No data was changed."
        : status?.needs_refresh ? `Stale or missing: ${stale.map((item) => item.label).join(", ")}. Refresh to update rosters, availability and NBA data.`
          : status ? `All ${evidence.length} sources are current.`
            : failure ? "Saved-evidence freshness could not be read. Waiver analysis below still uses the saved data." : "Checking saved evidence…";
  const sources = (["YAHOO", "NBA"] as const).filter((source) => finished?.stages.some((stage) => stage.source === source && stage.state === "SUCCEEDED")
    && !finished.stages.some((stage) => stage.source === source && stage.state === "FAILED"));
  const failedStages = (finished?.stages ?? []).filter((stage) => stage.state === "FAILED");
  const last = status?.last_complete_refresh_at
    ? `${status.last_complete_refresh_source === "refresh_job" ? "Last successful complete refresh" : "All waiver evidence current as of"}: ${longTimestamp(status.last_complete_refresh_at)}`
    : "No complete refresh recorded yet.";
  const rows = showJob && job
    ? job.stages.map((stage) => ({ key: stage.stage, label: stage.label, state: stage.state,
      text: STAGE_STATE_TEXT[stage.state], detail: stage.state === "FAILED" ? stage.message : stage.summary }))
    : evidence.map((item) => ({ key: item.stage, label: item.label, state: item.state,
      text: STAGE_STATE_TEXT[item.state], detail: item.summary }));
  const list = <div ref={progressRef} tabIndex={-1} role="group" className="waiver-refresh-progress" aria-label="Refresh progress by source">
    <ol className="waiver-refresh-stages">{rows.map((row) => <li key={row.key} className={`is-${row.state.toLowerCase()}`}>
      <span className="waiver-refresh-stage">{row.label}</span>
      <span className="waiver-refresh-state">{row.text}{row.detail ? ` — ${row.detail}` : ""}</span>
    </li>)}</ol>
  </div>;
  return <section className={`panel waiver-refresh is-${tone}`} aria-labelledby="waiver-refresh-title">
    <div className="waiver-refresh-head">
      <h2 id="waiver-refresh-title">{title}</h2>
      <div className="waiver-refresh-actions">
        {(partial || failed) && !busy && <button className="button button-primary" type="button" onClick={() => start(true)}>RETRY FAILED STAGE</button>}
        <button ref={buttonRef} type="button" className={`button ${tone === "current" || tone === "failed" ? "button-quiet" : "button-primary"}`}
          disabled={busy} onClick={() => start(false)}>{busy ? "REFRESHING…" : "REFRESH WAIVER DATA"}</button>
        {onReload && <button className="button button-quiet" type="button" onClick={onReload}>Reload persisted evidence</button>}
      </div>
    </div>
    <p className="waiver-refresh-summary">{summary}</p>
    {failure && <p className="waiver-refresh-error" role="alert">{failure.message}{failure.requestId ? ` Request ID: ${failure.requestId}.` : ""}</p>}
    {(partial || failed) && <ul className="waiver-refresh-outcome">
      {sources.map((source) => <li key={source}>{source === "YAHOO" ? "Yahoo roster data updated successfully." : "NBA data updated successfully."}</li>)}
      {failedStages.map((stage) => <li key={stage.stage}><strong>{stage.label} failed.</strong> {stage.message}</li>)}
    </ul>}
    {running && list}
    <div className="waiver-refresh-foot">
      <p className="waiver-refresh-last">{last}</p>
      {!running && <details className="waiver-refresh-details"><summary>{showJob ? "Stage details" : "Source details"}</summary>{list}</details>}
    </div>
    <p className="sr-only" role="status" aria-live="polite">{announcement}</p>
  </section>;
}

export function WaiverCenter() {
  const [mode, setMode] = useState<WaiverMode>("this_week");
  const [baseBoard, setBaseBoard] = useState<WaiverBoard | null>(null);
  const [replacementResult, setReplacementResult] = useState<{ mode: WaiverMode; dropId: number; board: WaiverBoard } | null>(null);
  const [selectedDropPlayerId, setSelectedDropPlayerId] = useState<number | null>(null);
  const [impactTarget, setImpactTarget] = useState<{ playerId: number; dropId: number | null; option: DecisionOption | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [replacementLoading, setReplacementLoading] = useState(false);
  const [failure, setFailure] = useState<WaiverFailure | null>(null);
  const [replacementError, setReplacementError] = useState("");
  const [retry, setRetry] = useState(0);
  const [transactionPair, setTransactionPair] = useState<SwapAnalysis | null>(null);
  const [fillDetail, setFillDetail] = useState<FillRecommendation | null>(null);
  const [transactions, setTransactions] = useState<{ mode: WaiverMode; reload: number; analysis: TransactionAnalysis } | null>(null);
  const [transactionsFailure, setTransactionsFailure] = useState<WaiverFailure | null>(null);
  const reload = useCallback(() => {
    setBaseBoard(null);
    setReplacementResult(null);
    setTransactionPair(null);
    setFillDetail(null);
    setRetry((value) => value + 1);
  }, []);
  const refresh = useWaiverRefresh(reload);
  const startRefresh = useCallback(() => refresh.start(false), [refresh.start]);

  useEffect(() => {
    const controller = new AbortController();
    setBaseBoard(null);
    setReplacementResult(null);
    setTransactionPair(null);
    setFillDetail(null);
    setLoading(true);
    setFailure(null);
    api.getWaivers(mode, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setBaseBoard(data); })
      .catch((cause: unknown) => { if (!isAborted(cause, controller.signal)) setFailure(toFailure(cause, "Could not load waiver evidence.")); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [mode, retry]);

  useEffect(() => {
    const controller = new AbortController();
    setTransactions(null);
    setTransactionsFailure(null);
    api.getWaiverTransactions(mode, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setTransactions({ mode, reload: retry, analysis: data }); })
      .catch((cause: unknown) => { if (!isAborted(cause, controller.signal)) setTransactionsFailure(toFailure(cause, "Best-move analysis failed.")); });
    return () => controller.abort();
  }, [mode, retry]);

  const receivedBaseBoard = baseBoard?.mode === mode ? baseBoard : null;
  const activeBaseBoard = receivedBaseBoard?.model_version === CURRENT_WAIVER_MODEL_VERSION ? receivedBaseBoard : null;
  const analysis = transactions && transactions.mode === mode && transactions.reload === retry && transactions.analysis.mode === mode
    ? transactions.analysis : null;
  // No drop is ever preselected: the comparison tool waits for an explicit roster choice.
  const selectedDropId = activeBaseBoard?.roster.some((candidate) => candidate.player_id === selectedDropPlayerId)
    ? selectedDropPlayerId
    : null;

  useEffect(() => {
    if (!activeBaseBoard || selectedDropId === null) {
      setReplacementResult(null);
      setReplacementLoading(false);
      return;
    }
    const controller = new AbortController();
    setReplacementResult(null);
    setReplacementLoading(true);
    setReplacementError("");
    api.getWaiverReplacements(selectedDropId, mode, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) setReplacementResult({ mode, dropId: selectedDropId, board: data });
      })
      .catch((cause: unknown) => {
        if (!isAborted(cause, controller.signal)) setReplacementError(toFailure(cause, "Could not load replacements.").message);
      })
      .finally(() => { if (!controller.signal.aborted) setReplacementLoading(false); });
    return () => controller.abort();
  }, [activeBaseBoard, mode, selectedDropId, retry]);

  const showOption = (option: DecisionOption) => setImpactTarget({ playerId: option.player_id, dropId: null, option });
  const modes: [WaiverMode, string][] = [["this_week", "Rest of Week"], ["next_7_days", "Next 7 Days"],
    ["next_14_days", "Next 14 Days"], ["ros", "Rest of Season Outlook"]];
  const ready = activeBaseBoard !== null && !loading;

  return <main className="waiver-center">
    <header className="waiver-heading"><div><Link to="/">Court IQ · Draft desk</Link><h1>Waiver Command Center</h1>
      <p className="waiver-team">{activeBaseBoard?.team_name ?? "Your Roster"}</p></div>
      <WaiverRefreshPanel refresh={refresh} onReload={reload} /></header>
    <p className="waiver-intro">Who to add, whether a drop or IL move is needed, and why, from saved Yahoo and NBA data. Analysis only: nothing is ever executed in Yahoo. The app-configured team is not Yahoo-authenticated ownership evidence; dates use Pacific Time.</p>
    <div className="waiver-controls">
      <fieldset><legend>Analysis window</legend>{modes.map(([value, title]) =>
        <label key={value}><input type="radio" name="waiver-mode" checked={mode === value} onChange={() => setMode(value)} />{title}</label>)}</fieldset>
      {ready && <WindowNote board={activeBaseBoard} />}
    </div>
    {receivedBaseBoard && receivedBaseBoard.model_version !== CURRENT_WAIVER_MODEL_VERSION &&
      <p className="notice notice-error" role="alert">Stale deployed version: {receivedBaseBoard.model_version}. Expected {CURRENT_WAIVER_MODEL_VERSION}; board actions are disabled.</p>}
    {failure && <section className="panel waiver-panel waiver-situation" aria-labelledby="waiver-situation">
      <h2 id="waiver-situation">TEAM SITUATION</h2>
      <WaiverFailureNotice failure={failure} surface="team situation" onRetry={reload} onRefresh={startRefresh} />
    </section>}
    {loading && <p role="status">Loading persisted waiver evidence...</p>}
    {ready && <TeamSituation board={activeBaseBoard} />}
    <BestMoves board={ready ? activeBaseBoard : null} analysis={analysis} failure={transactionsFailure} mode={mode}
      boardFailed={failure !== null || (receivedBaseBoard !== null && activeBaseBoard === null)}
      onAnalyzeFill={setFillDetail} onAnalyzePair={setTransactionPair} onDetails={showOption}
      onRetry={reload} onRefresh={startRefresh} />
    {ready && <OtherGoodOptions board={activeBaseBoard} analysis={analysis} onDetails={showOption} onAnalyzePair={setTransactionPair} />}
    {ready && <CompareDropSection board={activeBaseBoard} selectedDropId={selectedDropId} onSelect={setSelectedDropPlayerId}
      replacementBoard={replacementResult?.mode === mode && replacementResult.dropId === selectedDropId ? replacementResult.board : null}
      loading={replacementLoading} error={replacementError}
      onAnalyze={(id) => setImpactTarget({ playerId: id, dropId: selectedDropId, option: null })} />}
    {ready && <FullWaiverList board={activeBaseBoard} onDetails={showOption} />}
    {ready && <AdvancedEvidence board={activeBaseBoard} analysis={analysis} />}
    {impactTarget !== null &&
      <ImpactDialog key={`${mode}-${impactTarget.playerId}-${impactTarget.dropId ?? "none"}`} playerId={impactTarget.playerId} mode={mode}
        dropPlayerId={impactTarget.dropId} option={impactTarget.option} onClose={() => setImpactTarget(null)} />}
    {transactionPair && transactionPair.mode === mode && <TransactionDialog swap={transactionPair} onClose={() => setTransactionPair(null)} />}
    {fillDetail && <FillDialog fill={fillDetail} mode={mode} onClose={() => setFillDetail(null)} />}
  </main>;
}

function TransactionDialog({ swap, onClose }: { swap: SwapAnalysis; onClose: () => void }) {
  const dialog = useModalDialog();
  return <dialog ref={dialog} className="waiver-dialog" aria-label="Supported transaction analysis" onCancel={onClose}>
    <button className="button button-quiet waiver-close" autoFocus onClick={onClose}>Close transaction analysis</button>
    <p>{swap.decision} · hypothetical ADD {swap.add_player.player_name} / DROP {swap.drop_player.player_name}</p>
    <ImpactContent impact={{
      league_key: "", team_key: "", mode: swap.mode, model_version: CURRENT_WAIVER_MODEL_VERSION, candidate: swap.add_player,
      comparison: swap.comparison, limitations: swap.limitations,
    }} selectedDropId={swap.drop_player.player_id} />
    <h3>Selected drop evidence: {swap.drop_player.player_name}</h3>
    <FormPanel candidate={swap.drop_player} />
    <CandidateSamples candidate={swap.drop_player} />
    <RoleEvidence candidate={swap.drop_player} />
    <ul>{swap.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
  </dialog>;
}

function FillDialog({ fill, mode, onClose }: { fill: FillRecommendation; mode: WaiverMode; onClose: () => void }) {
  const dialog = useModalDialog();
  const move = fill.suggested_injury_move;
  return <dialog ref={dialog} className="waiver-dialog" aria-label="Recommended addition analysis" onCancel={onClose}>
    <button className="button button-quiet waiver-close" autoFocus onClick={onClose}>Close addition analysis</button>
    <p className="waiver-action-label"><ActionBadge action={fill.action_type} /> <span>{fill.label}</span></p>
    {move && <ol className="waiver-steps">
      <li>Move {move.player_name} from {move.from_slot} to {move.to_slot}. {move.detail}</li>
      <li>Add {fill.add_player.player_name}.</li>
    </ol>}
    <ImpactContent impact={{
      league_key: "", team_key: "", mode, model_version: CURRENT_WAIVER_MODEL_VERSION, candidate: fill.add_player,
      comparison: fill.comparison, limitations: fill.limitations,
    }} selectedDropId={null} />
    <ul>{fill.reasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>
  </dialog>;
}

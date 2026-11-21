"""Read-only waiver analysis over imported Yahoo and NBA evidence."""

import asyncio
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from math import fsum, isfinite
from statistics import mean, median
from typing import Any, Callable
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timing import record_count, record_phase
from app.features.championship.service import _numeric
from app.features.leagues.models import League, Team
from app.features.nba.models import (
    NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule,
)
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.features.players.normalization import _positions
from app.features.players.service import list_roster_baselines, roster_data_status
from app.features.waivers.capacity import (
    RosterEntryEvidence,
    analyze_roster_capacity,
    analyze_team_needs,
    coverage_date_from_payload,
    eligible_positions_from_payload,
    lineup_eligible,
    need_order,
    newly_covered_slot,
    player_positions,
    position_set,
    slot_accepts,
    slot_configuration,
    starting_slot_list,
    uncovered_slots,
)
from app.features.waivers.contracts import (
    ACTIONABLE_AVAILABILITY,
    AVAILABILITY_CLASS_LABELS,
    CHECKABLE_AVAILABILITY,
    FORM_REASON_LABELS,
    MODEL_VERSION,
    RESOLVED_IDENTITY_STATES,
    AcquisitionContext,
    AcquisitionCoverage,
    ActionType,
    AvailabilityClass,
    AvailabilityEvidence,
    AvailabilitySummary,
    Candidate,
    Components,
    CoverageMetric,
    CoverageScope,
    CoverageSlice,
    CurrentRole,
    DataGap,
    DataGapCategory,
    DecisionSupport,
    DropOption,
    Evidence,
    EvidenceDimension,
    FillRecommendation,
    FormTrend,
    FormWindow,
    FreshnessItem,
    IdentityCoverage,
    InjuryMoveOption,
    MappingWorklistItem,
    Mode,
    NeedOption,
    Opportunity,
    OptionGroups,
    PotentialNbaMatch,
    ProductionCoverage,
    RankingEvidence,
    RecentForm,
    RootCause,
    RoleCoverage,
    RoleMetric,
    RoleWindow,
    RosterCapacity,
    SampleLabel,
    Schedule,
    ScheduleCoverage,
    StartsEvidence,
    StatusCoverage,
    SwapAnalysis,
    TeamNeeds,
    TransactionAnalysis,
    TransactionShape,
    TransactionVerdict,
    ValueEvidence,
    WaiverBoard,
    WaiverCoverage,
    WaiverImpact,
    availability_actionable,
    availability_class,
)
from app.features.waivers.decision_support import build_decision_support, measured_production, sample_label
from app.features.waivers.explanation import (
    COMPONENT_NAMES,
    EXPLANATION_GATE,
    NEAR_TIE_GATE,
    NEAR_TIE_NET,
    alternatives,
    drop_choice_text,
    explain_comparison,
    signed,
)
from app.features.waivers.sample import (
    SAMPLE_POLICY,
    SAMPLE_TIER_LABELS,
    SUPPORTED_SAMPLE_GAMES,
    assess_sample,
    limited_shortfall,
    sample_assessment,
    sample_tier,
    sufficient_sample,
)
from app.services.draft.metrics import _category_field, _selected_position_positions
from app.services.draft.player_status import (
    interpret_yahoo_status,
    recommendation_eligibility,
    status_is_supported,
    yahoo_status_reason,
)
from app.services.draft.utility import _maximum_slot_matching
from app.services.nba.player_importer import _name_key
from app.services.yahoo.normalization import extract_yahoo_records, _merge_settings, normalize_yahoo_settings

COMPONENTS = tuple(Components.model_fields)
WAIVER_TIMEZONE = ZoneInfo("America/Los_Angeles")
BASE_LIMITATIONS = [
    "Scores are descriptive heuristic indices, not predicted fantasy points or predictive accuracy.",
    "Season Evidence is historical per-game production, not a projection. Rest of Season Outlook is a current roster decision, not projected fantasy totals. No injury return dates are inferred.",
    "Acquisition value is unavailable until current rolling priority and transaction evidence are verified; it never affects ranking.",
    "Category-level waiver scoring and category swap impact are unavailable; no category values are simulated.",
    "Schedule counts describe persisted games, not guaranteed complete coverage or lineup starts. Matchup difficulty is unavailable.",
    "This Week uses today through Sunday in Pacific Time (PST/PDT), not a verified Yahoo matchup period.",
    "Next 7 Days includes Pacific today and the following six dates, not a Yahoo matchup week.",
    "Next 14 Days includes Pacific today and the following thirteen dates, not two Yahoo matchup weeks.",
    "A supported move needs at least seven current-season games and, in Rest of Week / Next 7 / Next 14 Days, seven games in the last 14 days for every compared player; five or six only with corroborating current-season evidence. Evidence quality is not probability.",
    "No Yahoo transactions are executed. Roster locks and transaction eligibility must be checked in Yahoo.",
]
ACTIONABLE_DECISIONS = {"ADD", "STREAM", "MUST ADD"}
FILL_SHAPES = {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD"}
ACTION_RANK = {"ADD_ONLY": 0, "MOVE_TO_IL_THEN_ADD": 0, "ADD_DROP": 0, "WATCH": 1, "HOLD": 2, "INSUFFICIENT_EVIDENCE": 3}
# Full candidate evidence returned per board; the page lists every player through compact decision
# options and fetches full evidence for one player on demand, so the response stays bounded.
BOARD_CANDIDATE_LIMIT = 12


def evidence(state: str, source: str, as_of: datetime | None, detail: str) -> Evidence:
    return Evidence(state=state, source=source, as_of=as_of, detail=detail)


def freshness(as_of: datetime | None, now: datetime, days: int = 1) -> str:
    if as_of is None:
        return "missing"
    return "stale" if now - as_of > timedelta(days=days) else "available"


def coverage_metric(count: int, total: int) -> CoverageMetric:
    return CoverageMetric(
        count=count,
        total=total,
        percentage=round(count / total * 100, 2) if total else 0,
    )


def identity_is_supported(player: Candidate) -> bool:
    return player.identity_mapping_state in RESOLVED_IDENTITY_STATES


def identity_mapping(
    identity: PlayerIdentity,
    nba_player: NbaPlayer | None,
    players_by_name: dict[str, list[NbaPlayer]],
    abbreviations: dict[str, str],
    yahoo_team_source: str | None,
) -> tuple[str, str, list[PotentialNbaMatch]]:
    key = _name_key(identity.player_name)
    potential = [
        PotentialNbaMatch(
            nba_player_id=row.nba_player_id,
            player_name=row.player_name,
            team=(abbreviations.get(row.team_id) if row.team_id else None) or row.team_abbreviation,
        )
        for row in players_by_name.get(key, [])
    ]
    yahoo_team = (yahoo_team_source or identity.team or "").strip().upper() or None
    nba_team = (
        abbreviations.get(nba_player.team_id)
        if nba_player and nba_player.team_id else None
    )
    if nba_player is None:
        if not identity.nba_player_id:
            if not potential:
                return "NO_MATCH", "No NBA player has the same normalized name in the persisted NBA player table.", potential
            same_team = [row for row in potential if row.team and yahoo_team == row.team.upper()]
            if len(same_team) == 1:
                return "MISSING_MAPPING", "A same-name/team NBA candidate exists, but the identity link is absent; no automatic mapping was made.", potential
            return "AMBIGUOUS", "Same-name NBA candidates exist, but the persisted evidence does not establish a unique same-team identity.", potential
        return "MISSING_MAPPING", f"NBA identity link {identity.nba_player_id} does not resolve to a persisted NBA player.", potential
    if not key or _name_key(nba_player.player_name) != key:
        return "AMBIGUOUS", "The linked NBA player name does not match the Yahoo name under the established normalization; identity requires review.", potential
    if not yahoo_team or not nba_team:
        return "AMBIGUOUS", "Name matches, but Yahoo or NBA team evidence is missing; identity cannot be confirmed.", potential
    if yahoo_team != nba_team.upper():
        return "AMBIGUOUS", f"Yahoo team {yahoo_team} conflicts with NBA team {nba_team}; a trade or stale identity is not assumed.", potential
    if identity.player_name.strip().casefold() == nba_player.player_name.strip().casefold():
        return "EXACT_NAME_TEAM", "Yahoo and NBA names and team abbreviations match.", potential
    return "NORMALIZED_NAME_TEAM", "Yahoo and NBA names match under established normalization and team abbreviations agree.", potential


@lru_cache(maxsize=256)
def schedulable_status(status: str | None) -> bool:
    """Final, postponed and cancelled games are never remaining games."""
    text = (status or "").lower()
    return not any(word in text for word in ("postpon", "cancel", "final"))


def resolve_schedule(
    rows: list[Any],
    today: date,
    window_end: date,
    now: datetime,
    daily_games: Counter,
    abbreviations: dict[str, str],
    *,
    nba_mapped: bool,
    team_mapped: bool,
    source_row_count: int | None = None,
    source_imported_at: datetime | None = None,
    rest_of_season_rows: int | None = None,
) -> Schedule:
    """`rows` need only game_date, game_status, opponent_team_id and imported_at. The loader passes
    the rows near the window plus the season-wide row count, oldest import and remaining-season row count."""
    valid_rows = [row for row in rows if schedulable_status(row.game_status)]
    window_rows = [row for row in valid_rows if today <= row.game_date <= window_end]
    next_7_days = [row for row in valid_rows if today <= row.game_date <= today + timedelta(days=6)]
    next_14_days = [row for row in valid_rows if today <= row.game_date <= today + timedelta(days=13)]
    remaining = (sum(row.game_date >= today for row in valid_rows) if rest_of_season_rows is None
        else rest_of_season_rows)
    row_count = len(rows) if source_row_count is None else source_row_count
    imported_at = (min((row.imported_at for row in rows), default=None)
        if source_row_count is None else source_imported_at)
    schedule_freshness = freshness(imported_at, now, 7)
    if not nba_mapped:
        diagnostic = "NBA_ID_UNMAPPED"
    elif not team_mapped:
        diagnostic = "TEAM_MAPPING_MISSING"
    elif not row_count:
        diagnostic = "NO_PLAYER_SCHEDULE_ROWS"
    elif schedule_freshness == "stale":
        diagnostic = "SCHEDULE_STALE"
    elif window_rows:
        diagnostic = "SCHEDULE_ROWS_PRESENT"
    else:
        diagnostic = "SCHEDULE_SOURCE_INCOMPLETE"
    dates = {row.game_date for row in window_rows}
    return Schedule(
        games_remaining=len(window_rows) if window_rows and schedule_freshness != "stale" else None,
        off_day_games=(
            sum(daily_games[row.game_date] <= 5 for row in window_rows)
            if window_rows and schedule_freshness != "stale" else None
        ),
        back_to_backs=(
            sum(day - timedelta(days=1) in dates for day in dates)
            if window_rows and schedule_freshness != "stale" else None
        ),
        next_7_days_games=(
            len(next_7_days) if next_7_days and schedule_freshness != "stale" else None
        ),
        next_14_days_games=(
            len(next_14_days) if next_14_days and schedule_freshness != "stale" else None
        ),
        rest_of_season_games=remaining if remaining and schedule_freshness != "stale" else None,
        persisted_window_games=len(window_rows) if window_rows else None,
        opponents=[abbreviations.get(row.opponent_team_id, "Unknown") for row in window_rows],
        game_dates=sorted(dates) if window_rows and schedule_freshness != "stale" else [],
        source_row_count=row_count,
        window_start=today,
        window_end=window_end,
        imported_at=imported_at,
        freshness=(
            "stale" if schedule_freshness == "stale"
            else "fresh" if imported_at is not None
            else "unknown"
        ),
        coverage=(
            "STALE" if schedule_freshness == "stale" and row_count
            else "PARTIAL" if window_rows
            else "UNKNOWN"
        ),
        diagnostic_reason=diagnostic,
    )


def identity_chain_diagnostic(
    *,
    yahoo_id: str | None,
    nba_id: str | None,
    nba_player_present: bool,
    team_mapped: bool,
    has_game_logs: bool,
    has_season_stats: bool,
    has_schedule_rows: bool,
    schedule_stale: bool,
) -> str:
    if not yahoo_id:
        return "YAHOO_ID_MISSING"
    if not nba_id:
        return "NBA_ID_UNMAPPED"
    if not nba_player_present:
        return "NBA_PLAYER_MISSING"
    if not team_mapped:
        return "TEAM_MAPPING_MISSING"
    if not has_game_logs:
        return "GAME_LOGS_MISSING"
    if not has_season_stats:
        return "SEASON_STATS_MISSING"
    if not has_schedule_rows:
        return "SCHEDULE_ROWS_MISSING"
    if schedule_stale:
        return "SCHEDULE_STALE"
    return "COMPLETE_MAPPING"


def validated_weights(weights: dict[str, float]) -> dict[str, float]:
    if set(weights) != set(COMPONENTS) or any(
        isinstance(v, bool) or not isfinite(v) or v < 0 for v in weights.values()
    ) or sum(weights.values()) <= 0:
        raise ValueError("WAIVER_WEIGHTS must contain all five components with finite nonnegative weights and a positive sum")
    total = sum(weights.values())
    return {key: value / total for key, value in weights.items()}


def aggregate(components: Components, weights: dict[str, float]) -> tuple[float | None, dict[str, float]]:
    values = components.model_dump()
    if values["player_value"] is None or values["roster_fit"] is None:
        return None, {}
    total = sum(weights[key] for key, value in values.items() if value is not None)
    if total <= 0:
        return None, {}
    effective = {key: weights[key] / total for key, value in values.items() if value is not None and weights[key] > 0}
    return round(sum(values[key] * weight for key, weight in effective.items()), 6), effective


def percentile(value: float | None, distribution: list[float]) -> float | None:
    if value is None or not distribution:
        return None
    return percentile_sorted(value, sorted(distribution))


def percentile_sorted(value: float | None, ordered: list[float]) -> float | None:
    """Midrank percentile over an ascending distribution; identical to counting with comparisons."""
    if value is None or not ordered:
        return None
    # Midrank preserves equal scores for ties and is independent of input order.
    below, through = bisect_left(ordered, value), bisect_right(ordered, value)
    return 100 * (below + (through - below) / 2) / len(ordered)


def scoring_fields(scoring: dict[str, Any]) -> dict[str, float] | None:
    if "point" not in str(scoring.get("scoring_type", "")).lower():
        return None
    categories = scoring.get("categories")
    if not isinstance(categories, list) or not categories:
        return None
    fields: dict[str, float] = defaultdict(float)
    for category in categories:
        if not isinstance(category, dict):
            return None
        modifier = _numeric(category.get("value"))
        if modifier is None:
            return None
        try:
            field = _category_field(category)
        except HTTPException:
            return None
        fields[field] += modifier
    return dict(fields)


def production(stats: dict[str, float], fields: dict[str, float] | None) -> float | None:
    if not fields or any(field not in stats for field, weight in fields.items() if weight != 0):
        return None
    return sum(stats[field] * weight for field, weight in fields.items() if weight != 0)


def production_detail(
    stats: dict[str, float],
    fields: dict[str, float] | None,
    window: str,
    observations: int,
) -> str:
    if fields is None:
        return f"{window} production is unsupported because persisted Yahoo points modifiers are unavailable."
    if observations == 0:
        return f"{window} production is missing because no eligible persisted NBA game/stat observations exist in the selected window."
    missing = sorted(field for field, weight in fields.items() if weight != 0 and field not in stats)
    if missing:
        return f"{window} production is unavailable because persisted NBA observations lack required scoring fields: {', '.join(missing)}."
    return f"{window} production is unavailable because complete numeric scoring inputs could not be calculated."


def verify_league_contract(league: League) -> list[str]:
    if league.league_key != "478.l.50505":
        return []
    settings = league.settings
    if settings is None:
        raise HTTPException(409, "Persisted Driveway Dudes settings missing; waiver analysis blocked")
    records = extract_yahoo_records(settings.source_payload, "league", "league_key")
    record = next((row for row in records if str(row.get("league_key")) == league.league_key), {})
    rules = _merge_settings(record.get("settings"))
    expected = {"scoring_type": "headpoint", "max_teams": "12", "uses_faab": "0",
        "waiver_type": "R", "waiver_rule": "all", "waiver_time": "2",
        "max_weekly_adds": "4", "post_draft_players": "W"}
    mismatches = [f"{key}: persisted {rules.get(key)!r}, expected {value!r}"
        for key, value in expected.items() if str(rules.get(key)) != value]
    for key, value in {"num_teams": "12", "weekly_deadline": "intraday", "allow_add_to_dl_extra_pos": "1"}.items():
        if str(record.get(key)) != value:
            mismatches.append(f"{key}: persisted {record.get(key)!r}, expected {value!r}")
    for source in (record, league.source_payload):
        for key, value in {"name": "Driveway Dudes", "scoring_type": "headpoint", "num_teams": "12",
            "max_teams": "12", "weekly_deadline": "intraday", "allow_add_to_dl_extra_pos": "1"}.items():
            if key in source and str(source[key]) != value:
                mismatches.append(f"league metadata {key}: persisted {source[key]!r}, expected {value!r}")
    # Yahoo omits max_adds when there is no season acquisition limit.
    if rules.get("max_adds") not in (None, "", "none", "None", "-1", -1):
        mismatches.append(f"max_adds: unexpected season limit {rules['max_adds']!r}")
    expected_fields = {"PTS": 1, "REB": 1.2, "AST": 1.5, "BLK": 3, "STL": 3, "TOV": -1}
    raw_scoring, raw_positions = normalize_yahoo_settings(league.league_key, settings.source_payload)
    if scoring_fields(settings.scoring_settings) != expected_fields or scoring_fields(raw_scoring) != expected_fields:
        mismatches.append("Yahoo scoring modifiers disagree with the verified points formula")
    expected_slots = Counter({"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 2, "UTIL": 2, "BN": 3, "IL": 3})
    for positions in (settings.roster_positions, raw_positions):
        actual: Counter[str] = Counter()
        for slot in positions:
            actual[str(slot.get("position", "")).upper()] += _numeric(slot.get("count")) or 0
        if actual != expected_slots:
            mismatches.append("Yahoo roster positions disagree with the verified 16-slot roster")
    if league.league_name != "Driveway Dudes" or league.source_payload.get("scoring_type") != "headpoint":
        mismatches.append("Persisted league identity/scoring type disagrees with Driveway Dudes H2H Points")
    if mismatches:
        raise HTTPException(409, {"message": "Persisted league contract mismatch; waiver analysis blocked", "mismatches": mismatches})
    return ["Continual rolling list", "Standard waiver mode", "2-day waiver period", "4 adds/week",
        "No season acquisition maximum", "Daily - Today deadline",
        "Post-draft players follow waiver rules", "Injured available players may be added directly to an injury slot"]


def _whole_number(value: object) -> int | None:
    number = _numeric(value)
    return int(number) if number is not None and float(number).is_integer() and number >= 0 else None


def acquisition_context_for(league: League, team: Team | None, now: datetime, rules: list[str]) -> AcquisitionContext:
    """Weekly adds and rolling waiver priority from the persisted Yahoo `league/{key}/teams` and
    settings payloads (the existing league import). Values are exposed only when the team, week and
    limit fields are present and agree with the same import; nothing is inferred from league rules."""
    settings = league.settings
    payload = team.source_payload if team is not None and isinstance(team.source_payload, dict) else {}
    as_of = team.imported_at if team is not None else None
    state = freshness(as_of, now) if team is not None else "missing"
    source = "Yahoo league teams resource (waiver_priority, roster_adds) and league settings (max_weekly_adds)"
    raw_rules: dict[str, Any] = {}
    if settings is not None:
        records = extract_yahoo_records(settings.source_payload, "league", "league_key")
        record = next((row for row in records if str(row.get("league_key")) == league.league_key), {})
        raw_rules = _merge_settings(record.get("settings"))
    priority = _whole_number(payload.get("waiver_priority"))
    adds = payload.get("roster_adds") if isinstance(payload.get("roster_adds"), dict) else {}
    used = _whole_number(adds.get("value"))
    adds_week = _whole_number(adds.get("coverage_value")) if adds.get("coverage_type") == "week" else None
    league_week = _whole_number(league.source_payload.get("current_week")) if isinstance(league.source_payload, dict) else None
    limit = _whole_number(raw_rules.get("max_weekly_adds"))
    problems = []
    if priority is None or priority < 1:
        problems.append("waiver_priority is missing")
        priority = None
    if used is None or adds_week is None:
        problems.append("weekly roster_adds is missing or not week-scoped")
    elif league_week is None or adds_week != league_week:
        problems.append(f"roster_adds covers Yahoo week {adds_week}, but the league's current week is {league_week}")
        used = None
    if limit is None:
        problems.append("max_weekly_adds is missing from league settings")
    remaining = max(0, limit - used) if limit is not None and used is not None else None
    if team is None:
        state, detail = "missing", "The configured team has no persisted Yahoo team record."
    elif problems and priority is None and used is None:
        state, detail = "missing", "Persisted Yahoo team evidence lacks acquisition fields: " + "; ".join(problems) + "."
    else:
        if problems and state == "available":
            state = "partial"
        parts = []
        if used is not None and limit is not None:
            parts.append(f"{used} of {limit} weekly adds used in Yahoo week {adds_week} ({remaining} remaining)")
        if priority is not None:
            parts.append(f"waiver priority {priority}")
        detail = ("Yahoo reports " + ", ".join(parts) + " as of the last league import"
            + (" (older than 24 hours; refresh before relying on it)" if state == "stale" else "") + "."
            + (" " + "; ".join(problems).capitalize() + "." if problems else ""))
    return AcquisitionContext(
        rules=rules, data_quality=evidence(state, source, as_of, detail),
        current_priority=priority, weekly_adds_used=used, weekly_adds_remaining=remaining,
        weekly_add_limit=limit, yahoo_week=adds_week if used is not None else None,
        state=state, source=source, as_of=as_of, detail=detail,
    )


def numeric_stats(payload: dict[str, Any]) -> dict[str, float]:
    return {key: number for key, value in payload.items() if (number := _numeric(value)) is not None}


def log_average(logs: list[PlayerGameLog]) -> dict[str, float]:
    if not logs:
        return {}
    fields = set.intersection(*(set(numeric_stats(row.stats_payload)) for row in logs))
    return {field: mean(float(row.stats_payload[field]) for row in logs) for field in fields}


ROLE_METHOD = (
    "Latest three vs preceding three persisted current-season regular-season games within the 14-day lookback. "
    "Each side needs three valid fresh observations. Minutes threshold: +/-3.0; usage threshold: +/-0.02 (2 percentage points). "
    "Mean and median changes must agree at the threshold, preventing a single-game outlier from establishing direction. "
    "Minutes establish role support; supported usage may add direction, but opposing material directions are insufficient evidence. "
    "No future minutes, usage or starting role is inferred."
)


def role_metric(logs: list[PlayerGameLog], field: str, now: datetime, today: date) -> RoleMetric:
    ordered = sorted(logs, key=lambda row: (row.game_date, row.game_id))[-6:]
    recent_rows, comparison_rows = ordered[-3:], ordered[:-3]
    def window(rows: list[PlayerGameLog]) -> RoleWindow:
        supported = []
        missing, stale = [], []
        for row in rows:
            value = _numeric(row.stats_payload.get(field))
            if value is None or value < 0 or (field == "USG_PCT" and value > 1):
                missing.append(row.game_id)
            elif freshness(row.imported_at, now, 7) != "available":
                stale.append(row.game_id)
            else:
                supported.append((row, value))
        return RoleWindow(
            average=mean(value for _, value in supported) if supported else None,
            median=median(value for _, value in supported) if supported else None,
            games=len(supported), game_ids=[row.game_id for row, _ in supported],
            window_start=min((row.game_date for row in rows), default=None),
            window_end=max((row.game_date for row in rows), default=None),
            as_of=min((row.imported_at for row in rows), default=None),
            missing_game_ids=missing, stale_game_ids=stale,
        )
    recent, comparison = window(recent_rows), window(comparison_rows)
    outdated = bool(ordered) and (ordered[-1].game_date < today - timedelta(days=7)
        or bool(recent.stale_game_ids or comparison.stale_game_ids))
    complete = recent.games == comparison.games == 3
    state = "stale" if outdated else "available" if complete else "partial" if recent.games or comparison.games else "unavailable"
    detail = (f"{field}: three valid fresh observations on each side required. "
        f"Recent {recent.games}/3; comparison {comparison.games}/3. "
        f"Missing/invalid: {len(recent.missing_game_ids) + len(comparison.missing_game_ids)}; "
        f"stale imports: {len(recent.stale_game_ids) + len(comparison.stale_game_ids)}. "
        "Windows are fixed by game date; missing/stale inputs are not zero-filled or backfilled.")
    return RoleMetric(quality=Evidence(state=state, source="NBA player_game_logs",
        as_of=min((row.imported_at for row in ordered), default=None),
        detail=detail, sample_count=recent.games + comparison.games),
        recent=recent, comparison=comparison,
        delta=round(recent.average - comparison.average, 6) if complete and not outdated else None,
        median_delta=round(recent.median - comparison.median, 6) if complete and not outdated else None,
        unit="minutes" if field == "MIN" else "fraction (multiply by 100 for percent / percentage-point delta)")


def current_role(logs: list[PlayerGameLog], season_stats: NbaPlayerSeasonStats | None,
    season: str, now: datetime, today: date) -> Opportunity:
    minutes, usage = (role_metric(logs, field, now, today) for field in ("MIN", "USG_PCT"))
    current = season_stats if season_stats and season_stats.season == season else None
    starter_payload = current.source_payload.get("starter_filter") if current else None
    explicit_starts = _numeric(starter_payload.get("GP")) if isinstance(starter_payload, dict) else None
    valid_starts = current is not None and current.games_played > 0 and explicit_starts is not None and explicit_starts.is_integer() and (
        0 <= explicit_starts <= current.games_played and explicit_starts == current.games_started)
    starts_state = (freshness(current.imported_at, now, 7) if valid_starts
        else "unavailable")
    if starts_state == "available" and current.games_played < 3:
        starts_state = "partial"
    starts = StartsEvidence(
        quality=Evidence(state=starts_state, source="NBA current-season starter-filter GP",
            as_of=current.imported_at if current else None,
            sample_count=current.games_played if valid_starts else 0,
            detail="Explicit starter-filter GP must match saved games_started; an absent starter row is not zero starts."),
        season=current.season if current else None,
        season_starts=int(explicit_starts) if valid_starts else None,
        season_games=current.games_played if valid_starts else None,
    )
    season_usage = _numeric(current.advanced_stats.get("USG_PCT")) if current else None
    if season_usage is None or not 0 <= season_usage <= 1:
        season_usage = None
    usage_quality = Evidence(
        state=freshness(current.imported_at, now, 7) if season_usage is not None else "unavailable",
        source="NBA current-season advanced statistics",
        as_of=current.imported_at if current else None,
        sample_count=current.games_played if season_usage is not None else 0,
        detail="Season usage is context only; it is not game-level recent usage or a comparison window.",
    )
    direction = "INSUFFICIENT EVIDENCE"
    state = minutes.quality.state
    def supported_direction(metric: RoleMetric, threshold: float) -> int | None:
        def band(value: float) -> int:
            return 1 if value >= threshold else -1 if value <= -threshold else 0
        average_band, median_band = band(metric.delta), band(metric.median_delta)
        return average_band if average_band == median_band else None
    if state == "available":
        minute_direction = supported_direction(minutes, 3)
        usage_direction = supported_direction(usage, .02) if usage.delta is not None else 0
        if minute_direction is None or usage_direction is None or minute_direction * usage_direction == -1:
            state = "partial"
        else:
            direction = "RISING" if max(minute_direction, usage_direction) > 0 else "FALLING" if min(minute_direction, usage_direction) < 0 else "STABLE"
    role = CurrentRole(minutes=minutes, usage=usage, starts=starts,
        quality=Evidence(state=state, source="Persisted NBA role windows", as_of=minutes.quality.as_of,
            sample_count=minutes.quality.sample_count,
            detail="Role requires qualified minutes windows. Missing usage/starts remain independent limitations; mean/median disagreement or opposing supported directions are insufficient evidence."),
        trend=direction, season_usage=season_usage, season_usage_quality=usage_quality,
        method=ROLE_METHOD, limitations=[
            "Role intelligence describes measured games only, not future minutes, usage, coach intent or injury replacement permanence.",
            "Recent game-level starts are unavailable; season starts do not establish the current lineup.",
            "No supported game-level usage means recent usage and usage delta remain unavailable; season usage is not substituted.",
        ])
    parts = {}
    if role.quality.state == "available":
        parts["minutes_level"] = min(100, max(0, minutes.recent.average / 36 * 100))
        if usage.delta is not None:
            parts["usage_change"] = min(100, max(0, 50 + usage.delta * 100))
        if starts.quality.state == "available":
            parts["season_start_rate"] = starts.season_starts / starts.season_games * 100
    return Opportunity(minutes=minutes.recent.average, minutes_trend=minutes.delta,
        usage_trend=usage.delta, historical_start_rate=starts.season_starts / starts.season_games if valid_starts else None,
        role=role.trend, score=mean(parts.values()) if parts else None, score_parts=parts, current_role=role)


RECENT_LOOKBACK_DAYS = 14
FORM_LOOKBACK_DAYS = 30
FORM_LOG_WINDOWS: tuple[tuple[str, str, int], ...] = (
    ("LAST_7_DAYS", "Last 7 Days", 7), ("LAST_14_DAYS", "Last 14 Days", RECENT_LOOKBACK_DAYS),
    ("LAST_30_DAYS", "Last 30 Days", FORM_LOOKBACK_DAYS),
)
# Form trend thresholds (2026-11-14 read-only audit): a fantasy PPG change of 30%+ between Last 14 Days and the
# earlier days 15-30 is the 75th percentile of observed changes (n=232; bootstrap 90% CI 26-32%); minutes reuse the
# role threshold. The trend is descriptive and never feeds an evidence gate.
FORM_TREND_PPG = 0.30
FORM_TREND_MINUTES = 3.0
FORM_TREND_MIN_GAMES = 3
FORM_TREND_METHOD = (
    "Last 14 Days against the earlier, non-overlapping days 15-30 of the 30-day look-back; each side needs 3+ fresh "
    "games. A fantasy PPG direction needs a 30%+ change (the 75th percentile of observed changes); a minutes direction "
    "needs 3.0+ minutes (the role threshold). Both signals are required: IMPROVING or DECLINING when one moves and the "
    "other does not oppose it, MIXED when they oppose, STABLE when neither moves. Descriptive only: never an evidence "
    "gate and never a forecast of minutes, role or health."
)
FORM_LIMITATIONS = [
    "Form windows look back at persisted games; they are evidence views, not decision horizons (Last 14 Days is not Next 14 Days).",
    "Fantasy PPG uses the configured Yahoo points formula; a missing statistic is never zero-filled.",
    "Game-level starts and usage are not in the persisted game logs, so recent windows show neither; season windows show them only with explicit provenance.",
]
LOG_STARTS_DETAIL = "Game-level starts are not in the persisted game logs; none are inferred."
LOG_USAGE_DETAIL = "Game-level usage is not in the persisted game logs; season usage is not substituted."


def _valid_minutes(logs: list[PlayerGameLog]) -> list[float]:
    values = []
    for row in logs:
        value = _numeric(row.stats_payload.get("MIN"))
        if value is not None and value >= 0:
            values.append(float(value))
    return values


def explicit_season_starts(row: NbaPlayerSeasonStats | None) -> int | None:
    """Season starts only with explicit starter-filter provenance matching games_started (never a default zero)."""
    payload = row.source_payload.get("starter_filter") if row is not None else None
    explicit = _numeric(payload.get("GP")) if isinstance(payload, dict) else None
    if (row is None or row.games_played <= 0 or explicit is None or not explicit.is_integer()
            or not 0 <= explicit <= row.games_played or explicit != row.games_started):
        return None
    return int(explicit)


def _log_window(key: str, label: str, logs: list[PlayerGameLog], fields: dict[str, float] | None, now: datetime,
        today: date, days: int, quality: Evidence | None, *, mapped: bool = True, logs_current: bool = True,
        logs_complete: bool = True) -> FormWindow:
    start = today - timedelta(days=days)
    rows = [row for row in logs if row.game_date >= start]
    stats = log_average(rows)
    value = production(stats, fields)
    minutes = _valid_minutes(rows)
    as_of = min((row.imported_at for row in rows), default=None)
    latest = max((row.game_date for row in rows), default=None)
    if quality is not None:
        state = quality.state  # Last 14 Days is exactly the model's recent production evidence.
    elif fields is None:
        state = "unsupported"
    elif not rows:
        state = "missing"
    elif freshness(as_of, now, 7) == "stale":
        state = "stale"
    else:
        state = "available" if value is not None else "missing"
    if value is None:
        detail = production_detail(stats, fields, label, len(rows))
    else:
        detail = (f"{label}: {value:.1f} Yahoo fantasy PPG in {len(rows)} persisted regular-season "
            f"game{'s' if len(rows) != 1 else ''}" + (" (stale import)." if state == "stale" else "."))
    reason = form_reason(value=value, rows=len(rows), fields=fields, stale=state == "stale", mapped=mapped,
        logs_current=logs_current, logs_complete=logs_complete)
    tier = sample_tier(len(rows))
    return FormWindow(key=key, label=label, games=len(rows),
        fantasy_ppg=round(value, 2) if value is not None else None,
        minutes_average=round(mean(minutes), 2) if minutes else None,
        minutes_median=round(median(minutes), 2) if minutes else None,
        starts_detail=LOG_STARTS_DETAIL, usage_detail=LOG_USAGE_DETAIL,
        sample_tier=tier, sample_label=SAMPLE_TIER_LABELS[tier], window_start=start, window_end=today,
        latest_game=latest, as_of=as_of, state=state, detail=detail,
        reason=reason, reason_label=FORM_REASON_LABELS[reason] if reason else "")


def form_reason(*, value: float | None, rows: int, fields: dict[str, float] | None, stale: bool, mapped: bool,
        logs_current: bool, previous: bool = False, logs_complete: bool = True) -> str | None:
    """Why a form window has no current value: never a bare "n/a" that hides the cause."""
    if value is not None:
        return "DATA_STALE" if stale else None
    if not mapped:
        return "MAPPING_UNRESOLVED"
    if fields is None:
        return "SCORING_UNSUPPORTED"
    if rows:
        return "DATA_STALE" if stale else "SCORING_FIELD_MISSING"
    if previous:
        return "NO_PREVIOUS_SEASON"
    if not logs_current:
        return "DATA_STALE"
    # Season stats count more current-season games than persisted logs: the empty window may be an import gap.
    if not logs_complete:
        return "GAME_LOGS_MISSING"
    return "NO_GAMES_IN_WINDOW"


def _season_window(key: str, label: str, row: NbaPlayerSeasonStats | None, fields: dict[str, float] | None,
        now: datetime, quality: Evidence | None, starts: int | None, usage: float | None, *, mapped: bool = True,
        logs_current: bool = True, logs_complete: bool = True) -> FormWindow:
    previous = key == "PREVIOUS_SEASON"
    if row is None:
        reason = form_reason(value=None, rows=0, fields=fields, stale=False, mapped=mapped, logs_current=logs_current,
            previous=previous, logs_complete=logs_complete)
        return FormWindow(key=key, label=label, state="missing", sample_tier="INSUFFICIENT",
            sample_label=SAMPLE_TIER_LABELS["INSUFFICIENT"],
            starts_detail="No persisted season statistics.", usage_detail="No persisted season statistics.",
            detail=f"No persisted {label.lower()} regular-season statistics.",
            reason=reason, reason_label=FORM_REASON_LABELS[reason] if reason else "")
    stats = numeric_stats(row.base_stats)
    value = production(stats, fields)
    if quality is not None:
        state = quality.state
    elif fields is None:
        state = "unsupported"
    elif value is None:
        state = "missing"
    else:
        state = freshness(row.imported_at, now, 7)
    minutes = row.minutes_per_game if row.minutes_per_game is not None and row.minutes_per_game >= 0 else None
    tier = sample_tier(row.games_played)
    reason = form_reason(value=value, rows=row.games_played, fields=fields, stale=state == "stale", mapped=mapped,
        logs_current=logs_current, previous=previous, logs_complete=logs_complete)
    return FormWindow(key=key, label=label, games=row.games_played,
        fantasy_ppg=round(value, 2) if value is not None else None,
        minutes_average=round(minutes, 2) if minutes is not None else None,
        starts=starts,
        starts_detail=("Season starts from explicit starter-filter provenance." if starts is not None
            else "Season starts lack explicit starter-filter provenance; none are inferred."),
        usage=usage,
        usage_detail=("Season usage context from persisted advanced statistics; not recent usage." if usage is not None
            else "Season usage is unavailable; none is inferred."),
        sample_tier=tier, sample_label=SAMPLE_TIER_LABELS[tier], season=row.season, as_of=row.imported_at,
        state=state,
        detail=(f"{label} {row.season}: {value:.1f} Yahoo fantasy PPG in {row.games_played} games." if value is not None
            else production_detail(stats, fields, label, row.games_played)),
        reason=reason, reason_label=FORM_REASON_LABELS[reason] if reason else "")


def form_trend(logs: list[PlayerGameLog], fields: dict[str, float] | None, now: datetime, today: date) -> FormTrend:
    recent_start, base_start = today - timedelta(days=RECENT_LOOKBACK_DAYS), today - timedelta(days=FORM_LOOKBACK_DAYS)
    recent = [row for row in logs if row.game_date >= recent_start]
    base = [row for row in logs if base_start <= row.game_date < recent_start]
    fresh = all(freshness(row.imported_at, now, 7) == "available" for row in [*recent, *base])
    trend = FormTrend(recent_games=len(recent), baseline_games=len(base), method=FORM_TREND_METHOD)
    recent_minutes, base_minutes = _valid_minutes(recent), _valid_minutes(base)
    if fresh and len(recent_minutes) >= FORM_TREND_MIN_GAMES and len(base_minutes) >= FORM_TREND_MIN_GAMES:
        trend.recent_minutes, trend.baseline_minutes = round(mean(recent_minutes), 2), round(mean(base_minutes), 2)
        trend.minutes_change = round(trend.recent_minutes - trend.baseline_minutes, 2)
    if fresh and len(recent) >= FORM_TREND_MIN_GAMES and len(base) >= FORM_TREND_MIN_GAMES:
        recent_ppg, base_ppg = production(log_average(recent), fields), production(log_average(base), fields)
        if recent_ppg is not None and base_ppg is not None and base_ppg > 0:
            trend.recent_ppg, trend.baseline_ppg = round(recent_ppg, 2), round(base_ppg, 2)
            trend.ppg_change = round((recent_ppg - base_ppg) / base_ppg, 4)
    if trend.ppg_change is None or trend.minutes_change is None:
        trend.detail = ("Insufficient evidence: both sides need 3+ fresh games with supported fantasy PPG and minutes "
            f"(Last 14 Days {len(recent)}, days 15-30 {len(base)}).")
        return trend
    ppg = 1 if trend.ppg_change >= FORM_TREND_PPG else -1 if trend.ppg_change <= -FORM_TREND_PPG else 0
    minutes = (1 if trend.minutes_change >= FORM_TREND_MINUTES else -1 if trend.minutes_change <= -FORM_TREND_MINUTES
        else 0)
    trend.trend = ("MIXED" if ppg * minutes == -1 else "IMPROVING" if max(ppg, minutes) == 1
        else "DECLINING" if min(ppg, minutes) == -1 else "STABLE")
    trend.detail = (f"Last 14 Days {trend.recent_ppg:.1f} fantasy PPG / {trend.recent_minutes:.1f} minutes vs days 15-30 "
        f"{trend.baseline_ppg:.1f} / {trend.baseline_minutes:.1f} ({trend.ppg_change * 100:+.0f}% PPG, "
        f"{trend.minutes_change:+.1f} minutes).")
    return trend


def recent_form(logs: list[PlayerGameLog], current_row: NbaPlayerSeasonStats | None,
        prior_row: NbaPlayerSeasonStats | None, fields: dict[str, float] | None, now: datetime, today: date, *,
        recent_quality: Evidence | None, season_quality: Evidence | None, starts: StartsEvidence | None,
        season_usage: float | None, mapped: bool = True, logs_current: bool = True,
        logs_complete: bool = True) -> RecentForm:
    """Last 7 / 14 / 30 Days from the one loaded 30-day log set, plus the current and previous season."""
    context = dict(mapped=mapped, logs_current=logs_current, logs_complete=logs_complete)
    windows = [_log_window(key, label, logs, fields, now, today, days,
        recent_quality if key == "LAST_14_DAYS" else None, **context) for key, label, days in FORM_LOG_WINDOWS]
    current_starts = starts.season_starts if starts is not None else None
    windows.append(_season_window("CURRENT_SEASON", "Current Season", current_row, fields, now,
        season_quality if current_row is not None else None, current_starts, season_usage, **context))
    prior_usage = _numeric(prior_row.advanced_stats.get("USG_PCT")) if prior_row is not None else None
    windows.append(_season_window("PREVIOUS_SEASON", "Previous Season", prior_row, fields, now, None,
        explicit_season_starts(prior_row), prior_usage if prior_usage is not None and 0 <= prior_usage <= 1 else None,
        **context))
    return RecentForm(windows=windows, trend=form_trend(logs, fields, now, today), limitations=list(FORM_LIMITATIONS))


@lru_cache(maxsize=4096)
def _matched_positions(positions: tuple[str, ...], slots: tuple[str, ...]) -> int:
    return len(_maximum_slot_matching(
        [_selected_position_positions(position) for position in positions], list(slots),
    ))


def matched_slots(roster: list[Candidate], slots: list[str]) -> int:
    return _matched_positions(tuple(sorted(player.position or "" for player in roster)), tuple(slots))


def coverage(roster: list[Candidate], slots: list[str]) -> float | None:
    if not slots or any(not position_set(player.position or "") for player in roster):
        return None
    return 100.0 * matched_slots(roster, slots) / len(slots)


def roster_fit(player: Candidate, roster: list[Candidate], slots: list[str]) -> float | None:
    return coverage([row for row in roster if row.player_id != player.player_id] + [player], slots)


def sample_gap(player: Candidate, mode: Mode) -> str | None:
    """Why `player` fails the recent-sample gate, naming the window and tier that fall short (None when it passes)."""
    assessment = sample_assessment(player, mode)
    if assessment.passes:
        return None
    gaps = []
    if mode != "ros" and player.current_season_games < SUPPORTED_SAMPLE_GAMES:
        gaps.append(f"{_game_count(player.current_season_games)} this season")
    if assessment.tier != "SUPPORTED":
        tier = SAMPLE_TIER_LABELS[assessment.tier]
        if assessment.tier == "LIMITED" and mode != "ros":
            tier += f": {limited_shortfall(assessment.required, assessment.corroborations)}"
        gaps.append(f"{_game_count(assessment.relevant_games)} {'this season' if mode == 'ros' else 'in the last 14 days'} ({tier})")
    elif mode == "ros" and player.current_season_games < SUPPORTED_SAMPLE_GAMES:
        gaps.append(f"{_game_count(player.current_season_games)} this season")
    quality = player.data_quality.get("ros" if mode == "ros" else "recent")
    if quality is None or quality.state != "available":
        gaps.append(f"production evidence {quality.state if quality is not None else 'missing'}")
    return f"{player.player_name} {' and '.join(gaps)}" if gaps else f"{player.player_name} {assessment.detail}"


def sample_gate_note(mode: Mode, gaps: list[str]) -> str:
    need = ("7 games this season" if mode == "ros"
        else "7 games this season and 7 in the last 14 days (5-6 only when corroborated by deeper current-season evidence)")
    return (f"Sample gate: {'; '.join(gaps)}. A supported move needs {need} for every compared player; "
        "prior-season history cannot bypass this gate.")


def _game_count(count: int) -> str:
    return f"{count} game{'' if count == 1 else 's'}"


def status_gap(player: Candidate, now: datetime) -> str | None:
    """Why `player`'s Yahoo status cannot support a strong recommendation (None when it can)."""
    status = player.data_quality.get("status")
    if not player.yahoo_status:
        # Only the loader's fully verified NO CURRENT YAHOO DESIGNATION passes; every other absence is UNKNOWN.
        if (player.decision_status_state == "NO_CURRENT_YAHOO_DESIGNATION" and status is not None
                and status.state == "available" and freshness(status.as_of, now) == "available"):
            return None
        return "blank (UNKNOWN)"
    if not status_is_supported(player.yahoo_status):
        return f"{player.yahoo_status} (unrecognized, UNKNOWN)"
    if status is None or status.state in {"missing", "stale", "unknown", "unavailable"}:
        return f"{player.yahoo_status} ({status.state if status is not None else 'missing'} status evidence)"
    if freshness(status.as_of, now) != "available":
        return f"{player.yahoo_status} (stale status evidence)"
    return None


def status_gate_note(gaps: list[str]) -> str:
    return (f"Yahoo status gate: {'; '.join(gaps)}. Blank, unrecognized or stale Yahoo status is UNKNOWN, "
        "not healthy, so strong recommendations are blocked.")


def gate_category(note: str, mode: Mode) -> str:
    """Aggregate reason counts group the player-specific gate notes under one shared reason."""
    if note.startswith("Sample gate: "):
        return ("Sample gate: fewer than 7 games this season" if mode == "ros"
            else "Sample gate: recent sample below the supported tier (under 7 games in the last 14 days or this season, and not corroborated)")
    if note.startswith("Yahoo status gate: "):
        return "Yahoo status gate: blank, unrecognized or stale Yahoo status (UNKNOWN)"
    if note.startswith(f"{EXPLANATION_GATE}:") or note == EXPLANATION_GATE:
        return (f"{EXPLANATION_GATE}: the positive index depends on a claim that does not hold in Yahoo fantasy points "
            "(for example a schedule edge smaller than the production loss)")
    if note.startswith(f"{NEAR_TIE_GATE}:"):
        return f"{NEAR_TIE_GATE}: net below the {NEAR_TIE_NET:.3f} display-stability threshold (no strong preference)"
    return note


def window_end_date(today: date, season_year: int, mode: Mode) -> date:
    if mode == "this_week":
        return today + timedelta(days=6 - today.weekday())
    if mode == "next_7_days":
        return today + timedelta(days=6)
    if mode == "next_14_days":
        return today + timedelta(days=13)
    return season_end_date(today, season_year)


def season_end_date(today: date, season_year: int) -> date:
    return max(today, today.replace(year=season_year + 1, month=6, day=30))


@dataclass
class Context:
    league: League
    team_key: str
    mode: Mode
    now: datetime
    players: dict[int, Candidate]
    roster_ids: list[int]
    slots: list[str]
    capacity: int | None
    roster_ready: bool
    weights: dict[str, float]
    quality: dict[str, Evidence]
    mapping_worklist: list[MappingWorklistItem] = field(default_factory=list)
    pool_ids: set[int] | None = None
    comparison_keys: list[str] | None = None
    roster_capacity: RosterCapacity | None = None
    team_needs: TeamNeeds | None = None
    # Starting slots from the persisted roster positions regardless of import age. They describe
    # needs only; scoring and fit use `slots`, which stays empty unless settings are fresh.
    needs_slots: list[str] = field(default_factory=list)
    evidence_freshness: list[FreshnessItem] = field(default_factory=list)
    availability_summary: AvailabilitySummary | None = None
    acquisition: AcquisitionContext | None = None
    # Request-scoped memo for pair comparisons. The loader enables it after the context is final;
    # hand-built contexts leave it None so every comparison is recomputed from current values.
    memo: dict[Any, Any] | None = None


def transaction_shape(ctx: Context) -> TransactionShape:
    return ctx.roster_capacity.transaction_shape if ctx.roster_capacity is not None else "UNDETERMINED"


def injury_slot_ids(ctx: Context) -> set[int]:
    if ctx.roster_capacity is None:
        return set()
    return {row.player_id for row in ctx.roster_capacity.assignments if row.slot_kind == "injury"}


def swap_roster_ids(ctx: Context) -> list[int]:
    """Roster players holding non-injury spots; only these can be dropped to open one."""
    excluded = injury_slot_ids(ctx)
    return [player_id for player_id in ctx.roster_ids if player_id not in excluded]


def planned_moves(ctx: Context) -> list[InjuryMoveOption]:
    if transaction_shape(ctx) == "UNDETERMINED":
        return []
    return list(ctx.roster_capacity.move_to_injury_slot_options)


def fill_members(ctx: Context) -> list[Candidate]:
    """Lineup-eligible players measured in no-drop comparisons, after any conditional IL moves."""
    moved = {move.player_id for move in planned_moves(ctx)}
    return [ctx.players[player_id] for player_id in swap_roster_ids(ctx)
        if player_id not in moved and lineup_eligible(ctx.players[player_id])]


def lineup_coverage(roster: list[Candidate], slots: list[str]) -> float | None:
    """Starting-slot coverage counting only players Yahoo status allows in the lineup."""
    return coverage([row for row in roster if lineup_eligible(row)], slots)


def need_slots(ctx: Context) -> list[str]:
    if ctx.team_needs is None:
        return []
    return sorted(set(ctx.team_needs.open_starting_slots), key=need_order)


def _coverage_metric(rows: list[Candidate], predicate: Callable[[Candidate], bool]) -> CoverageMetric:
    return coverage_metric(sum(predicate(row) for row in rows), len(rows))


def _coverage_slice(rows: list[Candidate]) -> CoverageSlice:
    identity_good = {
        "EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM",
        "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED",
    }
    recent = _coverage_metric(rows, lambda row: row.data_quality["recent"].state == "available")
    recent_stale = _coverage_metric(rows, lambda row: row.data_quality["recent"].state == "stale")
    season = _coverage_metric(rows, lambda row: row.data_quality["ros"].state == "available")
    season_stale = _coverage_metric(rows, lambda row: row.data_quality["ros"].state == "stale")
    schedule_supported = _coverage_metric(rows, lambda row: row.schedule.coverage == "PARTIAL")
    schedule_unknown = _coverage_metric(rows, lambda row: row.schedule.coverage == "UNKNOWN")
    schedule_stale = _coverage_metric(rows, lambda row: row.schedule.coverage == "STALE")
    schedule_incomplete = _coverage_metric(
        rows, lambda row: row.schedule.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE",
    )
    explicit_status = _coverage_metric(rows, lambda row: bool(row.raw_yahoo_status and row.raw_yahoo_status.strip()))
    blank_status = _coverage_metric(rows, lambda row: row.status_diagnostic == "YAHOO_SUPPLIED_BLANK")
    field_missing_status = _coverage_metric(rows, lambda row: row.status_diagnostic == "STATUS_FIELD_MISSING")
    no_current_designation = _coverage_metric(
        rows, lambda row: row.decision_status_state == "NO_CURRENT_YAHOO_DESIGNATION")
    stale_status = _coverage_metric(rows, lambda row: row.status_diagnostic == "STALE_PLAYER_POOL_IMPORT")
    minutes_qualified = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.minutes.quality.state == "available")
    usage_supported = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.usage.quality.state == "available")
    game_starts = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.starts.recent_starts is not None)
    season_starts = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.starts.season_starts is not None)
    insufficient_sample = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None
        and row.opportunity.current_role.minutes.quality.state == "partial")
    missing_role_inputs = _coverage_metric(rows, lambda row: row.opportunity.current_role is not None and (
        row.opportunity.current_role.minutes.quality.state != "available"
        or row.opportunity.current_role.usage.quality.state != "available"
        or row.opportunity.current_role.starts.recent_starts is None
    ))
    return CoverageSlice(
        identity=IdentityCoverage(
            complete=_coverage_metric(rows, lambda row: row.identity_mapping_state in identity_good),
            unresolved=_coverage_metric(rows, lambda row: row.identity_mapping_state not in identity_good),
            resolution_counts=dict(sorted(Counter(row.identity_mapping_state for row in rows).items())),
        ),
        production=ProductionCoverage(
            recent_supported=recent,
            recent_missing=coverage_metric(len(rows) - recent.count - recent_stale.count, len(rows)),
            recent_stale=recent_stale,
            season_supported=season,
            season_missing=coverage_metric(len(rows) - season.count - season_stale.count, len(rows)),
            season_stale=season_stale,
        ),
        schedule=ScheduleCoverage(
            supported=schedule_supported,
            unknown=schedule_unknown,
            stale=schedule_stale,
            source_incomplete=schedule_incomplete,
        ),
        status=StatusCoverage(explicit=explicit_status, yahoo_blank=blank_status, field_missing=field_missing_status,
            no_current_designation=no_current_designation, stale=stale_status),
        role=RoleCoverage(
            minutes_qualified=minutes_qualified,
            usage_supported=usage_supported,
            game_level_starts_supported=game_starts,
            season_starts_supported=season_starts,
            insufficient_sample=insufficient_sample,
            missing_inputs=missing_role_inputs,
        ),
    )


def board_coverage(ctx: Context) -> tuple[WaiverCoverage, list[DataGap]]:
    rows = (
        [ctx.players[player_id] for player_id in ctx.pool_ids if player_id in ctx.players]
        if ctx.pool_ids is not None else list(ctx.players.values())
    )
    candidates = [row for row in rows if availability_actionable(row)]
    roster = [ctx.players[player_id] for player_id in ctx.roster_ids]
    pool_coverage = _coverage_slice(rows)
    candidate_coverage = _coverage_slice(candidates)
    roster_coverage = _coverage_slice(roster)
    acquisition_available = ctx.quality["acquisition_value"].state == "available"
    coverage = WaiverCoverage(
        population=CoverageScope(total=len(rows), candidates=len(candidates), roster=len(roster)),
        pool=pool_coverage,
        candidates=candidate_coverage,
        roster=roster_coverage,
        acquisition=AcquisitionCoverage(
            supported=coverage_metric(int(acquisition_available), 1),
            unsupported=coverage_metric(int(not acquisition_available), 1),
        ),
        mapping_worklist=[
            item for item in ctx.mapping_worklist
            if ctx.pool_ids is None or item.internal_id in ctx.pool_ids
        ],
    )
    gaps: list[DataGap] = []

    categories: dict[RootCause, DataGapCategory] = {
        "RESOLVABLE_INTERNAL_DEFECT": "FIXABLE DATA ISSUE",
        "STALE_EXISTING_SOURCE": "FIXABLE DATA ISSUE",
        "MISSING_MAPPING": "FIXABLE DATA ISSUE",
        "MISSING_EXISTING_SOURCE_FIELD": "SOURCE DOES NOT SUPPLY",
        "SOURCE_DOES_NOT_SUPPLY": "SOURCE DOES NOT SUPPLY",
        "SOURCE_CONTRACT_UNVERIFIED": "SOURCE CONTRACT UNVERIFIED",
        "REQUIRES_MORE_GAMES": "WAITING FOR MORE GAMES",
        "REQUIRES_NEW_SOURCE": "NEW SOURCE REQUIRED",
        "INTENTIONALLY_UNSUPPORTED": "INTENTIONALLY UNSUPPORTED",
    }

    def add_gap(
        root_cause: RootCause,
        field_name: str,
        count: int,
        total: int,
        reason: str,
    ) -> None:
        if count:
            gaps.append(DataGap(
                category=categories[root_cause],
                field=field_name,
                count=count,
                total=total,
                percentage=round(count / total * 100, 2) if total else 0,
                reason=reason,
                root_cause=root_cause,
            ))

    unresolved = [
        row for row in rows
        if row.identity_mapping_state not in RESOLVED_IDENTITY_STATES
    ]
    add_gap(
        "MISSING_MAPPING", "Yahoo ↔ NBA identity mapping",
        sum(row.identity_mapping_state != "NON_NBA_PLAYER" for row in unresolved),
        len(rows),
        "Persisted names/teams do not establish a unique mapping. Review the mapping worklist; no identity or team was changed automatically.",
    )

    for field_name, quality_key in (("Recent production", "recent"), ("Season Evidence", "ros")):
        evidence = [row.data_quality[quality_key] for row in candidates]
        for state, root_cause, reason in (
            ("stale", "STALE_EXISTING_SOURCE", "Persisted production evidence is outside the supported freshness window; stale values are not used for scoring."),
            ("unsupported", "SOURCE_CONTRACT_UNVERIFIED", "Persisted Yahoo scoring modifiers are unavailable; the production calculation contract cannot be verified."),
        ):
            add_gap(root_cause, field_name, sum(item.state == state for item in evidence), len(candidates), reason)
        no_observations = sum(
            item.state == "missing" and "no eligible persisted NBA game/stat observations" in item.detail
            for item in evidence
        )
        missing_fields = sum(
            item.state == "missing" and "lack required scoring fields" in item.detail
            for item in evidence
        )
        internal_defects = sum(
            item.state == "missing" and "complete numeric scoring inputs could not be calculated" in item.detail
            for item in evidence
        )
        if no_observations:
            add_gap(
                "REQUIRES_MORE_GAMES", field_name, no_observations, len(candidates),
                "No eligible persisted game/stat observations exist in the selected window; this is an evidence/sample limitation.",
            )
        add_gap(
            "MISSING_EXISTING_SOURCE_FIELD", field_name, missing_fields, len(candidates),
            "Persisted NBA observations lack one or more required Yahoo-scoring stat fields; missing values are not zero-filled.",
        )
        add_gap(
            "RESOLVABLE_INTERNAL_DEFECT", field_name, internal_defects, len(candidates),
            "Complete numeric scoring inputs were persisted but the calculation could not be completed; investigate the calculation path.",
        )

    no_schedule_rows = [
        row for row in rows
        if row.schedule.diagnostic_reason == "NO_PLAYER_SCHEDULE_ROWS"
    ]
    add_gap(
        "MISSING_MAPPING", "Player schedule rows blocked by identity",
        sum(not identity_is_supported(row) for row in no_schedule_rows), len(rows),
        "The NBA identity chain is unresolved, so player schedule rows cannot be attributed safely.",
    )
    add_gap(
        "MISSING_EXISTING_SOURCE_FIELD", "Player schedule rows missing",
        sum(identity_is_supported(row) for row in no_schedule_rows), len(rows),
        "No per-player schedule rows are persisted for this resolved identity; no games are inferred from team-wide schedules.",
    )
    add_gap(
        "STALE_EXISTING_SOURCE", "Stale player schedule",
        pool_coverage.schedule.stale.count, pool_coverage.schedule.stale.total,
        "Persisted player schedule rows are older than the supported freshness window; counts are withheld until refreshed.",
    )
    add_gap(
        "STALE_EXISTING_SOURCE", "Stale Yahoo status",
        pool_coverage.status.stale.count, pool_coverage.status.stale.total,
        "The Yahoo player-pool observation is older than the status freshness limit; retain the raw status but do not treat it as current.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Schedule completeness",
        pool_coverage.schedule.source_incomplete.count, pool_coverage.schedule.source_incomplete.total,
        "Player schedule rows exist, but there is no verified completeness manifest. An empty requested window is UNKNOWN, not a verified zero.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Unrecognized Yahoo status token",
        sum(row.status_diagnostic == "UNRECOGNIZED_STATUS" for row in rows), len(rows),
        "This nonblank Yahoo status token is not in the verified status set; it remains UNKNOWN and cannot support a strong action.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Game-level usage",
        len(rows) - pool_coverage.role.usage_supported.count, len(rows),
        "Existing adapter capability for game-level USG_PCT is unverified; season usage is not substituted for game-level role evidence.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Recent game-level starts",
        len(rows) - pool_coverage.role.game_level_starts_supported.count, len(rows),
        "Existing adapter capability for explicit game-level starter status is unverified; season-level starts do not prove the current lineup.",
    )
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Acquisition and matchup context",
        int(not acquisition_available), 1,
        "Current priority, weekly adds, claim timing, matchup period, manager identity, and transaction history are not verified from persisted Yahoo evidence.",
    )
    unverified_claim_state = sum(availability_class(row) == "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT" for row in candidates)
    add_gap(
        "SOURCE_CONTRACT_UNVERIFIED", "Free-agent vs waiver-claim state",
        unverified_claim_state, len(candidates),
        "Absence from fresh league rosters is labeled unrostered; it does not establish current free-agent status or waiver-claim timing.",
    )
    return coverage, gaps


def roster_components(ctx: Context, roster: list[Candidate], keys: list[str]) -> Components:
    values: dict[str, float | None] = {}
    for key in keys:
        measured = [getattr(player.components, key) for player in roster]
        # fsum is exactly rounded and order-independent; statistics.mean's fraction arithmetic was a
        # measurable share of every pair comparison.
        values[key] = lineup_coverage(roster, ctx.slots) if key == "roster_fit" else (
            fsum(measured) / len(measured) if measured and all(value is not None for value in measured) else None
        )
    return Components(**values)


def _comparison_keys(ctx: Context, rows: list[Candidate]) -> list[str]:
    # A fixed common mask and normalization basis is used on BOTH sides of a comparison.
    return ctx.comparison_keys if ctx.comparison_keys is not None else [
        key for key in COMPONENTS if ctx.weights[key] > 0
        and all(row.components.model_dump()[key] is not None for row in rows)
    ]


def _scores(ctx: Context, before_total: Components, after_total: Components, keys: list[str]) -> tuple[
    float | None, float | None, float | None, Components, dict[str, float],
]:
    before_values, after_values = before_total.model_dump(), after_total.model_dump()
    if not all(before_values[key] is not None and after_values[key] is not None for key in keys):
        return None, None, None, Components(), {}
    denominator = sum(ctx.weights[key] for key in keys)
    effective = {key: ctx.weights[key] / denominator for key in keys}
    before_score = round(sum(before_values[key] * effective[key] for key in keys), 6)
    after_score = round(sum(after_values[key] * effective[key] for key in keys), 6)
    deltas = Components(**{key: round(after_values[key] - before_values[key], 6) for key in keys})
    return before_score, after_score, round(after_score - before_score, 6), deltas, effective


def _slot_counts(ctx: Context, roster: list[Candidate]) -> int | None:
    lineup = [row for row in roster if lineup_eligible(row)]
    return matched_slots(lineup, ctx.slots) if coverage(lineup, ctx.slots) is not None else None


def _swap_baseline(ctx: Context, roster: list[Candidate], keys: list[str]) -> tuple[Components, int | None, list[str]]:
    """Before-side roster components, slot count and uncovered slots: identical for every add and
    drop of one request, so they are measured once instead of once per pair."""
    memo_key = ("swap_baseline", tuple(keys))
    if ctx.memo is not None and memo_key in ctx.memo:
        return ctx.memo[memo_key]
    lineup = [row for row in roster if lineup_eligible(row)]
    baseline = (roster_components(ctx, roster, keys), _slot_counts(ctx, roster),
        uncovered_slots(lineup, ctx.slots) if ctx.slots else [])
    if ctx.memo is not None:
        ctx.memo[memo_key] = baseline
    return baseline


def compare(ctx: Context, player: Candidate, drop_id: int | None) -> DropOption:
    if drop_id is None:
        return compare_no_drop(ctx, player)
    if drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the configured manager roster")
    memo_key = ("pair", player.player_id, drop_id)
    if ctx.memo is not None and memo_key in ctx.memo:
        return ctx.memo[memo_key]
    result = _compare_pair(ctx, player, drop_id)
    if ctx.memo is not None:
        ctx.memo[memo_key] = result
    return result


def _compare_pair(ctx: Context, player: Candidate, drop_id: int) -> DropOption:
    dropped = ctx.players[drop_id]
    if drop_id in injury_slot_ids(ctx):
        return DropOption(
            player_id=drop_id, player_name=dropped.player_name, before_score=None, after_score=None,
            net_improvement=None, component_deltas=Components(),
            starting_slots_required=len(ctx.slots) or None,
            reasons=[f"{dropped.player_name} occupies an injury slot; dropping that player does not open a non-injury roster spot for this add."],
        )
    roster = [ctx.players[pid] for pid in swap_roster_ids(ctx)]
    after = [row for row in roster if row.player_id != drop_id] + [player]
    keys = _comparison_keys(ctx, [*roster, player])
    before_total, slots_before, uncovered_before = _swap_baseline(ctx, roster, keys)
    after_total = roster_components(ctx, after, keys)
    before_score = after_score = net = None
    deltas = Components()
    effective: dict[str, float] = {}
    if ctx.roster_ready and player.eligible and {"roster_fit", "player_value"} <= set(keys):
        before_score, after_score, net, deltas, effective = _scores(ctx, before_total, after_total, keys)
    target = None
    if ctx.slots:
        target = newly_covered_slot(
            uncovered_before,
            uncovered_slots([row for row in after if lineup_eligible(row)], ctx.slots), player,
        )
        if target is None and ctx.roster_capacity is not None:
            released = next((row.roster_slot for row in ctx.roster_capacity.assignments if row.player_id == drop_id), None)
            # The add inherits the released slot only when Yahoo eligibility allows it there.
            target = released if released and slot_accepts(released, player) else None
    option = DropOption(
        player_id=drop_id, player_name=dropped.player_name,
        before_score=before_score, after_score=after_score, net_improvement=net,
        component_deltas=deltas,
        component_before=before_total, component_after=after_total, effective_weights=effective,
        starting_slots_before=slots_before,
        starting_slots_after=_slot_counts(ctx, after),
        starting_slots_required=len(ctx.slots) or None,
        comparison_type="ADD_DROP", target_roster_position=target,
        reasons=[
            "Before/after scores are 0-100 roster indices: mean player components over players holding non-injury roster spots, with positional fit measured once as the percentage of starting slots coverable by lineup-eligible players.",
            "Both sides use the same weights and fixed league production percentiles. Fully covered lineups receive no extra fit gain from reassignment.",
            f"Common measured components: {', '.join(keys)}.",
            "Net improvement is a model-index difference, not a forecast of fantasy points.",
        ] if net is not None else ["Swap impact unavailable: fresh manager roster, positional eligibility and supported player values for every roster member are required."],
    )
    if net is not None:
        option.explanation = explain_comparison(
            mode=ctx.mode, add=player, drop=dropped, comparison=option,
            window=(player.schedule.window_start, player.schedule.window_end),
            omitted=omitted_components(ctx, list(effective)),
            recompute=lambda subset: _scores(ctx, before_total, after_total, subset)[2])
    return option


def omitted_components(ctx: Context, keys: list[str]) -> dict[str, str]:
    """Why each component outside the common mask is not part of a comparison (never filled with a value)."""
    reasons = {}
    for key in COMPONENTS:
        if key in keys:
            continue
        if ctx.weights.get(key, 0) <= 0:
            reasons[key] = "its configured weight is 0."
        elif key == "acquisition_value":
            reasons[key] = ("acquisition value is unavailable (current rolling priority and transaction evidence are "
                "unverified); it never affects ranking.")
        elif key == "schedule":
            reasons[key] = ("at least one comparable player has no persisted game in this window or a stale schedule "
                "(unknown, never zero), so schedule is omitted for every pair.")
        elif key == "opportunity":
            reasons[key] = ("qualified fresh role evidence is missing for at least one comparable player, so "
                "opportunity is omitted for every pair.")
        else:
            reasons[key] = "mandatory evidence is missing."
    return reasons


def explanation_supports(option: DropOption | None) -> bool:
    """The explanation-consistency gate for a positive comparison (comparisons built outside the engine carry none)."""
    return option is None or option.explanation is None or option.explanation.consistent


def _fill_components(ctx: Context, members: list[Candidate], keys: list[str], spots: int | None) -> Components:
    values: dict[str, float | None] = {}
    for key in keys:
        if key == "roster_fit":
            values[key] = coverage(members, ctx.slots)
        else:
            measured = [getattr(row.components, key) for row in members]
            values[key] = (sum(measured) / spots
                if spots and all(value is not None for value in measured) else None)
    return Components(**values)


def compare_no_drop(ctx: Context, player: Candidate) -> DropOption:
    """ADD ONLY / MOVE TO IL THEN ADD: nobody is removed from the roster.

    Non-fit components average over the fixed non-injury roster spots, so an open spot (or a
    spot held by an Out/Not Active player) contributes no production, opportunity or games.
    Positional fit is measured once for the whole lineup, never summed per player.
    """
    memo_key = ("no_drop", player.player_id)
    if ctx.memo is not None and memo_key in ctx.memo:
        return ctx.memo[memo_key]
    result = _compare_no_drop(ctx, player)
    if ctx.memo is not None:
        ctx.memo[memo_key] = result
    return result


def _fill_baseline(ctx: Context, members: list[Candidate], keys: list[str], spots: int | None) -> tuple[Components, int | None, list[str]]:
    memo_key = ("fill_baseline", tuple(keys), spots)
    if ctx.memo is not None and memo_key in ctx.memo:
        return ctx.memo[memo_key]
    baseline = (_fill_components(ctx, members, keys, spots),
        matched_slots(members, ctx.slots) if coverage(members, ctx.slots) is not None else None,
        uncovered_slots(members, ctx.slots) if ctx.slots else [])
    if ctx.memo is not None:
        ctx.memo[memo_key] = baseline
    return baseline


def _compare_no_drop(ctx: Context, player: Candidate) -> DropOption:
    capacity = ctx.roster_capacity
    shape = transaction_shape(ctx)
    members = fill_members(ctx)
    after = [*members, player]
    move = planned_moves(ctx)[0] if shape == "MOVE_TO_IL_THEN_ADD" else None
    if capacity is not None and shape in FILL_SHAPES:
        spots = capacity.non_injury_capacity
        open_before = 1 if move is not None else capacity.open_roster_spots
    elif capacity is None and ctx.capacity is not None:
        spots, open_before = ctx.capacity, ctx.capacity - len(ctx.roster_ids)
    else:
        spots, open_before = None, None
    keys = _comparison_keys(ctx, [*members, player])
    before_total, slots_before, uncovered_before = _fill_baseline(ctx, members, keys, spots)
    after_total = _fill_components(ctx, after, keys, spots)
    before_score = after_score = net = None
    deltas = Components()
    effective: dict[str, float] = {}
    possible = bool(spots) and open_before is not None and open_before >= 1
    if possible and ctx.roster_ready and player.eligible and {"roster_fit", "player_value"} <= set(keys):
        before_score, after_score, net, deltas, effective = _scores(ctx, before_total, after_total, keys)
    target = None
    if ctx.slots:
        target = newly_covered_slot(uncovered_before, uncovered_slots(after, ctx.slots), player) or "BN"
    comparison_type = "MOVE_TO_IL_THEN_ADD" if move is not None else "ADD_ONLY"
    if net is not None:
        reasons = [
            f"No-drop comparison over the same {spots} non-injury roster spots: nobody is removed. Open spots and spots held by Out/Not Active players contribute no production, opportunity or scheduled games.",
            "Positional fit is measured once for the whole lineup as the percentage of starting slots coverable; it is not a sum of player marginal assignments.",
            f"Common measured components: {', '.join(keys)}.",
            "Net improvement is a model-index difference, not a forecast of fantasy points.",
        ]
        if move is not None:
            reasons.insert(1, (f"Baseline assumes {move.player_name} moves from {move.from_slot} to {move.to_slot} first; "
                f"{move.player_name} stays on the roster. This is not a drop, and it depends on Yahoo currently allowing the IL placement."))
    elif not possible:
        reasons = ["No-drop impact unavailable: persisted Yahoo slot evidence does not establish an open non-injury roster spot."]
    else:
        reasons = ["No-drop impact unavailable: fresh manager roster, positional eligibility and supported values for every measured lineup player are required."]
    option = DropOption(
        player_id=None,
        player_name=f"No drop (move {move.player_name} to {move.to_slot})" if move is not None else "No drop (open roster slot)",
        before_score=before_score, after_score=after_score, net_improvement=net,
        component_deltas=deltas, component_before=before_total, component_after=after_total,
        effective_weights=effective,
        starting_slots_before=slots_before,
        starting_slots_after=matched_slots(after, ctx.slots) if coverage(after, ctx.slots) is not None else None,
        starting_slots_required=len(ctx.slots) or None,
        comparison_type=comparison_type,
        moved_to_injury_slot_player_id=move.player_id if move is not None else None,
        moved_to_injury_slot_player_name=move.player_name if move is not None else None,
        target_roster_position=target, roster_spots_basis=spots,
        open_roster_spots_before=open_before if possible else None,
        open_roster_spots_after=open_before - 1 if possible else None,
        reasons=reasons,
    )
    if net is not None:
        option.explanation = explain_comparison(
            mode=ctx.mode, add=player, drop=None, comparison=option,
            window=(player.schedule.window_start, player.schedule.window_end),
            omitted=omitted_components(ctx, list(effective)),
            recompute=lambda subset: _scores(ctx, before_total, after_total, subset)[2])
    return option


def _undetermined_capacity_reason(ctx: Context) -> str:
    blockers = ctx.roster_capacity.blockers if ctx.roster_capacity is not None else []
    return ("Roster capacity is undetermined; no ADD + DROP default is applied"
        + (f": {blockers[0]}" if blockers else "."))


def action_label(ctx: Context, row: Candidate, action: ActionType, drop_id: int | None) -> str:
    target = row.target_roster_position
    covers = f" to cover {target}" if target and target != "BN" else ""
    if action == "ADD_ONLY":
        return f"ADD ONLY: Add {row.player_name}{covers}. You have an open roster spot. No player needs to be dropped."
    if action == "MOVE_TO_IL_THEN_ADD" and row.suggested_injury_move is not None:
        move = row.suggested_injury_move
        return (f"MOVE {move.player_name} TO {move.to_slot}, THEN ADD {row.player_name}{covers}. "
            f"{move.player_name} stays on your roster; this is not a drop.")
    if action == "ADD_DROP":
        drop = ctx.players[drop_id].player_name if drop_id is not None else (
            row.comparison.player_name if row.comparison is not None else "the selected player")
        if transaction_shape(ctx) in FILL_SHAPES:
            return f"ADD {row.player_name} + DROP {drop}: optional comparison. Your roster has open capacity, so no drop is required."
        return f"ADD {row.player_name} + DROP {drop}: Your roster is full."
    if action == "WATCH":
        return "WATCH: The measured fit is positive, but the sample is too small for a supported move."
    if action == "HOLD":
        return "HOLD: No sufficiently supported move currently improves the roster."
    explanation = row.comparison.explanation if row.comparison is not None else None
    if explanation is not None and (row.net_improvement or 0) > 0 and not explanation.consistent:
        prefix = "NEAR TIE — NO STRONG PREFERENCE" if explanation.near_tie else "DO NOT ADD"
        return f"{prefix}: {explanation.statement}"
    first = next(iter(row.evidence_blockers), "required evidence is missing, stale or unverified.")
    return f"INSUFFICIENT EVIDENCE: {first}"


def classify_action(ctx: Context, result: Candidate, drop_id: int | None) -> None:
    shape = transaction_shape(ctx)
    actionable = (result.recommended_action in ACTIONABLE_DECISIONS
        and result.net_improvement is not None and result.net_improvement > 0)
    kind: ActionType | None
    result.requires_injury_slot_move = False
    result.suggested_injury_move = None
    if drop_id is not None:
        kind, result.requires_drop = "ADD_DROP", True
    elif shape == "ADD_ONLY":
        kind, result.requires_drop = "ADD_ONLY", False
    elif shape == "MOVE_TO_IL_THEN_ADD":
        kind, result.requires_drop = "MOVE_TO_IL_THEN_ADD", False
        result.requires_injury_slot_move = True
        result.suggested_injury_move = planned_moves(ctx)[0]
    elif shape == "ADD_DROP":
        kind, result.requires_drop = "ADD_DROP", True
    else:
        kind, result.requires_drop = None, None
    result.target_roster_position = result.comparison.target_roster_position if result.comparison else None
    result.fills_needs = [slot for slot in need_slots(ctx) if slot_accepts(slot, result)]
    if kind is not None and actionable:
        action: ActionType = kind
    elif result.recommended_action == "WATCH":
        action = "WATCH"
    elif result.recommended_action == "PASS":
        action = "HOLD"
    else:
        action = "INSUFFICIENT_EVIDENCE"
    result.recommended_action_type = action
    result.action_label = action_label(ctx, result, action, drop_id)
    result.move_intent, result.move_intent_detail = move_intent(ctx, result, action)
    result.verdict, result.verdict_text = transaction_verdict(ctx, result)
    result.evidence_dimensions = evidence_dimensions(ctx, result)


def pair_text(ctx: Context, row: Candidate) -> str:
    comparison = row.comparison
    if comparison is None:
        return f"ADD {row.player_name}"
    if comparison.comparison_type == "MOVE_TO_IL_THEN_ADD":
        return f"MOVE {comparison.moved_to_injury_slot_player_name} TO IL, THEN ADD {row.player_name}"
    if comparison.player_id is None:
        return f"ADD ONLY {row.player_name}"
    return f"ADD {row.player_name} / DROP {comparison.player_name}"


def transaction_verdict(ctx: Context, row: Candidate) -> tuple[TransactionVerdict, str]:
    """The backend's answer to "should I make this move?" from the candidate's exact comparison and decision."""
    comparison = row.comparison
    net = comparison.net_improvement if comparison is not None else None
    explanation = comparison.explanation if comparison is not None else None
    action = row.recommended_action_type
    pair = pair_text(ctx, row)
    if action in SUPPORTED_ACTION_TYPES:
        return "SUPPORTED_ADD", f"SUPPORTED ADD — {pair}, net {signed(net)} roster-index points."
    if explanation is not None and explanation.near_tie:
        return "NEAR_TIE", (f"NEAR TIE — NO STRONG PREFERENCE. Best measured comparison: {pair}, net {net:+.4f} "
            f"(rounds to {net:+.2f}).")
    if action == "WATCH":
        blocker = next((note for note in row.evidence_blockers if note.startswith("Sample gate: ")), None)
        detail = blocker.removeprefix("Sample gate: ").split(". A supported move needs")[0] if blocker else "a small sample"
        return "WATCH_ONLY", (f"WATCH ONLY — No supported positive add/drop combination was found. Best measured "
            f"comparison: {pair}, net {signed(net)}, blocked by: {detail}.")
    if explanation is not None and net is not None and net > 0 and not explanation.consistent:
        return "DO_NOT_ADD", f"DO NOT ADD — {pair} shows {signed(net)} index points, but {explanation.statement}"
    if action == "HOLD":
        unsupported = (f" Its {', '.join(COMPONENT_NAMES.get(key, key) for key in explanation.refuted)} edge does "
            f"not hold in Yahoo fantasy points; without it the net is {signed(explanation.reconciled_net)}."
            if explanation is not None and explanation.refuted else "")
        return "DO_NOT_ADD", (f"DO NOT ADD — Best comparison is {pair}, net {signed(net)}.{unsupported} Keep your "
            "current roster under this model.")
    first = next(iter(row.evidence_blockers), "required evidence is missing, stale or unverified")
    return "CANNOT_EVALUATE", f"CANNOT EVALUATE — {first.rstrip('.')}."


def evidence_dimensions(ctx: Context, row: Candidate) -> list[EvidenceDimension]:
    """Each evidence label with its dimension, so different label systems are never shown unlabeled together."""
    assessment = sample_assessment(row, ctx.mode)
    games, where = assessment.relevant_games, ("this season" if ctx.mode == "ros" else "in the last 14 days")
    quality = row.data_quality.get("ros" if ctx.mode == "ros" else "recent")
    if assessment.tier == "SUPPORTED" and assessment.passes:
        sample = ("STRONG", f"Strong: {_game_count(games)} {where}")
    elif assessment.tier == "SUPPORTED":
        sample = ("STALE" if quality is not None and quality.state == "stale" else "TOO_SMALL",
            f"Not supported: {assessment.detail}")
    elif assessment.tier == "LIMITED" and assessment.passes:
        sample = ("LIMITED_CORROBORATED", f"Limited but corroborated: {_game_count(games)} {where}; "
            f"{assessment.corroborations_passed} of {len(assessment.corroborations)} corroborations passed")
    elif assessment.tier == "LIMITED":
        shortfall = (limited_shortfall(assessment.required, assessment.corroborations) if ctx.mode != "ros"
            else "a limited current-season sample cannot be corroborated by older seasons")
        sample = ("LIMITED_NOT_CORROBORATED", f"Limited, not corroborated: {_game_count(games)} {where}; {shortfall}")
    else:
        prefix = f"{games}-GAME SAMPLE — WATCH ONLY" if games in {1, 2} else "Too small"
        sample = ("TOO_SMALL", f"{prefix}: {_game_count(games)} {where}; 7+ needed (5-6 only when corroborated)")
    role = row.opportunity.current_role
    role_state = role.quality.state if role is not None else "unavailable"
    role_text = {
        "available": f"Supported: {role.trend if role else ''} role, {row.opportunity.minutes or 0:.1f} recent minutes",
        "partial": "Partial: fewer than three valid fresh games on each side, or conflicting directions",
        "stale": "Stale: role evidence is older than seven days",
    }.get(role_state, "Unavailable: no qualified role windows")
    schedule = row.schedule
    horizon = HORIZON_LABELS[ctx.mode]
    if schedule.coverage == "STALE":
        schedule_state, schedule_text = "STALE", "Stale: schedule import is older than seven days"
    elif schedule.games_remaining is not None:
        schedule_state, schedule_text = "ROWS_PRESENT_PARTIAL", (f"{_game_count(schedule.games_remaining)} in "
            f"{horizon}: rows present, coverage partial (no completeness manifest)")
    else:
        schedule_state, schedule_text = "UNKNOWN", f"Unknown in {horizon} ({schedule.diagnostic_reason}); never zero"
    status = row.data_quality.get("status")
    stale_sources = [name for name, evidence in (("production", quality), ("Yahoo status", status))
        if evidence is not None and evidence.state == "stale"]
    freshness_state = "STALE" if stale_sources else "CURRENT"
    return [
        EvidenceDimension(key="PRODUCTION_SAMPLE", label="PRODUCTION SAMPLE", state=sample[0], text=sample[1],
            detail=assessment.detail),
        EvidenceDimension(key="CURRENT_ROLE", label="CURRENT ROLE", state=role_state.upper(), text=role_text,
            detail=role.quality.detail if role is not None else ""),
        EvidenceDimension(key="SCHEDULE", label="SCHEDULE", state=schedule_state, text=schedule_text),
        EvidenceDimension(key="SOURCE_FRESHNESS", label="SOURCE FRESHNESS", state=freshness_state,
            text=("Stale: " + ", ".join(stale_sources)) if stale_sources else "Current: production and Yahoo status"),
        EvidenceDimension(key="TRANSACTION_VERDICT", label="TRANSACTION VERDICT", state=row.verdict,
            text=row.verdict_text),
    ]


SUPPORTED_ACTION_TYPES = frozenset({"ADD_ONLY", "MOVE_TO_IL_THEN_ADD", "ADD_DROP"})
HORIZON_LABELS = {"this_week": "Rest of Week", "next_7_days": "Next 7 Days", "next_14_days": "Next 14 Days",
    "ros": "Rest of Season Outlook"}


def move_intent(ctx: Context, row: Candidate, action: ActionType) -> tuple[str, str]:
    """What a supported move is for. The reason comes from the pair's measured contributions (never a component
    outside the common mask or with a nonpositive contribution); it never changes a gate."""
    if action not in SUPPORTED_ACTION_TYPES:
        return {"WATCH": "WATCH", "HOLD": "HOLD"}.get(action, "INSUFFICIENT_EVIDENCE"), ""
    explanation = row.comparison.explanation if row.comparison is not None else None
    because = explanation.primary_reason if explanation is not None else "the measured roster-index gain"
    horizon = HORIZON_LABELS[ctx.mode]
    scheduled = bool(row.schedule.games_remaining)
    # Without persisted games in the horizon a zero is never asserted, and the schedule is not part of the support.
    unscheduled = "" if scheduled or ctx.mode == "ros" else (f" Games for {row.player_name} in {horizon} are not "
        f"established ({row.schedule.diagnostic_reason}), so the schedule is not part of this support.")
    if ctx.mode == "ros":
        return "LONGER_TERM_ADD", (f"Rest of Season Outlook move. Main reason: {because}. Season Evidence is "
            "historical, not a projection.")
    if row.recommended_action == "ADD" and row.hold_type == "longer_term_hold":
        return "LONGER_TERM_ADD", (f"Supported in {horizon}. Main reason: {because}. {row.player_name} also has "
            "longer-term Season Evidence (20+ games, top-40% production, 24+ minutes); historical, not a projection."
            f"{unscheduled}")
    if ctx.mode == "next_14_days":
        return "TWO_WEEK_STREAM", f"Two-week move. Main reason: {because}.{unscheduled}"
    return "STREAM", f"Short-term move in {horizon}. Main reason: {because}.{unscheduled}"


def enrich(ctx: Context, player: Candidate, drop_id: int | None = None) -> Candidate:
    result = player.model_copy(update={"reasons": list(player.reasons)})
    shape = transaction_shape(ctx)
    blockers: list[str] = []
    if drop_id is not None:
        result.best_drop_options = [compare(ctx, player, drop_id)]
        result.comparison = result.best_drop_options[0]
    elif shape in FILL_SHAPES:
        # Open capacity: no drop comparison is calculated or requested.
        result.best_drop_options = []
        result.comparison = compare_no_drop(ctx, player)
    elif shape == "ADD_DROP":
        options = [compare(ctx, player, pid) for pid in swap_roster_ids(ctx)]
        options.sort(key=lambda row: (row.net_improvement is None, -(row.net_improvement or 0), row.player_id))
        chosen = _decision_pair(ctx, player, options)
        if chosen is not None:
            return chosen
        # Without a supported pair the add shows its best comparison that the explanation gate does not refute: a
        # positive index that fails in Yahoo fantasy points is not this add's best measured answer.
        fallback = (next((option for option in options if option.net_improvement is not None
                and option.net_improvement > 0 and explanation_supports(option)), None)
            or next((option for option in options if option.net_improvement is not None
                and (option.net_improvement <= 0 or explanation_supports(option))), None)
            or next(iter(options), None))
        result.best_drop_options = ([fallback, *[row for row in options if row is not fallback]][:3]
            if fallback is not None else [])
        result.comparison = fallback
        result.drop_alternatives = drop_alternatives(ctx, player, options, fallback)
        result.drop_choice = drop_choice_text(result, fallback, result.drop_alternatives)
    else:
        result.best_drop_options = []
        result.comparison = None
        blockers.append(_undetermined_capacity_reason(ctx))
    result.add_only_impact = (result.comparison if drop_id is None else compare_no_drop(ctx, player)) if shape in FILL_SHAPES else None
    if drop_id is not None and shape in FILL_SHAPES and ctx.roster_capacity is not None:
        result.reasons.append(f"Dropping is optional: {ctx.roster_capacity.additions_after_injury_moves} no-drop addition(s) are available.")
    result.net_improvement = result.comparison.net_improvement if result.comparison else None
    selected = ctx.players.get(result.comparison.player_id) if result.comparison and result.comparison.player_id is not None else None
    gate_notes: list[str] = []
    status_gaps: list[str] = []
    for key in ("settings", "roster"):
        if ctx.quality.get(key) is None or ctx.quality[key].state != "available":
            blockers.append(f"{key} evidence is missing or stale")
    compared = [result] + ([selected] if selected else [])
    for row in compared:
        if not identity_is_supported(row):
            blockers.append(f"{row.player_name}: Yahoo-to-NBA identity is unresolved; NBA-derived evidence is not decision-eligible")
        gap = status_gap(row, ctx.now)
        if gap is not None:
            status_gaps.append(f"{row.player_name} {gap}")
        for key in (("recent", "ros") if ctx.mode == "ros" else ("recent",)):
            if row.data_quality.get(key) is None or row.data_quality[key].state != "available":
                blockers.append(f"{row.player_name}: {key} evidence is missing, incomplete or stale")
    status_unverified = bool(status_gaps)
    if result.data_quality.get("availability") is None or result.data_quality["availability"].state != "available":
        blockers.append("fresh availability evidence is required")
    if not result.eligible or result.overall_score is None or not ctx.roster_ready or result.net_improvement is None or blockers:
        result.recommended_action = "INSUFFICIENT EVIDENCE"
        result.reasons.extend(blockers)
        if not blockers:
            gate_notes.append("Numeric impact is unavailable: eligibility, a supported overall score and a fresh roster are required.")
    elif result.net_improvement <= 0:
        if status_unverified:
            result.recommended_action = "INSUFFICIENT EVIDENCE"
            gate_notes.append(status_gate_note(status_gaps))
        else:
            result.recommended_action = "PASS"
    elif not explanation_supports(result.comparison):
        # A positive index whose explanation cannot be reconciled (or a near tie) is never a supported move or WATCH.
        result.recommended_action = "INSUFFICIENT EVIDENCE"
        gate_notes.append(result.comparison.explanation.blocker or EXPLANATION_GATE)
        if status_unverified:
            gate_notes.append(status_gate_note(status_gaps))
    elif not sufficient_sample(result, ctx.mode) or (selected and not sufficient_sample(selected, ctx.mode)):
        result.recommended_action = "WATCH" if result.current_season_games > 0 else "INSUFFICIENT EVIDENCE"
        gate_notes.append(sample_gate_note(ctx.mode, [text for text in (sample_gap(row, ctx.mode) for row in compared) if text]))
        if status_unverified:
            gate_notes.append(status_gate_note(status_gaps))
    elif status_unverified:
        result.recommended_action = "INSUFFICIENT EVIDENCE"
        gate_notes.append(status_gate_note(status_gaps))
    else:
        comparison = result.comparison
        gains = {key: max(0, getattr(comparison.component_deltas, key) or 0) * weight
            for key, weight in comparison.effective_weights.items()}
        short_term = ctx.mode != "ros" and (
            result.hold_type == "streamer" or
            gains.get("schedule", 0) + gains.get("opportunity", 0) > gains.get("player_value", 0) + gains.get("roster_fit", 0)
        )
        role_supported = all(
            row.opportunity.current_role is not None
            and row.opportunity.current_role.quality.state == "available"
            and row.opportunity.current_role.trend != "INSUFFICIENT EVIDENCE"
            and freshness(row.opportunity.current_role.quality.as_of, ctx.now, 7) == "available"
            for row in compared
        )
        opportunity_material = gains.get("opportunity", 0) > sum(
            value for key, value in gains.items() if key != "opportunity")
        if short_term:
            schedule_quality = result.data_quality.get("schedule")
            opportunity_quality = result.data_quality.get("opportunity")
            result.recommended_action = "STREAM" if (
                schedule_quality is not None and schedule_quality.state in {"available", "partial"}
                and freshness(schedule_quality.as_of, ctx.now, 7) == "available"
                and result.schedule.games_remaining is not None
                and opportunity_quality is not None and opportunity_quality.state == "available"
                and freshness(opportunity_quality.as_of, ctx.now, 7) == "available"
                and result.opportunity.minutes is not None
                and role_supported
            ) else "INSUFFICIENT EVIDENCE"
            if result.recommended_action == "INSUFFICIENT EVIDENCE":
                gate_notes.append("Schedule/opportunity-driven moves require fresh measured schedule and qualified role evidence for every compared player for STREAM.")
        elif opportunity_material and not role_supported:
            result.recommended_action = "INSUFFICIENT EVIDENCE"
            gate_notes.append("Opportunity materially drives this move; qualified fresh role evidence for every compared player is required.")
        else:
            result.recommended_action = "ADD"
    result.reasons.extend(gate_notes)
    result.evidence_blockers = list(dict.fromkeys(blockers + gate_notes))
    classify_action(ctx, result, drop_id)
    return result


def transaction_blockers(ctx: Context, add: Candidate, drop: Candidate) -> list[str]:
    blockers = []
    if not ctx.roster_ready:
        blockers.append("Manager roster is unavailable or stale")
    for key in ("settings", "roster"):
        if key not in ctx.quality or ctx.quality[key].state != "available":
            blockers.append(f"{key} evidence is missing or stale")
    if not add.eligible:
        blockers.append("Add availability or Yahoo status excludes recommendation")
    if add.data_quality.get("availability") is None or add.data_quality["availability"].state != "available":
        blockers.append("Fresh add availability is unverified")
    for row in (add, drop):
        if not identity_is_supported(row):
            blockers.append(f"{row.player_name}: Yahoo-to-NBA identity is unresolved")
        if not sufficient_sample(row, ctx.mode):
            blockers.append("Insufficient fresh current-season sample for add or drop")
        for key in (("recent", "ros") if ctx.mode == "ros" else ("recent",)):
            if key not in row.data_quality or row.data_quality[key].state != "available":
                blockers.append("Required production evidence is missing, incomplete or stale")
        if status_gap(row, ctx.now) is not None:
            blockers.append("Add or drop Yahoo status is unknown, unrecognized or stale")
    return sorted(set(blockers))


@dataclass(frozen=True)
class PairOutcome:
    """One ADD + DROP pair exactly as the global optimizer judges it. The board, replacements and impact reuse
    this judgment, so a supported pair can never disagree between surfaces."""
    pair: Candidate
    drop: Candidate
    blockers: list[str]
    supported: bool

    @property
    def net(self) -> float | None:
        return self.pair.comparison.net_improvement if self.pair.comparison is not None else None

    @property
    def strong(self) -> bool:
        return self.supported and self.pair.recommended_action in ACTIONABLE_DECISIONS and (self.net or 0) > 0


def _short_blocker(note: str) -> str:
    return note.split(". A supported move needs")[0].split(". Blank, unrecognized")[0]


def drop_alternatives(ctx: Context, add: Candidate, options: list[DropOption], chosen: DropOption | None) -> list:
    """Alternatives for "why this drop"; a higher-index drop that was not used names the gate that stopped it."""
    rows = alternatives(options, chosen)
    for row in rows:
        if row.margin is not None and row.margin < 0 and not row.note:
            outcome = evaluate_pair(ctx, ctx.players[add.player_id], row.player_id)
            if not outcome.strong:
                row.note = _short_blocker(next(iter(outcome.pair.evidence_blockers), "not supported"))
    return rows


def evaluate_pair(ctx: Context, add: Candidate, drop_id: int) -> PairOutcome:
    pair = enrich(ctx, add, drop_id)
    drop = ctx.players[drop_id]
    blockers = transaction_blockers(ctx, pair, drop)
    if pair.comparison is None or pair.comparison.net_improvement is None:
        blockers.append("Numeric swap impact is unavailable")
    elif pair.comparison.net_improvement > 0 and not explanation_supports(pair.comparison):
        blockers.append(gate_category(pair.comparison.explanation.blocker or EXPLANATION_GATE, ctx.mode))
    if pair.recommended_action == "INSUFFICIENT EVIDENCE":
        blockers.append("Phase-1 decision is INSUFFICIENT EVIDENCE")
    supported = not blockers and pair.recommended_action in {"ADD", "STREAM", "MUST ADD", "PASS"}
    return PairOutcome(pair=pair, drop=drop, blockers=blockers, supported=supported)


def pair_order(net: float | None, add_id: int, drop_id: int) -> tuple[float, int, int]:
    """The one ordering of ADD + DROP pairs: highest net first, then add and drop ID."""
    return (-(net or 0), add_id, drop_id)


def _decision_pair(ctx: Context, player: Candidate, options: list[DropOption]) -> Candidate | None:
    """The add's decision on a full roster: its best pair that clears every optimizer gate, scanning drops by net.

    Returns None when no positive pair is supported; the add then keeps its highest-net measured comparison. A
    larger net against an unsupported drop never replaces the supported pair (2026-11-14 Next 7 Days defect)."""
    first: PairOutcome | None = None
    for option in options:
        if option.player_id is None or option.net_improvement is None or option.net_improvement <= 0:
            break
        outcome = evaluate_pair(ctx, player, option.player_id)
        first = first or outcome
        if outcome.strong:
            outcome.pair.best_drop_options = [option, *[row for row in options if row.player_id != option.player_id]][:3]
            outcome.pair.drop_alternatives = drop_alternatives(ctx, player, options, option)
            outcome.pair.drop_choice = drop_choice_text(outcome.pair, option, outcome.pair.drop_alternatives)
            return outcome.pair
    if first is not None and first.pair.recommended_action in ACTIONABLE_DECISIONS:
        # Defensive: a pair the optimizer excludes is never presented as a strong action.
        pair = first.pair
        pair.recommended_action = "INSUFFICIENT EVIDENCE"
        pair.evidence_blockers = list(dict.fromkeys([*pair.evidence_blockers, *first.blockers]))
        pair.reasons.extend(first.blockers)
        classify_action(ctx, pair, first.drop.player_id)
        pair.best_drop_options = options[:3]
        return pair
    return None


def addition_pool(ctx: Context) -> list[Candidate]:
    return sorted((row for row in ctx.players.values()
        if row.availability in {"free_agent", "waivers", "unrostered", "unknown"}), key=lambda row: row.player_id)


def _fill_reasons(ctx: Context, row: Candidate, label: str, target: str | None) -> list[str]:
    value = row.ros if ctx.mode == "ros" else row.recent
    capacity = ctx.roster_capacity
    return list(dict.fromkeys([
        label,
        (f"Fills the uncovered {target} starting slot measured for your lineup." if target and target != "BN"
            else "Adds depth: every starting slot is already coverable by lineup-eligible players."),
        (f"{'Season Evidence' if ctx.mode == 'ros' else 'Recent'} Yahoo-rule fantasy PPG {value.value} from {value.games} "
            f"games; evidence {row.evidence_quality}. Historical, not a projection."),
        *([capacity.drop_requirement_reason] if capacity is not None else []),
        *row.evidence_blockers,
    ]))


def _non_fit_gain(row: Candidate) -> float:
    """Weighted net improvement excluding positional fit, which the plan re-measures each step."""
    comparison = row.comparison
    if comparison is None or comparison.net_improvement is None:
        return float("-inf")
    fit = (comparison.component_deltas.roster_fit or 0) * comparison.effective_weights.get("roster_fit", 0)
    return comparison.net_improvement - fit


def build_fill_plan(ctx: Context, enriched: list[Candidate]) -> tuple[list[FillRecommendation], list[str]]:
    """Sequential no-drop fill plan: each step re-measures uncovered starting slots so a second
    player is never recommended for an already covered need while another need stays uncovered."""
    capacity = ctx.roster_capacity
    moves = planned_moves(ctx)
    open_spots = (capacity.open_roster_spots or 0) if capacity is not None else 0
    supported = [row for row in enriched if row.recommended_action_type in FILL_SHAPES]
    lineup = fill_members(ctx)
    plan: list[FillRecommendation] = []
    unfilled: list[str] = []
    used: set[int] = set()
    for step in range(open_spots + len(moves)):
        open_slots = uncovered_slots(lineup, ctx.slots) if ctx.slots else []

        def gained(row: Candidate) -> int:
            return len(open_slots) - len(uncovered_slots([*lineup, row], ctx.slots)) if ctx.slots else 0

        available = [row for row in supported if row.player_id not in used]
        if open_slots:
            available = [row for row in available if gained(row) > 0]
            if not available:
                unfilled = sorted(set(open_slots), key=need_order)
                break
        if not available:
            break
        pick = min(available, key=lambda row: (
            -gained(row), -_non_fit_gain(row), -(row.overall_score or 0), row.player_id))
        target = (newly_covered_slot(open_slots, uncovered_slots([*lineup, pick], ctx.slots), pick) or "BN") if ctx.slots else None
        move = moves[step - open_spots] if step >= open_spots else None
        covers = f" to cover {target}" if target and target != "BN" else ""
        if move is None:
            action: ActionType = "ADD_ONLY"
            label = f"ADD ONLY: Add {pick.player_name}{covers}. You have an open roster spot. No player needs to be dropped."
        else:
            action = "MOVE_TO_IL_THEN_ADD"
            label = (f"MOVE {move.player_name} TO {move.to_slot}, THEN ADD {pick.player_name}{covers}. "
                f"{move.player_name} stays on your roster; this is not a drop.")
        plan.append(FillRecommendation(
            step=step + 1, action_type=action, label=label, decision=pick.recommended_action,
            add_player=pick, target_roster_position=target,
            fills_needs=[slot for slot in dict.fromkeys(open_slots) if slot_accepts(slot, pick)],
            suggested_injury_move=move, comparison=pick.comparison,
            reasons=_fill_reasons(ctx, pick, label, target) + ([
                "This step's before/after comparison measures this addition alone against the current roster; plan order "
                "re-measures uncovered starting slots after earlier steps, and comparisons are never summed.",
            ] if step else []),
            limitations=list(dict.fromkeys(BASE_LIMITATIONS + (capacity.limitations if capacity else []))),
        ))
        lineup = [*lineup, pick]
        used.add(pick.player_id)
    return plan, unfilled


def watch_additions(ctx: Context, enriched: list[Candidate]) -> list[FillRecommendation]:
    watch = [row for row in enriched if row.recommended_action_type == "WATCH"
        and row.net_improvement is not None and row.net_improvement > 0]
    watch.sort(key=lambda row: (not row.fills_needs, -(row.net_improvement or 0), row.player_id))
    return [FillRecommendation(
        step=index + 1, action_type="WATCH", label=row.action_label, decision=row.recommended_action,
        add_player=row, target_roster_position=row.target_roster_position, fills_needs=row.fills_needs,
        comparison=row.comparison, reasons=_fill_reasons(ctx, row, row.action_label, row.target_roster_position),
        limitations=list(BASE_LIMITATIONS),
    ) for index, row in enumerate(watch[:5])]


def analyze_transactions(ctx: Context) -> TransactionAnalysis:
    shape = transaction_shape(ctx)
    capacity = ctx.roster_capacity
    supported: list[SwapAnalysis] = []
    watch: list[SwapAnalysis] = []
    excluded_reasons: Counter[str] = Counter()
    evaluated = excluded = 0
    adds = addition_pool(ctx)
    if shape == "ADD_DROP":
        for add in adds:
            for drop_id in sorted(swap_roster_ids(ctx)):
                evaluated += 1
                drop = ctx.players[drop_id]
                if not add.eligible:
                    # An ineligible add always has no numeric impact and an INSUFFICIENT EVIDENCE decision,
                    # so its exclusion reasons are known without measuring the pair.
                    excluded += 1
                    excluded_reasons.update(set(transaction_blockers(ctx, add, drop))
                        | {"Numeric swap impact is unavailable", "Phase-1 decision is INSUFFICIENT EVIDENCE"})
                    continue
                outcome = evaluate_pair(ctx, add, drop_id)
                pair, blockers, comparison = outcome.pair, outcome.blockers, outcome.pair.comparison
                is_supported = outcome.supported
                if not is_supported:
                    excluded += 1
                    excluded_reasons.update(set(blockers) or {"Phase-1 evidence does not support a strong transaction"})
                if comparison is None:
                    continue
                if is_supported or (pair.recommended_action == "WATCH" and comparison.net_improvement is not None and comparison.net_improvement > 0):
                    swap = SwapAnalysis(add_player=pair, drop_player=drop, mode=ctx.mode,
                        decision=pair.recommended_action, comparison=comparison,
                        reasons=list(dict.fromkeys(pair.reasons + comparison.reasons + blockers)),
                        limitations=list(dict.fromkeys(BASE_LIMITATIONS + drop.limitations)))
                    (supported if is_supported else watch).append(swap)

    def order(swap: SwapAnalysis) -> tuple[float, int, int]:
        return pair_order(swap.comparison.net_improvement, swap.add_player.player_id, swap.drop_player.player_id)
    supported.sort(key=order)
    watch.sort(key=order)
    best = next((swap for swap in supported if swap.comparison.net_improvement > 0
        and swap.decision in ACTIONABLE_DECISIONS), None)
    # "Why this drop?" for every pair the page shows: the add's other measured drops (memoized comparisons).
    for swap in [*supported[:5], *watch[:5], *([best] if best is not None else [])]:
        options = sorted((compare(ctx, ctx.players[swap.add_player.player_id], pid) for pid in swap_roster_ids(ctx)),
            key=lambda row: (row.net_improvement is None, -(row.net_improvement or 0), row.player_id))
        swap.add_player.drop_alternatives = drop_alternatives(ctx, swap.add_player, options, swap.comparison)
        swap.add_player.drop_choice = drop_choice_text(swap.add_player, swap.comparison, swap.add_player.drop_alternatives)

    fills: list[FillRecommendation] = []
    fill_watch: list[FillRecommendation] = []
    unfilled: list[str] = []
    addition_reasons: Counter[str] = Counter()
    evaluated_additions = supported_additions = watch_count = 0
    if shape in FILL_SHAPES:
        enriched = [enrich(ctx, add) for add in adds]
        fills, unfilled = build_fill_plan(ctx, enriched)
        fill_watch = watch_additions(ctx, enriched)
        evaluated_additions = len(enriched)
        supported_additions = sum(row.recommended_action_type in FILL_SHAPES for row in enriched)
        watch_count = sum(row.recommended_action_type == "WATCH" and (row.net_improvement or 0) > 0 for row in enriched)
        for row in enriched:
            if row.recommended_action_type not in FILL_SHAPES:
                addition_reasons.update({gate_category(note, ctx.mode) for note in row.evidence_blockers}
                    or {"Evidence does not support a no-drop addition"})

    settings_quality = ctx.quality["settings"]
    rules = verify_league_contract(ctx.league) if settings_quality.state == "available" else []
    limitations = list(BASE_LIMITATIONS)
    best_fill = fills[0] if fills else None
    if shape == "UNDETERMINED":
        decision = "INSUFFICIENT EVIDENCE"
        action: ActionType = "INSUFFICIENT_EVIDENCE"
        label = ("INSUFFICIENT EVIDENCE: Roster capacity cannot be established from persisted Yahoo evidence, "
            "so no add, drop or IL move is recommended and no drop is assumed.")
        decision_reasons = (list(capacity.blockers) if capacity is not None and capacity.blockers
            else ["Roster capacity evidence is unavailable."])[:4]
        limitations.append("No add/drop pairs or no-drop additions are evaluated until roster capacity is established.")
    elif shape in FILL_SHAPES:
        decision = best_fill.decision if best_fill else "HOLD"
        action = best_fill.action_type if best_fill else "HOLD"
        spots = capacity.additions_after_injury_moves if capacity is not None else 0
        label = best_fill.label if best_fill else (
            "HOLD: No sufficiently supported move currently improves the roster. "
            f"{spots} roster spot(s) can be filled without a drop once an available player clears the evidence gates.")
        if best_fill:
            decision_reasons = best_fill.reasons[:4]
        else:
            decision_reasons = [f"No available player cleared all evidence gates for the {spots} no-drop roster spot(s)."]
            decision_reasons.extend(f"{reason} ({count} players)." for reason, count in
                sorted(addition_reasons.items(), key=lambda item: (-item[1], item[0]))[:2])
            if fill_watch:
                decision_reasons.append("Positive WATCH additions remain below the supported recommendation threshold.")
            decision_reasons = decision_reasons[:4]
        if unfilled:
            decision_reasons.append(
                f"No supported available player covers {', '.join(unfilled)}; review alternatives and WATCH options.")
        limitations.append("ADD + DROP pairs are not evaluated while no-drop capacity exists; Compare a specific drop remains an optional what-if.")
    else:
        decision = best.decision if best else "HOLD"
        action = "ADD_DROP" if best else "HOLD"
        label = best.add_player.action_label if best else "HOLD: No sufficiently supported move currently improves the roster."
        decision_reasons = (
            list(dict.fromkeys(best.reasons))[:4]
            if best else ["No add/drop pair cleared all current evidence gates."]
        )
        if best is None:
            decision_reasons.extend(
                f"{reason} ({count} pairs)." for reason, count in
                sorted(excluded_reasons.items(), key=lambda item: (-item[1], item[0]))[:2]
            )
            if watch:
                decision_reasons.append(
                    "Positive WATCH comparisons remain below the supported recommendation threshold."
                )
            decision_reasons = decision_reasons[:4]
        limitations += [
            "Hypothetical add/drop analysis only; no Yahoo transaction is executed.",
            "Excluded pairs are excluded from the supported pool; WATCH is a separate subset. Exclusion reason counts can overlap.",
            "Top supported and WATCH lists are limited to five pairs each; all pairs are evaluated.",
        ]
    return TransactionAnalysis(league_key=ctx.league.league_key, team_key=ctx.team_key,
        mode=ctx.mode, generated_at=ctx.now, model_version=MODEL_VERSION,
        decision=decision, decision_reasons=decision_reasons,
        best_transaction=best, top_supported_transactions=supported[:5],
        watch_transactions=watch[:5], evaluated_pair_count=evaluated,
        supported_pair_count=len(supported), watch_pair_count=len(watch),
        supported_move_count=sum(swap.comparison.net_improvement > 0 and swap.decision in ACTIONABLE_DECISIONS
            for swap in supported),
        excluded_pair_count=excluded, excluded_pair_reasons=dict(sorted(excluded_reasons.items())),
        data_quality=ctx.quality,
        acquisition_context=ctx.acquisition or AcquisitionContext(rules=rules, data_quality=settings_quality),
        limitations=limitations,
        recommended_action_type=action, action_label=label,
        roster_capacity=capacity, team_needs_analysis=ctx.team_needs,
        best_addition=best_fill, add_only_recommendations=fills, watch_additions=fill_watch,
        unfilled_needs=unfilled, evaluated_addition_count=evaluated_additions,
        supported_addition_count=supported_additions,
        watch_addition_count=watch_count,
        excluded_addition_count=evaluated_additions - supported_additions,
        excluded_addition_reasons=dict(sorted(addition_reasons.items())),
    )


async def get_transactions(session: AsyncSession, league_key: str, team_key: str, mode: Mode) -> TransactionAnalysis:
    with record_phase("load"):
        ctx = await load_context(session, league_key, team_key, mode)
    with record_phase("analyze"):
        analysis = await asyncio.to_thread(analyze_transactions, ctx)
    assert_transactions_recommendation_invariant(ctx, analysis)
    return analysis


def _clear_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10]) if value else None
    except ValueError:
        return None


def classify_availability(
    *,
    in_manager_roster: bool,
    in_other_roster: bool,
    ownership: object,
    manager_team_key: str,
    excluded_status: bool,
    observation_at: datetime | None,
    observation_fresh: bool,
    snapshots_expected: int,
    snapshots_current: int,
    snapshots_missing: int,
    oldest_snapshot: datetime | None,
) -> tuple[AvailabilityClass, str, AvailabilityEvidence]:
    """Classify one player's Yahoo availability from persisted evidence only.

    A supported add needs every league roster snapshot current, absence from all of them, explicit
    Yahoo FA/W state when a payload supplies it, and no O/OFS/NA status. Without explicit FA/W state the
    player is UNROSTERED: the FA-vs-waiver state must still be confirmed in Yahoo.
    Returns (classification, legacy availability, evidence).
    """
    ownership = ownership if isinstance(ownership, dict) else {}
    ownership_type = str(ownership.get("ownership_type") or "").strip().lower()
    owner = str(ownership.get("owner_team_key") or "").strip()
    explicit = "FA" if ownership_type == "freeagents" else "W" if ownership_type == "waivers" else None
    clear_date = _clear_date(ownership.get("waiver_date")) if explicit == "W" else None
    complete = snapshots_expected > 0 and snapshots_current == snapshots_expected
    snapshot_text = (f"{snapshots_current} of {snapshots_expected} league roster snapshots are current"
        + (f"; oldest saved {oldest_snapshot.astimezone(WAIVER_TIMEZONE).strftime('%Y-%m-%d %H:%M %Z')}"
            if oldest_snapshot else ""))
    common = dict(imported_at=oldest_snapshot if complete else observation_at, roster_snapshot_complete=complete,
        roster_snapshots_current=snapshots_current, roster_snapshots_expected=snapshots_expected,
        yahoo_ownership_state=explicit, waiver_clear_date=clear_date)
    base_legacy = ("free_agent" if explicit == "FA" else "waivers" if explicit == "W" else "unrostered") \
        if complete and observation_fresh else "unknown"

    def result(classification: AvailabilityClass, legacy: str, source: str, detail: str,
            blockers: list[str] | None = None, reason: str | None = None, **overrides):
        return classification, legacy, AvailabilityEvidence(
            classification=classification, label=AVAILABILITY_CLASS_LABELS[classification],
            actionable=classification in ACTIONABLE_AVAILABILITY, source=source, detail=detail,
            blockers=blockers or [], eligibility_reason=reason, **{**common, **overrides})

    if in_manager_roster or (ownership_type == "team" and owner and owner == manager_team_key):
        return result("ROSTERED_BY_MANAGER", "rostered", "Yahoo rosters", "On your saved Yahoo roster.",
            ["Already on your roster."], imported_at=observation_at)
    if in_other_roster or ownership_type == "team":
        return result("ROSTERED_BY_OTHER_TEAM", "rostered", "Yahoo rosters",
            "On another team's saved Yahoo roster; never a waiver target.",
            ["Rostered by another team in saved Yahoo evidence."], imported_at=observation_at)
    if excluded_status:
        return result("EXCLUDED_STATUS", base_legacy, "Yahoo player status",
            "Yahoo status O/OFS/NA excludes this player from recommendations.",
            ["Yahoo status is O, OFS or NA."])
    if observation_at is None or snapshots_missing or snapshots_expected == 0:
        return result("AVAILABILITY_UNVERIFIED", "unknown", "Yahoo rosters / player pool",
            ("No saved Yahoo player observation exists for this player." if observation_at is None
                else f"{snapshots_missing} league team(s) have no saved Yahoo roster, so absence from saved rosters proves nothing."),
            [f"Availability unverified: {snapshot_text}."])
    if not complete or not observation_fresh:
        return result("SOURCE_STALE", "unknown", "Yahoo rosters / player pool",
            (f"Not on any saved league roster, but {snapshot_text} (rosters must be under 24 hours old and newer "
                "than the latest league/team/settings import)" + ("" if observation_fresh
                else "; the Yahoo player-pool observation is also older than 24 hours")
                + ". The player may have been added since; check Yahoo."),
            ["Saved Yahoo rosters or player-pool evidence are stale; refresh waiver data."])
    if explicit == "FA":
        return result("CONFIRMED_FA", "free_agent", "Yahoo player ownership",
            f"Yahoo lists this player as a free agent and {snapshot_text}.",
            reason=f"Explicit Yahoo free-agent state; absent from all {snapshots_expected} current league rosters; not O/OFS/NA.")
    if explicit == "W":
        clears = f" until {clear_date.isoformat()}" if clear_date else ""
        return result("CONFIRMED_WAIVER", "waivers", "Yahoo player ownership",
            f"Yahoo lists this player on waivers{clears}; a claim is processed by waiver priority. {snapshot_text}.",
            reason=f"Explicit Yahoo waiver state{clears}; absent from all {snapshots_expected} current league rosters; not O/OFS/NA.")
    return result("UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT", "unrostered", "Yahoo rosters",
        (f"Absent from all {snapshots_expected} current league roster snapshots. Yahoo's player payload does not state "
            "free-agent vs waiver status, so confirm the FA/waiver state in Yahoo."),
        reason=f"Absent from all {snapshots_expected} current league rosters; not O/OFS/NA.")


async def load_context(session: AsyncSession, league_key: str, team_key: str, mode: Mode) -> Context:
    now = datetime.now(timezone.utc)
    league = await session.get(League, league_key)
    if league is None:
        raise HTTPException(404, "Persisted Yahoo league was not found")
    verify_league_contract(league)
    baselines = await list_roster_baselines(session, league_key)
    manager = next(((team, roster) for team, roster in baselines if team.team_key == team_key), None)
    if manager is None:
        raise HTTPException(404, "Team does not belong to the selected Yahoo league")
    team, roster = manager
    settings = league.settings
    settings_state = freshness(settings.imported_at, now) if settings else "missing"
    fields = scoring_fields(settings.scoring_settings) if settings_state == "available" else None
    # Decision support measures players with the persisted (contract-verified) formula even when the
    # settings import is stale; strict scoring above still requires fresh settings.
    measure_fields = scoring_fields(settings.scoring_settings) if settings else None
    roster_state = roster_data_status(team, roster)
    if roster_state == "available":
        roster_state = freshness(roster.imported_at, now)
    ready = roster_state == "available"
    snapshot_states = [
        "missing" if row is None else "current" if roster_data_status(owner, row) == "available"
        and freshness(row.imported_at, now) == "available" else "stale"
        for owner, row in baselines
    ]
    snapshots_current = snapshot_states.count("current")
    snapshots_missing = snapshot_states.count("missing")
    oldest_snapshot = min((row.imported_at for _, row in baselines if row), default=None)
    all_rosters_ready = bool(baselines) and snapshots_current == len(baselines)
    rostered_ids = {
        entry.player_identity_id for _, row in baselines if row for entry in row.roster_entries
    }
    manager_ids = [entry.player_identity_id for entry in roster.roster_entries] if roster else []
    manager_id_set = set(manager_ids)
    observations = list((await session.execute(
        select(LeaguePlayer, PlayerIdentity).join(PlayerIdentity, LeaguePlayer.player_identity_id == PlayerIdentity.id)
        .where(LeaguePlayer.league_key == league_key).order_by(PlayerIdentity.id)
    )).all())
    identities = {
        identity.id: (identity, observation.source_payload, observation.imported_at)
        for observation, identity in observations
    }
    yahoo_pool_ids = set(identities)
    if roster:
        for entry in roster.roster_entries:
            observed = identities.get(entry.player_identity_id)
            if observed is None:
                identities[entry.player_identity_id] = (
                    entry.identity, entry.source_payload, entry.imported_at,
                )
                continue
            identity, player_pool_payload, player_pool_imported_at = observed
            roster_payload = {**player_pool_payload, **entry.source_payload}
            for key in ("status", "status_full"):
                if key in player_pool_payload:
                    roster_payload[key] = player_pool_payload[key]
            identities[entry.player_identity_id] = (
                identity, roster_payload, player_pool_imported_at,
            )
    nba_ids = {identity.nba_player_id for identity, _, _ in identities.values() if identity.nba_player_id}
    today = now.astimezone(WAIVER_TIMEZONE).date()
    season_year = league.season or today.year
    season = f"{season_year}-{str(season_year + 1)[-2:]}"
    window_end = window_end_date(today, season_year, mode)
    stats_rows = list((await session.scalars(
        select(NbaPlayerSeasonStats).where(NbaPlayerSeasonStats.nba_player_id.in_(nba_ids),
            NbaPlayerSeasonStats.season_type == "Regular Season", NbaPlayerSeasonStats.games_played > 0,
            NbaPlayerSeasonStats.season <= season)
    )).all())
    stats_by_id: dict[str, NbaPlayerSeasonStats] = {}
    prior_by_id: dict[str, NbaPlayerSeasonStats] = {}
    for row in sorted(stats_rows, key=lambda row: row.season):
        stats_by_id[row.nba_player_id] = row
        if row.season < season:
            prior_by_id[row.nba_player_id] = row
    # One query loads the last 30 days of regular-season logs; Last 7 / 14 / 30 Days form windows and the 14-day
    # production and role evidence are in-memory subsets of it.
    logs = list((await session.scalars(select(PlayerGameLog).where(
        PlayerGameLog.nba_player_id.in_(nba_ids), PlayerGameLog.season == season,
        PlayerGameLog.season_type == "Regular Season",
        PlayerGameLog.game_date >= today - timedelta(days=FORM_LOOKBACK_DAYS), PlayerGameLog.game_date <= today,
    ).order_by(PlayerGameLog.game_date, PlayerGameLog.game_id))).all())
    logs_by_id: dict[str, list[PlayerGameLog]] = defaultdict(list)
    for log in logs:
        logs_by_id[log.nba_player_id].append(log)
    # Season-wide persisted log counts and the league log import's freshness: they tell a window with no games
    # ("no games played") apart from a stale import or a player whose season stats count more games than logs.
    log_counts = dict((await session.execute(select(PlayerGameLog.nba_player_id, func.count()).where(
        PlayerGameLog.nba_player_id.in_(nba_ids), PlayerGameLog.season == season,
        PlayerGameLog.season_type == "Regular Season").group_by(PlayerGameLog.nba_player_id))).all())
    log_imported_at, latest_log_game = (await session.execute(
        select(func.max(PlayerGameLog.imported_at), func.max(PlayerGameLog.game_date)).where(
            PlayerGameLog.season == season, PlayerGameLog.season_type == "Regular Season"))).one()
    log_state = freshness(log_imported_at, now, 7)
    if latest_log_game is not None and latest_log_game < today - timedelta(days=7):
        log_state = "stale"
    recent_start = today - timedelta(days=RECENT_LOOKBACK_DAYS)
    teams = list((await session.scalars(select(NbaTeam))).all())
    abbreviations = {row.nba_team_id: row.abbreviation for row in teams}
    nba_players = list((await session.scalars(select(NbaPlayer))).all())
    nba_players_by_id = {row.nba_player_id: row for row in nba_players}
    nba_players_by_name: dict[str, list[NbaPlayer]] = defaultdict(list)
    for row in nba_players:
        if key := _name_key(row.player_name):
            nba_players_by_name[key].append(row)
    # Only the columns the schedule resolver needs, and only rows near the selected window; the
    # season-wide row count and oldest import per player come from one aggregate query. Loading
    # every season row as an ORM object with its JSON payload dominated read latency.
    schedule_end = max(window_end, today + timedelta(days=13))
    status_text = func.lower(func.coalesce(PlayerSchedule.game_status, ""))
    schedulable = and_(~status_text.contains("postpon"), ~status_text.contains("cancel"), ~status_text.contains("final"))
    schedule_rows = (await session.execute(select(
        PlayerSchedule.nba_player_id, PlayerSchedule.game_date,
        PlayerSchedule.opponent_team_id, PlayerSchedule.game_status,
    ).where(
        PlayerSchedule.nba_player_id.in_(nba_ids), PlayerSchedule.season == season,
        PlayerSchedule.game_date >= today, PlayerSchedule.game_date <= schedule_end, schedulable,
    ).order_by(PlayerSchedule.game_date, PlayerSchedule.game_id))).all()
    schedules_by_id: dict[str, list[Any]] = defaultdict(list)
    for row in schedule_rows:
        schedules_by_id[row.nba_player_id].append(row)
    season_end = season_end_date(today, season_year)
    schedule_summary = {
        row.nba_player_id: (row.row_count, row.oldest_import, row.newest_import, row.remaining)
        for row in (await session.execute(select(
            PlayerSchedule.nba_player_id, func.count().label("row_count"),
            func.min(PlayerSchedule.imported_at).label("oldest_import"),
            func.max(PlayerSchedule.imported_at).label("newest_import"),
            func.count().filter(and_(PlayerSchedule.game_date >= today, PlayerSchedule.game_date <= season_end,
                schedulable)).label("remaining"),
        ).where(PlayerSchedule.nba_player_id.in_(nba_ids), PlayerSchedule.season == season)
        .group_by(PlayerSchedule.nba_player_id))).all()
    }
    games = list((await session.scalars(select(NbaGame).where(
        NbaGame.season == season, NbaGame.game_date >= today, NbaGame.game_date <= window_end,
    ).order_by(NbaGame.game_date, NbaGame.game_id))).all())
    games = [row for row in games if not any(word in (row.game_status or "").lower() for word in ("postpon", "cancel", "final"))]
    daily_games = Counter(row.game_date for row in games)
    slot_config, slot_problems = slot_configuration(settings.roster_positions if settings else [])
    positions_valid = settings_state == "available" and bool(slot_config) and not slot_problems
    slots = starting_slot_list(slot_config) if positions_valid else []
    needs_slots = starting_slot_list(slot_config) if slot_config and not slot_problems else []
    capacity = sum(slot.count for slot in slot_config if slot.kind in {"starting", "bench"})
    quality = {
        "league": evidence(freshness(league.imported_at, now), "Yahoo league", league.imported_at, f"Imported league season: {league.season}. Missing season uses the current Pacific year only as a historical-data cutoff."),
        "roster": evidence("missing" if roster_state == "not_imported" else roster_state, "Yahoo rosters", roster.imported_at if roster else None, "Manager roster must be imported and refreshed within 24 hours; later league/team/settings imports invalidate older snapshots."),
        "settings": evidence(settings_state, "Yahoo settings", settings.imported_at if settings else None, "Scoring modifiers and roster slots must have been imported within 24 hours."),
        "availability": evidence("available" if all_rosters_ready else "partial", "Yahoo rosters", min((row.imported_at for _, row in baselines if row), default=None), "Absence means available only when every league team has a fresh imported roster."),
        "category_scoring": evidence("unsupported", "Waiver model", None, "Category waiver scoring is not implemented; existing category baselines remain available in Championship HQ."),
        "acquisition_value": evidence("missing", "Yahoo rolling waivers", None, "Current rolling priority and transaction evidence are unverified; excluded from all scores."),
    }
    players: dict[int, Candidate] = {}
    mapping_worklist: list[MappingWorklistItem] = []
    for pid, (identity, payload, imported_at) in identities.items():
        position = _positions(payload) or identity.position
        yahoo_team = str(payload.get("editorial_team_abbr") or identity.team or "").strip().upper() or None
        observation_fresh = imported_at is not None and freshness(imported_at, now) == "available"
        nba_player = nba_players_by_id.get(identity.nba_player_id) if identity.nba_player_id else None
        mapping_state, mapping_reason, potential_matches = identity_mapping(
            identity, nba_player, nba_players_by_name, abbreviations, yahoo_team,
        )
        yahoo = interpret_yahoo_status(
            payload, identity_yahoo_player_id=identity.yahoo_player_id, identity_status=identity.status,
            player_pool_observation=pid in yahoo_pool_ids, observation_fresh=observation_fresh,
            identity_resolved=mapping_state in RESOLVED_IDENTITY_STATES,
            mapping_conflict=mapping_state == "TEAM_CHANGE_SUPPORTED", rosters_complete=all_rosters_ready,
        )
        raw_status, status = yahoo.raw_status, yahoo.status
        availability_class_value, availability, availability_evidence = classify_availability(
            in_manager_roster=pid in manager_id_set, in_other_roster=pid in rostered_ids and pid not in manager_id_set,
            ownership=payload.get("ownership"), manager_team_key=team_key,
            excluded_status=recommendation_eligibility(status) == "excluded",
            observation_at=imported_at, observation_fresh=observation_fresh,
            snapshots_expected=len(baselines), snapshots_current=snapshots_current,
            snapshots_missing=snapshots_missing, oldest_snapshot=oldest_snapshot,
        )
        availability_detail = availability_evidence.detail
        availability_as_of = oldest_snapshot if availability in {"free_agent", "waivers", "unrostered"} else imported_at
        form_logs = logs_by_id.get(identity.nba_player_id, [])
        recent_logs = [row for row in form_logs if row.game_date >= recent_start]
        recent_stats = log_average(recent_logs)
        historical = stats_by_id.get(identity.nba_player_id)
        historical_stats = numeric_stats(historical.base_stats) if historical else {}
        recent = ValueEvidence(value=production(recent_stats, fields), games=len(recent_logs), season=season,
            per_game_stats=recent_stats, label="Last 14 calendar days of persisted regular-season NBA games; points per game under Yahoo rules",
            sample_label=sample_label(len(recent_logs)))
        ros = ValueEvidence(value=production(historical_stats, fields), games=historical.games_played if historical else 0,
            season=historical.season if historical else None, per_game_stats=historical_stats,
            label="Season Evidence: persisted regular-season historical fantasy points per game; not a projection",
            sample_label=sample_label(historical.games_played if historical else 0))
        for value_evidence in (recent, ros):
            value_evidence.scoring_weights = fields or {}
            if value_evidence.value is not None and fields:
                value_evidence.scoring_contributions = {
                    field: value_evidence.per_game_stats[field] * weight
                    for field, weight in fields.items() if weight != 0
                }
        current_games = historical.games_played if historical and historical.season == season else len(recent_logs)
        opportunity = current_role(recent_logs, historical, season, now, today)
        role = opportunity.current_role
        nba_team = (
            (abbreviations.get(nba_player.team_id) if nba_player and nba_player.team_id else None)
            or (nba_player.team_abbreviation if nba_player else None)
        )
        if mapping_state not in {"EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM", "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED"}:
            mapping_worklist.append(MappingWorklistItem(
                internal_id=pid,
                yahoo_player_id=identity.yahoo_player_id,
                yahoo_name=identity.player_name,
                yahoo_team=yahoo_team,
                normalized_name=_name_key(identity.player_name),
                potential_nba_matches=potential_matches,
                conflict_reason=mapping_reason,
                resolution_state=mapping_state,
            ))
        player_schedule = schedules_by_id.get(identity.nba_player_id, []) if identity.nba_player_id else []
        schedule_rows_total, schedule_oldest_import, _, remaining_games = schedule_summary.get(
            identity.nba_player_id, (0, None, None, 0)) if identity.nba_player_id else (0, None, None, 0)
        schedule = resolve_schedule(
            player_schedule, today, window_end, now, daily_games, abbreviations,
            nba_mapped=bool(identity.nba_player_id and nba_player),
            team_mapped=bool(nba_player and nba_player.team_id and nba_player.team_id in abbreviations),
            source_row_count=schedule_rows_total, source_imported_at=schedule_oldest_import,
            rest_of_season_rows=remaining_games,
        )
        schedule_as_of = schedule.imported_at
        mapping_diagnostic = identity_chain_diagnostic(
            yahoo_id=identity.yahoo_player_id,
            nba_id=identity.nba_player_id,
            nba_player_present=nba_player is not None,
            team_mapped=bool(nba_player and nba_player.team_id and nba_player.team_id in abbreviations),
            has_game_logs=bool(identity.nba_player_id and recent_logs),
            has_season_stats=bool(identity.nba_player_id and stats_by_id.get(identity.nba_player_id)),
            has_schedule_rows=schedule_rows_total > 0,
            schedule_stale=schedule.freshness == "stale",
        )
        status_diagnostic = (
            "MISSING_PLAYER_OBSERVATION" if imported_at is None else
            "STALE_PLAYER_POOL_IMPORT" if freshness(imported_at, now) == "stale" else
            "STATUS_FIELD_MISSING" if yahoo.field_state == "STATUS_FIELD_MISSING" else
            "YAHOO_SUPPLIED_BLANK" if status is None else
            "UNRECOGNIZED_STATUS" if not status_is_supported(status) else
            "STATUS_PRESENT"
        )
        recent_as_of = min((row.imported_at for row in recent_logs), default=None)
        recent_state = freshness(recent_as_of, now, 7)
        if recent_logs and max(row.game_date for row in recent_logs) < today - timedelta(days=7):
            recent_state = "stale"
        recent_quality_state = (
            "unsupported" if fields is None
            else "stale" if recent_state == "stale"
            else "available" if recent.value is not None
            else "missing"
        )
        season_freshness = freshness(historical.imported_at, now, 7) if historical else "missing"
        season_quality_state = (
            "unsupported" if fields is None
            else "stale" if season_freshness == "stale"
            else "available" if ros.value is not None
            else "missing"
        )
        value = ros if mode == "ros" else recent
        eligible = availability_class_value in ACTIONABLE_AVAILABILITY
        quality_fields = {
            "identity": evidence("available" if mapping_state in {"EXACT_ID", "EXACT_NAME_TEAM", "NORMALIZED_NAME_TEAM", "KNOWN_ALIAS_TEAM", "TEAM_CHANGE_SUPPORTED"} else "partial", "Yahoo/NBA identity mapping", imported_at, mapping_reason),
            "status": Evidence(state="available" if yahoo.decision_state == "NO_CURRENT_YAHOO_DESIGNATION"
                    else "stale" if status_diagnostic == "STALE_PLAYER_POOL_IMPORT" else "unknown" if not status_is_supported(status) else "partial" if status in {"Q", "P"} else "available",
                source="Yahoo player import", as_of=imported_at, sample_count=1 if imported_at else 0,
                detail=(
                    yahoo.detail
                    if status_diagnostic == "STATUS_FIELD_MISSING"
                    else "Yahoo supplied a blank status; blank is unknown, not healthy."
                    if status_diagnostic == "YAHOO_SUPPLIED_BLANK"
                    else "Status came from a stale player-pool import."
                    if status_diagnostic == "STALE_PLAYER_POOL_IMPORT"
                    else yahoo_status_reason(status)
                )),
            "availability": evidence("unknown" if availability == "unknown" else freshness(availability_as_of, now), "Yahoo ownership / rosters", availability_as_of, availability_detail),
            "recent": evidence(recent_quality_state, "NBA player_game_logs", recent_as_of,
                production_detail(recent_stats, fields, "Recent", len(recent_logs))),
            "ros": evidence(season_quality_state, "NBA season statistics", historical.imported_at if historical else None,
                production_detail(historical_stats, fields, "Season Evidence", historical.games_played if historical else 0)),
            "opportunity": Evidence(state=role.quality.state if opportunity.score is not None else "stale" if role.quality.state == "stale" else "unavailable",
                source="Persisted NBA role evidence", as_of=role.quality.as_of, sample_count=role.quality.sample_count,
                detail="Score requires qualified role windows: minutes level counted once, optional supported usage delta and explicit season start rate. No separate minutes-delta score."),
            "role": role.quality,
            "minutes": role.minutes.quality,
            "usage": role.usage.quality,
            "starts": role.starts.quality,
            "schedule": Evidence(state="stale" if schedule.coverage == "STALE" else "partial" if schedule.games_remaining is not None else "unavailable",
                source="NBA player schedule", as_of=schedule_as_of, sample_count=schedule.games_remaining or 0,
                detail=(
                    f"{schedule.diagnostic_reason}: {schedule.source_row_count} persisted player schedule rows; requested-window zero is not asserted because source completeness is unverified."
                    if schedule.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE"
                    else "No completeness manifest: coverage PARTIAL with rows, UNKNOWN without rows, never COMPLETE. Off-day means at most five persisted NBA games that date. Opponents are identities, not difficulty estimates."
                )),
            "roster_fit": quality["roster"],
            "acquisition_value": quality["acquisition_value"],
        }
        ranking = RankingEvidence(label="Historical Season Evidence per-game value, not a projection" if mode == "ros" else "Recent per-game value; no supported independent prior-season history")
        if quality_fields["ros" if mode == "ros" else "recent"].state != "available":
            value_score = None
        else:
            value_score = value.value
            if mode != "ros":
                ranking.recent_weight = 1.0
                prior = prior_by_id.get(identity.nba_player_id)
                prior_value = production(numeric_stats(prior.base_stats), fields) if prior else None
                if prior is not None and prior_value is not None and recent.value is not None and freshness(prior.imported_at, now, 7) == "available":
                    # Ten historical-equivalent games shrink small samples without forecasting.
                    weight = recent.games / (recent.games + 10)
                    value_score = weight * recent.value + (1 - weight) * prior_value
                    ranking = RankingEvidence(recent_weight=weight, historical_value=prior_value,
                        historical_games=prior.games_played, historical_season=prior.season,
                        label="Descriptive blend: recent PPG weighted n/(n+10), independent prior-season PPG weighted 10/(n+10); not a projection or calibrated confidence")
        ranking.value = value_score
        current_row = historical if historical is not None and historical.season == season else None
        prior_row = prior_by_id.get(identity.nba_player_id) if identity.nba_player_id else None
        measured = measured_production(
            mode=mode, season=season,
            recent_value=production(recent_stats, measure_fields), recent_games=len(recent_logs),
            recent_as_of=recent_as_of, recent_latest_game=max((row.game_date for row in recent_logs), default=None),
            current_value=production(numeric_stats(current_row.base_stats), measure_fields) if current_row else None,
            current_games=current_row.games_played if current_row else 0,
            current_as_of=current_row.imported_at if current_row else None,
            prior_value=production(numeric_stats(prior_row.base_stats), measure_fields) if prior_row else None,
            prior_games=prior_row.games_played if prior_row else 0,
            prior_season=prior_row.season if prior_row else None,
            scoring_available=measure_fields is not None, now=now, today=today,
        )
        players[pid] = Candidate(
            player_id=pid, yahoo_player_id=identity.yahoo_player_id, player_name=identity.player_name,
            position=position, yahoo_team=yahoo_team, nba_team=nba_team,
            raw_yahoo_status=raw_status, yahoo_status=status,
            status_field_state=yahoo.field_state, decision_status_state=yahoo.decision_state,
            status_reason=yahoo.reason, status_label=yahoo.label, status_detail=yahoo.detail,
            identity_mapping_state=mapping_state, identity_mapping_reason=mapping_reason,
            mapping_diagnostic=mapping_diagnostic, status_diagnostic=status_diagnostic,
            availability=availability, eligible=eligible,
            availability_classification=availability_class_value, availability_evidence=availability_evidence,
            recent=recent, ros=ros, opportunity=opportunity, schedule=schedule,
            ranking_value=ranking,
            components=Components(player_value=value_score, opportunity=opportunity.score),
            recommended_action="INSUFFICIENT EVIDENCE", hold_type="undetermined",
            current_season_games=current_games, evidence_quality=sample_label(current_games),
            reasons=[f"Current Yahoo status: {yahoo.label}. {yahoo.detail}"
                if yahoo.decision_state == "NO_CURRENT_YAHOO_DESIGNATION" else yahoo_status_reason(status),
                availability_detail],
            limitations=list(BASE_LIMITATIONS), data_quality=quality_fields, measured=measured,
        )
        players[pid].status_gate_supported = status_gap(players[pid], now) is None
        logged = log_counts.get(identity.nba_player_id, 0) if identity.nba_player_id else 0
        players[pid].form = recent_form(form_logs, current_row, prior_row, fields, now, today,
            recent_quality=quality_fields["recent"], season_quality=quality_fields["ros"],
            starts=opportunity.current_role.starts if opportunity.current_role else None,
            season_usage=opportunity.current_role.season_usage if opportunity.current_role else None,
            mapped=bool(identity.nba_player_id and nba_player), logs_current=log_state == "available",
            logs_complete=current_row is None or current_row.games_played <= logged)
        players[pid].sample = assess_sample(players[pid], mode)
    value_distribution = sorted(row.components.player_value for row in players.values() if row.components.player_value is not None)
    schedule_distribution = sorted(row.schedule.games_remaining for row in players.values() if row.schedule.games_remaining is not None and row.data_quality["schedule"].state != "stale")
    weights = validated_weights(get_settings().waiver_weights)
    entries = []
    for entry in roster.roster_entries if roster else []:
        row = players[entry.player_identity_id]
        payload = identities[entry.player_identity_id][1]
        note = payload.get("injury_note")
        entries.append(RosterEntryEvidence(
            player_id=row.player_id, player_name=row.player_name, positions=row.position,
            roster_slot=entry.roster_position, eligible_positions=eligible_positions_from_payload(payload),
            yahoo_status=row.yahoo_status, status_state=row.data_quality["status"].state,
            injury_note=str(note).strip() or None if note is not None else None,
            coverage_date=coverage_date_from_payload(payload),
            status_label=row.status_label, decision_status_state=row.decision_status_state,
        ))
    roster_capacity = analyze_roster_capacity(
        roster_positions=settings.roster_positions if settings else None,
        settings_state=settings_state, roster_state=quality["roster"].state,
        roster_as_of=roster.imported_at if roster else None,
        status_as_of=min((identities[pid][2] for pid in manager_ids if identities[pid][2] is not None), default=None),
        entries=entries, today=today,
    )
    ctx = Context(league, team_key, mode, now, players, manager_ids, slots,
        capacity if positions_valid else None, ready, weights, quality, mapping_worklist,
        pool_ids=yahoo_pool_ids, roster_capacity=roster_capacity, needs_slots=needs_slots)
    # Fit counts only players able to fill a lineup slot: non-injury slots and no O/OFS/NA status.
    fit_roster = [players[pid] for pid in swap_roster_ids(ctx) if lineup_eligible(players[pid])]
    historical_distribution = sorted(row.ros.value for row in players.values()
        if row.ros.value is not None and row.data_quality["ros"].state == "available")
    for player in players.values():
        player.components.player_value = percentile_sorted(player.components.player_value, value_distribution)
        player.components.schedule = percentile_sorted(player.schedule.games_remaining, schedule_distribution) if player.data_quality["schedule"].state != "stale" else None
        player.components.roster_fit = roster_fit(player, fit_roster, slots) if ready else None
        player.overall_score, player.effective_weights = aggregate(player.components, weights)
        player.data_quality["overall_score"] = evidence("partial" if player.overall_score is not None else "missing", "Waiver model", now, "Missing components are omitted and measured weights renormalized; a supported player value and roster fit are mandatory.")
        player.data_quality["roster_fit"] = evidence("available" if player.components.roster_fit is not None else "missing", "Yahoo positions / manager roster", roster.imported_at if roster else None, "Positional slot coverage only; replacement value is measured by the before/after swap model. Category fit is unavailable.")
        player.reasons.append(f"Starting-slot coverage with player: {player.components.roster_fit}/100; eligibility coverage is not player quality.")
        selected_value = player.ros if mode == "ros" else player.recent
        player.reasons.append(f"{selected_value.sample_label}: {selected_value.games} games. No predictive superiority is established.")
        player.reasons.append(player.ranking_value.label)
        player.reasons.append(
            f"{'Season Evidence' if mode == 'ros' else 'Recent'} Yahoo-rule value: {selected_value.value} fantasy points/game from {selected_value.games} persisted games, season {selected_value.season}; not a projection."
            if selected_value.value is not None else "Player value unavailable: supported Yahoo points modifiers and complete persisted production are required."
        )
        player.reasons.append(
            f"Persisted schedule: {player.schedule.games_remaining} games, {player.schedule.off_day_games} off-day games; coverage is partial."
            if player.schedule.games_remaining is not None else "Schedule is unknown; no zero-game assumption is made."
        )
        if player.opportunity.minutes is not None:
            player.reasons.append(f"Measured recent minutes/game: {player.opportunity.minutes:.1f}; current role: {player.opportunity.role.lower()}.")
        player.reasons.extend([
            f"Current role evidence: {player.opportunity.role}. {role_detail}"
            for role_detail in [
                player.opportunity.current_role.minutes.quality.detail,
                player.opportunity.current_role.usage.quality.detail,
                player.opportunity.current_role.starts.quality.detail,
            ]
        ])
        if player.opportunity.minutes_trend is not None:
            player.reasons.append(f"Minutes changed by {player.opportunity.minutes_trend:+.2f} over the measured three-game windows.")
        if player.opportunity.usage_trend is not None:
            player.reasons.append(f"Usage changed by {player.opportunity.usage_trend * 100:+.2f} percentage points over the measured windows.")
        historical_percentile = percentile_sorted(player.ros.value, historical_distribution)
        if sufficient_sample(player, mode) and player.data_quality["ros"].state == "available" and historical_percentile is not None and historical_percentile >= 60 and player.ros.games >= 20 and player.components.opportunity is not None and player.opportunity.minutes is not None and player.opportunity.minutes >= 24:
            player.hold_type = "longer_term_hold"
        elif sufficient_sample(player, mode) and mode != "ros" and player.components.schedule is not None and player.components.schedule >= 60 and player.data_quality["schedule"].state in {"available", "partial"} and player.data_quality["opportunity"].state == "available" and player.components.opportunity is not None and player.components.player_value is not None and player.opportunity.minutes_trend is not None and player.opportunity.minutes_trend > 0:
            player.hold_type = "streamer"
        player.reasons.append(f"Hold classification: {player.hold_type}; a descriptive evidence label, not a future role prediction.")
    measured_roster = (fill_members(ctx) if roster_capacity.transaction_shape in FILL_SHAPES
        else [players[pid] for pid in swap_roster_ids(ctx)])
    comparable = measured_roster + [row for row in players.values()
        if row.eligible and row.components.player_value is not None and row.components.roster_fit is not None]
    ctx.comparison_keys = [key for key in COMPONENTS if weights[key] > 0
        and comparable and all(getattr(row.components, key) is not None for row in comparable)]
    ctx.team_needs = analyze_team_needs(
        capacity=roster_capacity, players=players, roster_ids=manager_ids, starting_slots=needs_slots,
        mode=mode, window_start=today, window_end=window_end,
        roster_state=quality["roster"].state, settings_state=settings_state,
    )
    pool_imported_at = max((observation.imported_at for observation, _ in observations), default=None)
    stats_imported_at = max((row.imported_at for row in stats_rows), default=None)
    schedule_imported_at = max((summary[2] for summary in schedule_summary.values()), default=None)
    saved_slots = len(manager_ids) - len(roster_capacity.unassigned_player_ids)
    ctx.evidence_freshness = [
        FreshnessItem(source="Yahoo league settings", state=quality["settings"].state,
            as_of=settings.imported_at if settings else None,
            detail="Roster positions and scoring rules; fresh for 24 hours."),
        FreshnessItem(source="Your saved Yahoo roster", state=quality["roster"].state,
            as_of=roster.imported_at if roster else None,
            detail=f"Yahoo slot assignments saved for {saved_slots} of {len(manager_ids)} players; fresh for 24 hours."),
        FreshnessItem(source="League rosters (availability)", state=quality["availability"].state,
            as_of=quality["availability"].as_of,
            detail=(f"{snapshots_current} of {len(baselines)} league roster snapshots are current; availability is "
                "confirmed only when every league roster is under 24 hours old.")),
        FreshnessItem(source="Yahoo player pool and statuses", state=freshness(pool_imported_at, now),
            as_of=pool_imported_at, detail=("Yahoo status and ownership; fresh for 24 hours. A fresh, verified record "
                "without a status field is NO CURRENT YAHOO DESIGNATION, not a medical-health guarantee; a supplied blank "
                "or unverifiable status is UNKNOWN.")),
        FreshnessItem(source="NBA game logs", state=log_state, as_of=log_imported_at,
            detail=(f"Latest persisted game {latest_log_game.isoformat()}; recent production uses the last 14 days and form windows look back 30 days."
                if latest_log_game else "No persisted current-season game logs.")),
        FreshnessItem(source="NBA season stats", state=freshness(stats_imported_at, now, 7), as_of=stats_imported_at,
            detail="Current and prior-season per-game production; fresh for 7 days."),
        FreshnessItem(source="NBA schedule", state=freshness(schedule_imported_at, now, 7), as_of=schedule_imported_at,
            detail="Persisted games used for window counts; fresh for 7 days."),
    ]
    explicit_state = any(isinstance(payload.get("ownership"), dict)
        and str(payload["ownership"].get("ownership_type") or "").lower() in {"freeagents", "waivers"}
        for _, payload, _ in identities.values())
    ctx.availability_summary = AvailabilitySummary(
        state=("available" if all_rosters_ready else "missing" if not baselines or snapshots_missing == len(baselines)
            else "partial" if snapshots_missing else "stale"),
        roster_snapshot_complete=all_rosters_ready, roster_snapshots_current=snapshots_current,
        roster_snapshots_expected=len(baselines), oldest_roster_snapshot=oldest_snapshot,
        player_pool_imported_at=pool_imported_at,
        counts=dict(sorted(Counter(availability_class(row) for row in players.values()).items())),
        explicit_state_supplied=explicit_state,
        source_gap=None if explicit_state else (
            "The existing Yahoo player-pool import does not include free-agent/waiver ownership, so unrostered "
            "players are labeled UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO, never confirmed free agents."),
        detail=(f"{snapshots_current} of {len(baselines)} league roster snapshots are current. "
            + ("Supported adds may use players absent from every current roster." if all_rosters_ready
                else "Until every snapshot is current, unrostered players are only POTENTIAL TARGETS TO CHECK IN YAHOO.")),
    )
    ctx.acquisition = acquisition_context_for(
        league, team, now, verify_league_contract(league) if settings_state == "available" else [])
    ctx.memo = {}
    return ctx


def lineup_slot_days_gained(ctx: Context, candidate: Candidate) -> int | None:
    needs = ctx.team_needs
    if (needs is None or needs.lineup_day_state != "partial" or candidate.schedule.games_remaining is None
            or candidate.schedule.coverage != "PARTIAL"):
        return None
    members = fill_members(ctx)
    slots = ctx.needs_slots or ctx.slots
    gained = 0
    for day in needs.lineup_days:
        if day.date in candidate.schedule.game_dates:
            playing = [row for row in members if day.date in row.schedule.game_dates]
            gained += len(uncovered_slots(playing, slots)) - len(uncovered_slots([*playing, candidate], slots))
    return gained


def _option_key(row: Candidate) -> tuple:
    return (ACTION_RANK[row.recommended_action_type], -(row.net_improvement if row.net_improvement is not None else -1e9),
        -(row.overall_score if row.overall_score is not None else -1e9), row.player_id)


def replacement_order(row: Candidate) -> tuple:
    """Explicit-drop list order: an evidence-supported decision always outranks unsupported measured upside.
    Decision tier first (ACTION_RANK: supported ADD/STREAM/MUST ADD, WATCH, supported nonpositive HOLD, insufficient
    evidence), then measured net improvement (unavailable last) and stable player ID. It orders the list only: each
    candidate keeps its own decision and exact comparison against the selected drop. Within the supported tier this
    equals `pair_order` for the fixed drop, so the first supported row is the board's best add for that drop."""
    return (ACTION_RANK[row.recommended_action_type], row.net_improvement is None, -(row.net_improvement or 0),
        row.player_id)


def option_groups(ctx: Context, candidates: list[Candidate]) -> OptionGroups:
    by_need = []
    for slot in need_slots(ctx):
        best = min((row for row in candidates if slot_accepts(slot, row)), key=_option_key, default=None)
        by_need.append(NeedOption(
            slot=slot, candidate_id=best.player_id if best else None,
            action_type=best.recommended_action_type if best else None,
            reason=(f"Best available option able to cover {slot}: {best.action_label}" if best
                else f"No eligible available player can cover {slot} in the persisted pool."),
        ))
    flexible = min((row for row in candidates
        if len(player_positions(row) & {"PG", "SG", "SF", "PF", "C"}) >= 2
        and (len(row.fills_needs) >= 2 or not need_slots(ctx))), key=_option_key, default=None)
    short_term = min((row for row in candidates if row.schedule.games_remaining is not None and ctx.mode != "ros"),
        key=lambda row: (ACTION_RANK[row.recommended_action_type],
            -(row.lineup_slot_days_gained if row.lineup_slot_days_gained is not None else -1),
            -(row.schedule.games_remaining or 0), *_option_key(row)[1:]), default=None)
    longer_term = min((row for row in candidates if row.ros.value is not None
        and row.data_quality.get("ros") is not None and row.data_quality["ros"].state == "available"),
        key=lambda row: (ACTION_RANK[row.recommended_action_type], -(row.ros.value or 0), row.player_id), default=None)
    watch = sorted((row for row in candidates if row.recommended_action_type == "WATCH"), key=_option_key)
    return OptionGroups(
        by_need=by_need,
        flexible_candidate_id=flexible.player_id if flexible else None,
        short_term_candidate_id=short_term.player_id if short_term else None,
        longer_term_candidate_id=longer_term.player_id if longer_term else None,
        watch_candidate_ids=[row.player_id for row in watch[:5]],
        detail=("Backend-ranked alternatives: supported actions first, then WATCH, HOLD and insufficient evidence; "
            "within a group by measured net improvement, overall score and player ID. Short-term ranks persisted "
            "lineup-slot dates gained and games in the window; longer-term ranks Season Evidence fantasy PPG "
            "(historical, not a projection)."),
    )


def _best_actionable(candidates: list[Candidate]) -> Candidate | None:
    # Same order as the optimizer (highest net, then lowest add ID); on a full roster each candidate already
    # carries its best supported pair, so this is the optimizer's best transaction.
    actionable = [row for row in candidates if row.overall_score is not None
        and row.recommended_action in ACTIONABLE_DECISIONS and row.net_improvement is not None and row.net_improvement > 0]
    return min(actionable, key=lambda row: pair_order(row.net_improvement, row.player_id,
        row.comparison.player_id if row.comparison is not None and row.comparison.player_id is not None else 0), default=None)


def supported_board_moves(ctx: Context, candidates: list[Candidate]) -> tuple[list[FillRecommendation], Candidate | None]:
    """Strict supported moves the board features with no explicit drop: the fill plan shared with the
    transactions endpoint for open capacity, else the best actionable ADD + DROP; none when undetermined."""
    shape = transaction_shape(ctx)
    if shape in FILL_SHAPES:
        plan, _ = build_fill_plan(ctx, candidates)
        return plan, plan[0].add_player if plan else None
    if shape == "UNDETERMINED":
        return [], None
    return [], _best_actionable(candidates)


def supported_pick_ids(plan: list[FillRecommendation], best_add: Candidate | None) -> list[int]:
    return [fill.add_player.player_id for fill in plan] or ([best_add.player_id] if best_add is not None else [])


def decision_support_for(ctx: Context, candidates: list[Candidate]) -> DecisionSupport:
    plan, best_add = supported_board_moves(ctx, candidates)
    return build_decision_support(ctx, candidates, supported_pick_ids(plan, best_add))


def team_need_lines(ctx: Context) -> list[str]:
    capacity, needs = ctx.roster_capacity, ctx.team_needs
    lines = [capacity.drop_requirement_reason] if capacity is not None else []
    if needs is not None and needs.starting_slots_required:
        lines.append(f"{needs.starting_slots_covered} of {needs.starting_slots_required} starting slots can be covered by "
            "lineup-eligible players (eligibility only; not a daily lineup optimizer).")
        lines.extend(need.reason for need in needs.needs)
    else:
        lines.append("Team needs unavailable until fresh Yahoo roster slots and settings are imported.")
    lines.append("Category needs are not used: this is a Head-to-Head Points league.")
    return lines


async def get_waivers(session: AsyncSession, league_key: str, team_key: str, mode: Mode, drop_id: int | None = None) -> WaiverBoard:
    with record_phase("load"):
        ctx = await load_context(session, league_key, team_key, mode)
    if drop_id is not None and drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the configured manager roster")
    with record_phase("analyze"):
        # CPU-only work over the loaded context; a worker thread keeps the event loop responsive.
        board = await asyncio.to_thread(build_board, ctx, league_key, team_key, mode, drop_id)
    assert_board_recommendation_invariant(board)
    return board


def build_board(ctx: Context, league_key: str, team_key: str, mode: Mode, drop_id: int | None) -> WaiverBoard:
    eligible_rows = [row for row in ctx.players.values() if availability_actionable(row)]
    candidates = [enrich(ctx, row, drop_id) for row in eligible_rows]
    candidates.sort(key=replacement_order if drop_id is not None
        else lambda row: (row.overall_score is None, -(row.overall_score or 0), row.player_id))
    if drop_id is None:
        for row in candidates:
            row.lineup_slot_days_gained = lineup_slot_days_gained(ctx, row)
    for index, row in enumerate(sorted(candidates, key=lambda row: (
            ACTION_RANK[row.recommended_action_type], not row.fills_needs, *_option_key(row)[1:]))):
        row.decision_priority = index + 1
    scored = [row for row in candidates if row.overall_score is not None]
    best_overall = max((row for row in candidates if row.components.player_value is not None),
        key=lambda row: (row.components.player_value, -row.player_id), default=None)
    top_measured = max((row for row in scored if row.net_improvement is not None),
        key=lambda row: (row.net_improvement, row.overall_score, -row.player_id), default=None)
    shape = transaction_shape(ctx)
    if drop_id is None:
        plan, best_add = supported_board_moves(ctx, candidates)
    else:
        plan, best_add = [], _best_actionable(candidates)
    manager = [ctx.players[pid] for pid in ctx.roster_ids]
    for player in manager:
        # Pair comparisons are memoized per request, so this reuses the board's ADD + DROP pairs.
        supported = [compare(ctx, row, player.player_id) for row in eligible_rows]
        measured = [option.net_improvement for option in supported if option.net_improvement is not None]
        if ctx.roster_ready and measured:
            # The same gated exact-pair decision the optimizer uses; only positive pairs can be strong or WATCH.
            label = "keep_on_measured_model"
            for row, option in zip(eligible_rows, supported):
                if (option.net_improvement or 0) <= 0:
                    continue
                decision = enrich(ctx, row, player.player_id).recommended_action
                if decision in ACTIONABLE_DECISIONS:
                    label = "review_replacement"
                    break
                if decision == "WATCH":
                    label = "watch_replacement"
            player.roster_decision = label
    if ctx.team_needs is not None and drop_id is None:
        for need in ctx.team_needs.needs:
            need.compatible_candidate_ids = [row.player_id for row in sorted(
                (row for row in candidates if slot_accepts(need.slot, row)), key=_option_key)[:3]]
    coverage, data_gaps = board_coverage(ctx)
    decision = None
    if drop_id is None:
        decision = build_decision_support(ctx, candidates, supported_pick_ids(plan, best_add))
        ranked = {option.player_id: option for option in decision.options}
        for row in candidates:
            if row.player_id in ranked:
                row.decision_support_class = ranked[row.player_id].classification
                row.decision_rank = ranked[row.player_id].decision_rank
    if best_add is not None:
        action_type: ActionType = best_add.recommended_action_type
    elif drop_id is None and shape == "UNDETERMINED":
        action_type = "INSUFFICIENT_EVIDENCE"
    elif any(row.recommended_action_type == "WATCH" for row in candidates):
        action_type = "WATCH"
    elif any(row.recommended_action_type == "HOLD" for row in candidates):
        action_type = "HOLD"
    else:
        action_type = "INSUFFICIENT_EVIDENCE"
    eligible_ids = [row.player_id for row in sorted(candidates, key=lambda row: (row.decision_priority or 0, row.player_id))]
    # Full evidence for a bounded set, always including the featured best add and, for an explicit drop, the top
    # measured option the page names; every eligible player stays listed by ID (and in decision support).
    shown = candidates[:BOARD_CANDIDATE_LIMIT]
    for row in (best_add, top_measured if drop_id is not None else None):
        if row is not None and all(row.player_id != kept.player_id for kept in shown):
            shown.append(row)
    record_count("candidates", len(candidates))
    return WaiverBoard(
        league_key=league_key, team_key=team_key, mode=mode, generated_at=ctx.now, weights=ctx.weights,
        best_overall_available_id=best_overall.player_id if best_overall else None,
        best_add_for_team_id=best_add.player_id if best_add else None,
        best_drop_for_team_id=(best_add.comparison.player_id if best_add is not None and best_add.requires_drop
            and best_add.comparison is not None else None),
        team_needs=team_need_lines(ctx),
        candidates=shown,
        eligible_candidate_ids=eligible_ids, candidate_count=len(candidates), candidate_limit=BOARD_CANDIDATE_LIMIT,
        top_measured_candidate_id=top_measured.player_id if top_measured else None,
        roster=manager, selected_drop_player_id=drop_id,
        waiver_rules=verify_league_contract(ctx.league) if ctx.quality["settings"].state == "available" else [],
        selected_player_result=(
            f"HOLD {ctx.players[drop_id].player_name}" if drop_id is not None and top_measured and top_measured.net_improvement <= 0
            else best_add.recommended_action if best_add
            else "WATCH" if any(row.recommended_action == "WATCH" for row in candidates)
            else "INSUFFICIENT EVIDENCE"
        ),
        excluded_count=sum(row.availability in {"free_agent", "waivers", "unrostered"} and not row.eligible for row in ctx.players.values()),
        unknown_availability_count=sum(row.availability == "unknown" for row in ctx.players.values()),
        limitations=BASE_LIMITATIONS, data_quality=ctx.quality,
        coverage=coverage, data_gaps=data_gaps,
        recommended_action_type=action_type,
        roster_capacity=ctx.roster_capacity, team_needs_analysis=ctx.team_needs,
        option_groups=option_groups(ctx, candidates) if drop_id is None else None,
        decision_support=decision, evidence_freshness=ctx.evidence_freshness,
        availability_summary=ctx.availability_summary, acquisition_context=ctx.acquisition,
        sample_policy=SAMPLE_POLICY,
    )


class RecommendationContractError(HTTPException):
    def __init__(self, surface: str, violations: list[str]):
        super().__init__(500, {
            "code": "RECOMMENDATION_CONTRACT_VIOLATION",
            "message": f"The {surface} named players outside the current waiver-eligible candidate set; the result was withheld.",
            "violations": violations[:20],
        })


def board_recommended_ids(board: WaiverBoard) -> dict[str, list[int]]:
    """Every player the board features as a move or recommendation (potential targets excluded)."""
    ids: dict[str, list[int]] = {}
    if board.best_add_for_team_id is not None:
        ids["best_add_for_team_id"] = [board.best_add_for_team_id]
    support = board.decision_support
    if support is not None:
        ids["supported_actions"] = [row.player_id for row in support.options if row.classification == "SUPPORTED_ACTION"]
        ids["best_measured"] = list(support.best_measured_ids)
        ids["groups"] = [group.player_id for group in support.groups if group.player_id is not None]
        ids["watch"] = list(support.watch_ids)
    groups = board.option_groups
    if groups is not None:
        ids["option_groups"] = [pid for pid in (
            *(option.candidate_id for option in groups.by_need), groups.flexible_candidate_id,
            groups.short_term_candidate_id, groups.longer_term_candidate_id, *groups.watch_candidate_ids,
        ) if pid is not None]
    if board.team_needs_analysis is not None:
        ids["need_options"] = [pid for need in board.team_needs_analysis.needs for pid in need.compatible_candidate_ids]
    return ids


def assert_board_recommendation_invariant(board: WaiverBoard) -> None:
    eligible = set(board.eligible_candidate_ids)
    violations = [f"{source}: player {pid} is not waiver-eligible"
        for source, pids in board_recommended_ids(board).items() for pid in pids if pid not in eligible]
    support = board.decision_support
    if support is not None:
        options = {row.player_id: row for row in support.options}
        for pid in support.potential_target_ids:
            option = options.get(pid)
            if pid in eligible or option is None or option.availability_classification not in CHECKABLE_AVAILABILITY:
                violations.append(f"potential_targets: player {pid} is not an unconfirmed, unrostered player")
        for option in support.options:
            if option.classification in {"SUPPORTED_ACTION", "BEST_MEASURED_OPTION", "WATCH", "MEASURED"} and (
                    option.player_id not in eligible or option.availability_classification not in ACTIONABLE_AVAILABILITY):
                violations.append(f"decision_support: {option.classification} player {option.player_id} lacks actionable availability")
    if violations:
        raise RecommendationContractError("waiver board", violations)


def assert_transactions_recommendation_invariant(ctx: Context, analysis: TransactionAnalysis) -> None:
    adds = [
        *((analysis.best_transaction.add_player,) if analysis.best_transaction else ()),
        *(swap.add_player for swap in analysis.top_supported_transactions),
        *(swap.add_player for swap in analysis.watch_transactions),
        *((analysis.best_addition.add_player,) if analysis.best_addition else ()),
        *(fill.add_player for fill in analysis.add_only_recommendations),
        *(fill.add_player for fill in analysis.watch_additions),
    ]
    violations = [f"transactions: player {row.player_id} is not waiver-eligible" for row in adds
        if row.player_id not in ctx.players or not availability_actionable(ctx.players[row.player_id])]
    if violations:
        raise RecommendationContractError("best-move analysis", violations)


async def get_impact(session: AsyncSession, league_key: str, team_key: str, player_id: int, drop_id: int | None, mode: Mode) -> WaiverImpact:
    with record_phase("load"):
        ctx = await load_context(session, league_key, team_key, mode)
    player = ctx.players.get(player_id)
    if player is None:
        raise HTTPException(404, "Player is not in the persisted Yahoo league pool")
    if player.availability == "rostered":
        raise HTTPException(409, "Player is already rostered in the selected league")
    if drop_id is not None and drop_id not in ctx.roster_ids:
        raise HTTPException(422, "Drop player must belong to the selected manager roster")
    with record_phase("analyze"):
        candidate = enrich(ctx, player, drop_id)
    return WaiverImpact(league_key=league_key, team_key=team_key, mode=mode,
        model_version=MODEL_VERSION, candidate=candidate, comparison=candidate.comparison,
        limitations=BASE_LIMITATIONS + (ctx.roster_capacity.limitations if ctx.roster_capacity else []),
        roster_capacity=ctx.roster_capacity)

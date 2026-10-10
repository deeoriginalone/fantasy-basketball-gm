from math import ceil, exp, isfinite
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import (
    DraftPlayerAvailability,
    DraftRun,
    DraftTiming,
    DraftUtilityPick,
    DraftUtilityRequest,
    DraftUtilityResult,
)
from app.features.draft.models import DraftMarketData, DraftPlayerMetric
from app.features.leagues.models import LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.services.draft.market_sync import MARKET_STALE_AFTER

CORE_POSITIONS = {"PG", "SG", "SF", "PF", "C"}
MARKET_SOURCE_PRIORITY = ("fantrax",)
SURVIVAL_DECISION_THRESHOLD = 0.5
POSITION_GROUPS = {
    "center": {"C"},
    "guard": {"PG", "SG", "G"},
    "forward": {"SF", "PF", "F"},
}


def _positions(value: str | None) -> set[str]:
    if not value:
        return set()
    return {position.strip().upper() for position in value.replace("/", ",").split(",") if position.strip()}


def _slot_positions(position: str) -> set[str]:
    normalized = position.upper()
    if normalized == "G":
        return {"PG", "SG"}
    if normalized == "F":
        return {"SF", "PF"}
    if normalized in CORE_POSITIONS:
        return {normalized}
    return set()


def _slot_accepts(slot: str, player_positions: set[str]) -> bool:
    normalized = slot.upper()
    if normalized in {"UTIL", "UT", "BN"}:
        return bool(player_positions)
    accepted = _slot_positions(normalized)
    eligible = set().union(*(_slot_positions(position) for position in player_positions)) if player_positions else set()
    return bool(accepted & eligible)


def _expanded_slots(roster_positions: list[dict]) -> list[str]:
    slots = []
    for roster_slot in roster_positions:
        position = str(roster_slot.get("position") or "").upper()
        is_starting = bool(int(roster_slot.get("is_starting_position", 1) or 0))
        if not position or position in {"IL", "IL+", "IR"}:
            continue
        if not is_starting and position != "BN":
            continue
        try:
            count = max(0, int(float(roster_slot.get("count", 0) or 0)))
        except (TypeError, ValueError):
            continue
        slots.extend([position] * count)
    return slots


def _maximum_slot_matching(player_positions: list[set[str]], slots: list[str]) -> dict[int, int]:
    slot_to_player: dict[int, int] = {}

    def assign(player_index: int, seen_slots: set[int]) -> bool:
        for slot_index, slot in enumerate(slots):
            if slot_index in seen_slots or not _slot_accepts(slot, player_positions[player_index]):
                continue
            seen_slots.add(slot_index)
            previous_player = slot_to_player.get(slot_index)
            if previous_player is None or assign(previous_player, seen_slots):
                slot_to_player[slot_index] = player_index
                return True
        return False

    order = sorted(
        range(len(player_positions)),
        key=lambda index: sum(_slot_accepts(slot, player_positions[index]) for slot in slots),
    )
    for player_index in order:
        assign(player_index, set())
    return slot_to_player


def calculate_utility_score(
    *,
    fantasy_value: float,
    replacement_value: float,
    positional_scarcity: float,
    durability_score: float,
    risk_score: float,
    upside_score: float,
    positional_need_score: float,
    roster_construction_score: float,
) -> float:
    value_scale = max(abs(fantasy_value), 1.0)
    quality_multiplier = (
        1.0
        + 0.05 * durability_score / 100.0
        + 0.05 * upside_score / 100.0
        - 0.05 * risk_score / 100.0
    )
    need = positional_need_score / 100.0
    scarcity = positional_scarcity / 100.0
    construction = roster_construction_score / 100.0
    return (
        fantasy_value * quality_multiplier
        + 0.5 * replacement_value
        + value_scale * (0.10 * need + 0.05 * scarcity * need + 0.05 * construction)
    )


def calculate_snake_draft_timing(
    draft_position: int,
    round_number: int,
    total_teams: int,
) -> DraftTiming:
    if total_teams < 2 or not 1 <= draft_position <= total_teams or round_number < 1:
        raise ValueError("Draft position, round, and team count are outside valid bounds")
    current_round_position = draft_position if round_number % 2 else total_teams - draft_position + 1
    current_pick_number = (round_number - 1) * total_teams + current_round_position
    next_round_number = round_number + 1
    next_round_position = draft_position if next_round_number % 2 else total_teams - draft_position + 1
    next_pick_number = round_number * total_teams + next_round_position
    return DraftTiming(
        draft_position=draft_position,
        round_number=round_number,
        total_teams=total_teams,
        current_pick_number=current_pick_number,
        picks_until_next_turn=next_pick_number - current_pick_number - 1,
        next_pick_number=next_pick_number,
    )


def _position_groups(positions: set[str]) -> set[str]:
    groups = set()
    for group, accepted_positions in POSITION_GROUPS.items():
        if positions & accepted_positions:
            groups.add(group)
        if group == "guard" and "G" in positions:
            groups.add(group)
        if group == "forward" and "F" in positions:
            groups.add(group)
    return groups


def detect_draft_runs(
    recent_pick_player_ids: list[int],
    identities_by_id: dict[int, PlayerIdentity],
    *,
    window_limit: int = 10,
) -> tuple[list[DraftRun], set[str]]:
    window = recent_pick_player_ids[-window_limit:]
    counts = {group: 0 for group in POSITION_GROUPS}
    for player_id in window:
        identity = identities_by_id.get(player_id)
        if identity is None:
            continue
        for group in _position_groups(_positions(identity.position)):
            counts[group] += 1
    threshold = max(3, ceil(len(window) * 0.3)) if window else 3
    active_groups = {
        group for group, count in counts.items()
        if count >= threshold and count >= 3
    }
    runs = [
        DraftRun(
            position_group=group,
            recent_pick_count=counts[group],
            window_size=len(window),
            active=group in active_groups,
        )
        for group in POSITION_GROUPS
    ]
    return runs, active_groups


def _survival_probability(
    adp: float,
    next_pick_number: int,
    total_teams: int,
    draft_frequency: float | None = None,
    recent_run_count: int = 0,
) -> float:
    scale = max(total_teams / 2.0, 1.0)
    z_score = max(-60.0, min(60.0, (adp - next_pick_number) / scale))
    survival = 1.0 / (1.0 + exp(-z_score))
    if draft_frequency is not None:
        frequency = max(0.0, min(100.0, draft_frequency)) / 100.0
        survival *= 1.0 - 0.25 * frequency
    if recent_run_count > 0:
        survival = survival ** (1.0 + 0.12 * min(recent_run_count, 8))
    return max(0.0, min(1.0, survival))


def _availability_score(
    survival_probability: float,
    positional_scarcity: float,
    picks_until_next_turn: int,
    total_teams: int,
) -> float:
    scarcity = max(0.0, min(1.0, positional_scarcity / 100.0))
    pick_pressure = max(0.0, min(1.0, picks_until_next_turn / max(1, 2 * (total_teams - 1))))
    score = 100.0 * survival_probability * (1.0 - 0.2 * scarcity) * (1.0 - 0.2 * pick_pressure)
    return max(0.0, min(100.0, score))


def _market_timing_scores(
    adp: float | None,
    current_pick_number: int | None,
    total_teams: int | None,
) -> tuple[float | None, float | None, float | None]:
    if adp is None or current_pick_number is None or total_teams is None:
        return None, None, None
    delta = adp - current_pick_number
    scale = max(float(total_teams), 1.0)
    reach_score = min(100.0, max(0.0, delta) / scale * 100.0)
    fall_score = min(100.0, max(0.0, -delta) / scale * 100.0)
    return round(delta, 1), round(reach_score, 1), round(fall_score, 1)


def _mode_adjustment(metric: DraftPlayerMetric, mode: str) -> float:
    value_scale = max(abs(metric.fantasy_value), 1.0)
    durability = metric.durability_score / 100.0
    risk = metric.risk_score / 100.0
    upside = metric.upside_score / 100.0
    if mode == "safe":
        return value_scale * (0.12 * durability - 0.12 * risk)
    if mode == "upside":
        return value_scale * (0.18 * upside - 0.04 * durability)
    return 0.0


def _run_bonus(metric: DraftPlayerMetric, positions: set[str], active_runs: list[DraftRun]) -> float:
    groups = _position_groups(positions)
    pressure = max(
        (run.recent_pick_count for run in active_runs if run.active and run.position_group in groups),
        default=0,
    )
    if pressure < 3:
        return 0.0
    value_scale = max(abs(metric.fantasy_value), 1.0)
    bonus = min(0.12, 0.025 * (pressure - 2))
    return value_scale * bonus


async def calculate_draft_utility(
    session: AsyncSession,
    request: DraftUtilityRequest,
) -> DraftUtilityResult:
    drafted_ids = request.drafted_player_ids
    available_ids = request.available_player_ids
    if len(set(drafted_ids)) != len(drafted_ids) or len(set(available_ids)) != len(available_ids):
        raise HTTPException(status_code=422, detail="Drafted and available player IDs must not contain duplicates")
    if set(drafted_ids) & set(available_ids):
        raise HTTPException(status_code=422, detail="A player cannot be both drafted and available")
    recent_pick_ids = request.recent_pick_player_ids
    if len(set(recent_pick_ids)) != len(recent_pick_ids):
        raise HTTPException(status_code=422, detail="Recent draft picks must not contain duplicate player IDs")
    if any(not isfinite(adp) or adp <= 0 for adp in request.adp_by_player_id.values()):
        raise HTTPException(status_code=422, detail="ADP values must be finite positive overall pick numbers")
    if set(request.adp_by_player_id) - set(available_ids):
        raise HTTPException(status_code=422, detail="ADP may only be supplied for available player IDs")

    timing_inputs = (request.draft_position, request.round_number, request.total_teams)
    if any(value is not None for value in timing_inputs) and not all(value is not None for value in timing_inputs):
        raise HTTPException(status_code=422, detail="draft_position, round_number, and total_teams must be supplied together")

    team = await session.get(Team, request.team_key)
    if team is None or team.league_key != request.league_key:
        raise HTTPException(status_code=404, detail="Draft team was not found in the selected league")
    settings = await session.get(LeagueSettings, request.league_key)
    if settings is None:
        raise HTTPException(status_code=404, detail="Imported league settings were not found")

    requested_ids = set(drafted_ids) | set(available_ids) | set(recent_pick_ids)
    valid_ids = set((await session.scalars(
        select(LeaguePlayer.player_identity_id).where(
            LeaguePlayer.league_key == request.league_key,
            LeaguePlayer.player_identity_id.in_(requested_ids),
        )
    )).all()) if requested_ids else set()
    if valid_ids != requested_ids:
        raise HTTPException(status_code=422, detail="Every drafted, recent, and available player must belong to the imported Yahoo league pool")

    identity_ids = list(requested_ids)
    identities = list((await session.scalars(
        select(PlayerIdentity).where(PlayerIdentity.id.in_(identity_ids))
    )).all()) if identity_ids else []
    identities_by_id = {identity.id: identity for identity in identities}
    drafted_positions = [
        _positions(identities_by_id[player_id].position)
        for player_id in drafted_ids
        if player_id in identities_by_id
    ]
    slots = _expanded_slots(settings.roster_positions)
    team_count = int((await session.scalar(
        select(func.count()).select_from(Team).where(Team.league_key == request.league_key)
    )) or 0)
    draft_timing = None
    if all(value is not None for value in timing_inputs):
        if request.total_teams != team_count:
            raise HTTPException(status_code=422, detail="total_teams must match the imported Yahoo league team count")
        try:
            draft_timing = calculate_snake_draft_timing(
                request.draft_position,
                request.round_number,
                request.total_teams,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    draft_runs, active_run_groups = detect_draft_runs(recent_pick_ids, identities_by_id)
    current_matching = _maximum_slot_matching(drafted_positions, slots)
    open_slot_indexes = set(range(len(slots))) - set(current_matching)
    remaining_slots = max(1, len(open_slot_indexes))

    metrics = list((await session.scalars(
        select(DraftPlayerMetric).where(
            DraftPlayerMetric.league_key == request.league_key,
            DraftPlayerMetric.season == request.season,
            DraftPlayerMetric.player_identity_id.in_(available_ids),
        )
    )).all()) if available_ids else []
    metrics_by_identity = {metric.player_identity_id: metric for metric in metrics}
    unscored = [player_id for player_id in available_ids if player_id not in metrics_by_identity]
    market_rows = list((await session.scalars(
        select(DraftMarketData)
        .where(
            DraftMarketData.season == request.season,
            DraftMarketData.player_id.in_(available_ids),
            DraftMarketData.source.in_(MARKET_SOURCE_PRIORITY),
        )
        .order_by(DraftMarketData.last_updated.desc(), DraftMarketData.source)
    )).all()) if available_ids else []
    market_rows_by_player: dict[int, list[DraftMarketData]] = {}
    for market_row in market_rows:
        market_rows_by_player.setdefault(market_row.player_id, []).append(market_row)

    current_time = datetime.now(timezone.utc)

    def market_row_is_stale(row: DraftMarketData) -> bool:
        updated_at = row.last_updated
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        return current_time - updated_at > MARKET_STALE_AFTER

    market_inputs: dict[int, tuple[
        float | None, int | None, float | None, str | None, str, bool
    ]] = {}
    for player_id in available_ids:
        player_market_rows = market_rows_by_player.get(player_id, [])
        market_row = None
        stale_row = None
        for source in MARKET_SOURCE_PRIORITY:
            source_rows = [row for row in player_market_rows if row.source == source]
            fresh_source_rows = [row for row in source_rows if not market_row_is_stale(row)]
            if fresh_source_rows:
                market_row = next((row for row in fresh_source_rows if row.adp is not None), fresh_source_rows[0])
                break
            if source_rows and stale_row is None:
                stale_row = source_rows[0]
        if market_row is None:
            market_row = stale_row
        request_adp = request.adp_by_player_id.get(player_id)
        is_stale = market_row is not None and market_row_is_stale(market_row)
        freshness = (
            "request" if request_adp is not None
            else "stale" if is_stale and market_row.adp is not None
            else "fresh" if market_row is not None and market_row.adp is not None
            else "unknown"
        )
        stored_adp = market_row.adp if market_row is not None and not is_stale else None
        market_inputs[player_id] = (
            request_adp if request_adp is not None else stored_adp,
            market_row.draft_rank if market_row is not None and not is_stale else None,
            market_row.draft_frequency if market_row is not None and not is_stale else None,
            "request" if request_adp is not None else (market_row.source if market_row else None),
            freshness,
            is_stale,
        )
    adp_missing = [player_id for player_id in available_ids if market_inputs[player_id][0] is None]

    def run_count_for(player_id: int) -> int:
        identity = identities_by_id.get(player_id)
        if identity is None:
            return 0
        groups = _position_groups(_positions(identity.position))
        return max(
            (run.recent_pick_count for run in draft_runs if run.active and run.position_group in groups),
            default=0,
        )

    availability_by_id: dict[int, tuple[float | None, float | None]] = {}
    player_availability = []
    for player_id in available_ids:
        metric = metrics_by_identity.get(player_id)
        adp, draft_rank, draft_frequency, adp_source, data_freshness, is_stale = market_inputs[player_id]
        market_value_delta, reach_score, fall_score = _market_timing_scores(
            adp,
            draft_timing.current_pick_number if draft_timing else None,
            draft_timing.total_teams if draft_timing else None,
        )
        survival_probability = None
        availability_score = None
        blocker = None
        draft_now = None
        safe_to_wait = None
        survival_confidence = "unknown"
        if draft_timing is None:
            blocker = "draft timing not supplied"
        elif adp is None:
            blocker = "ADP data is stale" if is_stale else "ADP not supplied"
        else:
            survival_probability = _survival_probability(
                adp,
                draft_timing.next_pick_number,
                draft_timing.total_teams,
                draft_frequency,
                run_count_for(player_id),
            )
            survival_confidence = "heuristic_unvalidated"
            draft_now = survival_probability < SURVIVAL_DECISION_THRESHOLD
            safe_to_wait = not draft_now
            if metric is None:
                blocker = "player draft metrics unavailable"
            else:
                availability_score = _availability_score(
                    survival_probability,
                    metric.positional_scarcity,
                    draft_timing.picks_until_next_turn,
                    draft_timing.total_teams,
                )
        if market_value_delta is None:
            market_explanation = "Market timing is unknown because ADP or draft timing is missing."
        elif market_value_delta > 0:
            market_explanation = (
                f"ADP {adp:.1f} vs current pick {draft_timing.current_pick_number}: market projects "
                f"this as a {market_value_delta:.1f}-pick reach (reach {reach_score:.0f}/100, "
                f"fall {fall_score:.0f}/100)."
            )
        elif market_value_delta < 0:
            market_explanation = (
                f"ADP {adp:.1f} vs current pick {draft_timing.current_pick_number}: market ADP "
                f"has fallen {abs(market_value_delta):.1f} picks past this selection "
                f"(reach {reach_score:.0f}/100, fall {fall_score:.0f}/100)."
            )
        else:
            market_explanation = (
                f"ADP {adp:.1f} aligns with current pick {draft_timing.current_pick_number} "
                f"(reach {reach_score:.0f}/100, fall {fall_score:.0f}/100)."
            )
        if survival_probability is None:
            explanation = blocker or "Next-pick survival is unknown because ADP or draft timing is missing."
        else:
            decision = "Draft now" if draft_now else "Wait is favored by the heuristic"
            explanation = (
                f"{decision}: estimated {survival_probability:.0%} chance to survive until pick "
                f"{draft_timing.next_pick_number} using {adp_source} ADP. {market_explanation} "
                "The 50% decision threshold is a heuristic, not a calibrated probability."
            )
        if market_value_delta is not None and survival_probability is None:
            explanation = f"{market_explanation} {explanation}"
        availability_by_id[player_id] = (survival_probability, availability_score)
        player_availability.append(DraftPlayerAvailability(
            player_identity_id=player_id,
            adp=adp,
            market_value_delta=market_value_delta,
            reach_score=reach_score,
            fall_score=fall_score,
            draft_rank=draft_rank,
            draft_frequency=draft_frequency,
            adp_source=adp_source,
            positional_scarcity=metric.positional_scarcity if metric else None,
            availability_score=availability_score,
            next_pick_survival_probability=survival_probability,
            survival_confidence=survival_confidence,
            data_freshness=data_freshness,
            draft_now=draft_now,
            safe_to_wait=safe_to_wait,
            explanation=explanation,
            blocker=blocker,
        ))

    best_pick = None
    best_key = None
    best_value_before_pick = None
    best_value_before_key = None
    for player_id in available_ids:
        identity = identities_by_id.get(player_id)
        metric = metrics_by_identity.get(player_id)
        if identity is None or metric is None or not identity.nba_player_id:
            continue
        eligible = _positions(identity.position)
        open_eligible_slots = [
            index for index in open_slot_indexes
            if _slot_accepts(slots[index], eligible)
        ]
        need_score = 100.0 * len(open_eligible_slots) / remaining_slots
        matching_after = _maximum_slot_matching([*drafted_positions, eligible], slots)
        new_player_slots = [
            slots[index]
            for index, assigned_player in matching_after.items()
            if assigned_player == len(drafted_positions) and index not in current_matching
        ]
        if len(matching_after) <= len(current_matching) or not new_player_slots:
            construction_score = 0.0
        elif any(slot in CORE_POSITIONS for slot in new_player_slots):
            construction_score = 100.0
        elif any(slot in {"G", "F"} for slot in new_player_slots):
            construction_score = 60.0
        elif any(slot in {"UTIL", "UT"} for slot in new_player_slots):
            construction_score = 30.0
        else:
            construction_score = 10.0
        utility_score = calculate_utility_score(
            fantasy_value=metric.fantasy_value,
            replacement_value=metric.replacement_value,
            positional_scarcity=metric.positional_scarcity,
            durability_score=metric.durability_score,
            risk_score=metric.risk_score,
            upside_score=metric.upside_score,
            positional_need_score=need_score,
            roster_construction_score=construction_score,
        )
        mode_adjustment = _mode_adjustment(metric, request.mode)
        run_bonus = _run_bonus(metric, eligible, draft_runs)
        adp, draft_rank, draft_frequency, adp_source, data_freshness, _ = market_inputs[player_id]
        survival_probability, availability_score = availability_by_id[player_id]
        survival_confidence = "heuristic_unvalidated" if survival_probability is not None else "unknown"
        draft_now = (
            survival_probability < SURVIVAL_DECISION_THRESHOLD
            if survival_probability is not None else None
        )
        safe_to_wait = not draft_now if draft_now is not None else None
        urgency_bonus = 0.0
        if survival_probability is not None and draft_timing is not None:
            urgency_bonus = max(abs(metric.fantasy_value), 1.0) * (
                0.08
                * (metric.positional_scarcity / 100.0)
                * (1.0 - survival_probability)
            )
        mode_adjusted_utility_score = utility_score + mode_adjustment + run_bonus + urgency_bonus
        opportunity_cost_if_wait = (
            mode_adjusted_utility_score * (1.0 - survival_probability)
            if survival_probability is not None else None
        )
        market_value_delta, reach_score, fall_score = _market_timing_scores(
            adp,
            draft_timing.current_pick_number if draft_timing else None,
            draft_timing.total_teams if draft_timing else None,
        )
        run_for_player = [
            run.position_group for run in draft_runs
            if run.active and run.position_group in _position_groups(eligible)
        ]
        reasons = [
            f"Roster fit: {request.mode.title()} mode-adjusted utility is {mode_adjusted_utility_score:.2f}; position need is {need_score:.0f}/100 with {len(open_eligible_slots)} compatible open slots.",
            f"Scarcity impact: {metric.positional_scarcity:.0f}/100; replacement value is {metric.replacement_value:.2f}.",
            f"Roster construction impact: {construction_score:.0f}/100 for the best available slot fit.",
        ]
        if market_value_delta is not None:
            reasons.append(
                f"ADP impact: ADP {adp:.1f} vs current pick {draft_timing.current_pick_number} gives market delta {market_value_delta:+.1f} picks (reach {reach_score:.0f}/100, fall {fall_score:.0f}/100)."
            )
        else:
            reasons.append("ADP impact: unknown because current ADP or draft timing is unavailable.")
        if run_for_player:
            reasons.append(f"Scarcity/run impact: active {'/'.join(run_for_player)} run adds {run_bonus:.2f} utility pressure.")
        if survival_probability is not None and draft_timing is not None:
            reasons.append(
                f"Survival impact: estimated {survival_probability:.0%} chance to remain available at pick {draft_timing.next_pick_number}; draft now is {draft_now}, safe to wait is {safe_to_wait}."
            )
            reasons.append(
                f"Opportunity cost if you wait: {opportunity_cost_if_wait:.2f} utility at risk before your next turn."
            )
            reasons.append("Survival and the 50% decision threshold are heuristic and uncalibrated.")
        else:
            reasons.append(
                "Next-pick survival is unknown because ADP is stale or unavailable, or draft timing is missing."
            )
        pick = DraftUtilityPick(
            player_identity_id=identity.id,
            yahoo_player_id=identity.yahoo_player_id,
            nba_player_id=identity.nba_player_id,
            player_name=identity.player_name,
            positions=sorted(eligible),
            fantasy_value=metric.fantasy_value,
            replacement_value=metric.replacement_value,
            positional_scarcity=metric.positional_scarcity,
            durability_score=metric.durability_score,
            risk_score=metric.risk_score,
            upside_score=metric.upside_score,
            positional_need_score=need_score,
            roster_construction_score=construction_score,
            utility_score=utility_score,
            mode_adjusted_utility_score=mode_adjusted_utility_score,
            adp=adp,
            market_value_delta=market_value_delta,
            reach_score=reach_score,
            fall_score=fall_score,
            opportunity_cost_if_wait=opportunity_cost_if_wait,
            draft_rank=draft_rank,
            draft_frequency=draft_frequency,
            adp_source=adp_source,
            availability_score=availability_score,
            next_pick_survival_probability=survival_probability,
            survival_confidence=survival_confidence,
            data_freshness=data_freshness,
            draft_now=draft_now,
            safe_to_wait=safe_to_wait,
            run_bonus=run_bonus,
            reasons=reasons,
        )
        tie_break = (mode_adjusted_utility_score, metric.fantasy_value, -identity.id)
        if best_key is None or tie_break > best_key:
            best_key = tie_break
            best_pick = pick
        if survival_probability is not None:
            value_at_risk = opportunity_cost_if_wait
            assert value_at_risk is not None
            before_pick_key = (value_at_risk, mode_adjusted_utility_score, -identity.id)
            if best_value_before_key is None or before_pick_key > best_value_before_key:
                best_value_before_key = before_pick_key
                best_value_before_pick = pick.model_copy(update={
                    "reasons": [
                        *reasons,
                        f"Highest opportunity cost if you wait: {value_at_risk:.2f} utility at risk before the next turn.",
                    ]
                })

    return DraftUtilityResult(
        league_key=request.league_key,
        team_key=request.team_key,
        season=request.season,
        drafted_count=len(drafted_ids),
        available_count=len(available_ids),
        mode=request.mode,
        draft_timing=draft_timing,
        draft_runs=draft_runs,
        player_availability=player_availability,
        best_pick=best_pick,
        best_value_before_next_pick=best_value_before_pick,
        adp_missing_available_player_ids=adp_missing,
        unscored_available_player_ids=unscored,
    )

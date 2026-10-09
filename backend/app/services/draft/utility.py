from collections.abc import Iterable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import DraftUtilityPick, DraftUtilityRequest, DraftUtilityResult
from app.features.draft.models import DraftPlayerMetric
from app.features.leagues.models import LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity

CORE_POSITIONS = {"PG", "SG", "SF", "PF", "C"}


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

    team = await session.get(Team, request.team_key)
    if team is None or team.league_key != request.league_key:
        raise HTTPException(status_code=404, detail="Draft team was not found in the selected league")
    settings = await session.get(LeagueSettings, request.league_key)
    if settings is None:
        raise HTTPException(status_code=404, detail="Imported league settings were not found")

    requested_ids = set(drafted_ids) | set(available_ids)
    valid_ids = set((await session.scalars(
        select(LeaguePlayer.player_identity_id).where(
            LeaguePlayer.league_key == request.league_key,
            LeaguePlayer.player_identity_id.in_(requested_ids),
        )
    )).all()) if requested_ids else set()
    if valid_ids != requested_ids:
        raise HTTPException(status_code=422, detail="Every drafted and available player must belong to the imported Yahoo league pool")

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

    best_pick = None
    best_key = None
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
        )
        tie_break = (utility_score, metric.fantasy_value, -identity.id)
        if best_key is None or tie_break > best_key:
            best_key = tie_break
            best_pick = pick

    return DraftUtilityResult(
        league_key=request.league_key,
        team_key=request.team_key,
        season=request.season,
        drafted_count=len(drafted_ids),
        available_count=len(available_ids),
        best_pick=best_pick,
        unscored_available_player_ids=unscored,
    )

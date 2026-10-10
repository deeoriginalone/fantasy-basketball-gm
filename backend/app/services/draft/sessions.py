from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import (
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftPickView,
    DraftSessionCreateRequest,
    DraftSessionEventResult,
    DraftSessionState,
    DraftTargetRequest,
    DraftTargetView,
    DraftUtilityRequest,
)
from app.features.draft.models import (
    DraftPick,
    DraftPickEvent,
    DraftRecommendationSnapshot as DraftRecommendationSnapshotModel,
    DraftSession,
    DraftTarget as DraftTargetModel,
)
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer
from app.services.draft.utility import calculate_draft_utility


def _next_overall_pick(picks: list[DraftPick]) -> int:
    selected = {pick.overall_pick for pick in picks if pick.selected_player_id is not None}
    overall_pick = 1
    while overall_pick in selected:
        overall_pick += 1
    return overall_pick


def _pick_slot(overall_pick: int, total_teams: int) -> tuple[int, int]:
    round_number = (overall_pick - 1) // total_teams + 1
    pick_in_round = (overall_pick - 1) % total_teams + 1
    team_slot = pick_in_round if round_number % 2 else total_teams - pick_in_round + 1
    return round_number, team_slot


async def _locked_session(session: AsyncSession, session_id: str) -> DraftSession:
    draft_session = await session.scalar(
        select(DraftSession).where(DraftSession.id == session_id).with_for_update()
    )
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    return draft_session


async def _session_state(session: AsyncSession, draft_session: DraftSession) -> DraftSessionState:
    picks = list((await session.scalars(
        select(DraftPick)
        .where(DraftPick.session_id == draft_session.id)
        .order_by(DraftPick.overall_pick)
    )).all())
    targets = list((await session.scalars(
        select(DraftTargetModel)
        .where(DraftTargetModel.session_id == draft_session.id)
        .order_by(DraftTargetModel.player_id)
    )).all())
    snapshot = await session.scalar(
        select(DraftRecommendationSnapshotModel)
        .where(DraftRecommendationSnapshotModel.session_id == draft_session.id)
        .order_by(DraftRecommendationSnapshotModel.session_version.desc())
        .limit(1)
    )
    return DraftSessionState(
        session_id=draft_session.id,
        league_key=draft_session.league_key,
        season=draft_session.season,
        manager_team_key=draft_session.manager_team_key,
        draft_position=draft_session.draft_position,
        total_teams=draft_session.total_teams,
        rounds=draft_session.rounds,
        status=draft_session.status,
        mode=draft_session.mode,
        version=draft_session.version,
        next_overall_pick=_next_overall_pick(picks),
        picks=[DraftPickView(
            overall_pick=pick.overall_pick,
            round_number=pick.round_number,
            team_slot=pick.team_slot,
            team_key=pick.team_key,
            selected_player_id=pick.selected_player_id,
            source=pick.source,
            picked_at=pick.picked_at.isoformat() if pick.picked_at else None,
        ) for pick in picks],
        targets=[DraftTargetView(
            player_id=target.player_id,
            status=target.status,
            note=target.note,
        ) for target in targets],
        latest_recommendation=snapshot.response if snapshot else None,
        recommendation_version=snapshot.session_version if snapshot else None,
    )


async def _record_recommendation_snapshot(
    session: AsyncSession,
    draft_session: DraftSession,
) -> None:
    picks = list((await session.scalars(
        select(DraftPick)
        .where(
            DraftPick.session_id == draft_session.id,
            DraftPick.selected_player_id.is_not(None),
        )
        .order_by(DraftPick.overall_pick)
    )).all())
    drafted_ids = [pick.selected_player_id for pick in picks if pick.selected_player_id is not None]
    all_player_ids = list((await session.scalars(
        select(LeaguePlayer.player_identity_id)
        .where(LeaguePlayer.league_key == draft_session.league_key)
        .order_by(LeaguePlayer.player_identity_id)
    )).all())
    drafted_set = set(drafted_ids)
    available_ids = [player_id for player_id in all_player_ids if player_id not in drafted_set]
    input_state = {
        "session_id": draft_session.id,
        "session_version": draft_session.version,
        "league_key": draft_session.league_key,
        "season": draft_session.season,
        "manager_team_key": draft_session.manager_team_key,
        "draft_position": draft_session.draft_position,
        "total_teams": draft_session.total_teams,
        "rounds": draft_session.rounds,
        "mode": draft_session.mode,
        "team_slots": draft_session.team_slots,
        "drafted_player_ids": drafted_ids,
        "available_player_ids": available_ids,
        "picks": [{
            "overall_pick": pick.overall_pick,
            "round_number": pick.round_number,
            "team_slot": pick.team_slot,
            "team_key": pick.team_key,
            "selected_player_id": pick.selected_player_id,
            "source": pick.source,
            "picked_at": pick.picked_at.isoformat() if pick.picked_at else None,
            "source_evidence": pick.source_evidence,
        } for pick in picks],
        "available_player_count": len(available_ids),
        "pick_count": len(picks),
    }

    if not available_ids:
        response = {
            "status": "draft_complete",
            "recommendation": None,
            "reason_code": "NO_AVAILABLE_PLAYERS",
            "message": "No unselected Yahoo league-pool players remain.",
        }
        recommendation_player_id = None
    else:
        next_overall = _next_overall_pick(picks)
        manager_round = next((
            round_number
            for round_number in range(1, draft_session.rounds + 1)
            if ((round_number - 1) * draft_session.total_teams
                + (draft_session.draft_position if round_number % 2
                   else draft_session.total_teams - draft_session.draft_position + 1)) >= next_overall
        ), None)
        if manager_round is None:
            response = {
                "status": "draft_complete",
                "recommendation": None,
                "reason_code": "DRAFT_ROUNDS_COMPLETE",
                "message": "The configured draft rounds are complete.",
            }
            recommendation_player_id = None
        else:
            utility_request = DraftUtilityRequest(
                league_key=draft_session.league_key,
                team_key=draft_session.manager_team_key,
                season=draft_session.season,
                drafted_player_ids=drafted_ids,
                available_player_ids=available_ids,
                draft_position=draft_session.draft_position,
                round_number=manager_round,
                total_teams=draft_session.total_teams,
                recent_pick_player_ids=drafted_ids[-10:],
                mode=draft_session.mode,
            )
            result = await calculate_draft_utility(session, utility_request)
            response = result.model_dump(mode="json")
            recommendation_player_id = (
                result.best_pick.player_identity_id if result.best_pick else None
            )

    session.add(DraftRecommendationSnapshotModel(
        session_id=draft_session.id,
        session_version=draft_session.version,
        recommendation_player_id=recommendation_player_id,
        input_state=input_state,
        response=response,
    ))


async def create_draft_session(
    session: AsyncSession,
    request: DraftSessionCreateRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        league = await session.get(League, request.league_key)
        if league is None:
            raise HTTPException(status_code=404, detail="Imported Yahoo league was not found")
        settings = await session.get(LeagueSettings, request.league_key)
        if settings is None:
            raise HTTPException(status_code=409, detail="Imported Yahoo league settings are required")
        teams = list((await session.scalars(
            select(Team).where(Team.league_key == request.league_key)
        )).all())
        team_keys = {team.team_key for team in teams}
        if len(teams) != request.total_teams or set(request.team_slots) != team_keys:
            raise HTTPException(
                status_code=422,
                detail="team_slots must map every imported Yahoo team and total_teams must match",
            )
        if request.manager_team_key not in team_keys:
            raise HTTPException(status_code=404, detail="Manager team was not found in the selected league")
        if league.season is not None and str(league.season) != request.season[:4]:
            raise HTTPException(status_code=422, detail="season does not match the imported Yahoo league")

        draft_session = DraftSession(
            id=str(uuid4()),
            league_key=request.league_key,
            season=request.season,
            manager_team_key=request.manager_team_key,
            draft_position=request.draft_position,
            total_teams=request.total_teams,
            rounds=request.rounds,
            status="active",
            mode=request.mode,
            team_slots=request.team_slots,
            version=0,
        )
        session.add(draft_session)
        await session.flush()
        await _record_recommendation_snapshot(session, draft_session)
        state = await _session_state(session, draft_session)
    return DraftSessionEventResult(state=state, event="created")


async def get_draft_session(session: AsyncSession, session_id: str) -> DraftSessionState:
    draft_session = await session.get(DraftSession, session_id)
    if draft_session is None:
        raise HTTPException(status_code=404, detail="Draft session was not found")
    return await _session_state(session, draft_session)


async def _validate_player(
    session: AsyncSession,
    draft_session: DraftSession,
    player_id: int,
    *,
    excluding_pick: int | None = None,
) -> None:
    in_pool = await session.scalar(select(LeaguePlayer.player_identity_id).where(
        LeaguePlayer.league_key == draft_session.league_key,
        LeaguePlayer.player_identity_id == player_id,
    ))
    if in_pool is None:
        raise HTTPException(status_code=422, detail="Selected player is not in the imported Yahoo league pool")
    already_selected = await session.scalar(select(DraftPick.overall_pick).where(
        DraftPick.session_id == draft_session.id,
        DraftPick.selected_player_id == player_id,
        DraftPick.overall_pick != (excluding_pick or -1),
    ))
    if already_selected is not None:
        raise HTTPException(status_code=409, detail="Selected player is already drafted in this session")


def _check_version(draft_session: DraftSession, expected_version: int) -> None:
    if draft_session.version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "reason_code": "STALE_SESSION_VERSION",
                "expected_version": expected_version,
                "current_version": draft_session.version,
            },
        )
    if draft_session.status != "active":
        raise HTTPException(status_code=409, detail="Draft session is not active")


async def _finish_update(
    session: AsyncSession,
    draft_session: DraftSession,
    *,
    overall_pick: int,
    event_type: str,
    previous_player_id: int | None,
    selected_player_id: int | None,
    source: str,
    evidence: dict,
) -> DraftSessionEventResult:
    draft_session.version += 1
    draft_session.updated_at = datetime.now(timezone.utc)
    session.add(DraftPickEvent(
        session_id=draft_session.id,
        overall_pick=overall_pick,
        event_type=event_type,
        previous_player_id=previous_player_id,
        selected_player_id=selected_player_id,
        source=source,
        version_after=draft_session.version,
        evidence=evidence,
    ))
    await session.flush()
    await _record_recommendation_snapshot(session, draft_session)
    state = await _session_state(session, draft_session)
    return DraftSessionEventResult(state=state, event=event_type)


async def record_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        existing = await session.get(DraftPick, (session_id, overall_pick))
        if existing is not None and existing.selected_player_id == request.selected_player_id:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version)
        picks = list((await session.scalars(
            select(DraftPick).where(DraftPick.session_id == session_id)
        )).all())
        next_pick = _next_overall_pick(picks)
        if overall_pick != next_pick:
            raise HTTPException(
                status_code=409,
                detail={"reason_code": "OUT_OF_ORDER_PICK", "expected_overall_pick": next_pick},
            )
        if overall_pick > draft_session.total_teams * draft_session.rounds:
            raise HTTPException(status_code=409, detail="Pick exceeds the configured draft rounds")
        await _validate_player(session, draft_session, request.selected_player_id)
        round_number, team_slot = _pick_slot(overall_pick, draft_session.total_teams)
        team_key = next((key for key, slot in draft_session.team_slots.items() if slot == team_slot), None)
        if team_key is None:
            raise HTTPException(status_code=409, detail="Draft slot mapping is incomplete")
        picked_at = request.picked_at or datetime.now(timezone.utc)
        if picked_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="picked_at must include a timezone")
        if existing is None:
            existing = DraftPick(
                session_id=session_id,
                overall_pick=overall_pick,
                round_number=round_number,
                team_slot=team_slot,
                team_key=team_key,
                selected_player_id=request.selected_player_id,
                source=request.source,
                picked_at=picked_at,
                source_evidence=request.evidence,
            )
            session.add(existing)
        else:
            existing.round_number = round_number
            existing.team_slot = team_slot
            existing.team_key = team_key
            existing.selected_player_id = request.selected_player_id
            existing.source = request.source
            existing.picked_at = picked_at
            existing.source_evidence = request.evidence
        result = await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="recorded",
            previous_player_id=None,
            selected_player_id=request.selected_player_id,
            source=request.source,
            evidence=request.evidence,
        )
    return result


async def correct_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        pick = await session.get(DraftPick, (session_id, overall_pick))
        if pick is None or pick.selected_player_id is None:
            raise HTTPException(status_code=404, detail="Recorded draft pick was not found")
        if pick.selected_player_id == request.selected_player_id:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version)
        await _validate_player(
            session,
            draft_session,
            request.selected_player_id,
            excluding_pick=overall_pick,
        )
        previous_player_id = pick.selected_player_id
        picked_at = request.picked_at or datetime.now(timezone.utc)
        if picked_at.tzinfo is None:
            raise HTTPException(status_code=422, detail="picked_at must include a timezone")
        pick.selected_player_id = request.selected_player_id
        pick.source = request.source
        pick.picked_at = picked_at
        pick.source_evidence = request.evidence
        return await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="corrected",
            previous_player_id=previous_player_id,
            selected_player_id=request.selected_player_id,
            source=request.source,
            evidence=request.evidence,
        )


async def undo_draft_pick(
    session: AsyncSession,
    session_id: str,
    overall_pick: int,
    request: DraftPickUndoRequest,
) -> DraftSessionEventResult:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        pick = await session.get(DraftPick, (session_id, overall_pick))
        if pick is None or pick.selected_player_id is None:
            return DraftSessionEventResult(state=await _session_state(session, draft_session), event="unchanged")
        _check_version(draft_session, request.expected_version)
        picks = list((await session.scalars(
            select(DraftPick).where(DraftPick.session_id == session_id)
        )).all())
        latest_selected = max(
            (item.overall_pick for item in picks if item.selected_player_id is not None),
            default=0,
        )
        if overall_pick != latest_selected:
            raise HTTPException(status_code=409, detail="Only the latest recorded pick can be undone")
        previous_player_id = pick.selected_player_id
        pick.selected_player_id = None
        pick.picked_at = None
        pick.source = request.source
        pick.source_evidence = request.evidence
        return await _finish_update(
            session,
            draft_session,
            overall_pick=overall_pick,
            event_type="undone",
            previous_player_id=previous_player_id,
            selected_player_id=None,
            source=request.source,
            evidence=request.evidence,
        )


async def put_draft_target(
    session: AsyncSession,
    session_id: str,
    player_id: int,
    request: DraftTargetRequest,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        _check_version(draft_session, request.expected_version)
        if await session.scalar(select(LeaguePlayer.player_identity_id).where(
            LeaguePlayer.league_key == draft_session.league_key,
            LeaguePlayer.player_identity_id == player_id,
        )) is None:
            raise HTTPException(status_code=404, detail="Player is not in the imported Yahoo league pool")
        target = await session.get(DraftTargetModel, (session_id, player_id))
        if target is None:
            target = DraftTargetModel(
                session_id=session_id,
                player_id=player_id,
                status=request.status,
                note=request.note,
            )
            session.add(target)
        else:
            target.status = request.status
            target.note = request.note
        draft_session.version += 1
        draft_session.updated_at = datetime.now(timezone.utc)
        await session.flush()
        await _record_recommendation_snapshot(session, draft_session)
        return await _session_state(session, draft_session)


async def delete_draft_target(
    session: AsyncSession,
    session_id: str,
    player_id: int,
    expected_version: int,
) -> DraftSessionState:
    async with session.begin():
        draft_session = await _locked_session(session, session_id)
        _check_version(draft_session, expected_version)
        target = await session.get(DraftTargetModel, (session_id, player_id))
        if target is not None:
            await session.delete(target)
            draft_session.version += 1
            draft_session.updated_at = datetime.now(timezone.utc)
            await session.flush()
            await _record_recommendation_snapshot(session, draft_session)
        return await _session_state(session, draft_session)
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.draft.contracts import (
    DraftMetricsResult,
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
    DraftSessionEventResult,
    DraftSessionState,
    DraftTargetRequest,
    DraftUtilityRequest,
    DraftUtilityResult,
)
from app.services.draft.metrics import recompute_draft_metrics
from app.services.draft.sessions import (
    correct_draft_pick,
    create_draft_session,
    delete_draft_target,
    get_draft_session,
    put_draft_target,
    record_draft_pick,
    undo_draft_pick,
)
from app.services.draft.utility import calculate_draft_utility

router = APIRouter(prefix="/api/v1/draft", tags=["Draft Readiness"])
v2_router = APIRouter(prefix="/api/v2/draft", tags=["Draft Sessions"])


@router.post("/metrics", response_model=DraftMetricsResult)
async def build_draft_metrics(
    league_key: str = Query(min_length=1),
    season: str = Query(pattern=r"^\d{4}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> DraftMetricsResult:
    return await recompute_draft_metrics(session, league_key, season)


@router.post("/utility", response_model=DraftUtilityResult)
async def draft_utility(
    request: DraftUtilityRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftUtilityResult:
    await recompute_draft_metrics(session, request.league_key, request.season)
    return await calculate_draft_utility(session, request)


@v2_router.post("/sessions", response_model=DraftSessionEventResult, status_code=201)
async def create_session(
    request: DraftSessionCreateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await create_draft_session(session, request)


@v2_router.get("/sessions/{session_id}", response_model=DraftSessionState)
async def read_session(
    session_id: str,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await get_draft_session(session, session_id)


@v2_router.post(
    "/sessions/{session_id}/picks/{overall_pick}",
    response_model=DraftSessionEventResult,
)
async def add_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await record_draft_pick(session, session_id, overall_pick, request)


@v2_router.put(
    "/sessions/{session_id}/picks/{overall_pick}",
    response_model=DraftSessionEventResult,
)
async def replace_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await correct_draft_pick(session, session_id, overall_pick, request)


@v2_router.post(
    "/sessions/{session_id}/picks/{overall_pick}/undo",
    response_model=DraftSessionEventResult,
)
async def remove_latest_pick(
    session_id: str,
    overall_pick: int,
    request: DraftPickUndoRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionEventResult:
    return await undo_draft_pick(session, session_id, overall_pick, request)


@v2_router.put("/sessions/{session_id}/targets/{player_id}", response_model=DraftSessionState)
async def mark_target(
    session_id: str,
    player_id: int,
    request: DraftTargetRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await put_draft_target(session, session_id, player_id, request)


@v2_router.delete("/sessions/{session_id}/targets/{player_id}", response_model=DraftSessionState)
async def unmark_target(
    session_id: str,
    player_id: int,
    expected_version: int = Query(ge=0),
    session: AsyncSession = Depends(get_session),
) -> DraftSessionState:
    return await delete_draft_target(session, session_id, player_id, expected_version)

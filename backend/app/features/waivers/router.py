from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.features.leagues.models import Team
from app.features.waivers.admission import heavy_read_slot, until_client_leaves
from app.features.waivers.contracts import (
    Mode, RefreshRequest, RefreshStatus, TransactionAnalysis, WaiverBoard, WaiverImpact,
)
from app.features.waivers.refresh import refresh_coordinator
from app.features.waivers.service import get_waivers, get_impact, get_transactions

router = APIRouter(prefix="/api/v1/waivers", tags=["Waiver Center"])
# Route-level dependencies resolve before parameter dependencies, so a queued heavy read holds no database session.
HEAVY_READ = [Depends(heavy_read_slot)]


@router.post("/refresh", response_model=RefreshStatus, status_code=202)
async def start_refresh(
    body: RefreshRequest | None = None,
    session: AsyncSession = Depends(get_session),
) -> RefreshStatus:
    """The one deliberate mutation: start (or rejoin) the orchestrated Yahoo + NBA refresh."""
    job, already_running = await refresh_coordinator.start(retry_failed=bool(body and body.retry_failed))
    status = await refresh_coordinator.status(session)
    status.job, status.already_running = job, already_running
    return status


@router.get("/refresh", response_model=RefreshStatus)
async def read_refresh(session: AsyncSession = Depends(get_session)) -> RefreshStatus:
    """Refresh progress and persisted evidence freshness; database-only and safe to poll."""
    return await refresh_coordinator.status(session)


async def configured_team(
    league_key: str | None = Query(default=None, min_length=1),
    team_key: str | None = Query(default=None, min_length=1),
    session: AsyncSession = Depends(get_session),
) -> Team:
    manager_key = get_settings().waiver_manager_team_key
    if team_key is not None and team_key != manager_key:
        raise HTTPException(422, "Waiver Command Center analyzes only the configured manager team")
    team = await session.get(Team, manager_key)
    if team is None:
        raise HTTPException(404, "Configured waiver manager team is not in the persisted Yahoo teams")
    if league_key is not None and league_key != team.league_key:
        raise HTTPException(422, "League must match the configured waiver manager team")
    return team


@router.get("", response_model=WaiverBoard, dependencies=HEAVY_READ)
async def read_waivers(
    request: Request,
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverBoard:
    board = await until_client_leaves(request, get_waivers(session, team.league_key, team.team_key, mode))
    board.team_name = team.team_name
    return board


@router.get("/replacements", response_model=WaiverBoard, dependencies=HEAVY_READ)
async def read_replacements(
    request: Request,
    drop_player_id: int = Query(...),
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverBoard:
    board = await until_client_leaves(request, get_waivers(session, team.league_key, team.team_key, mode, drop_player_id))
    board.team_name = team.team_name
    return board


@router.get("/transactions", response_model=TransactionAnalysis, dependencies=HEAVY_READ)
async def read_transactions(
    request: Request,
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> TransactionAnalysis:
    analysis = await until_client_leaves(request, get_transactions(session, team.league_key, team.team_key, mode))
    analysis.team_name = team.team_name
    return analysis


@router.get("/{player_id}/impact", response_model=WaiverImpact, dependencies=HEAVY_READ)
async def read_impact(
    request: Request,
    player_id: int,
    drop_player_id: int | None = None,
    mode: Mode = "this_week",
    team: Team = Depends(configured_team),
    session: AsyncSession = Depends(get_session),
) -> WaiverImpact:
    return await until_client_leaves(request,
        get_impact(session, team.league_key, team.team_key, player_id, drop_player_id, mode))

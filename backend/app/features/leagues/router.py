from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.features.leagues.contracts import LeagueImportResult, LeagueResponse, LeagueTeamResponse
from app.features.leagues.service import get_imported_leagues, import_manager_leagues
from app.services.yahoo.normalization import normalize_yahoo_settings

router = APIRouter(prefix="/api/v1/leagues", tags=["Leagues"])
single_league_router = APIRouter(prefix="/api/v1/league", tags=["Leagues"])


@router.post("/import", response_model=LeagueImportResult)
async def import_leagues(
    session: AsyncSession = Depends(get_session),
) -> LeagueImportResult:
    return await import_manager_leagues(session, get_settings())


def _response(league) -> LeagueResponse:
    settings = league.settings
    scoring_settings, roster_positions = (
        normalize_yahoo_settings(league.league_key, settings.source_payload)
        if settings
        else ({}, [])
    )
    return LeagueResponse(
        league_key=league.league_key,
        league_name=league.league_name,
        season=league.season,
        scoring_settings=scoring_settings,
        roster_positions=roster_positions,
        teams=[
            LeagueTeamResponse(team_key=team.team_key, team_name=team.team_name)
            for team in league.teams
        ],
    )


@router.get("", response_model=list[LeagueResponse])
async def list_leagues(
    session: AsyncSession = Depends(get_session),
) -> list[LeagueResponse]:
    return [_response(league) for league in await get_imported_leagues(session)]


@single_league_router.get("", response_model=LeagueResponse)
async def get_league(
    league_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> LeagueResponse:
    leagues = await get_imported_leagues(session, league_key)
    if not leagues:
        raise HTTPException(status_code=404, detail="No imported Yahoo league was found")
    if league_key is None and len(leagues) > 1:
        raise HTTPException(
            status_code=409,
            detail="Multiple leagues are imported; specify the league_key query parameter",
        )
    return _response(leagues[0])
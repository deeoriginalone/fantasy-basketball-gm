from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.features.players.contracts import (
    FantasyRosterResponse,
    PlayerIdentityResponse,
    PlayerImportResult,
    RosterPlayerResponse,
)
from app.features.players.service import (
    get_player_identity,
    import_yahoo_players,
    list_persisted_rosters,
    list_player_identities,
)

router = APIRouter(prefix="/api/v1", tags=["Players"])


@router.post("/players/import", response_model=PlayerImportResult)
async def import_players(
    league_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> PlayerImportResult:
    return await import_yahoo_players(session, get_settings(), league_key)


@router.get("/players", response_model=list[PlayerIdentityResponse])
async def get_players(
    session: AsyncSession = Depends(get_session),
) -> list[PlayerIdentityResponse]:
    return [
        PlayerIdentityResponse.model_validate(player)
        for player in await list_player_identities(session)
    ]


@router.get("/player/{internal_id}", response_model=PlayerIdentityResponse)
async def get_player(
    internal_id: int,
    session: AsyncSession = Depends(get_session),
) -> PlayerIdentityResponse:
    player = await get_player_identity(session, internal_id)
    if player is None:
        raise HTTPException(status_code=404, detail="Player identity was not found")
    return PlayerIdentityResponse.model_validate(player)


@router.get("/rosters", response_model=list[FantasyRosterResponse])
async def get_rosters(
    league_key: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> list[FantasyRosterResponse]:
    rosters = await list_persisted_rosters(session)
    return [
        FantasyRosterResponse(
            league_key=team.league_key,
            team_key=team.team_key,
            team_name=team.team_name,
            players=[
                RosterPlayerResponse(
                    id=entry.identity.id,
                    yahoo_player_id=entry.yahoo_player_id,
                    player_name=entry.identity.player_name,
                    team=entry.identity.team,
                    position=entry.identity.position,
                    status=entry.identity.status,
                    roster_position=entry.roster_position,
                )
                for entry in team.roster_entries
            ],
        )
        for team in rosters
        if league_key is None or team.league_key == league_key
    ]
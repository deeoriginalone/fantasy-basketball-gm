from datetime import datetime, timezone
import logging

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.features.leagues.contracts import LeagueImportResult, LeagueImportSummary
from app.features.leagues.models import League, LeagueSettings, Team
from app.services.yahoo.auth import YahooAuthService
from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.game_keys import discover_active_nba_game_key
from app.services.yahoo.leagues import fetch_user_leagues

logger = logging.getLogger(__name__)


async def import_manager_leagues(
    session: AsyncSession,
    settings: Settings,
    client: YahooFantasyClient | None = None,
) -> LeagueImportResult:
    access_token = await YahooAuthService(settings).access_token(session)
    await session.commit()
    yahoo_client = client or YahooFantasyClient()
    game_key = await discover_active_nba_game_key(yahoo_client, access_token)
    imports = await fetch_user_leagues(yahoo_client, access_token, game_key)
    imported_at = datetime.now(timezone.utc)
    results: list[LeagueImportSummary] = []
    imported_team_count = 0

    try:
        async with session.begin():
            for normalized in imports:
                league_values = {
                    "league_key": normalized.league_key,
                    "game_key": game_key,
                    "league_name": normalized.league_name,
                    "season": normalized.season,
                    "source_payload": normalized.source_league,
                    "imported_at": imported_at,
                }
                league_statement = insert(League).values(**league_values)
                league_statement = league_statement.on_conflict_do_update(
                    index_elements=[League.league_key],
                    set_={key: value for key, value in league_values.items() if key != "league_key"},
                )
                await session.execute(league_statement)

                settings_values = {
                    "league_key": normalized.league_key,
                    "scoring_settings": normalized.scoring_settings,
                    "roster_positions": normalized.roster_positions,
                    "source_payload": normalized.source_settings,
                    "imported_at": imported_at,
                }
                settings_statement = insert(LeagueSettings).values(**settings_values)
                settings_statement = settings_statement.on_conflict_do_update(
                    index_elements=[LeagueSettings.league_key],
                    set_={key: value for key, value in settings_values.items() if key != "league_key"},
                )
                await session.execute(settings_statement)
                await session.execute(
                    delete(Team).where(Team.league_key == normalized.league_key)
                )
                if normalized.teams:
                    await session.execute(
                        insert(Team).values(
                            [
                                {
                                    "team_key": team.team_key,
                                    "league_key": normalized.league_key,
                                    "team_name": team.team_name,
                                    "source_payload": team.source_payload,
                                    "imported_at": imported_at,
                                }
                                for team in normalized.teams
                            ]
                        )
                    )
                imported_team_count += len(normalized.teams)
                results.append(
                    LeagueImportSummary(
                        league_key=normalized.league_key,
                        league_name=normalized.league_name,
                        season=normalized.season,
                        team_count=len(normalized.teams),
                    )
                )
    except SQLAlchemyError as error:
        logger.exception(
            "Unable to persist Yahoo league import",
            extra={"event": "yahoo_import_persistence_failed", "game_key": game_key},
        )
        raise HTTPException(status_code=502, detail="Yahoo league data could not be persisted") from error

    logger.info(
        "Yahoo league import completed",
        extra={
            "event": "yahoo_league_import_completed",
            "game_key": game_key,
            "league_count": len(results),
            "team_count": imported_team_count,
        },
    )
    return LeagueImportResult(
        game_key=game_key,
        imported_count=len(results),
        team_count=imported_team_count,
        leagues=results,
    )


async def get_imported_leagues(
    session: AsyncSession,
    league_key: str | None = None,
) -> list[League]:
    statement = (
        select(League)
        .options(selectinload(League.settings), selectinload(League.teams))
        .order_by(League.season.desc().nullslast(), League.league_key)
    )
    if league_key:
        statement = statement.where(League.league_key == league_key)
    result = await session.scalars(statement)
    return list(result.all())
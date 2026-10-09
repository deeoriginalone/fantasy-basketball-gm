from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, pool_pre_ping=True)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


async def initialize_schema() -> None:
    from app.features.draft.models import DraftPlayerMetric
    from app.features.leagues.models import League, LeagueSettings, Team
    from app.features.nba.models import (
        NbaGame,
        NbaPlayer,
        NbaPlayerSeasonStats,
        NbaTeam,
        PlayerGameLog,
        PlayerSchedule,
    )
    from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
    from app.features.yahoo.models import YahooCredential

    _ = (
        DraftPlayerMetric,
        League,
        LeagueSettings,
        Team,
        FantasyTeam,
        LeaguePlayer,
        PlayerIdentity,
        RosterEntry,
        YahooCredential,
        NbaTeam,
        NbaPlayer,
        NbaPlayerSeasonStats,
        NbaGame,
        PlayerGameLog,
        PlayerSchedule,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN home_team_id DROP NOT NULL"))
        await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN away_team_id DROP NOT NULL"))
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
    from app.core.migrations import MIGRATED_TABLES, upgrade
    from app.features.draft.models import (
        DraftPick,
        DraftPickEvent,
        DraftRecommendationSnapshot,
        DraftSession,
        DraftTarget,
        DraftMarketData,
        DraftMarketProviderSnapshot,
        DraftMarketSyncRun,
        DraftMarketUnmatchedRecord,
        DraftPlayerMetric,
    )
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
        DraftSession,
        DraftPick,
        DraftPickEvent,
        DraftRecommendationSnapshot,
        DraftTarget,
        DraftPlayerMetric,
        DraftMarketData,
        DraftMarketProviderSnapshot,
        DraftMarketSyncRun,
        DraftMarketUnmatchedRecord,
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
        legacy_tables = [
            table for table in Base.metadata.sorted_tables if table.name not in MIGRATED_TABLES
        ]
        await connection.run_sync(lambda sync_connection: Base.metadata.create_all(
            sync_connection,
            tables=legacy_tables,
        ))
        await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN home_team_id DROP NOT NULL"))
        await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN away_team_id DROP NOT NULL"))
        for column in (
            "provider_records_fetched",
            "matched_players",
            "ambiguous_matches",
            "unmatched_players",
            "adp_coverage_percentage",
            "rank_coverage_percentage",
            "draft_frequency_coverage_percentage",
            "stale_records",
        ):
            await connection.execute(text(
                f"ALTER TABLE draft_market_sync_runs ALTER COLUMN {column} DROP NOT NULL"
            ))
        await upgrade(connection)
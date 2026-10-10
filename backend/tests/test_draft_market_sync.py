import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.draft.models import (
    DraftMarketData,
    DraftMarketProviderSnapshot,
    DraftMarketSyncRun,
    DraftMarketUnmatchedRecord,
)
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import PlayerIdentity
from app.services.draft.market_providers.base import DraftMarketRecord
from app.services.draft.market_providers.fantrax import FANTRAX_SOURCE
from app.services.draft.market_sync import record_market_sync_failure, sync_market_data
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_market_sync_is_idempotent_and_provider_failure_preserves_prior_data() -> None:
    assert TEST_DATABASE_URL
    database_name = (make_url(TEST_DATABASE_URL).database or "").lower()
    assert "test" in database_name, "TEST_DATABASE_URL must name an isolated database containing 'test'"

    suffix = uuid4().hex[:12]
    yahoo_player_id = f"sync-test-{suffix}"
    test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    fetched_at = datetime(2026, 10, 10, tzinfo=timezone.utc)

    class FixtureProvider:
        name = FANTRAX_SOURCE

        def __init__(self, adp: float):
            self.adp = adp

        async def fetch(self, season: str) -> list[DraftMarketRecord]:
            return [DraftMarketRecord(
                internal_player_id=None,
                source_player_id="03e75",
                player_name="Jokic, Nikola",
                team="DEN",
                positions=("C",),
                adp=self.adp,
                draft_rank=None,
                xrank=None,
                draft_frequency=None,
                sample_size=None,
                source=FANTRAX_SOURCE,
                season=season,
                fetched_at=fetched_at,
            )]

    class FailingProvider:
        name = FANTRAX_SOURCE

        async def fetch(self, season: str) -> list[DraftMarketRecord]:
            raise TimeoutError("fixture timeout")

    class PartiallyUnmatchedProvider:
        name = FANTRAX_SOURCE

        async def fetch(self, season: str) -> list[DraftMarketRecord]:
            matched = await FixtureProvider(1.6).fetch(season)
            return [*matched, DraftMarketRecord(
                internal_player_id=None,
                source_player_id="no-team-player",
                player_name="Free Agent Example",
                team=None,
                positions=("C",),
                adp=250.0,
                draft_rank=None,
                xrank=None,
                draft_frequency=None,
                sample_size=None,
                source=FANTRAX_SOURCE,
                season=season,
                fetched_at=fetched_at,
            )]

    async def scenario() -> None:
        async with test_engine.begin() as connection:
            await create_test_schema(connection)
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
        identity_id = None
        sync_run_started_at = []
        try:
            async with session_factory() as session:
                identity_table = PlayerIdentity.__table__
                identity_id = await session.scalar(
                    identity_table.insert().values(
                        yahoo_player_id=yahoo_player_id,
                        player_name="Nikola Jokic",
                        team="DEN",
                        position="C",
                        status=None,
                    ).returning(identity_table.c.id)
                )
                await session.commit()

            async with session_factory() as session:
                first_started_at = datetime.now(timezone.utc)
                sync_run_started_at.append(first_started_at)
                async with session.begin():
                    first = await sync_market_data(
                        session, FixtureProvider(1.44), "2026-27", started_at=first_started_at
                    )
            assert first["provider_records_fetched"] == 1
            assert first["matched_players"] == 1
            assert first["ambiguous_matches"] == 0
            assert first["unmatched_players"] == 0

            async with session_factory() as session:
                second_started_at = datetime.now(timezone.utc)
                sync_run_started_at.append(second_started_at)
                async with session.begin():
                    second = await sync_market_data(
                        session, FixtureProvider(1.5), "2026-27", started_at=second_started_at
                    )
                rows = list((await session.execute(
                    select(DraftMarketData.__table__).where(
                        DraftMarketData.__table__.c.player_id == identity_id,
                        DraftMarketData.__table__.c.source == FANTRAX_SOURCE,
                    )
                )).mappings().all())
                snapshots = list((await session.execute(
                    select(DraftMarketProviderSnapshot.__table__).where(
                        DraftMarketProviderSnapshot.__table__.c.player_id == identity_id,
                        DraftMarketProviderSnapshot.__table__.c.source == FANTRAX_SOURCE,
                    )
                )).mappings().all())
            assert second["matched_players"] == 1
            assert len(rows) == 1
            assert rows[0]["adp"] == 1.5
            assert len(snapshots) == 1
            assert snapshots[0]["source_player_id"] == "03e75"
            assert snapshots[0]["positions"] == ["C"]

            async with session_factory() as session:
                third_started_at = datetime.now(timezone.utc)
                sync_run_started_at.append(third_started_at)
                async with session.begin():
                    third = await sync_market_data(
                        session,
                        PartiallyUnmatchedProvider(),
                        "2026-27",
                        started_at=third_started_at,
                    )
                unresolved = (await session.execute(
                    select(DraftMarketUnmatchedRecord.__table__).where(
                        DraftMarketUnmatchedRecord.__table__.c.source_player_id == "no-team-player",
                        DraftMarketUnmatchedRecord.__table__.c.season == "2026-27",
                        DraftMarketUnmatchedRecord.__table__.c.source == FANTRAX_SOURCE,
                    )
                )).mappings().one()
            assert third["matched_players"] == 1
            assert third["unmatched_by_reason"] == {"source_team_missing": 1}
            assert unresolved["rejection_reason"] == "source_team_missing"
            assert unresolved["adp"] == 250.0

            async with session_factory() as session:
                failed_started_at = datetime.now(timezone.utc)
                sync_run_started_at.append(failed_started_at)
                with pytest.raises(TimeoutError):
                    async with session.begin():
                        await sync_market_data(
                            session,
                            FailingProvider(),
                            "2026-27",
                            started_at=failed_started_at,
                        )
                async with session.begin():
                    await record_market_sync_failure(
                        session,
                        "2026-27",
                        FANTRAX_SOURCE,
                        failed_started_at,
                        TimeoutError("fixture timeout contains no persisted detail"),
                    )
                retained = await session.scalar(select(DraftMarketData.__table__.c.adp).where(
                    DraftMarketData.__table__.c.player_id == identity_id,
                    DraftMarketData.__table__.c.source == FANTRAX_SOURCE,
                ))
                failed_run = (await session.execute(
                    select(DraftMarketSyncRun.__table__).where(
                        DraftMarketSyncRun.__table__.c.started_at == failed_started_at
                    )
                )).mappings().one()
            assert retained == 1.6
            assert failed_run["status"] == "failed"
            assert failed_run["error_type"] == "TimeoutError"
            assert failed_run["provider_records_fetched"] is None
        finally:
            if identity_id is not None:
                async with session_factory() as session:
                    async with session.begin():
                        await session.execute(delete(DraftMarketSyncRun).where(
                            DraftMarketSyncRun.started_at.in_(sync_run_started_at),
                        ))
                        await session.execute(delete(DraftMarketProviderSnapshot).where(
                            DraftMarketProviderSnapshot.player_id == identity_id,
                        ))
                        await session.execute(delete(DraftMarketUnmatchedRecord).where(
                            DraftMarketUnmatchedRecord.source_player_id == "no-team-player",
                            DraftMarketUnmatchedRecord.season == "2026-27",
                            DraftMarketUnmatchedRecord.source == FANTRAX_SOURCE,
                        ))
                        await session.execute(delete(DraftMarketData).where(
                            DraftMarketData.player_id == identity_id,
                        ))
                        await session.execute(delete(PlayerIdentity).where(
                            PlayerIdentity.id == identity_id,
                        ))
            await test_engine.dispose()

    asyncio.run(scenario())
import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.draft.models import DraftMarketData
from app.features.players.models import PlayerIdentity
from app.services.draft.market_import import import_market_rows, parse_market_rows
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def test_parse_market_csv_rows_and_reject_bad_frequency() -> None:
    parsed = parse_market_rows(
        [{"player_id": "123", "adp": "24.5", "draft_rank": "20", "draft_frequency": "82.5"}],
        "2026-27",
        "manual",
    )
    assert parsed[0]["player_id"] == 123
    assert parsed[0]["adp"] == 24.5
    assert parsed[0]["draft_rank"] == 20
    assert parsed[0]["draft_frequency"] == 82.5
    assert parsed[0]["source"] == "manual"

    with pytest.raises(ValueError, match="draft_frequency must be at most 100"):
        parse_market_rows(
            [{"player_id": "123", "adp": "24", "draft_frequency": "101"}],
            "2026-27",
            "manual",
        )
    with pytest.raises(ValueError, match="adp must be finite"):
        parse_market_rows(
            [{"player_id": "123", "adp": "nan"}],
            "2026-27",
            "manual",
        )


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_market_upserts_by_player_season_source_without_touching_identity() -> None:
    assert TEST_DATABASE_URL
    database_name = (make_url(TEST_DATABASE_URL).database or "").lower()
    assert "test" in database_name, "TEST_DATABASE_URL must name an isolated database containing 'test'"

    yahoo_player_id = f"market-test-{uuid4().hex[:12]}"
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        identity_id = None
        try:
            async with session_factory() as session:
                identity = PlayerIdentity(
                    yahoo_player_id=yahoo_player_id,
                    player_name="Market Fixture Player",
                    team="BOS",
                    position="PG,SG",
                    status=None,
                )
                session.add(identity)
                await session.commit()
                identity_id = identity.id

                first = parse_market_rows(
                    [{"player_id": str(identity_id), "adp": "24.5", "draft_rank": "20", "draft_frequency": "82"}],
                    "2026-27",
                    "manual",
                )
                async with session.begin():
                    await import_market_rows(session, first)
                second = parse_market_rows(
                    [{"player_id": str(identity_id), "adp": "26", "draft_rank": "22", "draft_frequency": "85"}],
                    "2026-27",
                    "manual",
                )
                async with session.begin():
                    await import_market_rows(session, second)

                market_rows = list((await session.scalars(select(DraftMarketData))).all())
                unchanged_identity = await session.get(PlayerIdentity, identity_id)
                assert len(market_rows) == 1
                assert market_rows[0].adp == 26
                assert market_rows[0].draft_rank == 22
                assert market_rows[0].draft_frequency == 85
                assert unchanged_identity is not None
                assert unchanged_identity.yahoo_player_id == yahoo_player_id
                assert unchanged_identity.player_name == "Market Fixture Player"
                assert unchanged_identity.team == "BOS"
                assert unchanged_identity.position == "PG,SG"
        finally:
            if identity_id is not None:
                async with session_factory() as session:
                    async with session.begin():
                        await session.execute(delete(DraftMarketData).where(DraftMarketData.player_id == identity_id))
                        await session.execute(delete(PlayerIdentity).where(PlayerIdentity.id == identity_id))
            await engine.dispose()

    asyncio.run(scenario())

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

import app.core.database as database
from app.core.migrations import downgrade, upgrade
from app.main import app

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_draft_migration_up_down_up_uses_version_table_and_new_tables() -> None:
    assert TEST_DATABASE_URL
    base_url = make_url(TEST_DATABASE_URL)
    assert "test" in (base_url.database or "").lower()
    database_name = f"draft_migration_test_{uuid4().hex[:10]}"
    admin_engine = create_async_engine(base_url.set(database="postgres"), pool_pre_ping=True)
    test_engine = create_async_engine(base_url.set(database=database_name), pool_pre_ping=True)

    async def scenario() -> None:
        async with admin_engine.connect() as connection:
            autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
            await autocommit.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
        original_engine = database.engine
        database.engine = test_engine
        try:
            await database.initialize_schema()
            async with test_engine.connect() as connection:
                assert await connection.scalar(text(
                    "SELECT to_regclass('public.draft_sessions')"
                )) == "draft_sessions"
                assert await connection.scalar(text(
                    "SELECT revision FROM schema_migrations"
                )) == "0001_draft_persistence"

            async with test_engine.begin() as connection:
                await downgrade(connection)
                assert await connection.scalar(text(
                    "SELECT to_regclass('public.draft_sessions')"
                )) is None

            async def apply_revision() -> None:
                async with test_engine.begin() as connection:
                    await upgrade(connection)

            await asyncio.gather(apply_revision(), apply_revision())
            async with test_engine.connect() as connection:
                assert await connection.scalar(text(
                    "SELECT to_regclass('public.draft_targets')"
                )) == "draft_targets"
        finally:
            await test_engine.dispose()
            database.engine = original_engine
            async with admin_engine.connect() as connection:
                autocommit = await connection.execution_options(isolation_level="AUTOCOMMIT")
                await autocommit.exec_driver_sql(f'DROP DATABASE IF EXISTS "{database_name}"')
            await admin_engine.dispose()

    asyncio.run(scenario())
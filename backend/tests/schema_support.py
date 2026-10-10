from sqlalchemy.ext.asyncio import AsyncConnection

from app.core.database import Base
from app.core.migrations import MIGRATED_TABLES, upgrade
from app.main import app


async def create_test_schema(connection: AsyncConnection) -> None:
    legacy_tables = [
        table for table in Base.metadata.sorted_tables
        if table.name not in MIGRATED_TABLES
    ]
    await connection.run_sync(lambda sync: Base.metadata.create_all(
        sync,
        tables=legacy_tables,
    ))
    await upgrade(connection)
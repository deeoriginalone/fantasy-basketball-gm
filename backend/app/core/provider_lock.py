"""One provider import at a time, across processes, with no schema change.

A PostgreSQL session-level advisory lock is held on a dedicated connection for the duration of a
Yahoo/NBA import. The lock is released explicitly, or by PostgreSQL when the connection closes
(for example if the API process dies), so a crashed import never leaves it held.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.core.database import engine as default_engine

# Arbitrary constant identifying "provider import in progress" among this database's advisory locks.
PROVIDER_IMPORT_LOCK_KEY = 7_316_405_219_660_901_117


class ProviderImportBusy(RuntimeError):
    pass


BUSY_DETAIL = {
    "code": "PROVIDER_IMPORT_IN_PROGRESS",
    "message": "A waiver data refresh or another Yahoo/NBA import is already running. Wait for it to finish, then retry.",
}


class ProviderImportLock:
    def __init__(self, bind: AsyncEngine | None = None):
        self.bind = bind or default_engine
        self.connection: AsyncConnection | None = None

    async def acquire(self) -> None:
        connection = await self.bind.connect()
        try:
            acquired = await connection.scalar(text("SELECT pg_try_advisory_lock(:key)"),
                {"key": PROVIDER_IMPORT_LOCK_KEY})
            # Session-level locks outlive the transaction; ending it avoids an idle-in-transaction session.
            await connection.commit()
        except BaseException:
            await connection.close()
            raise
        if not acquired:
            await connection.close()
            raise ProviderImportBusy()
        self.connection = connection

    async def release(self) -> None:
        connection, self.connection = self.connection, None
        if connection is None:
            return
        try:
            await connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": PROVIDER_IMPORT_LOCK_KEY})
            await connection.commit()
        finally:
            await connection.close()


@asynccontextmanager
async def provider_import_lock(bind: AsyncEngine | None = None) -> AsyncIterator[None]:
    lock = ProviderImportLock(bind)
    await lock.acquire()
    try:
        yield
    finally:
        await lock.release()

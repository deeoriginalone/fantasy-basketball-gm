from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine, initialize_schema
from app.core.timing import RequestTimingMiddleware
from app.features.draft.router import router as draft_router
from app.features.draft.router import v2_router as draft_v2_router
from app.features.draft.browser_observer import router as browser_observer_router
from app.features.draft.observer_connection import router as observer_connection_router
from app.features.championship.router import router as championship_router
from app.features.waivers.router import router as waivers_router
from app.features.leagues.router import router as league_router
from app.features.leagues.router import single_league_router
from app.features.nba.router import router as nba_router
from app.features.players.router import router as players_router
from app.features.yahoo.router import router as yahoo_router
from app.services.draft.mock_drafts import mock_batch_worker_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_schema()
    worker_stop = asyncio.Event()
    worker_task = asyncio.create_task(mock_batch_worker_loop(worker_stop))
    yield
    worker_stop.set()
    await worker_task
    await engine.dispose()


app = FastAPI(title="Fantasy Basketball GM API", version="0.1.0", lifespan=lifespan)
# Refresh progress is polled; only its POST is timed and logged.
app.add_middleware(RequestTimingMiddleware, untimed_paths=("/api/v1/waivers/refresh",))
app.include_router(yahoo_router)
app.include_router(draft_router)
app.include_router(draft_v2_router)
app.include_router(browser_observer_router)
app.include_router(observer_connection_router)
app.include_router(championship_router)
app.include_router(waivers_router)
app.include_router(league_router)
app.include_router(single_league_router)
app.include_router(players_router)
app.include_router(nba_router)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}
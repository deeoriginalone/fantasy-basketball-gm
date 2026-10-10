from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text

from app.core.database import engine, initialize_schema
from app.features.draft.router import router as draft_router
from app.features.draft.router import v2_router as draft_v2_router
from app.features.leagues.router import router as league_router
from app.features.leagues.router import single_league_router
from app.features.nba.router import router as nba_router
from app.features.players.router import router as players_router
from app.features.yahoo.router import router as yahoo_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    await initialize_schema()
    yield
    await engine.dispose()


app = FastAPI(title="Fantasy Basketball GM API", version="0.1.0", lifespan=lifespan)
app.include_router(yahoo_router)
app.include_router(draft_router)
app.include_router(draft_v2_router)
app.include_router(league_router)
app.include_router(single_league_router)
app.include_router(players_router)
app.include_router(nba_router)


@app.get("/api/v1/health")
async def health() -> dict[str, str]:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
    return {"status": "ok"}
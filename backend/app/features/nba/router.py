from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.provider_lock import BUSY_DETAIL, ProviderImportBusy, provider_import_lock
from app.features.nba.contracts import NbaImportResult
from app.services.nba.client import NbaDataSourceError
from app.services.nba.importer import NbaPersistenceVerificationError, current_nba_season, import_nba_data

router = APIRouter(prefix="/api/v1/nba", tags=["NBA Data"])


@router.post("/import", response_model=NbaImportResult)
async def import_nba(
    season: str | None = Query(default=None, pattern=r"^\d{4}-\d{2}$"),
    recent_days: int = Query(default=30, ge=1, le=90),
    session: AsyncSession = Depends(get_session),
) -> NbaImportResult:
    selected_season = season or current_nba_season()
    try:
        async with provider_import_lock():
            return await import_nba_data(session, selected_season, recent_days)
    except ProviderImportBusy as error:
        raise HTTPException(status_code=409, detail=BUSY_DETAIL) from error
    except (NbaDataSourceError, NbaPersistenceVerificationError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

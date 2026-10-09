from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.features.draft.contracts import DraftMetricsResult, DraftUtilityRequest, DraftUtilityResult
from app.services.draft.metrics import recompute_draft_metrics
from app.services.draft.utility import calculate_draft_utility

router = APIRouter(prefix="/api/v1/draft", tags=["Draft Readiness"])


@router.post("/metrics", response_model=DraftMetricsResult)
async def build_draft_metrics(
    league_key: str = Query(min_length=1),
    season: str = Query(pattern=r"^\d{4}-\d{2}$"),
    session: AsyncSession = Depends(get_session),
) -> DraftMetricsResult:
    return await recompute_draft_metrics(session, league_key, season)


@router.post("/utility", response_model=DraftUtilityResult)
async def draft_utility(
    request: DraftUtilityRequest,
    session: AsyncSession = Depends(get_session),
) -> DraftUtilityResult:
    await recompute_draft_metrics(session, request.league_key, request.season)
    return await calculate_draft_utility(session, request)

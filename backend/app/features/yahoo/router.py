from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import create_oauth_state, validate_oauth_state
from app.features.leagues.service import import_manager_leagues
from app.features.yahoo.contracts import OAuthConnectionResult
from app.services.yahoo.auth import YahooAuthService

router = APIRouter(prefix="/api/v1/yahoo/oauth", tags=["Yahoo OAuth"])
YAHOO_AUTHORIZE_URL = "https://api.login.yahoo.com/oauth2/request_auth"


@router.get("/authorize")
async def authorize() -> RedirectResponse:
    settings = get_settings()
    auth = YahooAuthService(settings)
    auth.oauth.require_configuration()
    state = create_oauth_state(settings.oauth_state_secret)
    query = urlencode(
        {
            "client_id": settings.yahoo_client_id,
            "redirect_uri": settings.yahoo_redirect_uri,
            "response_type": "code",
            "state": state,
        }
    )
    response = RedirectResponse(f"{YAHOO_AUTHORIZE_URL}?{query}", status_code=307)
    response.set_cookie(
        "yahoo_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=settings.yahoo_redirect_uri.startswith("https://"),
        samesite="lax",
        path="/api/v1/yahoo/oauth",
    )
    return response


@router.get("/callback", response_model=OAuthConnectionResult)
async def callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    session: AsyncSession = Depends(get_session),
) -> JSONResponse:
    settings = get_settings()
    auth = YahooAuthService(settings)
    auth.oauth.require_configuration()
    if not state or not validate_oauth_state(
        state,
        request.cookies.get("yahoo_oauth_state"),
        settings.oauth_state_secret,
    ):
        raise HTTPException(status_code=400, detail="Yahoo OAuth state is invalid or expired")
    if error:
        raise HTTPException(status_code=400, detail="Yahoo authorization was not granted")
    if not code:
        raise HTTPException(status_code=400, detail="Yahoo authorization code is missing")
    await auth.store_authorization_code(session, code)
    imported = await import_manager_leagues(session, settings)
    response = JSONResponse(
        content=OAuthConnectionResult(
            connected=True,
            game_key=imported.game_key,
            imported_count=imported.imported_count,
            league_keys=[league.league_key for league in imported.leagues],
        ).model_dump()
    )
    response.delete_cookie("yahoo_oauth_state", path="/api/v1/yahoo/oauth")
    return response
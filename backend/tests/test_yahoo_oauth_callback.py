from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import get_session
from app.features.leagues.contracts import LeagueImportResult, LeagueImportSummary
from app.features.yahoo import router as yahoo_router_module
from app.features.yahoo.router import router as yahoo_router


async def _fake_session():
    yield object()


def test_oauth_callback_stores_tokens_then_imports_leagues(monkeypatch) -> None:
    settings = Settings(
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        yahoo_redirect_uri="http://localhost:8000/api/v1/yahoo/oauth/callback",
        oauth_state_secret="test-state-secret",
        token_encryption_key=Fernet.generate_key().decode("ascii"),
    )
    monkeypatch.setattr(yahoo_router_module, "get_settings", lambda: settings)
    store_authorization_code = AsyncMock()
    monkeypatch.setattr(
        "app.services.yahoo.auth.YahooAuthService.store_authorization_code",
        store_authorization_code,
    )
    import_leagues = AsyncMock(
        return_value=LeagueImportResult(
            game_key="nba_2026",
            imported_count=1,
            team_count=2,
            leagues=[
                LeagueImportSummary(
                    league_key="nba.l.1",
                    league_name="Hoops League",
                    season=2026,
                    team_count=2,
                )
            ],
        )
    )
    monkeypatch.setattr(yahoo_router_module, "import_manager_leagues", import_leagues)

    app = FastAPI()
    app.include_router(yahoo_router)
    app.dependency_overrides[get_session] = _fake_session

    with TestClient(app) as client:
        authorization = client.get("/api/v1/yahoo/oauth/authorize", follow_redirects=False)
        state = parse_qs(urlparse(authorization.headers["location"]).query)["state"][0]
        assert authorization.cookies.get("yahoo_oauth_state") == state
        assert "httponly" in authorization.headers["set-cookie"].lower()

        callback = client.get(
            "/api/v1/yahoo/oauth/callback",
            params={"code": "one-time-code", "state": state},
        )

    assert callback.status_code == 200
    assert callback.json() == {
        "connected": True,
        "game_key": "nba_2026",
        "imported_count": 1,
        "league_keys": ["nba.l.1"],
    }
    store_authorization_code.assert_awaited_once()
    assert store_authorization_code.await_args.args[1] == "one-time-code"
    import_leagues.assert_awaited_once()
    assert "access_token" not in callback.text
    assert "refresh_token" not in callback.text
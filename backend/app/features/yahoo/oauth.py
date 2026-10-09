from datetime import datetime, timedelta, timezone

import httpx
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import decrypt_token, encrypt_token
from app.features.yahoo.models import YahooCredential

YAHOO_TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"


class YahooOAuth:
    def __init__(self, settings: Settings):
        self.settings = settings

    def require_configuration(self) -> None:
        if not all(
            (
                self.settings.yahoo_client_id,
                self.settings.yahoo_client_secret,
                self.settings.oauth_state_secret,
                self.settings.token_encryption_key,
            )
        ):
            raise HTTPException(status_code=503, detail="Yahoo OAuth is not configured")
        try:
            Fernet(self.settings.token_encryption_key.encode("ascii"))
        except (ValueError, UnicodeEncodeError, InvalidToken) as error:
            raise HTTPException(status_code=503, detail="Yahoo token encryption key is invalid") from error

    async def exchange_code(self, code: str) -> dict:
        self.require_configuration()
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                YAHOO_TOKEN_URL,
                auth=(self.settings.yahoo_client_id, self.settings.yahoo_client_secret),
                data={
                    "grant_type": "authorization_code",
                    "redirect_uri": self.settings.yahoo_redirect_uri,
                    "code": code,
                },
            )
        if response.is_error:
            raise HTTPException(status_code=502, detail="Yahoo authorization code exchange failed")
        return response.json()

    async def save_tokens(self, session: AsyncSession, token_data: dict) -> None:
        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        if not access_token or not token_data.get("expires_in"):
            raise HTTPException(status_code=502, detail="Yahoo returned an incomplete token response")
        credential = await session.get(YahooCredential, 1)
        if credential is None:
            if not refresh_token:
                raise HTTPException(
                    status_code=502,
                    detail="Yahoo did not return a refresh token; account connection was not stored",
                )
            credential = YahooCredential(id=1)
        credential.access_token_encrypted = encrypt_token(
            access_token, self.settings.token_encryption_key
        )
        if refresh_token:
            credential.refresh_token_encrypted = encrypt_token(
                refresh_token, self.settings.token_encryption_key
            )
        credential.expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(token_data["expires_in"])
        )
        session.add(credential)
        await session.commit()

    async def access_token(self, session: AsyncSession) -> str:
        self.require_configuration()
        credential = await session.get(YahooCredential, 1)
        if credential is None:
            raise HTTPException(status_code=401, detail="Connect a Yahoo account before importing leagues")

        now = datetime.now(timezone.utc)
        if credential.expires_at > now + timedelta(seconds=60):
            return decrypt_token(credential.access_token_encrypted, self.settings.token_encryption_key)
        if not credential.refresh_token_encrypted:
            raise HTTPException(status_code=401, detail="Yahoo authorization expired; reconnect the account")

        refresh_token = decrypt_token(
            credential.refresh_token_encrypted, self.settings.token_encryption_key
        )
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                YAHOO_TOKEN_URL,
                auth=(self.settings.yahoo_client_id, self.settings.yahoo_client_secret),
                data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            )
        if response.is_error:
            raise HTTPException(status_code=401, detail="Yahoo token refresh failed; reconnect the account")
        token_data = response.json()
        token_data.setdefault("refresh_token", refresh_token)
        await self.save_tokens(session, token_data)
        return token_data["access_token"]
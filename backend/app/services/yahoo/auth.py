from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.features.yahoo.oauth import YahooOAuth


class YahooAuthService:
    def __init__(self, settings: Settings):
        self.oauth = YahooOAuth(settings)

    async def access_token(self, session: AsyncSession) -> str:
        return await self.oauth.access_token(session)

    async def store_authorization_code(self, session: AsyncSession, code: str) -> None:
        token_data = await self.oauth.exchange_code(code)
        await self.oauth.save_tokens(session, token_data)
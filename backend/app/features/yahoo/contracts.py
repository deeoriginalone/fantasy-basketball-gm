from pydantic import BaseModel


class OAuthConnectionResult(BaseModel):
    connected: bool
    game_key: str
    imported_count: int
    league_keys: list[str]
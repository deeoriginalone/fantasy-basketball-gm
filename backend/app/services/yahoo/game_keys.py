from typing import Any

from fastapi import HTTPException

from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.normalization import extract_yahoo_records


def _season_number(game: dict[str, Any]) -> int:
    try:
        return int(game.get("season", 0))
    except (TypeError, ValueError):
        return 0


async def discover_active_nba_game_key(client: YahooFantasyClient, access_token: str) -> str:
    payload = await client.get_json("games;game_codes=nba", access_token)
    games = extract_yahoo_records(payload, "game", "game_key")
    nba_games = [game for game in games if game.get("game_code", "nba") == "nba"]
    if not nba_games:
        raise HTTPException(status_code=502, detail="Yahoo did not return an active NBA game")

    current_games = [
        game for game in nba_games if str(game.get("is_current_game", "0")).lower() in {"1", "true"}
    ]
    candidates = current_games or nba_games
    selected = max(candidates, key=_season_number)
    game_key = selected.get("game_key")
    if not game_key:
        raise HTTPException(status_code=502, detail="Yahoo NBA game response omitted its game key")
    return str(game_key)
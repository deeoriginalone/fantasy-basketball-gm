from urllib.parse import quote

from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.normalization import NormalizedYahooLeague, extract_yahoo_records, normalize_yahoo_league


async def fetch_user_leagues(
    client: YahooFantasyClient,
    access_token: str,
    game_key: str,
) -> list[NormalizedYahooLeague]:
    encoded_game_key = quote(game_key, safe="._")
    payload = await client.get_json(
        f"users;use_login=1/games;game_keys={encoded_game_key}/leagues",
        access_token,
    )
    league_records = extract_yahoo_records(payload, "league", "league_key")
    normalized: list[NormalizedYahooLeague] = []

    for league in league_records:
        league_key = str(league["league_key"])
        encoded_league_key = quote(league_key, safe="._")
        settings_response = await client.get_json(
            f"league/{encoded_league_key}/settings",
            access_token,
        )
        teams_response = await client.get_json(
            f"league/{encoded_league_key}/teams",
            access_token,
        )
        normalized.append(
            normalize_yahoo_league(
                game_key,
                league,
                settings_response,
                teams_response,
            )
        )
    return normalized
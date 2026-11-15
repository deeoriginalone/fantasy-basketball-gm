from collections.abc import Iterable
from urllib.parse import quote

from fastapi import HTTPException

from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.normalization import extract_yahoo_records

MAX_PLAYER_PAGES = 200
# Per-player roster sub-resources that Yahoo returns beside the player metadata list.
ROSTER_PLAYER_SUBRESOURCES = ("selected_position", "starting_status")


def _merge_fragments(value: object) -> object:
    """Yahoo JSON encodes small sub-resources as lists of single-key fragments."""
    if not isinstance(value, list):
        return value
    merged: dict = {}
    for fragment in value:
        if isinstance(fragment, dict):
            merged.update(fragment)
    return merged


def extract_roster_player_records(payload: dict) -> list[dict]:
    """Extract roster players while keeping their per-player roster sub-resources.

    Yahoo returns a roster player as ``[[metadata fragments...], {"selected_position": [...]}]``.
    The generic record extractor keeps only the metadata list, which silently dropped the
    persisted slot assignment, so the sibling sub-resources are attached here.
    """
    records: dict[str, dict] = {}
    for player_value in _named_values(payload, "player"):
        found = extract_yahoo_records({"player": player_value}, "player", "player_key")
        siblings: dict[str, object] = {}
        if isinstance(player_value, list):
            for item in player_value:
                if isinstance(item, dict) and "player_key" not in item:
                    for key in ROSTER_PLAYER_SUBRESOURCES:
                        if key in item:
                            siblings[key] = item[key]
        for record in found:
            merged = dict(record)
            for key, value in siblings.items():
                merged.setdefault(key, value)
            for key in ROSTER_PLAYER_SUBRESOURCES:
                if key in merged:
                    merged[key] = _merge_fragments(merged[key])
            records[str(merged["player_key"])] = merged
    return list(records.values())


def _named_values(value: object, name: str) -> list[object]:
    if isinstance(value, dict):
        matches: list[object] = []
        for key, nested in value.items():
            if key == name:
                matches.append(nested)
            else:
                matches.extend(_named_values(nested, name))
        return matches
    if isinstance(value, list):
        matches = []
        for nested in value:
            matches.extend(_named_values(nested, name))
        return matches
    return []


def _collection_count(value: object) -> int | None:
    if isinstance(value, list):
        return len(value)
    if not isinstance(value, dict):
        return None
    if "count" in value:
        try:
            count = int(value["count"])
        except (TypeError, ValueError) as error:
            raise HTTPException(status_code=502, detail="Yahoo returned an invalid player collection count") from error
        if count < 0:
            raise HTTPException(status_code=502, detail="Yahoo returned an invalid player collection count")
        return count
    indexed_count = sum(str(key).isdigit() for key in value)
    return indexed_count or None


def _require_collection(payload: dict, name: str) -> int:
    for collection in _named_values(payload, name):
        count = _collection_count(collection)
        if count is not None:
            return count
    raise HTTPException(
        status_code=502,
        detail=f"Yahoo response omitted the expected {name} collection",
    )


async def fetch_all_league_players(
    client: YahooFantasyClient,
    access_token: str,
    league_key: str,
    page_size: int = 25,
) -> list[dict]:
    if page_size < 1:
        raise ValueError("page_size must be positive")
    encoded_league_key = quote(league_key, safe="._")
    players_by_key: dict[str, dict] = {}
    start = 0

    for _ in range(MAX_PLAYER_PAGES):
        payload = await client.get_json(
            f"league/{encoded_league_key}/players;start={start};count={page_size}",
            access_token,
        )
        advertised_count = _require_collection(payload, "players")
        page = extract_yahoo_records(payload, "player", "player_key")
        if advertised_count == 0 and page:
            raise HTTPException(status_code=502, detail="Yahoo player collection count did not match its records")
        if advertised_count > 0 and not page:
            raise HTTPException(status_code=502, detail="Yahoo player collection contained no parseable records")
        if not page:
            break
        page_keys = [str(player["player_key"]) for player in page]
        if not any(key not in players_by_key for key in page_keys):
            raise HTTPException(status_code=502, detail="Yahoo player pagination stopped advancing")
        for player in page:
            players_by_key[str(player["player_key"])] = player
        if len(page) < page_size:
            break
        start += len(page)
    else:
        raise HTTPException(status_code=502, detail="Yahoo player collection exceeded the paging limit")

    return list(players_by_key.values())


async def fetch_league_rosters(
    client: YahooFantasyClient,
    access_token: str,
    team_keys: Iterable[str],
) -> dict[str, list[dict]]:
    rosters: dict[str, list[dict]] = {}
    for team_key in team_keys:
        encoded_team_key = quote(team_key, safe="._")
        payload = await client.get_json(
            f"team/{encoded_team_key}/roster",
            access_token,
        )
        roster_resources = _named_values(payload, "roster")
        if not roster_resources:
            raise HTTPException(status_code=502, detail="Yahoo returned a malformed roster response")
        advertised_counts = [
            count
            for roster_resource in roster_resources
            for count in [_require_collection(roster_resource, "players")]
        ]
        players = extract_roster_player_records(payload)
        if sum(advertised_counts) == 0 and players:
            raise HTTPException(status_code=502, detail="Yahoo roster count did not match its player records")
        if sum(advertised_counts) > 0 and not players:
            raise HTTPException(status_code=502, detail="Yahoo roster contained no parseable player records")
        rosters[team_key] = players
    return rosters
import asyncio

import pytest
from fastapi import HTTPException

from app.features.players.normalization import normalize_yahoo_player
from app.services.yahoo.normalization import normalize_yahoo_league
from app.services.yahoo.players import fetch_all_league_players, fetch_league_rosters


def _player(player_id: str, name: str) -> list[dict]:
    return [
        {"player_key": f"nba.p.{player_id}", "player_id": player_id},
        {"name": {"full": name}},
        {"editorial_team_abbr": "DEN", "display_position": "C"},
    ]


def test_normalize_player_uses_yahoo_fields_and_does_not_infer_status() -> None:
    player = {
        "player_key": "nba.p.12345",
        "player_id": "12345",
        "name": {"first": "Nikola", "last": "Jokic"},
        "editorial_team_abbr": "DEN",
        "eligible_positions": {"0": {"position": "C"}, "1": {"position": "PF"}},
    }

    normalized = normalize_yahoo_player(player)

    assert normalized.yahoo_player_id == "12345"
    assert normalized.player_name == "Nikola Jokic"
    assert normalized.team == "DEN"
    assert normalized.position == "C,PF"
    assert normalized.status is None
    assert normalized.source_payload == player


def test_normalize_player_rejects_missing_identity_fields() -> None:
    with pytest.raises(ValueError, match="required player ID or name"):
        normalize_yahoo_player({"player_key": "nba.p.12345"})


def test_fetch_all_league_players_reads_every_page() -> None:
    responses = {
        "league/nba.l.1/players;start=0;count=2": {
            "fantasy_content": {"league": [{"players": {"0": {"player": _player("1", "Player One")}, "1": {"player": _player("2", "Player Two")}}}]}
        },
        "league/nba.l.1/players;start=2;count=2": {
            "fantasy_content": {"league": [{"players": {"0": {"player": _player("3", "Player Three")}}}]}
        },
    }

    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            assert access_token == "test-token"
            return responses[path]

    players = asyncio.run(
        fetch_all_league_players(FixtureClient(), "test-token", "nba.l.1", page_size=2)
    )

    assert [player["player_id"] for player in players] == ["1", "2", "3"]


def test_fetch_league_rosters_reads_players_per_yahoo_team() -> None:
    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            assert access_token == "test-token"
            assert path == "team/nba.l.1.t.1/roster"
            return {"fantasy_content": {"team": [{"roster": {"0": {"players": {"0": {"player": _player("1", "Player One")}}}}}]}}

    rosters = asyncio.run(
        fetch_league_rosters(FixtureClient(), "test-token", ["nba.l.1.t.1"])
    )

    assert rosters["nba.l.1.t.1"][0]["player_id"] == "1"


def test_pre_draft_empty_roster_is_valid() -> None:
    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            assert path == "team/nba.l.1.t.1/roster"
            return {
                "fantasy_content": {
                    "team": [{"roster": {"coverage_type": "week", "players": {"count": 0}}}]
                }
            }

    rosters = asyncio.run(
        fetch_league_rosters(FixtureClient(), "test-token", ["nba.l.1.t.1"])
    )

    assert rosters == {"nba.l.1.t.1": []}


@pytest.mark.parametrize(
    "payload",
    [
        {"fantasy_content": {"team": [{"team_key": "nba.l.1.t.1"}]}},
        {"fantasy_content": {"team": [{"roster": {"players": {}}}]}},
    ],
)
def test_malformed_roster_response_is_not_treated_as_empty(payload: dict) -> None:
    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            return payload

    with pytest.raises(HTTPException) as error:
        asyncio.run(fetch_league_rosters(FixtureClient(), "test-token", ["nba.l.1.t.1"]))

    assert error.value.status_code == 502


def test_malformed_player_collection_is_not_treated_as_empty() -> None:
    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            return {"fantasy_content": {"league": [{"league_key": "nba.l.1"}]}}

    with pytest.raises(HTTPException) as error:
        asyncio.run(fetch_all_league_players(FixtureClient(), "test-token", "nba.l.1"))

    assert error.value.status_code == 502


def test_valid_empty_player_collection_returns_no_players() -> None:
    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            return {"fantasy_content": {"league": [{"players": {"count": 0}}]}}

    players = asyncio.run(fetch_all_league_players(FixtureClient(), "test-token", "nba.l.1"))

    assert players == []


def test_league_settings_parse_yahoo_scoring_and_roster_positions_verbatim() -> None:
    positions = ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "Util", "Util", "BN", "BN", "BN", "IL", "IL", "IL"]
    roster_settings = {
        str(index): {"roster_position": {"position": position, "count": "1"}}
        for index, position in enumerate(positions)
    }
    settings_response = {
        "fantasy_content": {
            "league": [
                {"league_key": "nba.l.50505"},
                {
                    "settings": [
                        {"scoring_type": "head"},
                        {
                            "stat_categories": {
                                "stats": [
                                    {"stat": {"stat_id": "12", "name": "Points Scored", "display_name": "PTS"}},
                                    {"stat": {"stat_id": "15", "name": "Total Rebounds", "display_name": "REB"}},
                                    {"stat": {"stat_id": "16", "name": "Assists", "display_name": "AST"}},
                                    {"stat": {"stat_id": "18", "name": "Blocked Shots", "display_name": "BLK"}},
                                    {"stat": {"stat_id": "17", "name": "Steals", "display_name": "ST"}},
                                    {"stat": {"stat_id": "19", "name": "Turnovers", "display_name": "TO"}},
                                ]
                            }
                        },
                        {
                            "stat_modifiers": {
                                "stats": [
                                    {"stat": {"stat_id": "12", "value": "1"}},
                                    {"stat": {"stat_id": "15", "value": "1.2"}},
                                    {"stat": {"stat_id": "16", "value": "1.5"}},
                                    {"stat": {"stat_id": "18", "value": "3"}},
                                    {"stat": {"stat_id": "17", "value": "3"}},
                                    {"stat": {"stat_id": "19", "value": "-1"}},
                                ]
                            }
                        },
                        {"roster_positions": roster_settings},
                    ]
                },
            ]
        }
    }

    normalized = normalize_yahoo_league(
        "nba_2026",
        {"league_key": "nba.l.50505", "name": "Driveway Dudes", "season": "2026"},
        settings_response,
        {},
    )

    assert normalized.scoring_settings == {
        "scoring_type": "head",
        "categories": [
            {"stat_id": "12", "name": "PTS", "value": 1},
            {"stat_id": "15", "name": "REB", "value": 1.2},
            {"stat_id": "16", "name": "AST", "value": 1.5},
            {"stat_id": "18", "name": "BLK", "value": 3},
            {"stat_id": "17", "name": "ST", "value": 3},
            {"stat_id": "19", "name": "TO", "value": -1},
        ],
    }
    assert [position["position"] for position in normalized.roster_positions] == positions
    assert normalized.source_settings == settings_response
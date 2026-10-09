import asyncio
import logging

import httpx

from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.game_keys import discover_active_nba_game_key
from app.services.yahoo.normalization import extract_yahoo_records, normalize_yahoo_league


def test_fragmented_yahoo_league_and_team_records_are_merged() -> None:
    payload = {
        "fantasy_content": {
            "leagues": {
                "0": {
                    "league": [
                        {"league_key": "nba.l.1", "league_id": "1"},
                        {"name": "Hoops", "season": "2026"},
                    ]
                }
            }
        }
    }

    assert extract_yahoo_records(payload, "league", "league_key") == [
        {"league_key": "nba.l.1", "league_id": "1", "name": "Hoops", "season": "2026"}
    ]


def test_normalizer_preserves_settings_positions_and_team_source() -> None:
    league = {"league_key": "nba.l.1", "name": "Hoops", "season": "2026"}
    settings = {
        "fantasy_content": {
            "league": [
                {"league_key": "nba.l.1"},
                {
                    "settings": [
                        {"scoring_type": "head"},
                        {
                            "stat_categories": {
                                "stats": [
                                    {"stat": {"stat_id": "12", "name": "Points Scored", "display_name": "PTS"}},
                                    {"stat": {"stat_id": "15", "name": "Total Rebounds", "display_name": "REB"}},
                                ]
                            }
                        },
                        {
                            "stat_modifiers": {
                                "stats": [
                                    {"stat": {"stat_id": "12", "value": "1"}},
                                    {"stat": {"stat_id": "15", "value": "1.2"}},
                                ]
                            }
                        },
                        {"roster_positions": {"0": {"roster_position": {"position": "PG", "count": "1"}}}},
                    ]
                },
            ]
        }
    }
    teams = {
        "fantasy_content": {
            "teams": {
                "0": {
                    "team": [
                        {"team_key": "nba.l.1.t.1"},
                        {"name": "Fast Break"},
                    ]
                }
            }
        }
    }

    normalized = normalize_yahoo_league("nba_456", league, settings, teams)

    assert normalized.season == 2026
    assert normalized.scoring_settings == {
        "scoring_type": "head",
        "categories": [
            {"stat_id": "12", "name": "PTS", "value": 1},
            {"stat_id": "15", "name": "REB", "value": 1.2},
        ],
    }
    assert normalized.roster_positions == [{"position": "PG", "count": "1"}]
    assert normalized.teams[0].team_name == "Fast Break"
    assert normalized.teams[0].source_payload["team_key"] == "nba.l.1.t.1"
    assert normalized.source_settings == settings


def test_settings_normalizer_preserves_raw_settings_without_inventing_scores() -> None:
    league = {"league_key": "nba.l.1", "name": "Hoops", "season": "2026"}
    settings = {
        "fantasy_content": {
            "league": [
                {"league_key": "nba.l.1"},
                {"settings": {"stat_categories": {"0": {"stat_category": {"name": "PTS"}}}}},
            ]
        }
    }

    normalized = normalize_yahoo_league("nba_2026", league, settings, {})

    assert normalized.scoring_settings == {}
    assert normalized.source_settings == settings


def test_game_discovery_selects_current_game_without_hardcoded_season() -> None:
    payload = {
        "fantasy_content": {
            "games": {
                "0": {"game": [{"game_key": "nba_2025", "game_code": "nba", "season": "2025"}]},
                "1": {"game": [{"game_key": "nba_2026", "game_code": "nba", "season": "2026", "is_current_game": "1"}]},
            }
        }
    }

    class FixtureClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            assert path == "games;game_codes=nba"
            return payload

    assert asyncio.run(discover_active_nba_game_key(FixtureClient(), "token")) == "nba_2026"


def test_yahoo_client_retries_transient_responses_without_logging_tokens(caplog) -> None:
    attempts = 0
    access_token = "must-not-appear-in-logs"

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, request=request)
        return httpx.Response(200, json={"ok": True}, request=request)

    client = YahooFantasyClient(
        transport=httpx.MockTransport(handler),
        max_attempts=3,
        base_retry_delay=0.001,
    )
    with caplog.at_level(logging.WARNING):
        payload = asyncio.run(client.get_json("games;game_codes=nba", access_token))

    assert payload == {"ok": True}
    assert attempts == 3
    assert any(record.event == "yahoo_request_retry" for record in caplog.records)
    assert access_token not in caplog.text
from app.services.yahoo.normalization import extract_yahoo_records


def test_extract_records_from_yahoo_indexed_collection() -> None:
    payload = {
        "fantasy_content": {
            "games": {
                "0": {
                    "game": [
                        {
                            "game_key": "nba_123",
                            "game_code": "nba",
                        }
                    ]
                },
                "count": 1,
            }
        }
    }

    assert extract_yahoo_records(payload, "game", "game_key") == [
        {"game_key": "nba_123", "game_code": "nba"}
    ]


def test_extract_records_ignores_unidentified_entries() -> None:
    payload = {"leagues": {"league": [{"name": "No key"}, {"league_key": "nba.l.1"}]}}

    assert extract_yahoo_records(payload, "league", "league_key") == [{"league_key": "nba.l.1"}]
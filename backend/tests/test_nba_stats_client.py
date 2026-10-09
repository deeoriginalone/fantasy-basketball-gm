from nba_api.stats import endpoints

from app.services.nba.client import NbaApiClient


def test_player_season_stats_join_base_advanced_and_starter_rows(monkeypatch) -> None:
    class Frame:
        def __init__(self, rows: list[dict]) -> None:
            self.rows = rows

        def to_dict(self, orient: str) -> list[dict]:
            assert orient == "records"
            return self.rows

    class FixtureEndpoint:
        def __init__(self, *, measure_type_detailed_defense: str, starter_bench_nullable: str, **kwargs) -> None:
            assert kwargs["season"] == "2025-26"
            assert kwargs["season_type_all_star"] == "Regular Season"
            self.measure = measure_type_detailed_defense
            self.starter_filter = starter_bench_nullable

        def get_data_frames(self) -> list[Frame]:
            if self.measure == "Base":
                rows = [{"PLAYER_ID": 123, "PLAYER_NAME": "Fixture Player", "TEAM_ID": 1, "TEAM_ABBREVIATION": "BOS", "GP": 10, "MIN": 20.0, "PTS": 15.0}]
            elif self.starter_filter == "Starters":
                rows = [{"PLAYER_ID": 123, "GP": 7}]
            else:
                rows = [{"PLAYER_ID": 123, "GP": 10, "MIN": 20.0, "USG_PCT": 0.25, "TS_PCT": 0.6}]
            return [Frame(rows)]

    monkeypatch.setattr(endpoints, "LeagueDashPlayerStats", FixtureEndpoint)

    result = NbaApiClient().fetch_player_season_stats("2025-26", "Regular Season")

    assert result == [{
        "nba_player_id": "123",
        "player_name": "Fixture Player",
        "team_id": 1,
        "team_abbreviation": "BOS",
        "games_played": 10,
        "games_started": 7,
        "minutes_per_game": 20.0,
        "usage_pct": 0.25,
        "base_stats": {
            "PLAYER_ID": 123,
            "PLAYER_NAME": "Fixture Player",
            "TEAM_ID": 1,
            "TEAM_ABBREVIATION": "BOS",
            "GP": 10,
            "MIN": 20.0,
            "PTS": 15.0,
        },
        "advanced_stats": {"PLAYER_ID": 123, "GP": 10, "MIN": 20.0, "USG_PCT": 0.25, "TS_PCT": 0.6},
        "source_payload": {
            "base": {"PLAYER_ID": 123, "PLAYER_NAME": "Fixture Player", "TEAM_ID": 1, "TEAM_ABBREVIATION": "BOS", "GP": 10, "MIN": 20.0, "PTS": 15.0},
            "advanced": {"PLAYER_ID": 123, "GP": 10, "MIN": 20.0, "USG_PCT": 0.25, "TS_PCT": 0.6},
            "starter_filter": {"PLAYER_ID": 123, "GP": 7},
        },
    }]

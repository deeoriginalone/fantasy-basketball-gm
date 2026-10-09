from datetime import date
import math
from typing import Any


class NbaDataSourceError(RuntimeError):
    pass


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _frame_records(frame: Any) -> list[dict[str, Any]]:
    import pandas as pd

    records = []
    for record in frame.to_dict(orient="records"):
        normalized = {}
        for key, value in record.items():
            try:
                missing = bool(pd.isna(value))
            except (TypeError, ValueError):
                missing = False
            normalized[str(key)] = None if missing else _json_value(value)
        records.append(normalized)
    return records


class NbaApiClient:
    """Synchronous nba_api adapter; callers execute network methods off the event loop."""

    timeout_seconds = 30

    def fetch_teams(self) -> list[dict[str, Any]]:
        try:
            from nba_api.stats.static.teams import get_teams

            return [_json_value(team) for team in get_teams()]
        except Exception as error:
            raise NbaDataSourceError("NBA team data fetch failed") from error

    def fetch_players(self, season: str) -> list[dict[str, Any]]:
        try:
            from nba_api.stats.endpoints import CommonAllPlayers

            endpoint = CommonAllPlayers(
                is_only_current_season=1,
                league_id="00",
                season=season,
                timeout=self.timeout_seconds,
            )
            frames = endpoint.get_data_frames()
            return _frame_records(frames[0]) if frames else []
        except Exception as error:
            raise NbaDataSourceError("NBA player data fetch failed") from error

    def fetch_player_season_stats(self, season: str, season_type: str) -> list[dict[str, Any]]:
        try:
            from nba_api.stats.endpoints import LeagueDashPlayerStats

            def fetch(measure_type: str, starter_filter: str = "") -> list[dict[str, Any]]:
                endpoint = LeagueDashPlayerStats(
                    last_n_games=0,
                    measure_type_detailed_defense=measure_type,
                    pace_adjust="N",
                    per_mode_detailed="PerGame",
                    rank="N",
                    season=season,
                    season_type_all_star=season_type,
                    starter_bench_nullable=starter_filter,
                    timeout=self.timeout_seconds,
                )
                frames = endpoint.get_data_frames()
                return _frame_records(frames[0]) if frames else []

            base_rows = fetch("Base")
            advanced_rows = fetch("Advanced")
            starter_rows = fetch("Advanced", "Starters")

            def keyed(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
                by_id: dict[str, dict[str, Any]] = {}
                for row in rows:
                    player_id = row.get("PLAYER_ID")
                    if player_id is not None:
                        by_id[str(player_id)] = row
                return by_id

            base_by_id = keyed(base_rows)
            advanced_by_id = keyed(advanced_rows)
            starters_by_id = keyed(starter_rows)
            result = []
            for player_id in sorted(base_by_id.keys() | advanced_by_id.keys()):
                base = base_by_id.get(player_id, {})
                advanced = advanced_by_id.get(player_id, {})
                starts = starters_by_id.get(player_id, {})
                try:
                    games_played = int(float(base.get("GP") or advanced.get("GP") or 0))
                    games_started = int(float(starts.get("GP") or 0))
                except (TypeError, ValueError) as error:
                    raise NbaDataSourceError("NBA season statistics contained an invalid game count") from error
                result.append({
                    "nba_player_id": player_id,
                    "player_name": base.get("PLAYER_NAME") or advanced.get("PLAYER_NAME"),
                    "team_id": base.get("TEAM_ID") or advanced.get("TEAM_ID"),
                    "team_abbreviation": base.get("TEAM_ABBREVIATION") or advanced.get("TEAM_ABBREVIATION"),
                    "games_played": games_played,
                    "games_started": games_started,
                    "minutes_per_game": advanced.get("MIN") or base.get("MIN"),
                    "usage_pct": advanced.get("USG_PCT"),
                    "base_stats": base,
                    "advanced_stats": advanced,
                    "source_payload": {
                        "base": base,
                        "advanced": advanced,
                        "starter_filter": starts,
                    },
                })
            return result
        except NbaDataSourceError:
            raise
        except Exception as error:
            raise NbaDataSourceError("NBA player season statistics fetch failed") from error

    def fetch_schedule(self, season: str) -> list[dict[str, Any]]:
        try:
            from nba_api.stats.endpoints import ScheduleLeagueV2

            endpoint = ScheduleLeagueV2(
                league_id="00",
                season=season,
                timeout=self.timeout_seconds,
            )
            frames = endpoint.get_data_frames()
            return _frame_records(frames[0]) if frames else []
        except Exception as error:
            raise NbaDataSourceError("NBA schedule fetch failed") from error

    def fetch_recent_game_logs(
        self,
        season: str,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        try:
            from nba_api.stats.endpoints import LeagueGameLog

            date_from = start_date.strftime("%m/%d/%Y")
            date_to = end_date.strftime("%m/%d/%Y")
            records = []
            for season_type in ("Regular Season", "Pre Season"):
                endpoint = LeagueGameLog(
                    player_or_team_abbreviation="P",
                    season=season,
                    season_type_all_star=season_type,
                    date_from_nullable=date_from,
                    date_to_nullable=date_to,
                    timeout=self.timeout_seconds,
                )
                frames = endpoint.get_data_frames()
                if frames:
                    for record in _frame_records(frames[0]):
                        record["SEASON_TYPE"] = season_type
                        records.append(record)
            return records
        except Exception as error:
            raise NbaDataSourceError("NBA recent game log fetch failed") from error

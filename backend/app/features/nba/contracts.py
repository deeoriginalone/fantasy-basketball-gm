from datetime import date, datetime

from pydantic import BaseModel


class NbaImportResult(BaseModel):
    season: str
    recent_days: int
    teams_imported: int
    players_imported: int
    players_added_from_game_logs: int
    player_season_stats_imported: int
    games_imported: int
    game_logs_imported: int
    player_schedule_entries: int
    unresolved_schedule_team_references: int
    identity_mappings_added: int
    # Transaction timestamp stamped on every upserted row, and the newest game date in this import.
    imported_at: datetime | None = None
    latest_game_date: date | None = None

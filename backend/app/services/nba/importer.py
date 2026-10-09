import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.contracts import NbaImportResult
from app.services.nba.client import NbaApiClient
from app.services.nba.game_logs import import_game_logs
from app.services.nba.player_importer import import_players, link_player_identities
from app.services.nba.schedules import import_schedule, rebuild_player_schedule
from app.services.nba.statistics import import_player_season_stats
from app.services.nba.teams import import_teams


def current_nba_season(today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    start_year = today.year if today.month >= 7 else today.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def previous_nba_season(season: str) -> str:
    start_year = int(season[:4])
    return f"{start_year - 1}-{start_year % 100:02d}"


async def import_nba_data(
    session: AsyncSession,
    season: str,
    recent_days: int = 30,
    source: Any | None = None,
    as_of: date | None = None,
) -> NbaImportResult:
    if not 1 <= recent_days <= 90:
        raise ValueError("recent_days must be between 1 and 90")
    source = source or NbaApiClient()
    as_of = as_of or datetime.now(timezone.utc).date()
    start_date = as_of - timedelta(days=recent_days - 1)

    team_records = await asyncio.to_thread(source.fetch_teams)
    player_records = await asyncio.to_thread(source.fetch_players, season)
    schedule_records = await asyncio.to_thread(source.fetch_schedule, season)
    game_log_records = await asyncio.to_thread(
        source.fetch_recent_game_logs, season, start_date, as_of
    )
    stats_periods = (
        (previous_nba_season(season), "Regular Season"),
        (season, "Regular Season"),
        (season, "Pre Season"),
    )
    stats_batches = []
    for stats_season, season_type in stats_periods:
        records = await asyncio.to_thread(source.fetch_player_season_stats, stats_season, season_type)
        stats_batches.append((stats_season, season_type, records))

    async with session.begin():
        teams_imported = await import_teams(session, team_records)
        players_imported, identity_mappings_added = await import_players(session, player_records)
        games_imported, player_schedule_entries, unresolved_schedule_team_references = await import_schedule(
            session, season, schedule_records, as_of
        )
        game_logs_imported, players_added_from_game_logs = await import_game_logs(
            session, season, game_log_records
        )
        if players_added_from_game_logs:
            player_schedule_entries = await rebuild_player_schedule(session, season, as_of)
        player_season_stats_imported = 0
        for stats_season, season_type, records in stats_batches:
            player_season_stats_imported += await import_player_season_stats(
                session, stats_season, season_type, records
            )
        identity_mappings_added += await link_player_identities(session)

    return NbaImportResult(
        season=season,
        recent_days=recent_days,
        teams_imported=teams_imported,
        players_imported=players_imported,
        players_added_from_game_logs=players_added_from_game_logs,
        player_season_stats_imported=player_season_stats_imported,
        games_imported=games_imported,
        game_logs_imported=game_logs_imported,
        player_schedule_entries=player_schedule_entries,
        unresolved_schedule_team_references=unresolved_schedule_team_references,
        identity_mappings_added=identity_mappings_added,
    )

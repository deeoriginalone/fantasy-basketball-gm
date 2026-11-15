import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.contracts import NbaImportResult
from app.features.nba.models import NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule
from app.services.nba.client import NbaApiClient
from app.services.nba.game_logs import import_game_logs, normalize_game_log
from app.services.nba.player_importer import import_players, link_player_identities
from app.services.nba.schedules import import_schedule, rebuild_player_schedule
from app.services.nba.statistics import import_player_season_stats
from app.services.nba.teams import import_teams

# Stage callbacks let the waiver refresh report which part of the NBA boundary is running or failed.
StageCallback = Callable[[str], None]
NBA_TEAMS_PLAYERS, NBA_SCHEDULE, NBA_GAME_LOGS, NBA_SEASON_STATS = (
    "NBA_TEAMS_PLAYERS", "NBA_SCHEDULE", "NBA_GAME_LOGS", "NBA_SEASON_STATS",
)


class NbaPersistenceVerificationError(RuntimeError):
    """Persisted row counts disagree with the import; the transaction is rolled back."""

    def __init__(self, stage: str, message: str):
        self.stage = stage
        super().__init__(message)


def current_nba_season(today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    start_year = today.year if today.month >= 7 else today.year - 1
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def previous_nba_season(season: str) -> str:
    start_year = int(season[:4])
    return f"{start_year - 1}-{start_year % 100:02d}"


@dataclass
class NbaFetch:
    season: str
    recent_days: int
    as_of: date
    team_records: list[dict[str, Any]] = field(default_factory=list)
    player_records: list[dict[str, Any]] = field(default_factory=list)
    schedule_records: list[dict[str, Any]] = field(default_factory=list)
    game_log_records: list[dict[str, Any]] = field(default_factory=list)
    stats_batches: list[tuple[str, str, list[dict[str, Any]]]] = field(default_factory=list)


def _notify(on_stage: StageCallback | None, stage: str) -> None:
    if on_stage is not None:
        on_stage(stage)


async def fetch_nba_data(
    season: str,
    recent_days: int = 30,
    source: Any | None = None,
    as_of: date | None = None,
    on_stage: StageCallback | None = None,
) -> NbaFetch:
    """Fetch every NBA input before any write, so a provider failure never touches persisted data."""
    if not 1 <= recent_days <= 90:
        raise ValueError("recent_days must be between 1 and 90")
    source = source or NbaApiClient()
    as_of = as_of or datetime.now(timezone.utc).date()
    fetched = NbaFetch(season=season, recent_days=recent_days, as_of=as_of)
    _notify(on_stage, NBA_TEAMS_PLAYERS)
    fetched.team_records = await asyncio.to_thread(source.fetch_teams)
    fetched.player_records = await asyncio.to_thread(source.fetch_players, season)
    _notify(on_stage, NBA_SCHEDULE)
    fetched.schedule_records = await asyncio.to_thread(source.fetch_schedule, season)
    _notify(on_stage, NBA_GAME_LOGS)
    fetched.game_log_records = await asyncio.to_thread(
        source.fetch_recent_game_logs, season, as_of - timedelta(days=recent_days - 1), as_of
    )
    _notify(on_stage, NBA_SEASON_STATS)
    for stats_season, season_type in (
        (previous_nba_season(season), "Regular Season"),
        (season, "Regular Season"),
        (season, "Pre Season"),
    ):
        records = await asyncio.to_thread(source.fetch_player_season_stats, stats_season, season_type)
        fetched.stats_batches.append((stats_season, season_type, records))
    return fetched


async def _count_at(session: AsyncSession, model: Any, stamped: datetime, *conditions: Any) -> int:
    return int(await session.scalar(
        select(func.count()).select_from(model).where(model.imported_at == stamped, *conditions)) or 0)


async def persist_nba_data(
    session: AsyncSession,
    fetched: NbaFetch,
    on_stage: StageCallback | None = None,
) -> NbaImportResult:
    """Persist one NBA snapshot in a single transaction. Row counts stamped with this transaction's
    timestamp are verified before commit; any failure rolls back and keeps the previous snapshot."""
    season, as_of = fetched.season, fetched.as_of
    async with session.begin():
        stamped = await session.scalar(select(func.now()))
        _notify(on_stage, NBA_TEAMS_PLAYERS)
        teams_imported = await import_teams(session, fetched.team_records)
        players_imported, identity_mappings_added = await import_players(session, fetched.player_records)
        _notify(on_stage, NBA_SCHEDULE)
        games_imported, player_schedule_entries, unresolved_schedule_team_references = await import_schedule(
            session, season, fetched.schedule_records, as_of
        )
        _notify(on_stage, NBA_GAME_LOGS)
        game_logs_imported, players_added_from_game_logs = await import_game_logs(
            session, season, fetched.game_log_records
        )
        if players_added_from_game_logs:
            player_schedule_entries = await rebuild_player_schedule(session, season, as_of)
        _notify(on_stage, NBA_SEASON_STATS)
        player_season_stats_imported = 0
        for stats_season, season_type, records in fetched.stats_batches:
            player_season_stats_imported += await import_player_season_stats(
                session, stats_season, season_type, records
            )
        _notify(on_stage, NBA_TEAMS_PLAYERS)
        identity_mappings_added += await link_player_identities(session)

        checks = (
            (NBA_TEAMS_PLAYERS, "teams", await _count_at(session, NbaTeam, stamped), teams_imported),
            (NBA_SCHEDULE, "games", await _count_at(session, NbaGame, stamped), games_imported),
            (NBA_SCHEDULE, "player schedule rows",
                await _count_at(session, PlayerSchedule, stamped, PlayerSchedule.season == season), player_schedule_entries),
            (NBA_GAME_LOGS, "game logs", await _count_at(session, PlayerGameLog, stamped), game_logs_imported),
            (NBA_SEASON_STATS, "season stat rows",
                await _count_at(session, NbaPlayerSeasonStats, stamped), player_season_stats_imported),
        )
        for stage, label, persisted, expected in checks:
            if persisted != expected:
                raise NbaPersistenceVerificationError(
                    stage, f"NBA {label}: {persisted} rows were persisted but {expected} were imported")
        if await _count_at(session, NbaPlayer, stamped) < players_imported:
            raise NbaPersistenceVerificationError(NBA_TEAMS_PLAYERS, "NBA players were not all persisted")

    latest = max((normalize_game_log(record, season)["game_date"] for record in fetched.game_log_records), default=None)
    return NbaImportResult(
        season=season,
        recent_days=fetched.recent_days,
        teams_imported=teams_imported,
        players_imported=players_imported,
        players_added_from_game_logs=players_added_from_game_logs,
        player_season_stats_imported=player_season_stats_imported,
        games_imported=games_imported,
        game_logs_imported=game_logs_imported,
        player_schedule_entries=player_schedule_entries,
        unresolved_schedule_team_references=unresolved_schedule_team_references,
        identity_mappings_added=identity_mappings_added,
        imported_at=stamped,
        latest_game_date=latest,
    )


async def import_nba_data(
    session: AsyncSession,
    season: str,
    recent_days: int = 30,
    source: Any | None = None,
    as_of: date | None = None,
) -> NbaImportResult:
    fetched = await fetch_nba_data(season, recent_days, source, as_of)
    return await persist_nba_data(session, fetched)

"""One-click waiver data refresh: the single backend owner of the Yahoo and NBA imports the Waiver
Center needs, run in order as a background job with structured, re-readable stage progress.

Source boundaries keep their own all-or-nothing transactions: Yahoo league/settings/teams, then the
Yahoo player pool + every team roster (with slots, statuses and availability), then the NBA snapshot.
A later boundary failing never rolls back an earlier committed one, and every stage is judged by
re-reading persisted rows, never by a provider HTTP status. Ordinary waiver GETs never trigger it.
"""
import asyncio
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.database import SessionFactory
from app.core.provider_lock import BUSY_DETAIL, ProviderImportBusy, ProviderImportLock
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.leagues.service import import_manager_leagues
from app.features.nba.models import NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule, NbaGame
from app.features.players.models import FantasyTeam, LeaguePlayer, RosterEntry
from app.features.players.service import (
    PRACTICE_LEAGUE_PREFIX,
    YahooPlayerFetch,
    fetch_yahoo_players,
    is_local_practice_league,
    persist_yahoo_players,
    resolve_import_leagues,
    validate_yahoo_snapshot,
)
from app.features.waivers.capacity import INJURY_SLOTS
from app.features.waivers.contracts import (
    EvidenceStatus,
    RefreshCheck,
    RefreshJob,
    RefreshStage,
    RefreshStageName,
    RefreshStatus,
)
from app.services.draft.player_status import status_is_supported
from app.services.nba.client import NbaApiClient, NbaDataSourceError
from app.services.nba.importer import NbaPersistenceVerificationError, fetch_nba_data, persist_nba_data
from app.services.yahoo.auth import YahooAuthService
from app.services.yahoo.client import YahooFantasyClient

logger = logging.getLogger("uvicorn.error")
PACIFIC = ZoneInfo("America/Los_Angeles")
NBA_RECENT_DAYS = 30
YAHOO_FRESH = timedelta(hours=24)
NBA_FRESH = timedelta(days=7)
STAGES: tuple[tuple[RefreshStageName, str, str, str], ...] = (
    ("LEAGUE_SETTINGS", "Yahoo league/settings", "YAHOO", "YAHOO_LEAGUE"),
    ("PLAYER_POOL", "Yahoo player pool", "YAHOO", "YAHOO_PLAYERS"),
    ("LEAGUE_ROSTERS", "Yahoo rosters", "YAHOO", "YAHOO_PLAYERS"),
    ("ROSTER_SLOTS", "Roster slots", "YAHOO", "YAHOO_PLAYERS"),
    ("YAHOO_AVAILABILITY_STATUS", "Yahoo availability and status", "YAHOO", "YAHOO_PLAYERS"),
    ("NBA_TEAMS_PLAYERS", "NBA teams and players", "NBA", "NBA"),
    ("NBA_SCHEDULE", "NBA schedule", "NBA", "NBA"),
    ("NBA_GAME_LOGS", "NBA game logs", "NBA", "NBA"),
    ("NBA_SEASON_STATS", "NBA season stats", "NBA", "NBA"),
    ("POST_REFRESH_VERIFICATION", "Post-refresh verification", "VERIFICATION", "VERIFICATION"),
)
BOUNDARY = {name: boundary for name, _, _, boundary in STAGES}
YAHOO_PLAYER_STAGES: tuple[RefreshStageName, ...] = (
    "PLAYER_POOL", "LEAGUE_ROSTERS", "ROSTER_SLOTS", "YAHOO_AVAILABILITY_STATUS")
NBA_STAGES: tuple[RefreshStageName, ...] = ("NBA_TEAMS_PLAYERS", "NBA_SCHEDULE", "NBA_GAME_LOGS", "NBA_SEASON_STATS")


class PracticeLeagueRequestBlocked(RuntimeError):
    pass


class StageFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class GuardedYahooClient:
    """Read-only Yahoo access for the refresh. Local practice league keys and transaction resources
    are refused before any request is sent; every sent request path is recorded."""

    def __init__(self, inner: Any, blocked_keys: set[str]):
        self.inner = inner
        self.blocked_keys = {key for key in blocked_keys if key}
        self.paths: list[str] = []
        self.blocked_attempts = 0

    async def get_json(self, path: str, access_token: str) -> dict:
        if PRACTICE_LEAGUE_PREFIX in path or any(key in path for key in self.blocked_keys) or "transaction" in path.lower():
            self.blocked_attempts += 1
            raise PracticeLeagueRequestBlocked("A local practice league or transaction resource was refused")
        self.paths.append(path)
        return await self.inner.get_json(path, access_token)


def league_key_for_team(team_key: str) -> str:
    return team_key.rsplit(".t.", 1)[0]


def season_for(league: League | None, today: date) -> str:
    year = league.season if league is not None and league.season else (today.year if today.month >= 7 else today.year - 1)
    return f"{year}-{(year + 1) % 100:02d}"


def pacific_text(value: datetime | None) -> str:
    return value.astimezone(PACIFIC).strftime("%b %d, %Y %I:%M %p %Z") if value else "never"


def _sentence(text: str) -> str:
    text = text.strip()
    return text if text.endswith((".", "!", "?")) else f"{text}."


def safe_failure(error: BaseException, default_code: str) -> tuple[str, str]:
    """A stable code and a user-facing message; never a provider body, credential or traceback."""
    code, message = _classify_failure(error, default_code)
    return code, _sentence(message)


def _classify_failure(error: BaseException, default_code: str) -> tuple[str, str]:
    if isinstance(error, StageFailure):
        return error.code, str(error)
    if isinstance(error, PracticeLeagueRequestBlocked):
        return "PRACTICE_LEAGUE_BLOCKED", "A local practice league or transaction resource was refused before reaching Yahoo."
    if isinstance(error, ProviderImportBusy):
        return "PROVIDER_IMPORT_IN_PROGRESS", BUSY_DETAIL["message"]
    if isinstance(error, NbaPersistenceVerificationError):
        return "PERSISTENCE_NOT_VERIFIED", f"{error} The previous NBA snapshot was kept."
    if isinstance(error, NbaDataSourceError):
        return "NBA_SOURCE_FAILED", "The NBA statistics source did not return usable data. The previous NBA snapshot was kept."
    if isinstance(error, HTTPException):
        detail = error.detail if isinstance(error.detail, str) else "The request could not be completed."
        if error.status_code == 401:
            return "YAHOO_AUTH_REQUIRED", "Yahoo rejected the saved authorization. Reconnect Yahoo, then refresh again."
        if error.status_code == 404:
            return "LEAGUE_NOT_FOUND", detail
        if error.status_code == 422:
            return "PRACTICE_LEAGUE_REJECTED", detail
        if "nba_api" in detail:
            return "NBA_DATA_INVALID", "The NBA source returned inconsistent data. The previous NBA snapshot was kept."
        if "persisted" in detail.lower():
            return "PERSISTENCE_FAILED", detail
        return default_code, detail
    if isinstance(error, SQLAlchemyError):
        return "PERSISTENCE_FAILED", "The database rejected the write. The previous snapshot was kept."
    return "UNEXPECTED_ERROR", "The refresh stopped on an unexpected error. The previous data was kept."


def snapshot_current(roster_at: datetime | None, team_at: datetime | None, league_at: datetime | None,
        settings_at: datetime | None, now: datetime) -> bool:
    """A roster snapshot is current when it is under 24 hours old and not older than the latest
    league/team/settings import (the same rule as the roster API's `stale`)."""
    later = [value for value in (team_at, league_at, settings_at) if value is not None]
    return roster_at is not None and _fresh(roster_at, now, YAHOO_FRESH) and (not later or roster_at >= max(later))


@dataclass
class _Evidence:
    """Persisted evidence as plain values, read once for status and verification (database-only)."""
    league_name: str | None
    league_at: datetime | None
    settings_at: datetime | None
    team_keys: list[str]
    teams_current: int
    roster_snapshots: int
    roster_oldest: datetime | None
    roster_rows: int
    roster_slots_saved: int
    manager_present: bool
    manager_rows: int
    manager_slots_saved: int
    manager_injury_slots: int
    pool_count: int
    pool_oldest: datetime | None
    explicit_statuses: int
    explicit_availability: int
    season: str
    nba_players_at: datetime | None
    nba_teams_at: datetime | None
    schedule_at: datetime | None
    schedule_rows: int
    logs_at: datetime | None
    logs_count: int
    latest_game: date | None
    stats_at: datetime | None
    stats_rows: int


async def read_evidence(session: AsyncSession, league_key: str, team_key: str, now: datetime) -> _Evidence:
    league = (await session.execute(select(League.league_name, League.imported_at, League.season)
        .where(League.league_key == league_key))).first()
    settings_at = await session.scalar(select(LeagueSettings.imported_at).where(LeagueSettings.league_key == league_key))
    teams = (await session.execute(select(Team.team_key, Team.imported_at)
        .where(Team.league_key == league_key).order_by(Team.team_key))).all()
    rosters = dict((await session.execute(select(FantasyTeam.team_key, FantasyTeam.imported_at)
        .where(FantasyTeam.league_key == league_key))).all())
    roster_rows, roster_slots = (await session.execute(select(
        func.count(), func.count(RosterEntry.roster_position)).where(RosterEntry.league_key == league_key))).one()
    manager_slots = list((await session.scalars(
        select(RosterEntry.roster_position).where(RosterEntry.team_key == team_key))).all())
    pool_count, pool_oldest = (await session.execute(select(
        func.count(), func.min(LeaguePlayer.imported_at)).where(LeaguePlayer.league_key == league_key))).one()
    statuses = (await session.scalars(select(LeaguePlayer.source_payload["status"].astext).where(
        LeaguePlayer.league_key == league_key))).all()
    explicit_availability = await session.scalar(select(func.count()).select_from(LeaguePlayer).where(
        LeaguePlayer.league_key == league_key,
        LeaguePlayer.source_payload["ownership"]["ownership_type"].astext.in_(["freeagents", "waivers"])))
    league_at = league.imported_at if league else None
    season_year = league.season if league and league.season else None
    season = (f"{season_year}-{(season_year + 1) % 100:02d}" if season_year
        else season_for(None, now.astimezone(PACIFIC).date()))
    logs_at, logs_count, latest_game = (await session.execute(select(
        func.max(PlayerGameLog.imported_at), func.count(), func.max(PlayerGameLog.game_date)
    ).where(PlayerGameLog.season == season, PlayerGameLog.season_type == "Regular Season"))).one()
    schedule_at, schedule_rows = (await session.execute(select(
        func.max(PlayerSchedule.imported_at), func.count()).where(PlayerSchedule.season == season))).one()
    stats_at, stats_rows = (await session.execute(select(
        func.max(NbaPlayerSeasonStats.imported_at), func.count()).where(NbaPlayerSeasonStats.season == season,
            NbaPlayerSeasonStats.season_type == "Regular Season"))).one()
    return _Evidence(
        league_name=league.league_name if league else None, league_at=league_at, settings_at=settings_at,
        team_keys=[row.team_key for row in teams],
        teams_current=sum(snapshot_current(rosters.get(row.team_key), row.imported_at, league_at, settings_at, now)
            for row in teams),
        roster_snapshots=len(rosters), roster_oldest=min(rosters.values(), default=None),
        roster_rows=roster_rows, roster_slots_saved=roster_slots,
        manager_present=any(row.team_key == team_key for row in teams),
        manager_rows=len(manager_slots), manager_slots_saved=sum(bool(slot) for slot in manager_slots),
        manager_injury_slots=sum(str(slot or "").upper() in INJURY_SLOTS for slot in manager_slots),
        pool_count=pool_count, pool_oldest=pool_oldest,
        explicit_statuses=sum(status_is_supported((status or "").strip().upper() or None) for status in statuses),
        explicit_availability=int(explicit_availability or 0), season=season,
        nba_players_at=await session.scalar(select(func.max(NbaPlayer.imported_at))),
        nba_teams_at=await session.scalar(select(func.max(NbaTeam.imported_at))),
        schedule_at=schedule_at, schedule_rows=schedule_rows, logs_at=logs_at, logs_count=logs_count,
        latest_game=latest_game, stats_at=stats_at, stats_rows=stats_rows,
    )


def _fresh(value: datetime | None, now: datetime, limit: timedelta) -> bool:
    return value is not None and now - value <= limit


def evidence_status(evidence: _Evidence, now: datetime) -> list[EvidenceStatus]:
    """Per-stage persisted freshness, using the waiver model's own freshness rules."""
    today = now.astimezone(PACIFIC).date()

    def item(stage: RefreshStageName, current: bool, missing: bool, as_of: datetime | None, summary: str, detail: str):
        label = next(text for name, text, _, _ in STAGES if name == stage)
        return EvidenceStatus(stage=stage, label=label, state="missing" if missing else "current" if current else "stale",
            as_of=as_of, summary=summary, detail=detail)

    expected = len(evidence.team_keys)
    rosters_complete = expected > 0 and evidence.teams_current == expected
    league_current = _fresh(evidence.league_at, now, YAHOO_FRESH) and _fresh(evidence.settings_at, now, YAHOO_FRESH)
    pool_current = evidence.pool_count > 0 and _fresh(evidence.pool_oldest, now, YAHOO_FRESH)
    logs_current = (_fresh(evidence.logs_at, now, NBA_FRESH) and evidence.latest_game is not None
        and evidence.latest_game >= today - timedelta(days=7))
    return [
        item("LEAGUE_SETTINGS", league_current, evidence.league_at is None or evidence.settings_at is None,
            evidence.settings_at or evidence.league_at,
            f"{evidence.league_name} · {expected} teams" if evidence.league_name else "No saved Yahoo league",
            "Yahoo league, scoring/roster settings and teams; current for 24 hours."),
        item("PLAYER_POOL", pool_current, evidence.pool_count == 0, evidence.pool_oldest,
            f"{evidence.pool_count} players", "Yahoo player pool with statuses; current for 24 hours."),
        item("LEAGUE_ROSTERS", rosters_complete, evidence.roster_snapshots == 0, evidence.roster_oldest,
            f"{evidence.teams_current} of {expected} teams",
            "Every league team's saved roster must be under 24 hours old and newer than the league import."),
        item("ROSTER_SLOTS", rosters_complete and evidence.manager_present and evidence.manager_rows > 0
            and evidence.manager_slots_saved == evidence.manager_rows
            and evidence.roster_slots_saved == evidence.roster_rows,
            evidence.manager_rows == 0, evidence.roster_oldest,
            f"{evidence.manager_slots_saved} of {evidence.manager_rows} saved",
            f"Yahoo slot assignments (selected_position): {evidence.roster_slots_saved} of {evidence.roster_rows} league "
            f"roster players; {evidence.manager_injury_slots} of your players in IL."),
        item("YAHOO_AVAILABILITY_STATUS", rosters_complete and pool_current,
            evidence.roster_snapshots == 0 or evidence.pool_count == 0, evidence.roster_oldest,
            (f"{evidence.explicit_statuses} explicit statuses · Yahoo FA/W state "
                + ("supplied" if evidence.explicit_availability else "not supplied")),
            "Availability is confirmed only when every roster is current; without Yahoo FA/W state unrostered players "
            "must be confirmed in Yahoo."),
        item("NBA_TEAMS_PLAYERS", _fresh(evidence.nba_players_at, now, NBA_FRESH) and _fresh(evidence.nba_teams_at, now, NBA_FRESH),
            evidence.nba_players_at is None, evidence.nba_players_at, "NBA teams and players",
            "Current for 7 days."),
        item("NBA_SCHEDULE", _fresh(evidence.schedule_at, now, NBA_FRESH) and evidence.schedule_rows > 0,
            evidence.schedule_rows == 0, evidence.schedule_at, f"{evidence.schedule_rows} player schedule rows ({evidence.season})",
            "Current for 7 days; coverage stays PARTIAL without a completeness manifest."),
        item("NBA_GAME_LOGS", logs_current, evidence.logs_count == 0, evidence.logs_at,
            f"Latest game {evidence.latest_game.isoformat()}" if evidence.latest_game else "No game logs",
            "Imported within 7 days with a game in the last 7 days."),
        item("NBA_SEASON_STATS", _fresh(evidence.stats_at, now, NBA_FRESH) and evidence.stats_rows > 0,
            evidence.stats_rows == 0, evidence.stats_at, f"{evidence.stats_rows} regular-season rows ({evidence.season})",
            "Current-season regular-season per-game production (the rows the waiver model reads); current for 7 days."),
    ]


class RefreshCoordinator:
    """Owns at most one refresh per process; the provider advisory lock covers other processes and
    the manual import routes. Progress lives in memory; persisted evidence is re-read on demand."""

    def __init__(self) -> None:
        self.session_factory: async_sessionmaker[AsyncSession] = SessionFactory
        self.lock_bind: AsyncEngine | None = None
        self.yahoo_client_factory: Callable[[], Any] = YahooFantasyClient
        self.nba_source_factory: Callable[[], Any] = NbaApiClient
        self.settings_provider: Callable[[], Settings] = get_settings
        self.clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
        self.nba_today: Callable[[], date] = lambda: datetime.now(timezone.utc).date()
        self._job: RefreshJob | None = None
        self._last_success: RefreshJob | None = None
        self._task: asyncio.Task | None = None
        self._start_lock = asyncio.Lock()
        # Whether each source boundary's latest run succeeded; a retry reruns only the failed ones.
        self._boundary_ok: dict[str, bool] = {}

    def reset(self) -> None:
        """Forget jobs and restore production providers (used by tests)."""
        self.__init__()

    def snapshot(self) -> RefreshJob | None:
        return self._job.model_copy(deep=True) if self._job is not None else None

    async def wait(self) -> None:
        if self._task is not None:
            await asyncio.shield(self._task)

    async def start(self, retry_failed: bool = False) -> tuple[RefreshJob, bool]:
        async with self._start_lock:
            if self._job is not None and self._job.active:
                return self.snapshot(), True
            lock = ProviderImportLock(self.lock_bind)
            try:
                await lock.acquire()
            except ProviderImportBusy as error:
                raise HTTPException(409, BUSY_DETAIL) from error
            team_key = self.settings_provider().waiver_manager_team_key
            previous = self._job
            boundaries = {"YAHOO_LEAGUE", "YAHOO_PLAYERS", "NBA"}
            if retry_failed and previous is not None:
                boundaries = {name for name, ok in self._boundary_ok.items() if not ok} or boundaries
            job = RefreshJob(
                job_id=uuid4().hex[:12], state="RUNNING", active=True,
                scope="FAILED_STAGES" if retry_failed and previous is not None else "ALL",
                retry_of=previous.job_id if retry_failed and previous is not None else None,
                league_key=league_key_for_team(team_key), team_key=team_key, requested_at=self.clock(),
                stages=[RefreshStage(stage=name, label=label, source=source) for name, label, source, _ in STAGES],
                message="Refresh queued.",
            )
            self._job = job
            self._task = asyncio.create_task(self._run(job, lock, boundaries))
            return self.snapshot(), False

    async def status(self, session: AsyncSession) -> RefreshStatus:
        now = self.clock()
        team_key = self.settings_provider().waiver_manager_team_key
        evidence = evidence_status(await read_evidence(session, league_key_for_team(team_key), team_key, now), now)
        stale = [item.stage for item in evidence if item.state != "current"]
        if self._last_success is not None:
            last_at, source = self._last_success.completed_at, "refresh_job"
        elif not stale:
            last_at, source = max((item.as_of for item in evidence if item.as_of), default=None), "persisted_evidence"
        else:
            last_at, source = None, None
        return RefreshStatus(job=self.snapshot(), evidence=evidence, needs_refresh=bool(stale), stale_stages=stale,
            last_complete_refresh_at=last_at, last_complete_refresh_source=source, checked_at=now)

    # ---- stage bookkeeping -------------------------------------------------------------------
    def _stage(self, job: RefreshJob, name: RefreshStageName) -> RefreshStage:
        return next(stage for stage in job.stages if stage.stage == name)

    def _begin(self, job: RefreshJob, name: RefreshStageName) -> None:
        stage = self._stage(job, name)
        if stage.state == "PENDING":
            stage.state, stage.started_at = "RUNNING", self.clock()
            job.message = f"{stage.label}: running."

    def _finish(self, job: RefreshJob, name: RefreshStageName, state: str, message: str = "", code: str | None = None) -> None:
        stage = self._stage(job, name)
        stage.started_at = stage.started_at or self.clock()
        stage.state, stage.completed_at, stage.message, stage.error_code = state, self.clock(), message, code
        logger.info("waiver_refresh job=%s stage=%s state=%s code=%s", job.job_id, name, state, code or "-")

    def _verify(self, job: RefreshJob, name: RefreshStageName, checks: list[RefreshCheck], *, fetched: int | None,
            persisted: int | None, source_at: datetime | None, summary: str, success: str) -> bool:
        stage = self._stage(job, name)
        stage.checks, stage.rows_fetched, stage.rows_persisted = checks, fetched, persisted
        stage.source_timestamp, stage.summary = source_at, summary
        passed = all(check.passed for check in checks)
        stage.verification = "PASSED" if passed else "FAILED"
        failed = "; ".join(check.detail for check in checks if not check.passed)
        self._finish(job, name, "SUCCEEDED" if passed else "FAILED", success if passed
            else f"Saved data did not pass verification: {failed}", None if passed else "PERSISTENCE_NOT_VERIFIED")
        return passed

    def _skip_rest(self, job: RefreshJob, names: tuple[RefreshStageName, ...], message: str) -> None:
        for name in names:
            if self._stage(job, name).state in {"PENDING", "RUNNING"}:
                self._finish(job, name, "SKIPPED", message)

    # ---- run ---------------------------------------------------------------------------------
    async def _run(self, job: RefreshJob, lock: ProviderImportLock, boundaries: set[str]) -> None:
        job.started_at = self.clock()
        settings = self.settings_provider()
        yahoo: GuardedYahooClient | None = None
        try:
            async with self.session_factory() as session:
                practice = {row.league_key for row in (await session.scalars(select(League))).all()
                    if is_local_practice_league(row)}
            yahoo = GuardedYahooClient(self.yahoo_client_factory(), practice)
            not_rerun = "Not rerun: this source succeeded in the previous refresh."
            league_ok = True
            if "YAHOO_LEAGUE" in boundaries:
                league_ok = await self._league_stage(job, settings, yahoo)
            else:
                self._skip_rest(job, ("LEAGUE_SETTINGS",), not_rerun)
            if "YAHOO_PLAYERS" not in boundaries:
                self._skip_rest(job, YAHOO_PLAYER_STAGES, not_rerun)
            elif not league_ok:
                self._skip_rest(job, YAHOO_PLAYER_STAGES,
                    "Skipped because the Yahoo league/settings refresh failed; the previous rosters were kept.")
            else:
                await self._player_stages(job, settings, yahoo)
            if "NBA" in boundaries:
                await self._nba_stages(job)
            else:
                self._skip_rest(job, NBA_STAGES, not_rerun)
            await self._verification_stage(job, yahoo)
        except Exception as error:  # noqa: BLE001 - the job must always finish with a structured state
            code, message = safe_failure(error, "UNEXPECTED_ERROR")
            logger.warning("waiver_refresh job=%s unexpected=%s", job.job_id, type(error).__name__)
            running = [stage.stage for stage in job.stages if stage.state in {"RUNNING", "PENDING"}]
            if running:
                self._finish(job, running[0], "FAILED", message, code)
                self._skip_rest(job, tuple(running[1:]), "Not run because an earlier stage stopped the refresh.")
        finally:
            if yahoo is not None:
                job.yahoo_requests = len(yahoo.paths)
                job.practice_league_requests_blocked = yahoo.blocked_attempts
            self._complete(job, boundaries)
            await lock.release()

    def _complete(self, job: RefreshJob, boundaries: set[str]) -> None:
        job.completed_at, job.active = self.clock(), False
        failed = [stage for stage in job.stages if stage.state == "FAILED"]
        persisted = {BOUNDARY[stage.stage] for stage in job.stages
            if stage.state == "SUCCEEDED" and stage.stage != "POST_REFRESH_VERIFICATION"}
        for boundary in boundaries:
            self._boundary_ok[boundary] = all(stage.state == "SUCCEEDED" for stage in job.stages
                if BOUNDARY[stage.stage] == boundary)
        job.board_reload_recommended = bool(persisted)
        if not failed:
            job.state, job.message = "SUCCEEDED", "Waiver data refreshed and verified."
            self._last_success = job
        elif persisted:
            names = ", ".join(stage.label for stage in failed)
            job.state = "PARTIAL_FAILURE"
            job.message = (f"Refresh partially completed. Failed: {names}. Successful sources were saved; "
                "failed sources kept their previous snapshot and remain stale.")
        else:
            job.state = "FAILED"
            job.message = f"Refresh failed at {failed[0].label}: {failed[0].message} No data was changed."
        logger.info("waiver_refresh job=%s complete state=%s", job.job_id, job.state)

    async def _league_stage(self, job: RefreshJob, settings: Settings, yahoo: GuardedYahooClient) -> bool:
        self._begin(job, "LEAGUE_SETTINGS")
        started = self._stage(job, "LEAGUE_SETTINGS").started_at
        try:
            async with self.session_factory() as session:
                result = await import_manager_leagues(session, settings, yahoo)
        except Exception as error:  # noqa: BLE001
            code, message = safe_failure(error, "YAHOO_REQUEST_FAILED")
            self._finish(job, "LEAGUE_SETTINGS", "FAILED", message, code)
            return False
        async with self.session_factory() as session:
            league = (await session.execute(select(League.league_name, League.game_key, League.source_payload)
                .where(League.league_key == job.league_key))).first()
            settings_at = await session.scalar(select(LeagueSettings.imported_at).where(LeagueSettings.league_key == job.league_key))
            teams = (await session.execute(select(Team.team_key, Team.imported_at).where(Team.league_key == job.league_key))).all()
        current = [team for team in teams if team.imported_at >= started]
        practice = league is not None and is_local_practice_league(League(
            league_key=job.league_key, game_key=league.game_key, league_name=league.league_name, source_payload=league.source_payload))
        checks = [
            RefreshCheck(name="target league exists", passed=league is not None,
                detail=f"League {job.league_key} {'is saved' if league else 'was not returned for this Yahoo login'}."),
            RefreshCheck(name="league not a practice league", passed=not practice,
                detail="The target league is a real Yahoo league." if not practice else "The target is a local practice league."),
            RefreshCheck(name="settings current", passed=settings_at is not None and settings_at >= started,
                detail="League settings were saved by this refresh." if settings_at is not None and settings_at >= started
                    else "League settings were not updated by this refresh."),
            RefreshCheck(name="teams current", passed=bool(teams) and len(current) == len(teams),
                detail=f"{len(current)} of {len(teams)} teams saved by this refresh."),
            RefreshCheck(name="configured team present", passed=any(team.team_key == job.team_key for team in teams),
                detail=f"Configured team {job.team_key} {'is' if any(team.team_key == job.team_key for team in teams) else 'is not'} in the league."),
        ]
        return self._verify(job, "LEAGUE_SETTINGS", checks, fetched=result.imported_count + result.team_count,
            persisted=(2 if league is not None and settings_at is not None else 0) + len(current),
            source_at=settings_at,
            summary=f"{league.league_name if league else job.league_key} · {len(teams)} teams",
            success="League, settings and teams saved and verified.")

    async def _player_stages(self, job: RefreshJob, settings: Settings, yahoo: GuardedYahooClient) -> None:
        stage = "PLAYER_POOL"

        def on_fetch(name: str) -> None:
            nonlocal stage
            if name == "LEAGUE_ROSTERS":
                self._stage(job, "PLAYER_POOL").message = "Fetched; waiting for rosters before saving."
            stage = name
            self._begin(job, name)

        self._begin(job, "PLAYER_POOL")
        try:
            async with self.session_factory() as session:
                token = await YahooAuthService(settings).access_token(session)
                await session.commit()
                leagues = await resolve_import_leagues(session, job.league_key)
                fetched = await fetch_yahoo_players(yahoo, token, leagues, on_fetch)
        except Exception as error:  # noqa: BLE001
            code, message = safe_failure(error, "YAHOO_REQUEST_FAILED")
            self._finish(job, stage, "FAILED", f"{message} The previous roster snapshot was kept.", code)
            if stage == "LEAGUE_ROSTERS":
                self._finish(job, "PLAYER_POOL", "SKIPPED", "Fetched but not saved because the roster fetch failed; the previous player pool was kept.")
            self._skip_rest(job, YAHOO_PLAYER_STAGES, "Not saved because an earlier Yahoo stage failed; the previous snapshot was kept.")
            return
        self._begin(job, "ROSTER_SLOTS")
        self._begin(job, "YAHOO_AVAILABILITY_STATUS")
        problems = validate_yahoo_snapshot(fetched)
        if problems:
            self._finish(job, "ROSTER_SLOTS", "FAILED", "Yahoo returned an incomplete roster snapshot: " + "; ".join(problems)
                + ". The previous roster snapshot was kept.", "ROSTER_SLOTS_INCOMPLETE")
            self._skip_rest(job, YAHOO_PLAYER_STAGES, "Not saved because the roster snapshot was incomplete; the previous snapshot was kept.")
            return
        try:
            async with self.session_factory() as session:
                result = await persist_yahoo_players(session, fetched)
        except Exception as error:  # noqa: BLE001
            code, message = safe_failure(error, "PERSISTENCE_FAILED")
            self._finish(job, "PLAYER_POOL", "FAILED", message, code)
            self._skip_rest(job, YAHOO_PLAYER_STAGES, "Not saved: the Yahoo player/roster write failed and was rolled back.")
            return
        await self._verify_players(job, fetched, result.imported_at)

    async def _verify_players(self, job: RefreshJob, fetched: YahooPlayerFetch, stamped: datetime | None) -> None:
        batch = next((row for row in fetched.leagues if row.league.league_key == job.league_key), None)
        expected_players = len(batch.players) if batch else 0
        expected_rosters = len(batch.rosters) if batch else 0
        async with self.session_factory() as session:
            pool = await session.scalar(select(func.count()).select_from(LeaguePlayer).where(
                LeaguePlayer.league_key == job.league_key, LeaguePlayer.imported_at == stamped)) if stamped else 0
            league_at = await session.scalar(select(League.imported_at).where(League.league_key == job.league_key))
            settings_at = await session.scalar(select(LeagueSettings.imported_at).where(LeagueSettings.league_key == job.league_key))
            teams = (await session.execute(select(Team.team_key, Team.imported_at).where(Team.league_key == job.league_key))).all()
            snapshots = dict((await session.execute(select(FantasyTeam.team_key, FantasyTeam.imported_at).where(
                FantasyTeam.league_key == job.league_key))).all())
            entries = list((await session.execute(select(RosterEntry.team_key, RosterEntry.roster_position,
                RosterEntry.imported_at).where(RosterEntry.league_key == job.league_key))).all())
            statuses = (await session.scalars(select(LeaguePlayer.source_payload["status"].astext).where(
                LeaguePlayer.league_key == job.league_key))).all()
        now = self.clock()
        current_teams = [team for team in teams if snapshots.get(team.team_key) == stamped
            and snapshot_current(stamped, team.imported_at, league_at, settings_at, now)]
        stamped_entries = [row for row in entries if row.imported_at == stamped]
        manager = [row for row in stamped_entries if row.team_key == job.team_key]
        slotted = [row for row in stamped_entries if row.roster_position]
        injury = sum(str(row.roster_position or "").upper() in INJURY_SLOTS for row in manager)
        explicit = sum(status_is_supported((status or "").strip().upper() or None) for status in statuses)
        explicit_fa_w = sum(1 for player in (batch.players.values() if batch else [])
            if isinstance(player.source_payload.get("ownership"), dict)
            and player.source_payload["ownership"].get("ownership_type") in {"freeagents", "waivers"})
        self._verify(job, "PLAYER_POOL", [
            RefreshCheck(name="player pool persisted", passed=pool == expected_players and pool > 0,
                detail=f"{pool} of {expected_players} fetched players saved with this refresh's timestamp."),
        ], fetched=batch.pool_record_count if batch else 0, persisted=pool, source_at=stamped,
            summary=f"{pool} players", success="Player pool saved and verified.")
        rosters_ok = self._verify(job, "LEAGUE_ROSTERS", [
            RefreshCheck(name="every real team roster current", passed=bool(teams) and len(current_teams) == len(teams),
                detail=f"{len(current_teams)} of {len(teams)} team rosters saved by this refresh."),
            RefreshCheck(name="roster rows persisted", passed=len(stamped_entries) == expected_rosters == len(entries),
                detail=f"{len(stamped_entries)} of {expected_rosters} roster players saved."),
            RefreshCheck(name="configured roster present", passed=bool(manager),
                detail=f"{len(manager)} players on the configured team's saved roster."),
        ], fetched=sum(batch.roster_counts.values()) if batch else 0, persisted=len(stamped_entries), source_at=stamped,
            summary=f"{len(current_teams)} of {len(teams)} teams", success="Every team roster saved and verified.")
        self._verify(job, "ROSTER_SLOTS", [
            RefreshCheck(name="selected_position persisted", passed=bool(stamped_entries) and len(slotted) == len(stamped_entries),
                detail=f"Yahoo slots saved for {len(slotted)} of {len(stamped_entries)} roster players."),
            RefreshCheck(name="configured roster slots", passed=bool(manager) and all(row.roster_position for row in manager),
                detail=f"{sum(bool(row.roster_position) for row in manager)} of {len(manager)} of your players have a saved slot ({injury} in IL)."),
        ], fetched=sum(1 for row in (batch.rosters if batch else []) if row["roster_position"]), persisted=len(slotted),
            source_at=stamped, summary=f"{sum(bool(row.roster_position) for row in manager)} of {len(manager)} saved",
            success="Roster slots saved and verified.")
        self._verify(job, "YAHOO_AVAILABILITY_STATUS", [
            RefreshCheck(name="availability snapshot complete", passed=rosters_ok,
                detail="Availability is current only when every team roster is current."),
            RefreshCheck(name="status timestamp current", passed=pool == expected_players and pool > 0,
                detail=f"{explicit} players carry an explicit Yahoo status (O/OFS/NA/Q/P); a missing or blank status is never treated as healthy."),
        ], fetched=expected_players, persisted=pool, source_at=stamped,
            summary=(f"{explicit} explicit statuses · Yahoo FA/W state "
                + (f"supplied for {explicit_fa_w}" if explicit_fa_w else "not supplied (confirm in Yahoo)")),
            success="Availability and statuses current.")

    async def _nba_stages(self, job: RefreshJob) -> None:
        current = {"stage": "NBA_TEAMS_PLAYERS"}

        def on_stage(name: str) -> None:
            current["stage"] = name
            self._begin(job, name)

        async with self.session_factory() as session:
            league_season = await session.scalar(select(League.season).where(League.league_key == job.league_key))
        today = self.clock().astimezone(PACIFIC).date()
        season = (f"{league_season}-{(league_season + 1) % 100:02d}" if league_season else season_for(None, today))
        job.season = season
        try:
            fetched = await fetch_nba_data(season, NBA_RECENT_DAYS, self.nba_source_factory(), self.nba_today(), on_stage)
        except Exception as error:  # noqa: BLE001
            code, message = safe_failure(error, "NBA_SOURCE_FAILED")
            failed = current["stage"]
            self._finish(job, failed, "FAILED", message, code)
            for name in NBA_STAGES[:NBA_STAGES.index(failed)]:
                self._finish(job, name, "SKIPPED", f"Fetched but not saved because {self._stage(job, failed).label} failed; "
                    "the previous NBA snapshot was kept.")
            self._skip_rest(job, NBA_STAGES, f"Not run because {self._stage(job, failed).label} failed; the previous NBA snapshot was kept.")
            return
        current["stage"] = "NBA_TEAMS_PLAYERS"
        try:
            async with self.session_factory() as session:
                result = await persist_nba_data(session, fetched, lambda name: current.__setitem__("stage", name))
        except Exception as error:  # noqa: BLE001
            code, message = safe_failure(error, "PERSISTENCE_FAILED")
            failed = getattr(error, "stage", None) or current["stage"]
            self._finish(job, failed, "FAILED", message, code)
            self._skip_rest(job, NBA_STAGES, f"Not saved: the NBA write failed at {self._stage(job, failed).label} and was rolled back; "
                "the previous NBA snapshot was kept.")
            return
        stamped = result.imported_at
        async with self.session_factory() as session:
            async def count(model, *conditions):
                return int(await session.scalar(select(func.count()).select_from(model).where(model.imported_at == stamped, *conditions)) or 0)
            teams = await count(NbaTeam)
            players = await count(NbaPlayer)
            games = await count(NbaGame, NbaGame.season == season)
            schedule_total = int(await session.scalar(select(func.count()).select_from(PlayerSchedule).where(PlayerSchedule.season == season)) or 0)
            schedule = await count(PlayerSchedule, PlayerSchedule.season == season)
            logs = await count(PlayerGameLog)
            latest = await session.scalar(select(func.max(PlayerGameLog.game_date)).where(
                PlayerGameLog.season == season, PlayerGameLog.season_type == "Regular Season"))
            stats = await count(NbaPlayerSeasonStats)
            season_rows = await count(NbaPlayerSeasonStats, NbaPlayerSeasonStats.season == season,
                NbaPlayerSeasonStats.season_type == "Regular Season")
        committed = RefreshCheck(name="transaction committed", passed=teams > 0,
            detail="Rows written by the NBA transaction are visible after commit.")
        self._verify(job, "NBA_TEAMS_PLAYERS", [committed,
            RefreshCheck(name="teams and players persisted", passed=teams == result.teams_imported and players >= result.players_imported,
                detail=f"{teams} teams and {players} players saved with this refresh's timestamp.")],
            fetched=len(fetched.team_records) + len(fetched.player_records), persisted=teams + players, source_at=stamped,
            summary=f"{teams} teams · {players} players", success="NBA teams and players saved and verified.")
        self._verify(job, "NBA_SCHEDULE", [
            RefreshCheck(name="schedule rows persisted", passed=games == result.games_imported and schedule == schedule_total == result.player_schedule_entries,
                detail=f"{games} games and {schedule} player schedule rows saved for {season}.")],
            fetched=len(fetched.schedule_records), persisted=games + schedule, source_at=stamped,
            summary=f"{games} games · {schedule} player rows", success="NBA schedule saved and verified.")
        self._verify(job, "NBA_GAME_LOGS", [
            RefreshCheck(name="game logs persisted", passed=logs == result.game_logs_imported,
                detail=f"{logs} of {result.game_logs_imported} game logs saved in {(logs + 499) // 500 or 0} batches of up to 500."),
            RefreshCheck(name="latest game date", passed=latest is not None,
                detail=f"Latest saved game {latest.isoformat() if latest else 'none'}.")],
            fetched=len(fetched.game_log_records), persisted=logs, source_at=stamped,
            summary=f"Latest game {latest.isoformat()}" if latest else "No game logs", success="NBA game logs saved and verified.")
        self._verify(job, "NBA_SEASON_STATS", [
            RefreshCheck(name="season statistics persisted", passed=stats == result.player_season_stats_imported and season_rows > 0,
                detail=f"{stats} season rows saved; {season_rows} regular-season rows for {season}, the rows the waiver model reads.")],
            fetched=sum(len(records) for _, _, records in fetched.stats_batches), persisted=stats, source_at=stamped,
            summary=f"{season_rows} regular-season rows ({season})", success="NBA season stats saved and verified.")

    async def _verification_stage(self, job: RefreshJob, yahoo: GuardedYahooClient | None) -> None:
        self._begin(job, "POST_REFRESH_VERIFICATION")
        now = self.clock()
        async with self.session_factory() as session:
            evidence = await read_evidence(session, job.league_key, job.team_key, now)
        items = evidence_status(evidence, now)
        checks = [RefreshCheck(name=item.label, passed=item.state == "current",
            detail=f"{item.label}: {item.state} · {item.summary}") for item in items]
        paths = yahoo.paths if yahoo is not None else []
        checks.extend([
            RefreshCheck(name="no local practice league sent to Yahoo",
                passed=not any(PRACTICE_LEAGUE_PREFIX in path for path in paths)
                    and (yahoo is None or yahoo.blocked_attempts == 0),
                detail=f"{len(paths)} read-only Yahoo requests; none named a local practice league."),
            RefreshCheck(name="no Yahoo transaction executed", passed=not any("transaction" in path.lower() for path in paths),
                detail="The refresh only reads Yahoo; no add, drop or claim is ever submitted."),
        ])
        self._verify(job, "POST_REFRESH_VERIFICATION", checks, fetched=None, persisted=None, source_at=now,
            summary=f"{sum(check.passed for check in checks)} of {len(checks)} checks passed",
            success="Every source is current and verified.")


refresh_coordinator = RefreshCoordinator()

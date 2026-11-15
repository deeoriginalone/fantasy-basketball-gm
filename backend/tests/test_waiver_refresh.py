"""One-click waiver refresh orchestration against disposable PostgreSQL with fixture providers."""
import asyncio
import os
import time
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.provider_lock import ProviderImportBusy, provider_import_lock
from app.features.leagues.models import League, Team
from app.features.nba.contracts import NbaImportResult
from app.features.nba.models import NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog
from app.features.players.contracts import PlayerImportResult
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.waivers import refresh as refresh_module
from app.features.waivers.refresh import RefreshCoordinator, refresh_coordinator
from app.features.waivers.router import router as waivers_router
from app.services.nba import importer as nba_importer
from app.services.nba.client import NbaDataSourceError
from app.services.yahoo.auth import YahooAuthService
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL for refresh orchestration tests")
SLOTS = [("PG", 1), ("SG", 1), ("G", 1), ("SF", 1), ("PF", 1), ("F", 1), ("C", 2), ("Util", 2), ("BN", 3), ("IL", 3)]
NORMAL = [("PG", "PG"), ("SG", "SG"), ("G", "PG,SG"), ("SF", "SF"), ("PF", "PF"), ("F", "SF,PF"), ("C", "C"),
    ("C", "C"), ("Util", "PG"), ("Util", "SF"), ("BN", "C"), ("BN", "PG"), ("BN", "SF")]


class World:
    """A league with a 13-normal + 2-IL manager roster, two rival rosters and free agents."""

    def __init__(self) -> None:
        self.suffix = uuid4().hex[:8]
        self.year = 2200 + int(self.suffix, 16) % 700
        self.season = f"{self.year}-{(self.year + 1) % 100:02d}"
        self.today = datetime.now(timezone.utc).date()
        self.game_key = f"g{self.suffix}"
        self.league_key = f"{self.game_key}.l.{self.suffix}"
        self.manager, self.rival, self.third = (f"{self.league_key}.t.{index}" for index in (1, 2, 3))
        self.practice_key = f"yahoo-mock-practice.{self.suffix}"
        self.abbr, self.away_abbr = f"H{self.suffix[:6]}".upper(), f"A{self.suffix[:6]}".upper()
        self.home_id, self.away_id = f"{self.suffix}h", f"{self.suffix}a"
        self.players: dict[str, dict] = {}
        self.rosters: dict[str, list[tuple[str, str]]] = {self.manager: [], self.rival: [], self.third: []}
        for index, (slot, positions) in enumerate(NORMAL):
            self._player(f"mgr{index}", f"Manager {slot} {index}", positions, None, self.manager, slot)
        self._player("il1", "Injured Guard", "PG,SG", "O", self.manager, "IL")
        self._player("il2", "Injured Forward", "SF,PF", "O", self.manager, "IL")
        self._player("star", "Rival Star", "PG,SG", None, self.rival, "PG", nba=True)
        self._player("rival", "Rival Center", "C", None, self.rival, "C")
        self._player("third", "Third Wing", "SF", None, self.third, "SF")
        self._player("fa_guard", "Free Guard", "PG", None, nba=True)
        self._player("fa_center", "Free Center", "C", None, nba=True)
        self._player("fa_out", "Free Out", "C", "O", nba=True)
        self.league_record = {"league_key": self.league_key, "name": "Refresh Fixture League", "season": str(self.year),
            "current_week": 4, "num_teams": 3, "scoring_type": "headpoint"}

    def _player(self, key, name, positions, status, team=None, slot=None, nba=False):
        eligible = [*positions.split(","), "Util", *(["IL"] if status == "O" else [])]
        fragments = [{"player_key": f"{self.game_key}.p.{self.suffix}{key}", "player_id": f"{self.suffix}{key}"},
            {"name": {"full": name}}, {"editorial_team_abbr": self.abbr, "display_position": positions},
            {"eligible_positions": [{"position": position} for position in eligible]}]
        if status:
            fragments.append({"status": status})
        self.players[key] = {"yahoo_id": f"{self.suffix}{key}", "name": name, "fragments": fragments,
            "nba_id": f"{self.suffix}n{key}" if nba else None, "team": team}
        if team:
            self.rosters[team].append((key, slot))

    def yahoo_id(self, key: str) -> str:
        return self.players[key]["yahoo_id"]

    def settings_payload(self) -> dict:
        stats = [("12", "PTS", 1), ("15", "REB", 1.2), ("16", "AST", 1.5), ("17", "STL", 3), ("18", "BLK", 3), ("19", "TO", -1)]
        return {"max_weekly_adds": "4", "scoring_type": "headpoint", "uses_faab": "0",
            "roster_positions": [{"roster_position": {"position": position, "count": count,
                "is_starting_position": 0 if position in {"BN", "IL"} else 1}} for position, count in SLOTS],
            "stat_categories": {"stats": [{"stat": {"stat_id": stat_id, "display_name": name}} for stat_id, name, _ in stats]},
            "stat_modifiers": {"stats": [{"stat": {"stat_id": stat_id, "value": str(value)}} for stat_id, _, value in stats]}}

    def team_payload(self, team_key: str, name: str) -> list:
        extras = [{"waiver_priority": 4}, {"roster_adds": {"coverage_type": "week", "coverage_value": 4, "value": "2"}},
            {"is_owned_by_current_login": 1}] if team_key == self.manager else [{"waiver_priority": 2}]
        return [[{"team_key": team_key}, {"name": name}, *extras]]


class FixtureYahoo:
    def __init__(self, world: World, sequence: list, fail_on: str | None = None, delay: float = 0) -> None:
        self.world, self.sequence, self.fail_on, self.delay = world, sequence, fail_on, delay
        self.paths: list[str] = []

    async def get_json(self, path: str, access_token: str) -> dict:
        w = self.world
        self.paths.append(path)
        self.sequence.append(("yahoo", path))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail_on and self.fail_on in path:
            raise HTTPException(status_code=502, detail="Yahoo Fantasy API rejected the league request")
        if path == "games;game_codes=nba":
            return {"fantasy_content": {"games": {"0": {"game": [{"game_key": w.game_key, "game_code": "nba",
                "season": str(w.year), "is_current_game": 1}]}, "count": 1}}}
        if path == f"users;use_login=1/games;game_keys={w.game_key}/leagues":
            return {"fantasy_content": {"users": {"0": {"user": [{"games": {"0": {"game": [{"game_key": w.game_key},
                {"leagues": {"0": {"league": [dict(w.league_record)]}, "count": 1}}]}}}]}}}}
        if path == f"league/{w.league_key}/settings":
            return {"fantasy_content": {"league": [dict(w.league_record), {"settings": [w.settings_payload()]}]}}
        if path == f"league/{w.league_key}/teams":
            names = {w.manager: "Box Score Bully", w.rival: "Rival", w.third: "Third"}
            return {"fantasy_content": {"league": [dict(w.league_record), {"teams": {
                **{str(index): {"team": w.team_payload(key, names[key])} for index, key in enumerate(names)}, "count": 3}}]}}
        if path.startswith(f"league/{w.league_key}/players;start="):
            start = int(path.split("start=")[1].split(";")[0])
            page = list(w.players.values())[start:start + 25]
            return {"fantasy_content": {"league": [dict(w.league_record), {"players": {
                **{str(index): {"player": row["fragments"]} for index, row in enumerate(page)}, "count": len(page)}}]}}
        if path.startswith("team/") and path.endswith("/roster"):
            team_key = path[len("team/"):-len("/roster")]
            entries = w.rosters[team_key]
            return {"fantasy_content": {"team": [[{"team_key": team_key}], {"roster": {"coverage_type": "date", "0": {
                "players": {**{str(index): {"player": [w.players[key]["fragments"], {"selected_position": [
                    {"coverage_type": "date", "date": w.today.isoformat()}, {"position": slot}]}]}
                    for index, (key, slot) in enumerate(entries)}, "count": len(entries)}}}}]}}
        raise AssertionError(f"Unexpected Yahoo path {path}")


class FixtureNba:
    def __init__(self, world: World, sequence: list, fail_at: str | None = None) -> None:
        self.world, self.sequence, self.fail_at = world, sequence, fail_at
        self.calls: list[str] = []

    def _call(self, name: str) -> None:
        self.calls.append(name)
        self.sequence.append(("nba", name))
        if self.fail_at == name:
            raise NbaDataSourceError(f"NBA {name} fetch failed")

    def _players(self) -> list[dict]:
        return [row for row in self.world.players.values() if row["nba_id"]]

    def fetch_teams(self) -> list[dict]:
        self._call("teams")
        w = self.world
        return [{"id": w.home_id, "abbreviation": w.abbr, "full_name": "Fixture Home"},
            {"id": w.away_id, "abbreviation": w.away_abbr, "full_name": "Fixture Away"}]

    def fetch_players(self, season: str) -> list[dict]:
        self._call("players")
        return [{"PERSON_ID": row["nba_id"], "DISPLAY_FIRST_LAST": row["name"], "TEAM_ID": self.world.home_id,
            "TEAM_ABBREVIATION": self.world.abbr, "ROSTERSTATUS": 1} for row in self._players()]

    def _games(self) -> list[tuple[str, date]]:
        w = self.world
        return [(f"{w.suffix}g{offset + 9}", w.today + timedelta(days=offset)) for offset in (-7, -5, -3, -1, 1, 2, 4, 6)]

    def fetch_schedule(self, season: str) -> list[dict]:
        self._call("schedule")
        w = self.world
        return [{"gameId": game_id, "gameDateEst": f"{day.isoformat()}T00:00:00Z",
            "gameStatusText": "Final" if day < w.today else "Scheduled",
            "homeTeam_teamId": w.home_id, "awayTeam_teamId": w.away_id} for game_id, day in self._games()]

    def fetch_recent_game_logs(self, season: str, start: date, end: date) -> list[dict]:
        self._call("logs")
        return [{"PLAYER_ID": row["nba_id"], "PLAYER_NAME": row["name"], "GAME_ID": game_id, "GAME_DATE": day.isoformat(),
            "TEAM_ID": self.world.home_id, "PTS": 20, "REB": 6, "AST": 4, "STL": 1, "BLK": 1, "TOV": 2, "MIN": 30,
            "SEASON_TYPE": "Regular Season"} for row in self._players() for game_id, day in self._games() if day < self.world.today]

    def fetch_player_season_stats(self, season: str, season_type: str) -> list[dict]:
        self._call(f"stats:{season_type}")
        if season != self.world.season or season_type != "Regular Season":
            return []
        return [{"nba_player_id": row["nba_id"], "player_name": row["name"], "team_id": self.world.home_id,
            "team_abbreviation": self.world.abbr, "games_played": 4, "games_started": 4, "minutes_per_game": 30.0,
            "usage_pct": .2, "base_stats": {"PTS": 20, "REB": 6, "AST": 4, "STL": 1, "BLK": 1, "TOV": 2},
            "advanced_stats": {"USG_PCT": .2}, "source_payload": {"fixture": True}} for row in self._players()]


class PreseasonOnlyStatsNba(FixtureNba):
    """The current season's regular-season stats come back empty while preseason rows exist."""

    def fetch_player_season_stats(self, season: str, season_type: str) -> list[dict]:
        swapped = {"Regular Season": "Pre Season", "Pre Season": "Regular Season"}[season_type]
        return super().fetch_player_season_stats(season, swapped) if season == self.world.season else []


@pytest.fixture
def harness(monkeypatch):
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    world = World()
    sequence: list = []

    async def token(self, session) -> str:
        return "fixture-token"

    monkeypatch.setattr(YahooAuthService, "access_token", token)

    def coordinator(yahoo: FixtureYahoo, nba: FixtureNba, target: RefreshCoordinator | None = None) -> RefreshCoordinator:
        target = target or RefreshCoordinator()
        target.session_factory, target.lock_bind = sessions, engine
        target.yahoo_client_factory, target.nba_source_factory = (lambda: yahoo), (lambda: nba)
        target.settings_provider = lambda: Settings(database_url=TEST_DATABASE_URL, waiver_manager_team_key=world.manager)
        target.nba_today = lambda: world.today
        return target

    async def seed() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        async with sessions() as session, session.begin():
            session.add(League(league_key=world.practice_key, game_key="yahoo_mock_practice", league_name="Practice copy",
                season=world.year, source_payload={"practice_source": "fixture", "source_league_key": world.league_key}))

    asyncio.run(seed())
    asyncio.run(engine.dispose())
    yield world, sequence, coordinator, engine, sessions

    async def cleanup() -> None:
        async with sessions() as session, session.begin():
            nba_ids = [row["nba_id"] for row in world.players.values() if row["nba_id"]]
            await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_(nba_ids)))
            await session.execute(delete(NbaGame).where(NbaGame.game_id.like(f"{world.suffix}g%")))
            await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([world.home_id, world.away_id])))
            for key in (world.league_key, world.practice_key):
                await session.execute(delete(League).where(League.league_key == key))
            await session.execute(delete(PlayerIdentity).where(
                PlayerIdentity.yahoo_player_id.in_([row["yahoo_id"] for row in world.players.values()])))
        await engine.dispose()
    asyncio.run(cleanup())


def run(coordinator: RefreshCoordinator, retry_failed: bool = False):
    async def go():
        job, already = await coordinator.start(retry_failed=retry_failed)
        await coordinator.wait()
        return job, already, coordinator.snapshot()
    return asyncio.run(go())


def stages(job) -> dict:
    return {stage.stage: stage for stage in job.stages}


async def roster_rows(sessions, league_key):
    async with sessions() as session:
        return list((await session.execute(select(RosterEntry.team_key, RosterEntry.yahoo_player_id,
            RosterEntry.roster_position, RosterEntry.imported_at).where(RosterEntry.league_key == league_key))).all())


async def nba_stamps(sessions, world):
    async with sessions() as session:
        return {
            "teams": sorted((await session.scalars(select(NbaTeam.imported_at).where(NbaTeam.nba_team_id.in_([world.home_id, world.away_id])))).all()),
            "games": sorted((await session.scalars(select(NbaGame.imported_at).where(NbaGame.game_id.like(f"{world.suffix}g%")))).all()),
            "logs": await session.scalar(select(func.count()).select_from(PlayerGameLog).where(PlayerGameLog.game_id.like(f"{world.suffix}g%"))),
            "log_stamps": sorted(set((await session.scalars(select(PlayerGameLog.imported_at).where(PlayerGameLog.game_id.like(f"{world.suffix}g%")))).all())),
            "stats": sorted(set((await session.scalars(select(NbaPlayerSeasonStats.imported_at).where(NbaPlayerSeasonStats.season == world.season))).all())),
        }


def test_one_refresh_runs_league_players_and_nba_in_order_and_verifies_persisted_results(harness):
    world, sequence, make, engine, sessions = harness
    yahoo, nba = FixtureYahoo(world, sequence), FixtureNba(world, sequence)
    job, already, done = run(make(yahoo, nba))
    assert not already and job.active and job.state == "RUNNING"
    assert done.state == "SUCCEEDED" and not done.active, done.message
    for stage in done.stages:
        assert stage.state == "SUCCEEDED" and stage.verification == "PASSED", (stage.stage, stage.message)
        assert stage.started_at and stage.completed_at and stage.completed_at >= stage.started_at
    by_name = stages(done)
    assert by_name["LEAGUE_ROSTERS"].summary == "3 of 3 teams"
    assert by_name["ROSTER_SLOTS"].summary == "15 of 15 saved"
    assert by_name["PLAYER_POOL"].rows_persisted == len(world.players) == by_name["PLAYER_POOL"].rows_fetched
    assert by_name["NBA_GAME_LOGS"].summary == f"Latest game {(world.today - timedelta(days=1)).isoformat()}"
    assert by_name["NBA_GAME_LOGS"].rows_persisted == by_name["NBA_GAME_LOGS"].rows_fetched == 16
    assert done.season == world.season and done.board_reload_recommended

    # One owner, in order: league/settings/teams, scoped pool + every team roster, then the NBA snapshot.
    yahoo_paths = [path for source, path in sequence if source == "yahoo"]
    assert yahoo_paths[:4] == ["games;game_codes=nba", f"users;use_login=1/games;game_keys={world.game_key}/leagues",
        f"league/{world.league_key}/settings", f"league/{world.league_key}/teams"]
    assert yahoo_paths[4] == f"league/{world.league_key}/players;start=0;count=25"
    assert sorted(yahoo_paths[5:]) == sorted(f"team/{key}/roster" for key in (world.manager, world.rival, world.third))
    first_nba = next(index for index, (source, _) in enumerate(sequence) if source == "nba")
    assert all(source == "yahoo" for source, _ in sequence[:first_nba])
    assert nba.calls == ["teams", "players", "schedule", "logs", "stats:Regular Season", "stats:Regular Season", "stats:Pre Season"]
    assert not any(world.practice_key in path or "yahoo-mock-practice" in path for path in yahoo.paths)
    assert not any("transaction" in path for path in yahoo.paths)
    assert done.yahoo_transactions_executed == 0 and done.practice_league_requests_blocked == 0
    assert done.yahoo_requests == len(yahoo.paths)

    rows = asyncio.run(roster_rows(sessions, world.league_key))
    assert {row.team_key for row in rows} == {world.manager, world.rival, world.third}
    assert all(row.roster_position for row in rows), "selected_position persists for every roster player"
    manager = {row.yahoo_player_id: row.roster_position for row in rows if row.team_key == world.manager}
    assert len(manager) == 15 and sum(slot == "IL" for slot in manager.values()) == 2
    assert manager[world.yahoo_id("il1")] == manager[world.yahoo_id("il2")] == "IL"
    stamps = asyncio.run(nba_stamps(sessions, world))
    assert stamps["logs"] == 16 and len(stamps["log_stamps"]) == 1
    assert stamps["log_stamps"] == stamps["stats"] and datetime.now(timezone.utc) - stamps["log_stamps"][0] < timedelta(minutes=5)


def test_board_after_refresh_reports_full_roster_with_one_open_il_slot_and_never_recommends_rostered_players(harness, monkeypatch):
    world, sequence, make, engine, sessions = harness
    _, _, done = run(make(FixtureYahoo(world, sequence), FixtureNba(world, sequence)))
    assert done.state == "SUCCEEDED", done.message
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", world.manager)
    app = FastAPI()
    app.include_router(waivers_router)

    async def session_override():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    with TestClient(app) as client:
        response = client.get("/api/v1/waivers")
        assert response.status_code == 200, response.text
        board = response.json()
        capacity = board["roster_capacity"]
        assert (capacity["state"], capacity["transaction_shape"], capacity["requires_drop"]) == ("available", "ADD_DROP", True)
        assert (capacity["occupied_roster_spots"], capacity["non_injury_capacity"], capacity["open_roster_spots"]) == (13, 13, 0)
        assert (capacity["occupied_injury_slots"], capacity["injury_slot_capacity"], capacity["open_injury_slots"]) == (2, 3, 1)
        assert capacity["move_to_injury_slot_options"] == [], "IL occupants free no regular spot"
        assert capacity["headline"] == "ROSTER FULL — AN ADD REQUIRES A DROP"
        acquisition = board["acquisition_context"]
        assert (acquisition["weekly_adds_used"], acquisition["weekly_add_limit"], acquisition["weekly_adds_remaining"],
            acquisition["current_priority"], acquisition["yahoo_week"], acquisition["state"]) == (2, 4, 2, 4, 4, "available")
        ids = {key: next(row["player_id"] for row in [*board["roster"], *board["decision_support"]["options"]]
            if row["player_name"] == world.players[key]["name"]) for key in ("fa_guard", "fa_center")}
        assert set(ids.values()) <= set(board["eligible_candidate_ids"])
        options = {row["player_name"]: row for row in board["decision_support"]["options"]}
        assert options["Free Guard"]["availability_classification"] == "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT"
        assert options["Free Guard"]["availability_label"] == "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO"
        # The high-production rival player is on another team's current roster: never a candidate or target.
        for name in ("Rival Star", "Rival Center", "Third Wing", "Free Out"):
            assert name not in options
        assert board["decision_support"]["potential_target_ids"] == []
        assert board["availability_summary"]["counts"]["ROSTERED_BY_OTHER_TEAM"] == 3
        assert board["availability_summary"]["counts"]["EXCLUDED_STATUS"] == 1
        assert board["availability_summary"]["source_gap"].startswith("The existing Yahoo player-pool import")

        async def stale_third_roster() -> None:
            async with sessions() as session, session.begin():
                snapshot = await session.get(FantasyTeam, world.third)
                snapshot.imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        asyncio.run(stale_third_roster())
        response = client.get("/api/v1/waivers")
        assert response.status_code == 200, response.text
        stale = response.json()
        stale_options = {row["player_name"]: row for row in stale["decision_support"]["options"]}
        assert stale["eligible_candidate_ids"] == [] and stale["decision_support"]["best_measured_ids"] == []
        assert stale_options["Free Guard"]["classification"] == "POTENTIAL_TARGET"
        assert stale_options["Free Guard"]["availability_classification"] == "SOURCE_STALE"
        for name in ("Rival Star", "Rival Center", "Third Wing"):
            assert name not in stale_options, "rostered by another team: never a potential target"
        targets = set(stale["decision_support"]["potential_target_ids"])
        assert {stale_options["Free Guard"]["player_id"], stale_options["Free Center"]["player_id"]} <= targets


def test_nba_failure_keeps_yahoo_committed_and_previous_nba_snapshot_then_retry_reruns_only_nba(harness):
    world, sequence, make, engine, sessions = harness
    coordinator = make(FixtureYahoo(world, sequence), FixtureNba(world, sequence))
    _, _, first = run(coordinator)
    assert first.state == "SUCCEEDED", first.message
    before = asyncio.run(nba_stamps(sessions, world))
    yahoo = FixtureYahoo(world, sequence)
    make(yahoo, FixtureNba(world, sequence, fail_at="logs"), coordinator)
    _, _, failed = run(coordinator)
    by_name = stages(failed)
    assert failed.state == "PARTIAL_FAILURE" and "NBA game logs" in failed.message
    assert by_name["NBA_GAME_LOGS"].state == "FAILED" and by_name["NBA_GAME_LOGS"].error_code == "NBA_SOURCE_FAILED"
    assert "previous NBA snapshot was kept" in by_name["NBA_GAME_LOGS"].message
    for name in ("NBA_TEAMS_PLAYERS", "NBA_SCHEDULE"):
        assert by_name[name].state == "SKIPPED" and by_name[name].message.startswith("Fetched but not saved")
    assert by_name["NBA_SEASON_STATS"].state == "SKIPPED" and by_name["NBA_SEASON_STATS"].message.startswith("Not run")
    for name in ("LEAGUE_SETTINGS", "PLAYER_POOL", "LEAGUE_ROSTERS", "ROSTER_SLOTS", "YAHOO_AVAILABILITY_STATUS"):
        assert by_name[name].state == "SUCCEEDED", name
    assert asyncio.run(nba_stamps(sessions, world)) == before, "the previous NBA snapshot is untouched"
    rows = asyncio.run(roster_rows(sessions, world.league_key))
    assert {row.imported_at for row in rows} == {by_name["LEAGUE_ROSTERS"].source_timestamp}, "Yahoo success stays committed"

    retry_yahoo, retry_nba = FixtureYahoo(world, sequence), FixtureNba(world, sequence)
    make(retry_yahoo, retry_nba, coordinator)
    _, _, retried = run(coordinator, retry_failed=True)
    retry_stages = stages(retried)
    assert retried.scope == "FAILED_STAGES" and retried.retry_of == failed.job_id
    assert retried.state == "SUCCEEDED", retried.message
    assert retry_yahoo.paths == [], "Retry Failed Stage reran only the NBA boundary"
    assert all(retry_stages[name].state == "SKIPPED" and retry_stages[name].message.startswith("Not rerun")
        for name in ("LEAGUE_SETTINGS", "PLAYER_POOL", "LEAGUE_ROSTERS", "ROSTER_SLOTS", "YAHOO_AVAILABILITY_STATUS"))
    assert all(retry_stages[name].state == "SUCCEEDED" for name in ("NBA_TEAMS_PLAYERS", "NBA_SCHEDULE", "NBA_GAME_LOGS", "NBA_SEASON_STATS"))
    assert retry_nba.calls[0] == "teams"


def test_nba_write_failure_rolls_back_the_whole_nba_snapshot(harness, monkeypatch):
    world, sequence, make, engine, sessions = harness
    coordinator = make(FixtureYahoo(world, sequence), FixtureNba(world, sequence))
    assert run(coordinator)[2].state == "SUCCEEDED"
    before = asyncio.run(nba_stamps(sessions, world))

    async def broken_logs(*args, **kwargs):
        raise SQLAlchemyError("synthetic write failure")
    monkeypatch.setattr(nba_importer, "import_game_logs", broken_logs)
    make(FixtureYahoo(world, sequence), FixtureNba(world, sequence), coordinator)
    _, _, failed = run(coordinator)
    by_name = stages(failed)
    assert failed.state == "PARTIAL_FAILURE"
    assert (by_name["NBA_GAME_LOGS"].state, by_name["NBA_GAME_LOGS"].error_code) == ("FAILED", "PERSISTENCE_FAILED")
    assert all(by_name[name].state == "SKIPPED" and "rolled back" in by_name[name].message
        for name in ("NBA_TEAMS_PLAYERS", "NBA_SCHEDULE", "NBA_SEASON_STATS"))
    assert asyncio.run(nba_stamps(sessions, world)) == before, "teams, schedule and stats rolled back with the logs"


def test_yahoo_roster_failure_is_structured_and_keeps_the_previous_rosters(harness):
    world, sequence, make, engine, sessions = harness
    coordinator = make(FixtureYahoo(world, sequence), FixtureNba(world, sequence))
    assert run(coordinator)[2].state == "SUCCEEDED"
    before = asyncio.run(roster_rows(sessions, world.league_key))
    make(FixtureYahoo(world, sequence, fail_on=f"team/{world.rival}/roster"), FixtureNba(world, sequence), coordinator)
    _, _, failed = run(coordinator)
    by_name = stages(failed)
    assert failed.state == "PARTIAL_FAILURE" and "Yahoo rosters" in failed.message
    assert (by_name["LEAGUE_ROSTERS"].state, by_name["LEAGUE_ROSTERS"].error_code) == ("FAILED", "YAHOO_REQUEST_FAILED")
    assert "previous roster snapshot was kept" in by_name["LEAGUE_ROSTERS"].message
    assert by_name["PLAYER_POOL"].state == "SKIPPED" and by_name["PLAYER_POOL"].message.startswith("Fetched but not saved")
    assert by_name["ROSTER_SLOTS"].state == by_name["YAHOO_AVAILABILITY_STATUS"].state == "SKIPPED"
    assert by_name["LEAGUE_SETTINGS"].state == "SUCCEEDED" and by_name["NBA_GAME_LOGS"].state == "SUCCEEDED"
    assert asyncio.run(roster_rows(sessions, world.league_key)) == before


def test_verification_catches_success_shaped_results_with_unchanged_timestamps(harness, monkeypatch):
    world, sequence, make, engine, sessions = harness

    async def fake_players(session, fetched):
        return PlayerImportResult(league_count=1, players_seen=len(fetched.global_players), created_count=0,
            updated_count=0, unchanged_count=0, roster_entry_count=fetched.roster_entry_count, changes=[],
            imported_at=datetime.now(timezone.utc))

    async def fake_nba(session, fetched, on_stage=None):
        return NbaImportResult(season=fetched.season, recent_days=30, teams_imported=2, players_imported=4,
            players_added_from_game_logs=0, player_season_stats_imported=4, games_imported=8, game_logs_imported=16,
            player_schedule_entries=16, unresolved_schedule_team_references=0, identity_mappings_added=0,
            imported_at=datetime.now(timezone.utc), latest_game_date=world.today)

    monkeypatch.setattr(refresh_module, "persist_yahoo_players", fake_players)
    monkeypatch.setattr(refresh_module, "persist_nba_data", fake_nba)
    _, _, done = run(make(FixtureYahoo(world, sequence), FixtureNba(world, sequence)))
    by_name = stages(done)
    assert done.state == "PARTIAL_FAILURE"
    for name in ("PLAYER_POOL", "LEAGUE_ROSTERS", "ROSTER_SLOTS", "NBA_TEAMS_PLAYERS", "NBA_GAME_LOGS", "NBA_SEASON_STATS"):
        assert by_name[name].state == "FAILED" and by_name[name].error_code == "PERSISTENCE_NOT_VERIFIED", name
        assert by_name[name].verification == "FAILED"
    assert by_name["POST_REFRESH_VERIFICATION"].state == "FAILED"


def test_verification_requires_current_regular_season_stats_not_just_preseason_rows(harness):
    # Real-data finding (2026-11-14): the season-stats check counted 577 preseason rows that the waiver model never
    # reads, so a refresh without regular-season stats would still have been reported as verified.
    world, sequence, make, engine, sessions = harness
    _, _, job = run(make(FixtureYahoo(world, sequence), PreseasonOnlyStatsNba(world, sequence)))
    by_name = stages(job)
    stats = by_name["NBA_SEASON_STATS"]
    assert job.state == "PARTIAL_FAILURE"
    assert (stats.state, stats.error_code, stats.verification) == ("FAILED", "PERSISTENCE_NOT_VERIFIED", "FAILED")
    assert "0 regular-season rows" in stats.message
    assert by_name["NBA_GAME_LOGS"].state == "SUCCEEDED"
    verification = {check.name: check for check in by_name["POST_REFRESH_VERIFICATION"].checks}
    assert not verification["NBA season stats"].passed


def test_concurrent_refresh_requests_share_one_job_and_block_other_provider_imports(harness):
    world, sequence, make, engine, sessions = harness
    yahoo = FixtureYahoo(world, sequence, delay=0.05)
    coordinator = make(yahoo, FixtureNba(world, sequence))

    async def go():
        first, first_running = await coordinator.start()
        second, second_running = await coordinator.start()
        with pytest.raises(ProviderImportBusy):
            async with provider_import_lock(engine):
                pass
        await coordinator.wait()
        async with provider_import_lock(engine):
            pass
        return first, first_running, second, second_running
    first, first_running, second, second_running = asyncio.run(go())
    assert not first_running and second_running and first.job_id == second.job_id
    assert sum(path.startswith("users;use_login=1") for path in yahoo.paths) == 1


def test_progress_rereads_safely_and_only_the_refresh_post_mutates(harness, monkeypatch):
    world, sequence, make, engine, sessions = harness
    yahoo, nba = FixtureYahoo(world, sequence), FixtureNba(world, sequence)
    refresh_coordinator.reset()
    make(yahoo, nba, refresh_coordinator)
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", world.manager)
    app = FastAPI()
    app.include_router(waivers_router)

    async def session_override():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_session] = session_override
    try:
        with TestClient(app) as client:
            idle = client.get("/api/v1/waivers/refresh")
            assert idle.status_code == 200 and idle.json()["job"] is None and idle.json()["needs_refresh"]
            started = client.post("/api/v1/waivers/refresh")
            assert started.status_code == 202 and started.json()["job"]["active"]
            for _ in range(200):
                status = client.get("/api/v1/waivers/refresh").json()
                if not status["job"]["active"]:
                    break
                time.sleep(0.05)
            assert status["job"]["state"] == "SUCCEEDED", status["job"]["message"]
            assert status["needs_refresh"] is False and status["stale_stages"] == []
            assert status["last_complete_refresh_source"] == "refresh_job"
            assert {item["state"] for item in status["evidence"]} == {"current"}

            statements: list[str] = []

            def guard(connection, cursor, statement, parameters, context, executemany):
                statements.append(statement.lstrip().split()[0].upper())
            yahoo_calls, nba_calls = len(yahoo.paths), len(nba.calls)
            event.listen(engine.sync_engine, "before_cursor_execute", guard)
            try:
                reads = [client.get("/api/v1/waivers/refresh").json() for _ in range(3)]
                for mode in ("this_week", "next_7_days", "ros"):
                    assert client.get("/api/v1/waivers", params={"mode": mode}).status_code == 200
                    assert client.get("/api/v1/waivers/transactions", params={"mode": mode}).status_code == 200
            finally:
                event.remove(engine.sync_engine, "before_cursor_execute", guard)
            assert reads[0]["job"] == reads[1]["job"] == reads[2]["job"] == status["job"]
            assert set(statements) <= {"SELECT"}, "progress and waiver reads never write"
            assert (len(yahoo.paths), len(nba.calls)) == (yahoo_calls, nba_calls), "reads make no provider calls"
            again = client.post("/api/v1/waivers/refresh", json={"retry_failed": True})
            assert again.status_code == 202 and again.json()["job"]["job_id"] != status["job"]["job_id"]
            for _ in range(200):
                if not client.get("/api/v1/waivers/refresh").json()["job"]["active"]:
                    break
                time.sleep(0.05)
    finally:
        refresh_coordinator.reset()

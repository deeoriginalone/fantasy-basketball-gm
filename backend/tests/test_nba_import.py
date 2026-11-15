import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.nba.models import (
    NbaGame,
    NbaPlayer,
    NbaPlayerSeasonStats,
    NbaTeam,
    PlayerGameLog,
    PlayerSchedule,
)
from app.features.players.models import PlayerIdentity
from app.main import app
from app.services.nba.game_logs import import_game_logs
from app.services.nba.importer import import_nba_data
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def test_nba_import_is_registered_as_post_only() -> None:
    operations = app.openapi()["paths"]["/api/v1/nba/import"]
    assert set(operations) == {"post"}


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_nba_import_is_idempotent_and_preserves_yahoo_identity() -> None:
    assert TEST_DATABASE_URL
    database_name = (make_url(TEST_DATABASE_URL).database or "").lower()
    assert "test" in database_name, "TEST_DATABASE_URL must name an isolated database containing 'test'"

    suffix = uuid4().hex[:10]
    player_one_id = f"nba-{suffix}-1"
    player_two_id = f"nba-{suffix}-2"
    player_three_id = f"nba-{suffix}-3"
    log_only_player_id = f"nba-{suffix}-log-only"
    team_one_id = f"team-{suffix}-1"
    team_two_id = f"team-{suffix}-2"
    game_id = f"game-{suffix}"
    yahoo_ids = [f"yahoo-{suffix}-{index}" for index in range(1, 5)]

    class FixtureNbaSource:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.rename_player_one = False

        def fetch_teams(self) -> list[dict]:
            self.calls.append("teams")
            return [
                {"id": team_one_id, "abbreviation": "BOS", "full_name": "Boston Celtics", "city": "Boston"},
                {"id": team_two_id, "abbreviation": "LAL", "full_name": "Los Angeles Lakers", "city": "Los Angeles"},
            ]

        def fetch_players(self, season: str) -> list[dict]:
            assert season == "2026-27"
            self.calls.append("players")
            player_one_name = "Example Guard Renamed" if self.rename_player_one else "Example Guard"
            rows = [
                {"PERSON_ID": player_one_id, "DISPLAY_FIRST_LAST": player_one_name, "TEAM_ID": team_one_id, "TEAM_ABBREVIATION": "BOS", "ROSTERSTATUS": 1},
                {"PERSON_ID": player_two_id, "DISPLAY_FIRST_LAST": "Duplicate Player", "TEAM_ID": team_two_id, "TEAM_ABBREVIATION": "LAL", "ROSTERSTATUS": 1},
                {"PERSON_ID": player_three_id, "DISPLAY_FIRST_LAST": "Unmatched Player", "TEAM_ID": "0", "TEAM_ABBREVIATION": None, "ROSTERSTATUS": 0},
            ]
            return [*rows, rows[0]]

        def fetch_schedule(self, season: str) -> list[dict]:
            assert season == "2026-27"
            self.calls.append("schedule")
            row = {
                "gameId": game_id,
                "gameDateEst": "2026-10-10T00:00:00Z",
                "gameStatusText": "Scheduled",
                "homeTeam_teamId": team_one_id,
                "awayTeam_teamId": team_two_id,
            }
            tbd_game = {
                "gameId": f"{game_id}-tbd",
                "gameDateEst": "2026-12-04T00:00:00Z",
                "gameStatusText": "TBD",
                "homeTeam_teamId": 0,
                "awayTeam_teamId": 0,
            }
            external_opponent_game = {
                "gameId": f"{game_id}-external",
                "gameDateEst": "2026-10-11T00:00:00Z",
                "gameStatusText": "Final",
                "homeTeam_teamId": team_one_id,
                "awayTeam_teamId": "50015",
                "awayTeam_teamName": "Lions",
            }
            return [row, row, tbd_game, external_opponent_game]

        def fetch_recent_game_logs(self, season: str, start_date: date, end_date: date) -> list[dict]:
            assert season == "2026-27"
            assert start_date == date(2026, 9, 10)
            assert end_date == date(2026, 10, 9)
            self.calls.append("logs")
            row = {
                "PLAYER_ID": player_one_id,
                "PLAYER_NAME": "Example Guard",
                "GAME_ID": game_id,
                "GAME_DATE": "OCT 10, 2026",
                "TEAM_ID": team_one_id,
                "PTS": 10,
                "REB": 4,
                "SEASON_TYPE": "Regular Season",
            }
            log_only_row = {
                "PLAYER_ID": log_only_player_id,
                "PLAYER_NAME": "Log Only Player",
                "GAME_ID": game_id,
                "GAME_DATE": "OCT 10, 2026",
                "TEAM_ID": team_one_id,
                "PTS": 4,
                "REB": 2,
                "SEASON_TYPE": "Pre Season",
            }
            return [row, row, log_only_row]

        def fetch_player_season_stats(self, season: str, season_type: str) -> list[dict]:
            self.calls.append(f"stats:{season}:{season_type}")
            if season == "2025-26" and season_type == "Regular Season":
                return [
                    {
                        "nba_player_id": player_one_id,
                        "player_name": "Example Guard",
                        "team_id": team_one_id,
                        "team_abbreviation": "BOS",
                        "games_played": 80,
                        "games_started": 70,
                        "minutes_per_game": 32.0,
                        "usage_pct": 0.25,
                        "base_stats": {"PTS": 20.0, "REB": 4.0, "AST": 5.0, "STL": 1.0, "BLK": 0.5, "TOV": 2.0},
                        "advanced_stats": {"USG_PCT": 0.25},
                        "source_payload": {"fixture": "prior_regular"},
                    },
                    {
                        "nba_player_id": player_two_id,
                        "player_name": "Duplicate Player",
                        "team_id": team_two_id,
                        "team_abbreviation": "LAL",
                        "games_played": 70,
                        "games_started": 60,
                        "minutes_per_game": 28.0,
                        "usage_pct": 0.18,
                        "base_stats": {"PTS": 12.0, "REB": 8.0, "AST": 2.0, "STL": 0.5, "BLK": 1.5, "TOV": 1.0},
                        "advanced_stats": {"USG_PCT": 0.18},
                        "source_payload": {"fixture": "prior_regular"},
                    },
                ]
            if season == "2026-27" and season_type == "Pre Season":
                return [{
                    "nba_player_id": player_one_id,
                    "player_name": "Example Guard",
                    "team_id": team_one_id,
                    "team_abbreviation": "BOS",
                    "games_played": 2,
                    "games_started": 1,
                    "minutes_per_game": 24.0,
                    "usage_pct": 0.23,
                    "base_stats": {"PTS": 15.0, "REB": 3.0, "AST": 4.0, "STL": 1.0, "BLK": 0.0, "TOV": 1.0},
                    "advanced_stats": {"USG_PCT": 0.23},
                    "source_payload": {"fixture": "current_preseason"},
                }]
            return []

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    source = FixtureNbaSource()

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
            await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN home_team_id DROP NOT NULL"))
            await connection.execute(text("ALTER TABLE nba_games ALTER COLUMN away_team_id DROP NOT NULL"))
        try:
            async with session_factory() as session:
                session.add_all([
                    PlayerIdentity(yahoo_player_id=yahoo_ids[0], player_name="Example Guard", team="BOS", position="PG", status=None),
                    PlayerIdentity(yahoo_player_id=yahoo_ids[1], player_name="Duplicate Player", team="LAL", position="C", status=None),
                    PlayerIdentity(yahoo_player_id=yahoo_ids[2], player_name="Duplicate Player", team="LAL", position="C", status=None),
                    PlayerIdentity(yahoo_player_id=yahoo_ids[3], player_name="Log Only Player", team="BOS", position="SG", status=None),
                ])
                await session.commit()

                first = await import_nba_data(
                    session, "2026-27", recent_days=30, source=source, as_of=date(2026, 10, 9)
                )
                source.rename_player_one = True
                second = await import_nba_data(
                    session, "2026-27", recent_days=30, source=source, as_of=date(2026, 10, 9)
                )

                assert first.teams_imported == second.teams_imported == 2
                assert first.players_imported == second.players_imported == 3
                assert first.games_imported == second.games_imported == 3
                assert first.game_logs_imported == second.game_logs_imported == 2
                assert first.players_added_from_game_logs == 1
                assert second.players_added_from_game_logs == 0
                assert first.player_season_stats_imported == second.player_season_stats_imported == 3
                assert first.player_schedule_entries == second.player_schedule_entries == 3
                assert first.unresolved_schedule_team_references == second.unresolved_schedule_team_references == 1
                assert first.identity_mappings_added == 2
                assert second.identity_mappings_added == 0
                stats_calls = [
                    "stats:2025-26:Regular Season",
                    "stats:2026-27:Regular Season",
                    "stats:2026-27:Pre Season",
                ]
                assert source.calls == ["teams", "players", "schedule", "logs", *stats_calls] * 2

                assert await session.scalar(select(func.count()).select_from(NbaTeam)) == 2
                assert await session.scalar(select(func.count()).select_from(NbaPlayer)) == 4
                assert await session.scalar(select(func.count()).select_from(NbaGame)) == 3
                assert await session.scalar(select(func.count()).select_from(PlayerGameLog)) == 2
                assert await session.scalar(select(func.count()).select_from(PlayerSchedule)) == 3
                assert await session.scalar(select(func.count()).select_from(NbaPlayerSeasonStats)) == 3
                prior_stats = await session.get(
                    NbaPlayerSeasonStats,
                    (player_one_id, "2025-26", "Regular Season"),
                )
                assert prior_stats is not None
                assert prior_stats.games_played == 80
                assert prior_stats.games_started == 70
                assert prior_stats.minutes_per_game == 32.0
                assert prior_stats.usage_pct == 0.25

                identities = list((await session.scalars(
                    select(PlayerIdentity).where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids)).order_by(PlayerIdentity.yahoo_player_id)
                )).all())
                mapped = next(identity for identity in identities if identity.yahoo_player_id == yahoo_ids[0])
                ambiguous = [identity for identity in identities if identity.yahoo_player_id in yahoo_ids[1:3]]
                log_only_identity = next(identity for identity in identities if identity.yahoo_player_id == yahoo_ids[3])
                assert mapped.nba_player_id == player_one_id
                assert mapped.player_name == "Example Guard"
                assert mapped.team == "BOS"
                assert mapped.yahoo_player_id == yahoo_ids[0]
                assert all(identity.nba_player_id is None for identity in ambiguous)
                assert log_only_identity.nba_player_id == log_only_player_id
                tbd_game = await session.get(NbaGame, f"{game_id}-tbd")
                assert tbd_game is not None
                assert tbd_game.home_team_id is None and tbd_game.away_team_id is None
                external_game = await session.get(NbaGame, f"{game_id}-external")
                assert external_game is not None and external_game.away_team_id is None
                assert external_game.source_payload["awayTeam_teamId"] == "50015"
        finally:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(PlayerGameLog).where(PlayerGameLog.nba_player_id.in_([player_one_id, player_two_id, player_three_id, log_only_player_id])))
                    await session.execute(delete(PlayerSchedule).where(PlayerSchedule.nba_player_id.in_([player_one_id, player_two_id, player_three_id, log_only_player_id])))
                    await session.execute(delete(NbaPlayerSeasonStats).where(NbaPlayerSeasonStats.nba_player_id.in_([player_one_id, player_two_id, player_three_id, log_only_player_id])))
                    await session.execute(delete(NbaGame).where(NbaGame.game_id.in_([game_id, f"{game_id}-tbd", f"{game_id}-external"])))
                    await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_([player_one_id, player_two_id, player_three_id, log_only_player_id])))
                    await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([team_one_id, team_two_id])))
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids)))
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_game_log_import_batches_past_postgres_parameter_limit() -> None:
    """A 30-day league log exceeds 4,095 rows; one 8-column INSERT would pass PostgreSQL's 32,767 parameters."""
    assert TEST_DATABASE_URL
    suffix = uuid4().hex[:8]
    home_id, away_id = f"home-{suffix}", f"away-{suffix}"
    game_ids = [f"g-{suffix}-{index}" for index in range(64)]
    player_ids = [f"p-{suffix}-{index}" for index in range(65)]
    records = [
        {"PLAYER_ID": player_id, "PLAYER_NAME": f"Player {player_id}", "GAME_ID": game_id, "GAME_DATE": "2026-11-01",
         "TEAM_ID": home_id, "PTS": 10, "REB": 4, "SEASON_TYPE": "Regular Season"}
        for player_id in player_ids for game_id in game_ids
    ]
    assert len(records) * 8 > 32_767
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with session_factory() as session:
                async with session.begin():
                    session.add_all([
                        NbaTeam(nba_team_id=home_id, abbreviation=f"H{suffix}", full_name="Home Fixture", source_payload={}),
                        NbaTeam(nba_team_id=away_id, abbreviation=f"A{suffix}", full_name="Away Fixture", source_payload={}),
                    ])
                    await session.flush()
                    session.add_all([
                        NbaGame(game_id=game_id, season="2026-27", game_date=date(2026, 11, 1), game_status="Final",
                            home_team_id=home_id, away_team_id=away_id, source_payload={})
                        for game_id in game_ids
                    ])
                async with session.begin():
                    imported, players_added = await import_game_logs(session, "2026-27", records)
                async with session.begin():
                    reimported, players_added_again = await import_game_logs(session, "2026-27", records)
                persisted = await session.scalar(
                    select(func.count()).select_from(PlayerGameLog).where(PlayerGameLog.game_id.in_(game_ids))
                )
                assert imported == reimported == persisted == len(records) == 4160
                assert players_added == len(player_ids)
                assert players_added_again == 0
        finally:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(PlayerGameLog).where(PlayerGameLog.game_id.in_(game_ids)))
                    await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_(player_ids)))
                    await session.execute(delete(NbaGame).where(NbaGame.game_id.in_(game_ids)))
                    await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([home_id, away_id])))
            await engine.dispose()

    asyncio.run(scenario())


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_full_nba_import_over_parameter_limit_commits_every_row_with_current_timestamps() -> None:
    """The complete import (teams, players, schedule, >4,095 logs, stats) commits in one transaction,
    re-imports idempotently, omits nothing and never sends a statement over 32,767 parameters."""
    assert TEST_DATABASE_URL
    suffix = uuid4().hex[:8]
    season, as_of = "2391-92", date(2391, 12, 1)
    home_id, away_id = f"fh-{suffix}", f"fa-{suffix}"
    game_ids = [f"fg-{suffix}-{index}" for index in range(64)]
    player_ids = [f"fp-{suffix}-{index}" for index in range(65)]

    class LargeSource:
        def fetch_teams(self):
            return [{"id": home_id, "abbreviation": f"H{suffix[:6]}", "full_name": "Fixture Home"},
                {"id": away_id, "abbreviation": f"A{suffix[:6]}", "full_name": "Fixture Away"}]

        def fetch_players(self, requested):
            return [{"PERSON_ID": pid, "DISPLAY_FIRST_LAST": f"Player {pid}", "TEAM_ID": home_id,
                "TEAM_ABBREVIATION": f"H{suffix[:6]}", "ROSTERSTATUS": 1} for pid in player_ids]

        def fetch_schedule(self, requested):
            return [{"gameId": game_id, "gameDateEst": f"{(as_of - timedelta(days=index % 20)).isoformat()}T00:00:00Z",
                "gameStatusText": "Final", "homeTeam_teamId": home_id, "awayTeam_teamId": away_id}
                for index, game_id in enumerate(game_ids)] + [{"gameId": f"fg-{suffix}-next", "gameStatusText": "Scheduled",
                "gameDateEst": f"{(as_of + timedelta(days=1)).isoformat()}T00:00:00Z", "homeTeam_teamId": home_id,
                "awayTeam_teamId": away_id}]

        def fetch_recent_game_logs(self, requested, start, end):
            return [{"PLAYER_ID": pid, "PLAYER_NAME": f"Player {pid}", "GAME_ID": game_id,
                "GAME_DATE": (as_of - timedelta(days=index % 20)).isoformat(), "TEAM_ID": home_id, "PTS": 10,
                "SEASON_TYPE": "Regular Season"} for pid in player_ids for index, game_id in enumerate(game_ids)]

        def fetch_player_season_stats(self, requested, season_type):
            if requested != season or season_type != "Regular Season":
                return []
            return [{"nba_player_id": pid, "player_name": f"Player {pid}", "team_id": home_id, "games_played": 20,
                "games_started": 10, "base_stats": {"PTS": 10}, "advanced_stats": {}, "source_payload": {}} for pid in player_ids]

    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    largest: list[int] = [0]

    def measure(connection, cursor, statement, parameters, context, executemany):
        count = len(parameters) if isinstance(parameters, (list, tuple, dict)) else 0
        largest[0] = max(largest[0], count)

    async def stamped(session, model, stamp, *conditions):
        return await session.scalar(select(func.count()).select_from(model).where(model.imported_at == stamp, *conditions))

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        event.listen(engine.sync_engine, "before_cursor_execute", measure)
        try:
            async with session_factory() as session:
                first = await import_nba_data(session, season, 30, LargeSource(), as_of)
            async with session_factory() as session:
                second = await import_nba_data(session, season, 30, LargeSource(), as_of)
            assert first.game_logs_imported == second.game_logs_imported == 64 * 65 > 4095
            assert first.imported_at < second.imported_at
            assert datetime.now(timezone.utc) - second.imported_at < timedelta(minutes=5)
            assert first.latest_game_date == as_of
            async with session_factory() as session:
                logs = await session.scalar(select(func.count()).select_from(PlayerGameLog).where(PlayerGameLog.game_id.like(f"fg-{suffix}-%")))
                assert logs == 64 * 65, "repeated imports neither duplicate nor omit logs"
                assert await stamped(session, PlayerGameLog, second.imported_at, PlayerGameLog.game_id.like(f"fg-{suffix}-%")) == logs
                assert await stamped(session, NbaPlayerSeasonStats, second.imported_at, NbaPlayerSeasonStats.season == season) == 65
                # Rebuilt from games on or after as_of: four logged games dated as_of plus the next game.
                assert await stamped(session, PlayerSchedule, second.imported_at, PlayerSchedule.season == season) == second.player_schedule_entries == 65 * 5
                assert await stamped(session, NbaGame, second.imported_at, NbaGame.season == season) == 65
            assert 0 < largest[0] <= 32_767
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", measure)
            async with session_factory() as session, session.begin():
                await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_(player_ids)))
                await session.execute(delete(NbaGame).where(NbaGame.game_id.like(f"fg-{suffix}-%")))
                await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([home_id, away_id])))
            await engine.dispose()

    asyncio.run(scenario())

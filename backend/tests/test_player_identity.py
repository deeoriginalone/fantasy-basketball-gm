import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings
from app.core.database import Base
from app.features.leagues.models import League, Team
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.players.service import import_yahoo_players
from app.services.yahoo.auth import YahooAuthService
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="Set TEST_DATABASE_URL to run the PostgreSQL player identity integration test",
)


def _player_fragments(player_id: str, name: str, status: str | None = None) -> list[dict]:
    fragments = [
        {"player_key": f"nba.p.{player_id}", "player_id": player_id},
        {"name": {"full": name}},
        {"editorial_team_abbr": "DEN", "display_position": "C"},
    ]
    if status is not None:
        fragments.append({"status": status})
    return fragments


def test_player_identity_create_update_deduplicate_and_roster_persistence(monkeypatch) -> None:
    assert TEST_DATABASE_URL
    database_url = TEST_DATABASE_URL
    suffix = uuid4().hex[:12]
    league_key = f"nba.test.{suffix}"
    team_key = f"{league_key}.t.1"
    yahoo_id_one = f"test-{suffix}-1"
    yahoo_id_two = f"test-{suffix}-2"
    player_state = {"name": "Player One", "status": None, "rostered": False, "malformed": False}

    class FixtureYahooClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            if path.endswith("/players;start=0;count=25"):
                if player_state["malformed"]:
                    return {"fantasy_content": {"league": [{"league_key": league_key}]}}
                player_one = _player_fragments(yahoo_id_one, player_state["name"], player_state["status"])
                duplicate_one = [
                    {"player_key": f"nba.p.{yahoo_id_one}.duplicate", "player_id": yahoo_id_one},
                    {"name": {"full": player_state["name"]}},
                ]
                player_two = _player_fragments(yahoo_id_two, "Player Two", "DTD")
                return {
                    "fantasy_content": {
                        "league": [
                            {
                                "players": {
                                    "0": {"player": player_one},
                                    "1": {"player": duplicate_one},
                                    "2": {"player": player_two},
                                }
                            }
                        ]
                    }
                }
            if path == f"team/{team_key}/roster":
                if not player_state["rostered"]:
                    return {
                        "fantasy_content": {
                            "team": [
                                {
                                    "roster": {
                                        "coverage_type": "week",
                                        "players": {"count": 0},
                                    }
                                }
                            ]
                        }
                    }
                return {
                    "fantasy_content": {
                        "team": [
                            {
                                "roster": {
                                    "0": {
                                        "players": {
                                            "0": {
                                                "player": [
                                                    *_player_fragments(
                                                        yahoo_id_one,
                                                        player_state["name"],
                                                        player_state["status"],
                                                    ),
                                                    {"selected_position": {"position": "C"}},
                                                ]
                                            }
                                        }
                                    }
                                }
                            }
                        ]
                    }
                }
            raise AssertionError(f"Unexpected Yahoo request path: {path}")

    async def fixture_access_token(self, session) -> str:
        return "postgres-test-token"

    monkeypatch.setattr(YahooAuthService, "access_token", fixture_access_token)
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(database_url=database_url)

    async def scenario() -> dict:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with session_factory() as session:
                async with session.begin():
                    session.add(
                        League(
                            league_key=league_key,
                            game_key="nba_test",
                            league_name="Identity Test League",
                            season=2026,
                            source_payload={"league_key": league_key},
                        )
                    )
                    session.add(
                        Team(
                            team_key=team_key,
                            league_key=league_key,
                            team_name="Identity Test Team",
                            source_payload={"team_key": team_key},
                        )
                    )

                first = await import_yahoo_players(
                    session, settings, league_key, FixtureYahooClient()
                )
                identities_after_first = list(
                    (
                        await session.scalars(
                            select(PlayerIdentity)
                            .where(PlayerIdentity.yahoo_player_id.in_([yahoo_id_one, yahoo_id_two]))
                            .order_by(PlayerIdentity.yahoo_player_id)
                        )
                    ).all()
                )
                updated_at_before = identities_after_first[0].updated_at

                second = await import_yahoo_players(
                    session, settings, league_key, FixtureYahooClient()
                )
                pre_draft_roster_rows = await session.scalar(
                    select(func.count()).select_from(RosterEntry).where(RosterEntry.league_key == league_key)
                )
                pre_draft_team_rows = await session.scalar(
                    select(func.count()).select_from(FantasyTeam).where(FantasyTeam.league_key == league_key)
                )
                player_state["rostered"] = True
                post_draft = await import_yahoo_players(
                    session, settings, league_key, FixtureYahooClient()
                )
                post_draft_repeat = await import_yahoo_players(
                    session, settings, league_key, FixtureYahooClient()
                )
                player_state["name"] = "Player One Updated"
                third = await import_yahoo_players(
                    session, settings, league_key, FixtureYahooClient()
                )

                identities = list(
                    (
                        await session.scalars(
                            select(PlayerIdentity)
                            .where(PlayerIdentity.yahoo_player_id.in_([yahoo_id_one, yahoo_id_two]))
                            .order_by(PlayerIdentity.yahoo_player_id)
                        )
                    ).all()
                )
                player_rows = await session.scalar(
                    select(func.count()).select_from(LeaguePlayer).where(LeaguePlayer.league_key == league_key)
                )
                roster_rows = await session.scalar(
                    select(func.count()).select_from(RosterEntry).where(RosterEntry.league_key == league_key)
                )
                fantasy_team_rows = await session.scalar(
                    select(func.count()).select_from(FantasyTeam).where(FantasyTeam.league_key == league_key)
                )
                roster = await session.scalar(
                    select(RosterEntry).where(RosterEntry.league_key == league_key)
                )

                assert first.created_count == 2
                assert first.players_seen == 2
                assert first.roster_entry_count == 0
                assert pre_draft_roster_rows == 0
                assert pre_draft_team_rows == 1
                assert second.created_count == second.updated_count == 0
                assert second.unchanged_count == 2
                assert post_draft.created_count == post_draft.updated_count == 0
                assert post_draft.unchanged_count == 2
                assert post_draft.roster_entry_count == 1
                assert post_draft_repeat.roster_entry_count == 1
                assert post_draft_repeat.unchanged_count == 2
                assert third.updated_count == 1
                assert third.changes[0].fields == ["player_name"]
                assert identities[0].id >= 10001
                assert identities[0].player_name == "Player One Updated"
                assert identities[0].nba_player_id is None
                assert identities[0].espn_player_id is None
                assert identities[0].status is None
                identity_id_before = identities[0].id
                identities[0].nba_player_id = "retained-nba-identity"
                await session.commit()
                player_state["status"] = "O"
                refreshed = await import_yahoo_players(session, settings, league_key, FixtureYahooClient())
                await session.refresh(identities[0])
                assert refreshed.updated_count == 1
                assert identities[0].status == "O"
                assert identities[0].id == identity_id_before
                assert identities[0].nba_player_id == "retained-nba-identity"
                assert identities[0].updated_at >= updated_at_before
                assert player_rows == 2
                assert roster_rows == 1
                assert fantasy_team_rows == 1
                assert roster is not None and roster.player_identity_id == identities[0].id
                assert roster.roster_position == "C"

                player_state["malformed"] = True
                with pytest.raises(HTTPException) as malformed_error:
                    await import_yahoo_players(
                        session, settings, league_key, FixtureYahooClient()
                    )
                assert malformed_error.value.status_code == 502
                assert await session.scalar(
                    select(func.count()).select_from(LeaguePlayer).where(LeaguePlayer.league_key == league_key)
                ) == 2
                assert await session.scalar(
                    select(func.count()).select_from(RosterEntry).where(RosterEntry.league_key == league_key)
                ) == 1

                return {
                    "created": first.created_count,
                    "unchanged": second.unchanged_count,
                    "pre_draft_rosters": pre_draft_roster_rows,
                    "post_draft_rosters": post_draft.roster_entry_count,
                    "updated": third.updated_count,
                    "player_rows": player_rows,
                    "roster_rows": roster_rows,
                    "fantasy_team_rows": fantasy_team_rows,
                }
        finally:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(RosterEntry).where(RosterEntry.league_key == league_key))
                    await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == league_key))
                    await session.execute(delete(FantasyTeam).where(FantasyTeam.league_key == league_key))
                    await session.execute(
                        delete(PlayerIdentity).where(
                            PlayerIdentity.yahoo_player_id.in_([yahoo_id_one, yahoo_id_two])
                        )
                    )
                    await session.execute(delete(Team).where(Team.league_key == league_key))
                    await session.execute(delete(League).where(League.league_key == league_key))
        await engine.dispose()

    asyncio.run(scenario())


def test_default_import_skips_local_mock_practice_leagues(monkeypatch) -> None:
    """Without league_key, local practice pseudo-leagues (key prefix, game key or practice marker) are
    never sent to Yahoo, cannot roll back the real league, and naming one is a client error."""
    assert TEST_DATABASE_URL
    database_url = TEST_DATABASE_URL
    suffix = uuid4().hex[:12]
    league_key = f"nba.test.{suffix}"
    team_key, second_team_key = f"{league_key}.t.1", f"{league_key}.t.2"
    practice_key = f"yahoo-mock-practice.{suffix}"
    game_key_practice = f"practice-by-game.{suffix}"
    marker_practice = f"practice-by-marker.{suffix}"
    practice_keys = (practice_key, game_key_practice, marker_practice)
    yahoo_id = f"test-{suffix}-rostered"
    second_yahoo_id = f"test-{suffix}-second"
    pool_yahoo_id = f"test-{suffix}-practice-pool"
    requested: list[str] = []

    class FixtureYahooClient:
        async def get_json(self, path: str, access_token: str) -> dict:
            requested.append(path)
            if any(key in path for key in practice_keys):
                # What Yahoo does with a key that is not a Yahoo league.
                raise HTTPException(status_code=502, detail="Yahoo Fantasy API rejected the league request")
            if path == f"league/{league_key}/players;start=0;count=25":
                return {"fantasy_content": {"league": [{"players": {
                    "0": {"player": _player_fragments(yahoo_id, "Injured Center", "O")},
                    "1": {"player": _player_fragments(second_yahoo_id, "Bench Guard")},
                }}]}}
            if path == f"team/{team_key}/roster":
                return {"fantasy_content": {"team": [{"roster": {"0": {"players": {"0": {"player": [
                    _player_fragments(yahoo_id, "Injured Center", "O"),
                    {"selected_position": [{"coverage_type": "date", "date": "2026-11-13"}, {"position": "IL"}, {"is_flex": 0}]},
                ]}}}}}]}}
            if path == f"team/{second_team_key}/roster":
                return {"fantasy_content": {"team": [{"roster": {"0": {"players": {"0": {"player": [
                    _player_fragments(second_yahoo_id, "Bench Guard"),
                    {"selected_position": [{"coverage_type": "date", "date": "2026-11-13"}, {"position": "BN"}]},
                ]}}}}}]}}
            # Any other persisted real test league: a valid empty Yahoo collection.
            if path.startswith("league/"):
                return {"fantasy_content": {"league": [{"players": []}]}}
            return {"fantasy_content": {"team": [{"roster": {"coverage_type": "week", "players": {"count": 0}}}]}}

    async def fixture_access_token(self, session) -> str:
        return "postgres-test-token"

    monkeypatch.setattr(YahooAuthService, "access_token", fixture_access_token)
    engine = create_async_engine(database_url, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    settings = Settings(database_url=database_url)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        try:
            async with session_factory() as session:
                async with session.begin():
                    pool_identity = PlayerIdentity(yahoo_player_id=pool_yahoo_id, player_name="Practice Pool Player")
                    session.add_all([
                        League(league_key=league_key, game_key="nba_test", league_name="Real Test League",
                            season=2026, source_payload={"league_key": league_key}),
                        League(league_key=practice_key, game_key="yahoo_mock_practice", season=2026,
                            league_name="Yahoo Mock Practice - disposable", source_payload={"source_league_key": league_key}),
                        League(league_key=game_key_practice, game_key="yahoo_mock_practice", season=2026,
                            league_name="Practice by game key", source_payload={}),
                        League(league_key=marker_practice, game_key="nba_test", season=2026,
                            league_name="Practice by marker", source_payload={"practice_source": "fixture"}),
                        pool_identity,
                    ])
                    await session.flush()
                    session.add_all([
                        Team(team_key=team_key, league_key=league_key, team_name="Box Score Bully",
                            source_payload={"team_key": team_key}),
                        Team(team_key=second_team_key, league_key=league_key, team_name="Rival",
                            source_payload={"team_key": second_team_key}),
                        Team(team_key=f"{practice_key}.slot.1", league_key=practice_key, team_name="Box Score Bully",
                            source_payload={"mock_slot": 1}),
                        LeaguePlayer(league_key=practice_key, yahoo_player_id=pool_yahoo_id,
                            player_identity_id=pool_identity.id, source_payload={"copied": True}),
                    ])

                result = await import_yahoo_players(session, settings, None, FixtureYahooClient())
                rosters = {row.team_key: row for row in (await session.scalars(
                    select(RosterEntry).where(RosterEntry.league_key == league_key))).all()}
                assert not [path for path in requested if any(key in path for key in practice_keys)]
                assert {f"team/{team_key}/roster", f"team/{second_team_key}/roster"} <= set(requested)
                assert result.league_count >= 1 and result.imported_at is not None
                assert set(rosters) == {team_key, second_team_key}, "every real team roster is imported"
                assert rosters[team_key].roster_position == "IL" and rosters[second_team_key].roster_position == "BN"
                assert await session.scalar(select(func.count()).select_from(FantasyTeam).where(
                    FantasyTeam.league_key == league_key, FantasyTeam.imported_at == result.imported_at)) == 2
                assert await session.scalar(
                    select(func.count()).select_from(LeaguePlayer).where(LeaguePlayer.league_key == practice_key)
                ) == 1, "the practice league's copied pool is untouched"

                for key in practice_keys:
                    with pytest.raises(HTTPException) as practice_error:
                        await import_yahoo_players(session, settings, key, FixtureYahooClient())
                    assert practice_error.value.status_code == 422
                    assert "practice" in practice_error.value.detail.lower()
                assert not [path for path in requested if any(key in path for key in practice_keys)]
        finally:
            async with session_factory() as session:
                async with session.begin():
                    for key in (league_key, *practice_keys):
                        await session.execute(delete(RosterEntry).where(RosterEntry.league_key == key))
                        await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == key))
                        await session.execute(delete(FantasyTeam).where(FantasyTeam.league_key == key))
                        await session.execute(delete(Team).where(Team.league_key == key))
                    await session.execute(delete(PlayerIdentity).where(
                        PlayerIdentity.yahoo_player_id.in_([yahoo_id, second_yahoo_id, pool_yahoo_id])))
                    for key in (league_key, *practice_keys):
                        await session.execute(delete(League).where(League.league_key == key))
        await engine.dispose()

    asyncio.run(scenario())

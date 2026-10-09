import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.draft.contracts import DraftUtilityRequest
from app.features.draft.models import DraftPlayerMetric
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.nba.models import NbaPlayer, NbaPlayerSeasonStats, NbaTeam
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.main import app
from app.services.draft.metrics import recompute_draft_metrics
from app.services.draft.utility import calculate_draft_utility

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def test_draft_readiness_routes_are_post_only() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/draft/metrics"]) == {"post"}
    assert set(paths["/api/v1/draft/utility"]) == {"post"}


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_metrics_use_yahoo_points_and_utility_is_roster_specific() -> None:
    assert TEST_DATABASE_URL
    database_name = (make_url(TEST_DATABASE_URL).database or "").lower()
    assert "test" in database_name, "TEST_DATABASE_URL must name an isolated database containing 'test'"

    suffix = uuid4().hex[:10]
    league_key = f"nba.draft.{suffix}"
    team_key = f"{league_key}.t.1"
    nba_team_ids = {"BOS": f"bos-{suffix}", "LAL": f"lal-{suffix}"}
    players = [
        ("Draft Point Guard", "PG", "BOS", "10", {"PTS": 10, "REB": 5, "AST": 4, "STL": 1, "BLK": 0.2, "TOV": 2}),
        ("Draft Shooting Guard", "SG", "LAL", "11", {"PTS": 12, "REB": 3, "AST": 3, "STL": 1, "BLK": 0.1, "TOV": 1}),
        ("Draft Small Forward", "SF", "BOS", "12", {"PTS": 14, "REB": 5, "AST": 2, "STL": 0.8, "BLK": 0.5, "TOV": 1}),
        ("Draft Power Forward", "PF", "LAL", "13", {"PTS": 16, "REB": 7, "AST": 2, "STL": 0.6, "BLK": 1, "TOV": 2}),
        ("Draft Forward", "PF,SF", "BOS", "14", {"PTS": 15, "REB": 6, "AST": 3, "STL": 0.7, "BLK": 0.8, "TOV": 1}),
        ("Higher Raw Guard", "PG", "LAL", "15", {"PTS": 30, "REB": 5, "AST": 6, "STL": 1, "BLK": 0.3, "TOV": 2}),
        ("Roster Fit Center", "C", "BOS", "16", {"PTS": 20, "REB": 12, "AST": 2, "STL": 1, "BLK": 2, "TOV": 1}),
    ]
    yahoo_ids = [f"yahoo-{suffix}-{index}" for index in range(len(players))]
    nba_ids = [f"nba-player-{suffix}-{index}" for index in range(len(players))]
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        try:
            async with session_factory() as session:
                session.add(League(
                    league_key=league_key,
                    game_key="nba_fixture",
                    league_name="Draft Fixture",
                    season=2026,
                    source_payload={"fixture": True},
                ))
                session.add(LeagueSettings(
                    league_key=league_key,
                    scoring_settings={
                        "scoring_type": "headpoint",
                        "categories": [
                            {"stat_id": "12", "name": "PTS", "value": 1},
                            {"stat_id": "15", "name": "REB", "value": 1.2},
                            {"stat_id": "16", "name": "AST", "value": 1.5},
                            {"stat_id": "18", "name": "BLK", "value": 3},
                            {"stat_id": "17", "name": "ST", "value": 3},
                            {"stat_id": "19", "name": "TO", "value": -1},
                        ],
                    },
                    roster_positions=[
                        {"position": "PG", "count": 1, "is_starting_position": 1},
                        {"position": "SG", "count": 1, "is_starting_position": 1},
                        {"position": "G", "count": 1, "is_starting_position": 1},
                        {"position": "SF", "count": 1, "is_starting_position": 1},
                        {"position": "PF", "count": 1, "is_starting_position": 1},
                        {"position": "F", "count": 1, "is_starting_position": 1},
                        {"position": "C", "count": 2, "is_starting_position": 1},
                        {"position": "Util", "count": 2, "is_starting_position": 1},
                        {"position": "BN", "count": 3, "is_starting_position": 0},
                        {"position": "IL", "count": 3, "is_starting_position": 0},
                    ],
                    source_payload={"fixture": True},
                ))
                session.add_all([
                    Team(team_key=team_key, league_key=league_key, team_name="My Team", source_payload={"fixture": True}),
                    Team(team_key=f"{league_key}.t.2", league_key=league_key, team_name="Other Team", source_payload={"fixture": True}),
                    NbaTeam(nba_team_id=nba_team_ids["BOS"], abbreviation="BOS", full_name="Boston Celtics", source_payload={"fixture": True}),
                    NbaTeam(nba_team_id=nba_team_ids["LAL"], abbreviation="LAL", full_name="Los Angeles Lakers", source_payload={"fixture": True}),
                ])
                await session.flush()

                identities = []
                for index, (name, positions, abbreviation, _, base_stats) in enumerate(players):
                    identity = PlayerIdentity(
                        yahoo_player_id=yahoo_ids[index],
                        nba_player_id=nba_ids[index],
                        player_name=name,
                        team=abbreviation,
                        position=positions,
                        status=None,
                    )
                    session.add(identity)
                    await session.flush()
                    identities.append(identity)
                    session.add_all([
                        LeaguePlayer(
                            league_key=league_key,
                            yahoo_player_id=yahoo_ids[index],
                            player_identity_id=identity.id,
                            source_payload={"fixture": True},
                        ),
                        NbaPlayer(
                            nba_player_id=nba_ids[index],
                            player_name=name,
                            team_id=nba_team_ids[abbreviation],
                            team_abbreviation=abbreviation,
                            source_payload={"fixture": True},
                        ),
                        NbaPlayerSeasonStats(
                            nba_player_id=nba_ids[index],
                            season="2025-26",
                            season_type="Regular Season",
                            games_played=80,
                            games_started=60,
                            minutes_per_game=30,
                            usage_pct=0.2,
                            base_stats=base_stats,
                            advanced_stats={"USG_PCT": 0.2},
                            source_payload={"fixture": True},
                        ),
                    ])
                await session.commit()

                metrics_result = await recompute_draft_metrics(session, league_key, "2026-27")
                assert metrics_result.players_scored == 7
                assert metrics_result.players_missing_nba_mapping == 0
                assert metrics_result.players_missing_stats == 0
                guard_identity = identities[5]
                center_identity = identities[6]
                guard_metric = await session.get(DraftPlayerMetric, (league_key, guard_identity.id, "2026-27"))
                center_metric = await session.get(DraftPlayerMetric, (league_key, center_identity.id, "2026-27"))
                assert guard_metric is not None and guard_metric.fantasy_value == pytest.approx(30 + 6 + 9 + 3 + 0.9 - 2)
                assert center_metric is not None and center_metric.fantasy_value == pytest.approx(20 + 14.4 + 3 + 3 + 6 - 1)

                guard_metric.fantasy_value = 50
                guard_metric.replacement_value = -20
                guard_metric.positional_scarcity = 40
                guard_metric.durability_score = 95
                guard_metric.risk_score = 5
                guard_metric.upside_score = 60
                center_metric.fantasy_value = 32
                center_metric.replacement_value = 25
                center_metric.positional_scarcity = 100
                center_metric.durability_score = 80
                center_metric.risk_score = 20
                center_metric.upside_score = 80
                await session.commit()

                request = DraftUtilityRequest(
                    league_key=league_key,
                    team_key=team_key,
                    season="2026-27",
                    drafted_player_ids=[identity.id for identity in identities[:5]],
                    available_player_ids=[guard_identity.id, center_identity.id],
                )
                result = await calculate_draft_utility(session, request)
                assert result.best_pick is not None
                assert result.best_pick.player_identity_id == center_identity.id
                assert result.best_pick.player_name == "Roster Fit Center"
                assert result.best_pick.roster_construction_score == 100
                assert result.unscored_available_player_ids == []
                assert result.best_pick.positional_need_score > 0
                assert result.best_pick.utility_score > guard_metric.fantasy_value
        finally:
            async with session_factory() as session:
                async with session.begin():
                    await session.execute(delete(DraftPlayerMetric).where(DraftPlayerMetric.league_key == league_key))
                    await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == league_key))
                    await session.execute(delete(NbaPlayerSeasonStats).where(NbaPlayerSeasonStats.nba_player_id.in_(nba_ids)))
                    await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.in_(nba_ids)))
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids)))
                    await session.execute(delete(Team).where(Team.league_key == league_key))
                    await session.execute(delete(LeagueSettings).where(LeagueSettings.league_key == league_key))
                    await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_(list(nba_team_ids.values()))))
                    await session.execute(delete(League).where(League.league_key == league_key))
            await engine.dispose()

    asyncio.run(scenario())

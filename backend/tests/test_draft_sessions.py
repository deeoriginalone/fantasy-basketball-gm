import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import Base
from app.features.draft.contracts import (
    DraftPickUndoRequest,
    DraftPickUpdateRequest,
    DraftSessionCreateRequest,
    DraftSessionEventResult,
    DraftTargetRequest,
)
from app.features.draft.models import DraftPickEvent, DraftRecommendationSnapshot, DraftSession
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.players.models import LeaguePlayer, PlayerIdentity
from app.main import app
from app.services.draft.sessions import (
    correct_draft_pick,
    create_draft_session,
    delete_draft_target,
    get_draft_session,
    put_draft_target,
    record_draft_pick,
    undo_draft_pick,
)
from schema_support import create_test_schema

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


def test_draft_session_routes_are_versioned_and_v1_remains_available() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/draft/utility"]) == {"post"}
    assert set(paths["/api/v2/draft/sessions"]) == {"post"}
    assert set(paths["/api/v2/draft/sessions/{session_id}"]) == {"get"}
    assert set(paths["/api/v2/draft/sessions/{session_id}/picks/{overall_pick}"]) == {"post", "put"}


@pytest.mark.skipif(not TEST_DATABASE_URL, reason="Set TEST_DATABASE_URL to an isolated PostgreSQL test database")
def test_persisted_session_pick_lifecycle_and_target_versioning() -> None:
    assert TEST_DATABASE_URL
    assert "test" in (make_url(TEST_DATABASE_URL).database or "").lower()
    suffix = uuid4().hex[:10]
    league_key = f"draft-session.{suffix}"
    team_keys = [f"{league_key}.t.1", f"{league_key}.t.2"]
    yahoo_ids = [f"yahoo-{suffix}-{index}" for index in range(3)]
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def scenario() -> None:
        async with engine.begin() as connection:
            await create_test_schema(connection)
        session_id = None
        try:
            async with session_factory() as session:
                session.add_all([
                    League(
                        league_key=league_key,
                        game_key="nba_fixture",
                        league_name="Draft Session Fixture",
                        season=2026,
                        source_payload={"fixture": True},
                    ),
                    LeagueSettings(
                        league_key=league_key,
                        scoring_settings={"scoring_type": "headpoint", "categories": []},
                        roster_positions=[{"position": "PG", "count": 1, "is_starting_position": 1}],
                        source_payload={"fixture": True},
                    ),
                    Team(team_key=team_keys[0], league_key=league_key, team_name="Manager", source_payload={}),
                    Team(team_key=team_keys[1], league_key=league_key, team_name="Opponent", source_payload={}),
                ])
                await session.flush()
                player_ids = []
                for index, yahoo_id in enumerate(yahoo_ids):
                    identity = PlayerIdentity(
                        yahoo_player_id=yahoo_id,
                        nba_player_id=f"nba-{suffix}-{index}",
                        player_name=f"Session Player {index}",
                        team="BOS",
                        position="PG",
                        status=None,
                    )
                    session.add(identity)
                    await session.flush()
                    player_ids.append(identity.id)
                    session.add(LeaguePlayer(
                        league_key=league_key,
                        yahoo_player_id=yahoo_id,
                        player_identity_id=identity.id,
                        source_payload={"fixture": True},
                    ))
                await session.commit()

                created = await create_draft_session(session, DraftSessionCreateRequest(
                    league_key=league_key,
                    season="2026-27",
                    manager_team_key=team_keys[0],
                    draft_position=1,
                    total_teams=2,
                    rounds=3,
                    team_slots={team_keys[0]: 1, team_keys[1]: 2},
                ))
                session_id = created.state.session_id
                assert created.state.version == 0
                assert created.state.latest_recommendation is not None

                with pytest.raises(HTTPException) as out_of_order:
                    await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                        selected_player_id=player_ids[1],
                        expected_version=0,
                    ))
                assert out_of_order.value.status_code == 409
                assert out_of_order.value.detail["reason_code"] == "OUT_OF_ORDER_PICK"

                first_pick = await record_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[0],
                    expected_version=0,
                ))
                assert first_pick.event == "recorded"
                assert first_pick.state.version == 1
                assert first_pick.state.picks[0].team_slot == 1

                duplicate = await record_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[0],
                    expected_version=0,
                ))
                assert duplicate.event == "unchanged"
                assert duplicate.state.version == 1

                second_pick = await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                    selected_player_id=player_ids[1],
                    expected_version=1,
                ))
                assert second_pick.state.picks[1].team_slot == 2
                assert second_pick.state.version == 2

                corrected = await correct_draft_pick(session, session_id, 1, DraftPickUpdateRequest(
                    selected_player_id=player_ids[2],
                    expected_version=2,
                    source="correction",
                    evidence={"reason": "room selection corrected"},
                ))
                assert corrected.event == "corrected"
                assert corrected.state.picks[0].selected_player_id == player_ids[2]
                assert corrected.state.version == 3

                undone = await undo_draft_pick(session, session_id, 2, DraftPickUndoRequest(
                    expected_version=3,
                    source="undo",
                ))
                assert undone.event == "undone"
                assert undone.state.next_overall_pick == 2
                assert undone.state.picks[1].selected_player_id is None
                assert undone.state.version == 4

                with pytest.raises(HTTPException) as stale:
                    await record_draft_pick(session, session_id, 2, DraftPickUpdateRequest(
                        selected_player_id=player_ids[1],
                        expected_version=3,
                    ))
                assert stale.value.status_code == 409
                assert stale.value.detail["reason_code"] == "STALE_SESSION_VERSION"

                targeted = await put_draft_target(
                    session,
                    session_id,
                    player_ids[1],
                    DraftTargetRequest(status="priority", expected_version=4, note="guard depth"),
                )
                assert targeted.version == 5
                assert targeted.targets[0].status == "priority"
                unmarked = await delete_draft_target(session, session_id, player_ids[1], 5)
                assert unmarked.version == 6
                assert unmarked.targets == []

                async def race_pick(player_id: int):
                    async with session_factory() as client:
                        return await record_draft_pick(
                            client,
                            session_id,
                            2,
                            DraftPickUpdateRequest(
                                selected_player_id=player_id,
                                expected_version=6,
                            ),
                        )

                concurrent_results = await asyncio.gather(
                    race_pick(player_ids[0]),
                    race_pick(player_ids[1]),
                    return_exceptions=True,
                )
                assert sum(
                    isinstance(result, DraftSessionEventResult) and result.event == "recorded"
                    for result in concurrent_results
                ) == 1
                stale_results = [
                    result for result in concurrent_results
                    if isinstance(result, HTTPException)
                ]
                assert len(stale_results) == 1
                assert stale_results[0].status_code == 409
                assert stale_results[0].detail["reason_code"] == "STALE_SESSION_VERSION"

                async with session_factory() as reader:
                    resumed = await get_draft_session(reader, session_id)
                    assert resumed.version == 7
                    assert resumed.recommendation_version == 7
                    events = list((await reader.scalars(
                        select(DraftPickEvent)
                        .where(DraftPickEvent.session_id == session_id)
                        .order_by(DraftPickEvent.id)
                    )).all())
                    snapshots = list((await reader.scalars(
                        select(DraftRecommendationSnapshot).where(
                            DraftRecommendationSnapshot.session_id == session_id
                        )
                    )).all())
                    assert [event.event_type for event in events] == [
                        "recorded", "recorded", "corrected", "undone", "recorded",
                    ]
                    assert len(snapshots) == 8
        finally:
            async with session_factory() as session:
                async with session.begin():
                    if session_id is not None:
                        await session.execute(delete(DraftSession).where(DraftSession.id == session_id))
                    await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == league_key))
                    await session.execute(delete(PlayerIdentity).where(PlayerIdentity.yahoo_player_id.in_(yahoo_ids)))
                    await session.execute(delete(Team).where(Team.league_key == league_key))
                    await session.execute(delete(LeagueSettings).where(LeagueSettings.league_key == league_key))
                    await session.execute(delete(League).where(League.league_key == league_key))
            await engine.dispose()

    asyncio.run(scenario())
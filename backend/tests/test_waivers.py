import asyncio
import os
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException
from sqlalchemy import delete, select, event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import Settings, get_settings
from app.core.database import engine as app_engine, get_session
from app.features.leagues.models import League, LeagueSettings, Team
from app.features.nba.models import NbaGame, NbaPlayer, NbaPlayerSeasonStats, NbaTeam, PlayerGameLog, PlayerSchedule
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.waivers.capacity import (
    RosterEntryEvidence, analyze_roster_capacity, analyze_team_needs, slot_configuration, starting_slot_list,
)
from app.features.waivers.contracts import MODEL_VERSION, Candidate, Components, Evidence, Opportunity, Schedule, ValueEvidence
from app.features.waivers.decision_support import MIN_UNSHRUNK_GAMES, measured_production
from app.features.waivers.service import (
    Context, WAIVER_TIMEZONE, aggregate, analyze_transactions, board_coverage, compare, coverage, current_role, decision_support_for, enrich, freshness, identity_chain_diagnostic, identity_mapping, log_average, option_groups, percentile, production, resolve_schedule, roster_fit, sample_label, scoring_fields, sufficient_sample, transaction_blockers, validated_weights, verify_league_contract, window_end_date,
)
from app.main import app
from app.services.nba.client import NbaApiClient
from app.services.yahoo.client import YahooFantasyClient
from app.services.draft.player_status import status_is_supported
from schema_support import create_test_schema

engine = create_async_engine(os.getenv("TEST_DATABASE_URL") or app_engine.url, poolclass=NullPool)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
NOW = datetime.now(timezone.utc)
WEIGHTS = dict(roster_fit=.35, player_value=.25, opportunity=.15, schedule=.15, acquisition_value=.10)
# Explicit-drop decision tiers as documented: supported moves, WATCH, supported nonpositive HOLD, insufficient evidence.
TIER = {"ADD_DROP": 0, "WATCH": 1, "HOLD": 2, "INSUFFICIENT_EVIDENCE": 3}


def candidate(pid, position="C", value=60, schedule=50):
    return Candidate(
        player_id=pid, yahoo_player_id=str(pid), player_name=f"Player {pid}",
        position=position, nba_team="DEN", yahoo_status=None, availability="free_agent", eligible=True,
        recent=ValueEvidence(value=value, games=4, label="Recent"),
        ros=ValueEvidence(value=value, games=40, label="History, not projection"),
        opportunity=Opportunity(minutes=30), schedule=Schedule(window_start=NOW.date(), window_end=NOW.date()),
        components=Components(roster_fit=50, player_value=value, schedule=schedule, opportunity=70),
        recommended_action="WATCH", hold_type="undetermined", reasons=[], limitations=[], data_quality={},
    )


def attach_capacity(ctx, open_spots=0, injury_slots=0, assignments=None, eligible=None):
    """Attach fresh persisted Yahoo slot evidence: starting slots from ctx.slots, extra roster
    players and `open_spots` on the bench, and `injury_slots` IL slots."""
    bench_players = max(0, len(ctx.roster_ids) - len(ctx.slots))
    positions = [{"position": slot, "count": count} for slot, count in Counter(ctx.slots).items()]
    if bench_players + open_spots:
        positions.append({"position": "BN", "count": bench_players + open_spots})
    if injury_slots:
        positions.append({"position": "IL", "count": injury_slots})
    defaults = iter(list(ctx.slots) + ["BN"] * bench_players)
    assignments = assignments or {}
    entries = [RosterEntryEvidence(
        player_id=pid, player_name=ctx.players[pid].player_name, positions=ctx.players[pid].position,
        roster_slot=assignments[pid] if pid in assignments else next(defaults),
        eligible_positions=(eligible or {}).get(pid, ()), yahoo_status=ctx.players[pid].yahoo_status,
        status_state="available") for pid in ctx.roster_ids]
    ctx.roster_capacity = analyze_roster_capacity(
        roster_positions=positions, settings_state="available", roster_state="available",
        roster_as_of=NOW, status_as_of=NOW, entries=entries, today=NOW.date())
    return ctx


def test_weights_missing_evidence_and_determinism():
    weights = validated_weights(WEIGHTS)
    parts = Components(roster_fit=100, player_value=80, opportunity=40, schedule=60)
    first, effective = aggregate(parts, weights)
    assert first == aggregate(parts, weights)[0]
    assert first == round((35 + 20 + 6 + 9) / .9, 6)
    assert "acquisition_value" not in effective
    assert sum(effective.values()) == pytest.approx(1)
    assert aggregate(Components(roster_fit=100), weights) == (None, {})
    assert percentile(10, [10, 10]) == 50
    assert percentile(10, [1, 10, 20]) == percentile(10, [20, 10, 1])
    for invalid in ({}, {**WEIGHTS, "schedule": float("nan")}, {key: 0 for key in WEIGHTS}):
        with pytest.raises(ValueError):
            validated_weights(invalid)
    assert freshness(NOW - timedelta(days=2), NOW) == "stale"
    assert scoring_fields({"scoring_type": "head", "categories": []}) is None
    assert scoring_fields({"scoring_type": "points", "categories": [{"stat_id": "999", "name": "made up", "value": 1}]}) is None
    assert scoring_fields({"scoring_type": "points", "categories": [{"stat_id": "12"}]}) is None
    assert production({"PTS": 20}, {"PTS": 1, "AST": 2}) is None
    assert production({"PTS": 20, "AST": 0}, {"PTS": 1, "AST": 2}) == 20
    assert log_average([SimpleNamespace(stats_payload={"PTS": 10, "MIN": 20}), SimpleNamespace(stats_payload={"PTS": 20})]) == {"PTS": 15}


def test_personal_application_manager_configuration():
    settings = Settings(_env_file=None)
    assert settings.waiver_manager_team_key == "478.l.50505.t.9"


def test_identity_mapping_requires_normalized_name_and_verified_team_without_writes():
    nba = SimpleNamespace(
        nba_player_id="123", player_name="Jrue Holiday",
        team_id="den-id", team_abbreviation="DEN",
    )
    identity = SimpleNamespace(
        player_name="Jrue Holiday", yahoo_player_id="y123",
        nba_player_id="123", team="DEN",
    )
    by_name = {"jrue holiday": [nba]}
    assert identity_mapping(identity, nba, by_name, {"den-id": "DEN"}, "DEN")[:2] == (
        "EXACT_NAME_TEAM", "Yahoo and NBA names and team abbreviations match.",
    )

    state, reason, _ = identity_mapping(identity, nba, by_name, {"den-id": "DEN"}, "BOS")
    assert state == "AMBIGUOUS"
    assert "conflicts" in reason

    unmapped = SimpleNamespace(
        player_name="Jrue Holiday", yahoo_player_id="y-unmapped",
        nba_player_id=None, team="BOS",
    )
    state, reason, matches = identity_mapping(unmapped, None, by_name, {"den-id": "DEN"}, "BOS")
    assert state == "AMBIGUOUS"
    assert len(matches) == 1
    assert "does not establish a unique" in reason
    assert unmapped.nba_player_id is None


def test_positional_fit_changes_ranking_without_inventing_categories():
    guard = candidate(1, "PG", 90)
    extra_guard = candidate(2, "PG", 90)
    center = candidate(3, "C", 65)
    slots = ["PG", "C"]
    assert roster_fit(center, [guard], slots) == 100
    assert roster_fit(extra_guard, [guard], slots) == 50
    center.components.roster_fit = roster_fit(center, [guard], slots)
    extra_guard.components.roster_fit = roster_fit(extra_guard, [guard], slots)
    assert aggregate(center.components, WEIGHTS)[0] > aggregate(extra_guard.components, WEIGHTS)[0]
    assert roster_fit(center, [candidate(4, None)], slots) is None


def test_swap_model_recomputes_roster_with_fixed_common_weights():
    guard, weak, add = candidate(1, "PG", 60), candidate(2, "PG", 10), candidate(3, "C", 90)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {row.player_id: row for row in [guard, weak, add]},
        [1, 2], ["PG", "C"], 2, True, WEIGHTS, {})
    result = compare(ctx, add, 2)
    assert result.net_improvement > 0
    assert result.net_improvement == pytest.approx(result.after_score - result.before_score, abs=1e-6)
    assert result.component_deltas.roster_fit > 0
    assert compare(ctx, add, 2) == result
    add.components.schedule = 10
    assert compare(ctx, add, 2).net_improvement < result.net_improvement
    add.components.player_value = None
    assert compare(ctx, add, 2).net_improvement is None
    add.components.player_value = 90
    ctx.roster_ready = False
    assert compare(ctx, add, 2).net_improvement is None


def test_add_without_drop_uses_same_roster_model():
    guard, add = candidate(1, "PG", 60), candidate(2, "C", 80)
    ctx = Context(SimpleNamespace(), "t1", "ros", NOW, {1: guard, 2: add}, [1], ["PG", "C"], 2, True, WEIGHTS, {})
    result = compare(ctx, add, None)
    assert result.player_id is None
    assert result.net_improvement > 0
    assert result.component_deltas.roster_fit > 0


def test_fully_covered_lineup_has_no_fit_gain_from_reassignment_or_bench_flexibility():
    players = [candidate(1, "PG,SG", 70), candidate(2, "PF,C", 60),
        candidate(3, "SF,PF", 50), candidate(4, "PG", 65), candidate(5, "C", 55)]
    slots = ["PG", "C", "UTIL"]
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW,
        {row.player_id: row for row in players}, [1, 2, 3, 5], slots, 4, True, WEIGHTS, {})
    result = compare(ctx, players[3], 3)
    assert result.starting_slots_before == result.starting_slots_after == 3
    assert result.component_before.roster_fit == result.component_after.roster_fit == 100
    assert result.component_deltas.roster_fit == 0
    assert coverage(players[:3], slots) == 100
    for key, delta in result.component_deltas.model_dump().items():
        if delta is not None:
            assert -100 <= delta <= 100
            assert 0 <= getattr(result.component_before, key) <= 100
            assert 0 <= getattr(result.component_after, key) <= 100
    assert result.component_deltas.player_value == pytest.approx((65 - 50) / 4)
    assert 0 <= result.before_score <= 100
    assert 0 <= result.after_score <= 100
    for player in players:
        assert 0 <= roster_fit(player, players[:3], slots) <= 100
    assert compare(ctx, players[3], 3) == compare(ctx, players[3], 3)


def test_explicit_drop_controls_net_even_with_open_slot_or_better_drop():
    guard, weak, add = candidate(1, "PG", 90), candidate(2, "C", 10), candidate(3, "PG,C", 50)
    add.overall_score, add.effective_weights = aggregate(add.components, WEIGHTS)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {r.player_id: r for r in [guard, weak, add]},
        [1, 2], ["PG", "C"], 3, True, WEIGHTS, {})
    attach_capacity(ctx, open_spots=1)
    preferred = enrich(ctx, add)
    explicit = enrich(ctx, add, 1)
    assert preferred.comparison.player_id is None
    assert preferred.comparison.comparison_type == "ADD_ONLY"
    assert explicit.net_improvement == compare(ctx, add, 1).net_improvement
    assert explicit.comparison.player_id == 1
    assert [row.player_id for row in explicit.best_drop_options] == [1]
    assert explicit.add_only_impact == preferred.comparison
    assert explicit.net_improvement < compare(ctx, add, 2).net_improvement
    assert explicit.recommended_action == "INSUFFICIENT EVIDENCE"
    assert preferred.net_improvement != explicit.net_improvement
    with pytest.raises(HTTPException) as error:
        compare(ctx, add, 999)
    assert error.value.status_code == 422


@pytest.mark.parametrize(("games", "expected"), [
    (0, "NO CURRENT-SEASON EVIDENCE"), (1, "INSUFFICIENT FOR STRONG RECOMMENDATION"), (2, "INSUFFICIENT FOR STRONG RECOMMENDATION"), (3, "INSUFFICIENT FOR STRONG RECOMMENDATION"),
    (4, "VERY LIMITED"), (6, "VERY LIMITED"), (7, "LIMITED"), (9, "LIMITED"),
    (10, "GOOD"), (19, "GOOD"), (20, "EXCELLENT"),
])
def test_sample_size_labels(games, expected):
    assert sample_label(games) == expected
    player = candidate(1)
    player.recent.games = games
    player.current_season_games = games
    player.data_quality["recent"] = Evidence(state="available", source="Fixture", detail="Fresh")
    assert sufficient_sample(player, "this_week") == (games >= 7)
    assert sufficient_sample(player, "next_7_days") == (games >= 7)
    player.data_quality["recent"].state = "stale"
    assert not sufficient_sample(player, "this_week")


@pytest.mark.parametrize("instant", ["2026-10-26T06:30:00+00:00", "2026-12-28T07:30:00+00:00"])
def test_next_seven_days_crosses_pacific_sunday(instant):
    today = datetime.fromisoformat(instant).astimezone(WAIVER_TIMEZONE).date()
    assert today.weekday() == 6
    assert window_end_date(today, today.year, "this_week") == today
    assert window_end_date(today, today.year, "next_7_days") == today + timedelta(days=6)
    assert (window_end_date(today, today.year, "next_7_days") - today).days + 1 == 7
    assert window_end_date(date(2026, 10, 26), 2026, "this_week") == date(2026, 11, 1)


@pytest.fixture
def persisted(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("Set TEST_DATABASE_URL for PostgreSQL-backed waiver API tests")
    suffix = uuid4().hex[:10]
    league_key = f"waiver.{suffix}"
    team1, team2 = f"{league_key}.t.1", f"{league_key}.t.2"
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", team1)
    now = datetime.now(timezone.utc)
    today = now.astimezone(WAIVER_TIMEZONE).date()
    # Choose a current NBA season with today inside the fixture schedule window.
    year = today.year if today.month >= 7 else today.year - 1
    season = f"{year}-{str(year + 1)[-2:]}"
    earlier = now - timedelta(minutes=1)
    ids = {}
    no_yahoo = AsyncMock(side_effect=AssertionError("Yahoo provider called by waiver read"))
    monkeypatch.setattr(YahooFantasyClient, "get_json", no_yahoo)
    for name in dir(NbaApiClient):
        if name.startswith("fetch_"):
            monkeypatch.setattr(NbaApiClient, name, lambda *args, **kwargs: pytest.fail("NBA provider called by waiver read"))

    async def seed():
        async with engine.begin() as connection:
            await create_test_schema(connection)
        async with SessionFactory() as session, session.begin():
            session.add(League(league_key=league_key, game_key="nba", league_name="Waiver fixture", season=year, source_payload={}, imported_at=earlier))
            await session.flush()
            session.add(LeagueSettings(league_key=league_key,
                scoring_settings={"scoring_type": "points", "categories": [{"stat_id": "12", "name": "PTS", "value": 1}]},
                roster_positions=[{"position": "PG", "count": "1"}, {"position": "C", "count": "1"}],
                source_payload={}, imported_at=earlier))
            for key in (team1, team2):
                session.add(Team(team_key=key, league_key=league_key, team_name=key, source_payload={}, imported_at=earlier))
            await session.flush()
            for key in (team1, team2):
                session.add(FantasyTeam(team_key=key, league_key=league_key, team_name=key, source_payload={}, imported_at=now))
            team_a, team_b, team_c = f"{suffix}a", f"{suffix}b", f"{suffix}c"
            for tid, abbr in ((team_a, f"A{suffix[:4]}"), (team_b, f"B{suffix[:4]}"), (team_c, f"C{suffix[:4]}")):
                session.add(NbaTeam(nba_team_id=tid, abbreviation=abbr, full_name=abbr, source_payload={}, imported_at=now))
            await session.flush()
            for offset in range(3):
                session.add(NbaGame(game_id=f"{suffix}g{offset}", season=season, game_date=today + timedelta(days=offset),
                    home_team_id=team_a if offset < 2 else team_b, away_team_id=team_b if offset < 2 else team_c,
                    game_status="Scheduled", source_payload={}, imported_at=now))
            await session.flush()
            data = [
                ("guard", "PG", 40, 35, None, team1),
                ("weak", "PG", 5, 5, None, team1),
                ("opponent", "C", 15, 20, None, team2),
                ("center", "C", 20, 45, "Q", None),
                ("star", "PG", 50, 20, "P", None),
                ("out", "C", 99, 99, "O", None),
                ("inactive", "C", 99, 99, "NA", None),
                ("unknown", "C", 10, 10, "", None),
                ("unmapped", "C", None, None, "", None),
            ]
            for name, position, recent, historical, status, owner in data:
                yahoo_id = f"{suffix}-{name}"
                nba_id = yahoo_id if recent is not None else None
                identity = PlayerIdentity(yahoo_player_id=yahoo_id, nba_player_id=nba_id, player_name=name, position=position, team=f"A{suffix[:4]}", status="O")
                session.add(identity)
                await session.flush()
                ids[name] = identity.id
                payload = {"player_id": yahoo_id, "name": {"full": name}, "display_position": position,
                    "editorial_team_abbr": f"{'B' if name == 'star' else 'A'}{suffix[:4]}", "status": status}
                session.add(LeaguePlayer(league_key=league_key, yahoo_player_id=yahoo_id, player_identity_id=identity.id, source_payload=payload, imported_at=now))
                if owner:
                    # Persisted Yahoo selected_position: a full two-slot roster (PG + C).
                    slot = {"guard": "PG", "weak": "C"}.get(name, position)
                    session.add(RosterEntry(league_key=league_key, team_key=owner, yahoo_player_id=yahoo_id, player_identity_id=identity.id, roster_position=slot, source_payload=payload, imported_at=now))
                if nba_id is not None:
                    player_team_id = team_b if name == "star" else team_a
                    session.add(NbaPlayer(nba_player_id=nba_id, player_name=name, team_id=player_team_id,
                        team_abbreviation="B" if name == "star" else "A", source_payload={}, imported_at=now))
                    await session.flush()
                    session.add(NbaPlayerSeasonStats(nba_player_id=nba_id, season=season, season_type="Regular Season",
                        games_played=30, games_started=20, minutes_per_game=30, usage_pct=.2,
                        base_stats={"PTS": historical}, advanced_stats={}, source_payload={}, imported_at=now))
                    for offset in range(4):
                        game_id = f"{suffix}-{name}-{offset}"
                        session.add(NbaGame(game_id=game_id, season=season, game_date=today - timedelta(days=offset + 1),
                            home_team_id=team_a, away_team_id=team_b, source_payload={}, imported_at=now))
                        await session.flush()
                        session.add(PlayerGameLog(nba_player_id=nba_id, game_id=game_id, season=season, season_type="Regular Season",
                            game_date=today - timedelta(days=offset + 1), stats_payload={"PTS": recent, "MIN": 30 - offset},
                            source_payload={}, imported_at=now))
                    for offset in range(3):
                        if name == "star" and offset < 2:
                            team_id, opponent_id, is_home = team_b, team_a, False
                        elif name != "star" and offset < 2:
                            team_id, opponent_id, is_home = team_a, team_b, True
                        elif name == "star":
                            team_id, opponent_id, is_home = team_b, team_c, True
                        else:
                            continue
                        session.add(PlayerSchedule(
                            nba_player_id=nba_id,
                            game_id=f"{suffix}g{offset}",
                            season=season,
                            game_date=today + timedelta(days=offset),
                            team_id=team_id,
                            opponent_team_id=opponent_id,
                            is_home=is_home,
                            game_status="Scheduled",
                            source_payload={},
                            imported_at=now,
                        ))
    asyncio.run(seed())
    asyncio.run(engine.dispose())
    async def test_session():
        async with SessionFactory() as session:
            yield session
    monkeypatch.setitem(app.dependency_overrides, get_session, test_session)
    client = TestClient(app)
    try:
        yield SimpleNamespace(client=client, league=league_key, team1=team1, team2=team2, ids=ids, no_yahoo=no_yahoo)
    finally:
        client.close()
        async def cleanup():
            await engine.dispose()
            async with SessionFactory() as session, session.begin():
                await session.execute(delete(League).where(League.league_key == league_key))
                await session.execute(delete(PlayerIdentity).where(PlayerIdentity.id.in_(ids.values())))
                await session.execute(delete(NbaPlayer).where(NbaPlayer.nba_player_id.like(f"{suffix}-%")))
                await session.execute(delete(NbaGame).where(NbaGame.game_id.like(f"{suffix}%")))
                await session.execute(delete(NbaTeam).where(NbaTeam.nba_team_id.in_([f"{suffix}a", f"{suffix}b", f"{suffix}c"])))
            await engine.dispose()
        asyncio.run(cleanup())


def board(fixture, **params):
    response = fixture.client.get("/api/v1/waivers", params={"league_key": fixture.league, "team_key": fixture.team1, **params})
    assert response.status_code == 200, response.text
    return response.json()


def test_yahoo_availability_status_manager_isolation_and_provider_free_reads(persisted):
    f = persisted
    result = board(f)
    names = {row["player_name"] for row in result["candidates"]}
    assert {"center", "star", "unknown", "unmapped"} == names
    assert result["excluded_count"] == 2
    unknown = next(row for row in result["candidates"] if row["player_name"] == "unknown")
    assert unknown["yahoo_status"] is None
    assert unknown["data_quality"]["status"]["state"] == "unknown"
    assert unknown["raw_yahoo_status"] == ""
    assert next(row for row in result["candidates"] if row["player_name"] == "center")["yahoo_status"] == "Q"
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    assert center["mapping_diagnostic"] == "COMPLETE_MAPPING"
    assert center["status_diagnostic"] == "STATUS_PRESENT"
    assert all(option["player_id"] in {f.ids["guard"], f.ids["weak"]} for row in result["candidates"] for option in row["best_drop_options"])
    assert next(row for row in result["candidates"] if row["player_name"] == "unmapped")["overall_score"] is None
    assert result["best_add_for_team_id"] is None
    assert result["top_measured_candidate_id"] == f.ids["center"]
    assert result["best_overall_available_id"] == f.ids["star"]
    assert result["coverage"]["population"] == {"total": 9, "candidates": 4, "roster": 2}
    assert result["coverage"]["pool"]["identity"]["complete"]["count"] == 8
    assert result["coverage"]["pool"]["identity"]["unresolved"]["count"] == 1
    assert result["coverage"]["pool"]["identity"]["resolution_counts"]["NO_MATCH"] == 1
    assert result["coverage"]["candidates"]["identity"]["unresolved"] == {
        "count": 1, "total": 4, "percentage": 25.0,
    }
    assert result["coverage"]["roster"]["identity"]["complete"] == {
        "count": 2, "total": 2, "percentage": 100.0,
    }
    unresolved = result["coverage"]["mapping_worklist"]
    assert len(unresolved) == 1 and unresolved[0]["resolution_state"] == "NO_MATCH"
    assert unresolved[0]["yahoo_player_id"] == f"{f.league.split('.')[1]}-unmapped"
    assert any(gap["category"] == "SOURCE CONTRACT UNVERIFIED" and gap["field"] == "Game-level usage"
        and gap["root_cause"] == "SOURCE_CONTRACT_UNVERIFIED" for gap in result["data_gaps"])
    assert any(gap["category"] == "SOURCE CONTRACT UNVERIFIED" for gap in result["data_gaps"])
    invalid = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact",
        params={"league_key": f.league, "team_key": f.team1, "drop_player_id": f.ids["opponent"]})
    assert invalid.status_code == 422
    assert f.client.get("/api/v1/waivers", params={"league_key": f.league, "team_key": "foreign-team"}).status_code == 422
    f.no_yahoo.assert_not_called()


def test_modes_schedule_and_add_drop_impact(persisted):
    f = persisted
    week, ros = board(f), board(f, mode="ros")
    center_week = next(row for row in week["candidates"] if row["player_name"] == "center")
    center_ros = next(row for row in ros["candidates"] if row["player_name"] == "center")
    assert center_ros["components"]["player_value"] > center_week["components"]["player_value"]
    assert center_week["recent"]["value"] == 20
    assert center_ros["ros"]["value"] == 45
    assert center_ros["schedule"]["games_remaining"] >= center_week["schedule"]["games_remaining"]
    assert center_ros["schedule"]["games_remaining"] == 2
    assert next(row for row in ros["candidates"] if row["player_name"] == "star")["schedule"]["games_remaining"] == 3
    assert center_week["data_quality"]["schedule"]["state"] == "partial"
    next_days = board(f, mode="next_7_days")
    center_next = next(row for row in next_days["candidates"] if row["player_name"] == "center")
    assert center_next["ranking_value"] == center_week["ranking_value"]
    assert center_next["schedule"]["window_end"] == (
        date.fromisoformat(center_next["schedule"]["window_start"]) + timedelta(days=6)
    ).isoformat()
    assert center_next["schedule"]["games_remaining"] == 2
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact", params={
        "league_key": f.league, "team_key": f.team1, "drop_player_id": f.ids["weak"]})
    assert impact.status_code == 200
    comparison = impact.json()["comparison"]
    assert comparison["net_improvement"] > 0
    assert comparison["after_score"] - comparison["before_score"] == pytest.approx(comparison["net_improvement"], abs=1e-6)
    repeat = board(f)
    assert [row["overall_score"] for row in repeat["candidates"]] == [row["overall_score"] for row in week["candidates"]]
    assert f.client.get("/api/v1/waivers", params={"league_key": f.league, "team_key": f.team1, "mode": "fake"}).status_code == 422
    assert f.client.get("/api/v2/draft/sessions").status_code == 200
    f.no_yahoo.assert_not_called()


def test_next_14_days_horizon_and_form_windows_are_served_select_only_by_every_endpoint(persisted):
    f = persisted
    statements = []

    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        result = board(f, mode="next_14_days")
        assert (result["mode"], result["model_version"]) == ("next_14_days", MODEL_VERSION)
        center = next(row for row in result["candidates"] if row["player_name"] == "center")
        schedule = center["schedule"]
        assert date.fromisoformat(schedule["window_end"]) - date.fromisoformat(schedule["window_start"]) == timedelta(days=13)
        assert (schedule["games_remaining"], schedule["next_7_days_games"], schedule["next_14_days_games"]) == (2, 2, 2)
        assert schedule["rest_of_season_games"] == 2
        windows = {row["key"]: row for row in center["form"]["windows"]}
        assert [windows[key]["games"] for key in ("LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS")] == [4, 4, 4]
        assert windows["LAST_14_DAYS"]["state"] == center["data_quality"]["recent"]["state"]
        assert windows["LAST_14_DAYS"]["fantasy_ppg"] == center["recent"]["value"] == 20
        assert windows["CURRENT_SEASON"]["games"] == 30 and windows["CURRENT_SEASON"]["fantasy_ppg"] == 45
        assert windows["LAST_7_DAYS"]["starts"] is None and windows["LAST_7_DAYS"]["usage"] is None
        assert center["sample"]["window"] == "LAST_14_DAYS" and center["sample"]["tier"] == "VERY_LOW"
        assert not center["sample"]["passes"]
        option = next(row for row in result["decision_support"]["options"] if row["player_id"] == f.ids["center"])
        assert option["form"]["last_14_ppg"] == 20 and option["form"]["next_14_games"] == 2
        assert option["form"]["season_ppg"] == 45 and option["form"]["last_30_games"] == 4
        needs = result["team_needs_analysis"]
        assert needs["mode"] == "next_14_days" and date.fromisoformat(needs["window_end"]) == date.fromisoformat(needs["window_start"]) + timedelta(days=13)
        analysis = f.client.get("/api/v1/waivers/transactions", params={"mode": "next_14_days"}).json()
        assert (analysis["mode"], analysis["model_version"]) == ("next_14_days", MODEL_VERSION)
        replacements = f.client.get("/api/v1/waivers/replacements", params={"mode": "next_14_days", "drop_player_id": f.ids["weak"]})
        assert replacements.status_code == 200 and replacements.json()["mode"] == "next_14_days"
        impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact", params={"mode": "next_14_days", "drop_player_id": f.ids["weak"]})
        assert impact.status_code == 200 and impact.json()["model_version"] == MODEL_VERSION
        assert impact.json()["candidate"]["schedule"]["next_14_days_games"] == 2
        assert f.client.get("/api/v1/waivers", params={"mode": "next_21_days"}).status_code == 422
        f.no_yahoo.assert_not_called()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)


def test_replacements_use_only_explicit_manager_drop_and_reject_foreign_ids(persisted):
    f = persisted
    for drop_id in (f.ids["weak"], f.ids["guard"]):
        response = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": drop_id})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["selected_drop_player_id"] == drop_id
        assert {row["player_id"] for row in result["roster"]} == {f.ids["weak"], f.ids["guard"]}
        assert all(row["availability"] != "rostered" for row in result["candidates"])
        ranked = []
        for row in result["candidates"]:
            assert row["comparison"]["player_id"] == drop_id
            assert [option["player_id"] for option in row["best_drop_options"]] == [drop_id]
            assert row["net_improvement"] == row["comparison"]["net_improvement"]
            detail = f.client.get(f"/api/v1/waivers/{row['player_id']}/impact",
                params={"drop_player_id": drop_id}).json()
            assert detail["comparison"] == row["comparison"]
            ranked.append((TIER[row["recommended_action_type"]], row["net_improvement"]))
        # Decision tier first (supported, WATCH, HOLD, insufficient evidence), then measured net, unavailable last.
        assert [tier for tier, _ in ranked] == sorted(tier for tier, _ in ranked)
        for tier in {tier for tier, _ in ranked}:
            nets = [net for row_tier, net in ranked if row_tier == tier]
            measured = [net for net in nets if net is not None]
            assert measured == sorted(measured, reverse=True) and nets == measured + [None] * (len(nets) - len(measured))
    for foreign in (f.ids["opponent"], f.ids["center"], -1):
        assert f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": foreign}).status_code == 422
    assert f.client.get("/api/v1/waivers/replacements").status_code == 422
    assert f.client.get("/api/v1/waivers/replacements", params={
        "drop_player_id": f.ids["weak"], "team_key": f.team2,
    }).status_code == 422
    for method in ("post", "put", "delete"):
        assert getattr(f.client, method)("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["weak"]}).status_code == 405
    f.no_yahoo.assert_not_called()


def test_different_selected_positions_change_replacement_ranking(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            entry = (await session.scalars(select(RosterEntry).where(
                RosterEntry.team_key == f.team1, RosterEntry.player_identity_id == f.ids["weak"]))).one()
            entry.source_payload = {**entry.source_payload, "display_position": "C"}
        await engine.dispose()
    asyncio.run(change())
    center_drop = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["weak"]}).json()
    guard_drop = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["guard"]}).json()
    assert center_drop["candidates"][0]["player_id"] == f.ids["center"]
    assert guard_drop["candidates"][0]["player_id"] == f.ids["star"]
    assert center_drop["candidates"][0]["comparison"]["component_deltas"]["roster_fit"] == 0
    assert guard_drop["candidates"][0]["comparison"]["component_deltas"]["roster_fit"] == 0


def test_two_game_production_uses_independent_history_with_visible_uncertainty(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["star"])
            logs = list((await session.scalars(select(PlayerGameLog).where(
                PlayerGameLog.nba_player_id == identity.nba_player_id).order_by(PlayerGameLog.game_date))).all())
            for row in logs[:2]:
                await session.delete(row)
            year = logs[0].season[:4]
            session.add(NbaPlayerSeasonStats(nba_player_id=identity.nba_player_id,
                season=f"{int(year)-1}-{str(year)[-2:]}", season_type="Regular Season",
                games_played=60, games_started=30, base_stats={"PTS": 10}, advanced_stats={},
                source_payload={}, imported_at=datetime.now(timezone.utc)))
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    star = next(row for row in result["candidates"] if row["player_name"] == "star")
    assert star["recent"]["games"] == 2
    assert star["recent"]["sample_label"] == "INSUFFICIENT FOR STRONG RECOMMENDATION"
    # No earlier current-season games: two real games beside the prior season counted as two games.
    assert star["ranking_value"]["recent_weight"] == pytest.approx(2 / 4)
    assert star["ranking_value"]["prior_weight"] == pytest.approx(2 / 4)
    assert star["ranking_value"]["value"] == pytest.approx((2 * 50 + 2 * 10) / 4)
    earlier = next(row for row in star["ranking_value"]["buckets"] if row["key"] == "EARLIER")
    assert (earlier["games"], earlier["value"], earlier["share"]) == (0, None, 0)
    assert star["ranking_value"]["historical_games"] == 60
    assert star["ranking_value"]["historical_value"] == 10
    assert "not a projection" in star["ranking_value"]["label"]
    assert result["best_add_for_team_id"] is None
    assert any("INSUFFICIENT FOR STRONG RECOMMENDATION" in reason for reason in star["reasons"])
    ros = board(f, mode="ros")
    ros_star = next(row for row in ros["candidates"] if row["player_name"] == "star")
    assert ros_star["ranking_value"]["value"] == 20
    assert ros_star["ranking_value"]["recent_weight"] is None
    assert "not a projection" in ros_star["ranking_value"]["label"]

    async def stale_prior():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["star"])
            prior = (await session.scalars(select(NbaPlayerSeasonStats).where(
                NbaPlayerSeasonStats.nba_player_id == identity.nba_player_id,
                NbaPlayerSeasonStats.games_played == 60))).one()
            prior.imported_at = datetime.now(timezone.utc) - timedelta(days=8)
        await engine.dispose()
    asyncio.run(stale_prior())
    stale_star = next(row for row in board(f)["candidates"] if row["player_name"] == "star")
    assert stale_star["ranking_value"]["recent_weight"] == 1
    assert stale_star["ranking_value"]["value"] == 50
    assert stale_star["ranking_value"]["historical_value"] is None
    assert stale_star["recent"]["sample_label"] == "INSUFFICIENT FOR STRONG RECOMMENDATION"


def test_stale_rosters_unknown_availability_and_unsupported_scoring(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            roster = await session.get(FantasyTeam, f.team2)
            roster.imported_at = NOW - timedelta(days=2)
            settings = await session.get(LeagueSettings, f.league)
            settings.scoring_settings = {"scoring_type": "head", "categories": [{"stat_id": "12", "name": "PTS"}]}
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    assert result["candidates"] == []
    assert result["unknown_availability_count"] >= 4
    assert result["data_quality"]["availability"]["state"] == "partial"
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact", params={"league_key": f.league, "team_key": f.team1})
    assert impact.status_code == 200
    assert impact.json()["model_version"] == MODEL_VERSION
    assert impact.json()["candidate"]["recommended_action"] == "INSUFFICIENT EVIDENCE"
    assert impact.json()["comparison"]["net_improvement"] is None
    assert impact.json()["candidate"]["data_quality"]["recent"]["state"] == "unsupported"


def test_explicit_yahoo_waiver_state_needs_current_rosters_and_stale_logs_stay_visible(persisted):
    f = persisted

    async def change():
        await engine.dispose()
        async with SessionFactory() as session, session.begin():
            manager = await session.get(FantasyTeam, f.team1)
            manager.imported_at = NOW - timedelta(days=2)
            row = (await session.execute(
                select(LeaguePlayer).where(
                    LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["center"])
            )).scalar_one()
            row.source_payload = {**row.source_payload, "ownership": {"ownership_type": "waivers"}}
            logs = list((await session.scalars(
                select(PlayerGameLog).where(PlayerGameLog.nba_player_id == row.yahoo_player_id)
            )).all())
            for log in logs:
                log.imported_at = NOW - timedelta(days=8)
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    assert result["data_quality"]["roster"]["state"] == "stale"
    # Explicit Yahoo waiver state alone is not enough: every league roster snapshot must be current.
    assert result["candidates"] == [] and result["eligible_candidate_ids"] == []
    option = {row["player_id"]: row for row in result["decision_support"]["options"]}[f.ids["center"]]
    assert option["availability_classification"] == "SOURCE_STALE"
    assert option["classification"] == "POTENTIAL_TARGET"
    assert option["availability_evidence"]["yahoo_ownership_state"] == "W"
    assert f.ids["center"] in result["decision_support"]["potential_target_ids"]
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact")
    assert impact.status_code == 200
    center = impact.json()["candidate"]
    assert center["availability"] == "unknown" and center["availability_classification"] == "SOURCE_STALE"
    assert center["overall_score"] is None
    assert center["recommended_action"] == "INSUFFICIENT EVIDENCE"
    assert center["data_quality"]["recent"]["state"] == "stale"
    assert center["recent"]["value"] == 20
    assert center["components"]["player_value"] is None


def test_stale_ros_values_remain_visible_but_cannot_score_or_label_holds(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids["center"])
            stats = (await session.scalars(select(NbaPlayerSeasonStats).where(
                NbaPlayerSeasonStats.nba_player_id == identity.nba_player_id,
            ))).one()
            stats.imported_at = datetime.now(timezone.utc) - timedelta(days=8)
        await engine.dispose()
    asyncio.run(change())
    result = board(f, mode="ros")
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    assert center["ros"]["value"] == 45
    assert center["data_quality"]["ros"]["state"] == "stale"
    assert center["components"]["player_value"] is None
    assert center["overall_score"] is None
    assert center["net_improvement"] is None
    assert center["hold_type"] == "undetermined"
    assert result["best_overall_available_id"] != f.ids["center"]
    week_center = next(row for row in board(f)["candidates"] if row["player_name"] == "center")
    assert week_center["hold_type"] != "longer_term_hold"


@pytest.mark.parametrize("mode", ["this_week", "ros"])
def test_stale_settings_cannot_supply_scoring_or_roster_fit(persisted, mode):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            settings = await session.get(LeagueSettings, f.league)
            settings.imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        await engine.dispose()
    asyncio.run(change())
    result = board(f, mode=mode)
    assert result["data_quality"]["settings"]["state"] == "stale"
    assert result["best_overall_available_id"] is None
    assert result["best_add_for_team_id"] is None
    needs = result["team_needs_analysis"]
    # Needs are descriptive and use the persisted slot configuration, labeled stale; strict scoring,
    # fit and every supported action still require fresh settings.
    assert needs["state"] == "stale" and "refresh Yahoo" in needs["basis"]
    assert needs["starting_slots_required"] == 2 and needs["summary"]
    assert all(option["classification"] != "SUPPORTED_ACTION" for option in result["decision_support"]["options"])
    assert result["candidates"]
    for row in result["candidates"]:
        assert row["components"]["player_value"] is None
        assert row["components"]["roster_fit"] is None
        assert row["overall_score"] is None
        assert row["net_improvement"] is None
        assert row["recommended_action"] == "INSUFFICIENT EVIDENCE"


def test_window_configured_weights_and_missing_resource_contracts(persisted, monkeypatch):
    f = persisted
    configured = {**WEIGHTS, "schedule": 0}
    monkeypatch.setattr("app.features.waivers.service.get_settings",
        lambda: SimpleNamespace(waiver_weights=configured))
    result = board(f)
    assert result["weights"] == pytest.approx(validated_weights(configured))
    for row in result["candidates"]:
        window = row["schedule"]
        today = datetime.now(timezone.utc).astimezone(WAIVER_TIMEZONE).date()
        assert window["window_start"] == today.isoformat()
        assert window["window_end"] == (today + timedelta(days=6 - today.weekday())).isoformat()
        assert "schedule" not in row["effective_weights"]
    params = {"league_key": f.league, "team_key": f.team1}
    assert f.client.get("/api/v1/waivers", params={**params, "league_key": "missing"}).status_code == 422
    assert f.client.get("/api/v1/waivers/-1/impact", params=params).status_code == 404
    assert f.client.get(f"/api/v1/waivers/{f.ids['guard']}/impact", params=params).status_code == 409


def test_configured_target_defaults_and_rejects_other_rosters(persisted, monkeypatch):
    f = persisted
    fixed = datetime.now(timezone.utc)
    monkeypatch.setattr("app.features.waivers.service.datetime", SimpleNamespace(now=lambda tz: fixed))
    default = f.client.get("/api/v1/waivers")
    assert default.status_code == 200
    result = default.json()
    assert result["league_key"] == f.league
    assert result["team_key"] == f.team1
    assert result["team_name"] == f.team1
    assert result["mode"] == "this_week"
    assert result["candidates"] == board(f)["candidates"]
    assert result["best_add_for_team_id"] is None
    assert result["top_measured_candidate_id"] == f.ids["center"]
    for mode in ("this_week", "next_7_days", "ros"):
        impact_path = f"/api/v1/waivers/{f.ids['center']}/impact"
        impact = f.client.get(impact_path, params={"mode": mode, "drop_player_id": f.ids["weak"]})
        assert impact.status_code == 200
        assert impact.json()["league_key"] == f.league
        assert impact.json()["team_key"] == f.team1
        assert impact.json()["comparison"]["player_id"] == f.ids["weak"]
        assert impact.json()["comparison"]["net_improvement"] is not None
        for path in ("/api/v1/waivers", impact_path):
            for params in ({"team_key": f.team2}, {"league_key": "other.league"}):
                rejected = f.client.get(path, params={**params, "mode": mode})
                assert rejected.status_code == 422
                assert "configured" in rejected.json()["detail"]
    f.no_yahoo.assert_not_called()


def test_missing_configured_team_never_falls_back_to_another_roster(persisted, monkeypatch):
    f = persisted
    monkeypatch.setattr(get_settings(), "waiver_manager_team_key", "missing.t.9")
    for path in ("/api/v1/waivers", f"/api/v1/waivers/{f.ids['center']}/impact"):
        response = f.client.get(path)
        assert response.status_code == 404
        assert "Configured waiver manager team" in response.json()["detail"]


@pytest.mark.parametrize(("instant", "expected_day"), [
    ("2026-10-26T06:30:00+00:00", "2026-10-25"),
    ("2026-12-28T07:30:00+00:00", "2026-12-27"),
])
def test_pacific_sunday_window_does_not_roll_over_at_utc_midnight(persisted, monkeypatch, instant, expected_day):
    fixed = datetime.fromisoformat(instant)
    monkeypatch.setattr("app.features.waivers.service.datetime", SimpleNamespace(now=lambda tz: fixed))
    response = persisted.client.get(f"/api/v1/waivers/{persisted.ids['center']}/impact")
    assert response.status_code == 200
    schedule = response.json()["candidate"]["schedule"]
    assert schedule["window_start"] == expected_day
    assert schedule["window_end"] == expected_day


def verified_league():
    scoring = {"scoring_type": "headpoint", "categories": [
        {"stat_id": str(stat), "name": name, "value": weight}
        for stat, name, weight in [(12, "PTS", 1), (15, "REB", 1.2), (16, "AST", 1.5),
            (18, "BLK", 3), (17, "ST", 3), (19, "TO", -1)]
    ]}
    positions = [{"position": position, "count": count} for position, count in
        {"PG": 1, "SG": 1, "G": 1, "SF": 1, "PF": 1, "F": 1, "C": 2, "UTIL": 2, "BN": 3, "IL": 3}.items()]
    raw = dict(scoring_type="headpoint", max_teams="12", uses_faab="0", waiver_type="R",
        waiver_rule="all", waiver_time="2", max_weekly_adds="4", post_draft_players="W",
        stat_categories={"stats": [{"stat": {"stat_id": row["stat_id"], "display_name": row["name"]}} for row in scoring["categories"]]},
        stat_modifiers={"stats": [{"stat": {"stat_id": row["stat_id"], "value": row["value"]}} for row in scoring["categories"]]},
        roster_positions=[{"roster_position": row} for row in positions])
    record = dict(league_key="478.l.50505", num_teams=12, weekly_deadline="intraday",
        allow_add_to_dl_extra_pos=1, settings=[raw])
    return SimpleNamespace(league_key="478.l.50505", league_name="Driveway Dudes",
        source_payload={"scoring_type": "headpoint"},
        settings=SimpleNamespace(scoring_settings=scoring, roster_positions=positions,
            source_payload={"fantasy_content": {"league": record}}))


def test_exact_persisted_yahoo_formula_and_required_nba_mapping():
    league = verified_league()
    assert all("FAAB" not in rule.upper() for rule in verify_league_contract(league))
    fields = scoring_fields(league.settings.scoring_settings)
    assert fields == {"PTS": 1, "REB": 1.2, "AST": 1.5, "BLK": 3, "STL": 3, "TOV": -1}
    stats = dict(PTS=20, REB=10, AST=6, BLK=2, STL=3, TOV=4)
    assert production(stats, fields) == 52
    for field, weight in fields.items():
        assert production({**stats, field: stats[field] + 1}, fields) == pytest.approx(52 + weight)
        assert production({key: value for key, value in stats.items() if key != field}, fields) is None
    assert production(log_average([
        SimpleNamespace(stats_payload=stats),
        SimpleNamespace(stats_payload={key: value for key, value in stats.items() if key != "TOV"}),
    ]), fields) is None


@pytest.mark.parametrize("mutation", [
    "scoring", "raw_scoring", "slots", "raw_slots", "uses_faab", "waiver_type",
    "waiver_rule", "waiver_time", "max_weekly_adds", "max_teams", "post_draft_players",
    "max_adds", "weekly_deadline", "allow_add_to_dl_extra_pos", "num_teams", "identity", "missing",
])
def test_persisted_contract_mismatch_fails_closed(mutation):
    league = verified_league()
    record = league.settings.source_payload["fantasy_content"]["league"]
    raw = record["settings"][0]
    if mutation == "scoring":
        league.settings.scoring_settings["categories"][1]["value"] = 1
    elif mutation == "raw_scoring":
        raw["stat_modifiers"]["stats"][1]["stat"]["value"] = 1
    elif mutation == "slots":
        league.settings.roster_positions = []
    elif mutation == "raw_slots":
        raw["roster_positions"] = []
    elif mutation in {"weekly_deadline", "allow_add_to_dl_extra_pos", "num_teams"}:
        record[mutation] = "wrong"
    elif mutation == "identity":
        league.league_name = "Other"
    elif mutation == "missing":
        league.settings = None
    else:
        raw[mutation] = "wrong"
    with pytest.raises(HTTPException) as error:
        verify_league_contract(league)
    assert error.value.status_code == 409


def role_logs(minutes, usages=None):
    return [PlayerGameLog(nba_player_id="role", game_id=f"role-{index}", season="2026-27",
        season_type="Regular Season", game_date=NOW.date() - timedelta(days=len(minutes) - index),
        stats_payload={**({"MIN": value} if value is not None else {}),
            **({"USG_PCT": usages[index]} if usages is not None else {})},
        source_payload={}, imported_at=NOW)
        for index, value in enumerate(minutes)]


@pytest.mark.parametrize("minutes,expected,delta", [
    ([20, 20, 20, 27, 27, 27], "RISING", 7),
    ([30, 30, 30, 23, 23, 23], "FALLING", -7),
    ([25, 25, 25, 26, 26, 26], "STABLE", 1),
    ([20, 20, 20, 23, 23, 23], "RISING", 3),
    ([30, 30, 30, 27, 27, 27], "FALLING", -3),
    ([20, 20, 40], "INSUFFICIENT EVIDENCE", None),
    ([20, 20, 20, 30, 30], "INSUFFICIENT EVIDENCE", None),
])
def test_role_fixed_supported_windows_and_thresholds(minutes, expected, delta):
    opportunity = current_role(role_logs(minutes), None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == expected
    assert role.minutes.delta == delta
    assert role.minutes.recent.game_ids == [f"role-{i}" for i in range(max(0, len(minutes)-3), len(minutes))]
    assert role.minutes.recent.window_end == NOW.date() - timedelta(days=1)
    assert role.usage.quality.state == "unavailable"
    assert role.usage.delta is None
    assert "minutes_change" not in opportunity.score_parts
    assert (opportunity.score is not None) == (expected != "INSUFFICIENT EVIDENCE")
    assert not any(phrase in role.model_dump_json().lower() for phrase in
        ("expected minutes", "projected role", "usage will", "will replace", "breakout probability"))


@pytest.mark.parametrize("value", [None, -4, "bad", float("nan"), True])
def test_role_missing_invalid_minutes_never_zero_filled_or_backfilled(value):
    logs = role_logs([40, 40, 20, 20, 20, value, 30])
    opportunity = current_role(logs, None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == "INSUFFICIENT EVIDENCE"
    assert role.minutes.recent.games == 2
    assert role.minutes.recent.average == 25
    assert role.minutes.recent.missing_game_ids == ["role-5"]
    assert role.minutes.delta is None
    assert opportunity.score is None
    all_missing = current_role(role_logs([value] * 6), None, "2026-27", NOW, NOW.date())
    assert all_missing.current_role.minutes.quality.state == "unavailable"
    assert all_missing.minutes is None
    assert all_missing.current_role.minutes.recent.average is None


@pytest.mark.parametrize("minutes,usages", [
    ([20, 20, 20, 20, 20, 40], None),
    ([40, 20, 20, 20, 20, 20], None),
    ([25]*6, [.2]*5+[.4]),
    ([25]*6, [.4]+[.2]*5),
])
def test_single_game_outlier_cannot_supply_supported_role_direction(minutes, usages):
    opportunity = current_role(role_logs(minutes, usages), None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.trend == "INSUFFICIENT EVIDENCE"
    assert opportunity.current_role.quality.state == "partial"
    assert opportunity.score is None


@pytest.mark.parametrize("stale_import", [True, False])
def test_stale_log_import_or_old_game_window_cannot_supply_current_role(stale_import):
    logs = role_logs([20, 20, 20, 30, 30, 30])
    for row in logs:
        if stale_import:
            row.imported_at = NOW - timedelta(days=8)
        else:
            row.game_date -= timedelta(days=14)
    opportunity = current_role(logs, None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.quality.state == "stale"
    assert opportunity.current_role.trend == "INSUFFICIENT EVIDENCE"
    assert opportunity.minutes_trend is None
    assert opportunity.score is None


@pytest.mark.parametrize("minutes,usages,expected", [
    ([25]*6, [.20]*3 + [.22]*3, "RISING"),
    ([25]*6, [.22]*3 + [.20]*3, "FALLING"),
    ([25]*6, [.20]*3 + [.219]*3, "STABLE"),
    ([20]*3+[30]*3, [.30]*3+[.20]*3, "INSUFFICIENT EVIDENCE"),
])
def test_usage_units_thresholds_and_conflicting_role_directions(minutes, usages, expected):
    opportunity = current_role(role_logs(minutes, usages), None, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.trend == expected
    assert role.usage.recent.average == pytest.approx(usages[-1])
    assert role.usage.delta == pytest.approx(usages[-1] - usages[0])
    assert role.usage.quality.state == "available"
    assert (opportunity.score is not None) == (expected != "INSUFFICIENT EVIDENCE")
    if opportunity.score is not None:
        assert set(opportunity.score_parts) == {"minutes_level", "usage_change"}
        assert opportunity.score == pytest.approx(sum(opportunity.score_parts.values())/2)


@pytest.mark.parametrize("usage", [-.01, 1.1, None, float("inf"), True])
def test_invalid_game_usage_is_unavailable_not_neutral(usage):
    opportunity = current_role(role_logs([25]*6, [usage]*6), None, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.usage.quality.state == "unavailable"
    assert opportunity.usage_trend is None
    assert set(opportunity.score_parts) == {"minutes_level"}


@pytest.mark.parametrize("payload,starts,games,state,value", [
    ({}, 0, 8, "unavailable", None),
    ({"GP": 4}, 4, 8, "available", 4),
    ({"GP": 0}, 0, 8, "available", 0),
    ({"GP": 4}, 3, 8, "unavailable", None),
    ({"GP": 9}, 9, 8, "unavailable", None),
    ({"GP": 2}, 2, 2, "partial", 2),
    ({"GP": 0}, 0, 0, "unavailable", None),
])
def test_season_starts_need_explicit_matching_provenance_not_default_zero(payload, starts, games, state, value):
    history = NbaPlayerSeasonStats(nba_player_id="role", season="2026-27",
        season_type="Regular Season", games_played=games, games_started=starts,
        base_stats={}, advanced_stats={"USG_PCT": .24}, usage_pct=.24,
        source_payload={"starter_filter": payload}, imported_at=NOW)
    opportunity = current_role(role_logs([20]*3+[30]*3), history, "2026-27", NOW, NOW.date())
    role = opportunity.current_role
    assert role.starts.quality.state == state
    assert role.starts.season_starts == value
    assert role.starts.recent_starts is None
    assert role.season_usage == .24
    assert role.usage.quality.state == "unavailable"
    assert role.usage.delta is None
    assert ("season_start_rate" in opportunity.score_parts) == (state == "available")
    history.season = "2025-26"
    prior = current_role(role_logs([25]*6), history, "2026-27", NOW, NOW.date())
    assert prior.current_role.starts.season_starts is None
    assert prior.current_role.season_usage is None


def test_season_starts_and_usage_staleness_are_independent_of_fresh_minutes():
    history = NbaPlayerSeasonStats(nba_player_id="role", season="2026-27",
        season_type="Regular Season", games_played=8, games_started=4,
        base_stats={}, advanced_stats={"USG_PCT": .24}, usage_pct=.24,
        source_payload={"starter_filter": {"GP": 4}}, imported_at=NOW-timedelta(days=8))
    opportunity = current_role(role_logs([25]*6), history, "2026-27", NOW, NOW.date())
    assert opportunity.current_role.starts.quality.state == "stale"
    assert opportunity.current_role.season_usage_quality.state == "stale"
    assert set(opportunity.score_parts) == {"minutes_level"}


def decision_context(games=7):
    drop, add = candidate(1, value=20), candidate(2, value=90)
    fresh = Evidence(state="available", source="Fixture", as_of=NOW, detail="Verified")
    for row in (drop, add):
        row.identity_mapping_state = "EXACT_NAME_TEAM"
        row.current_season_games = games
        row.recent.games = games
        row.evidence_quality = sample_label(games)
        row.yahoo_status = "P"
        row.opportunity = current_role(role_logs([20, 20, 20, 27, 27, 27]), None, "2026-27", NOW, NOW.date())
        row.data_quality = {key: fresh.model_copy() for key in
            ("recent", "ros", "status", "availability", "schedule", "opportunity")}
        row.overall_score, row.effective_weights = aggregate(row.components, WEIGHTS)
    ctx = Context(SimpleNamespace(), "t1", "this_week", NOW, {1: drop, 2: add},
        [1], ["C"], 1, True, WEIGHTS,
        {"settings": fresh, "roster": fresh, "acquisition_value": fresh})
    return ctx, drop, add


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
@pytest.mark.parametrize("games", [2, 5])
def test_low_sample_breakout_is_watch_never_add_despite_rising_role_and_prior_history(mode, games):
    ctx, drop, add = decision_context(games)
    ctx.mode = mode
    assert add.opportunity.current_role.trend == "RISING"
    add.ranking_value.historical_games = 80
    add.ranking_value.historical_value = 100
    assert enrich(ctx, add, drop.player_id).recommended_action == "WATCH"
    assert not sufficient_sample(add, mode)


def test_seven_game_positive_candidate_and_negative_swap_decisions():
    ctx, drop, add = decision_context()
    assert enrich(ctx, add, drop.player_id).recommended_action == "ADD"
    add.components.player_value = 1
    assert enrich(ctx, add, drop.player_id).recommended_action == "PASS"


@pytest.mark.parametrize("status", [None, "", "HEALTHY", "D", "IL"])
def test_blank_or_unrecognized_yahoo_status_fails_closed(status):
    ctx, drop, add = decision_context()
    add.yahoo_status = status
    add.data_quality["status"] = Evidence(
        state="available", source="Fixture", as_of=NOW, detail="Nonblank status observed",
    )
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    assert any("status is unknown" in blocker.lower() or "unrecognized" in blocker.lower()
        for blocker in transaction_blockers(ctx, add, drop))
    add.components.player_value = 1
    negative = enrich(ctx, add, drop.player_id)
    assert negative.comparison.net_improvement < 0
    assert negative.recommended_action == "INSUFFICIENT EVIDENCE"
    assert not status_is_supported(status)


@pytest.mark.parametrize("identity_state", ["NO_MATCH", "MISSING_MAPPING", "AMBIGUOUS"])
@pytest.mark.parametrize("side", ["add", "drop"])
def test_unresolved_yahoo_nba_identity_blocks_add(identity_state, side):
    ctx, drop, add = decision_context()
    (add if side == "add" else drop).identity_mapping_state = identity_state
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    assert any("identity is unresolved" in blocker
        for blocker in transaction_blockers(ctx, add, drop))


def test_only_verified_yahoo_status_tokens_are_supported():
    assert all(status_is_supported(value) for value in ("O", "NA", "P", "Q"))
    assert not status_is_supported(None)
    assert not status_is_supported("HEALTHY")


def test_yahoo_status_field_keeps_a_missing_field_distinct_from_a_supplied_blank():
    # Real-data audit (2026-11-14): every blank status in the 744-player pool was a record with no `status` key;
    # none carried a supplied blank. The two are different evidence, and neither is a designation.
    from app.services.draft.player_status import normalize_yahoo_status, recommendation_eligibility, yahoo_status_field
    assert yahoo_status_field({}) == "STATUS_FIELD_MISSING"
    assert {yahoo_status_field({"status": value}) for value in ("", None, "  ")} == {"YAHOO_SUPPLIED_BLANK"}
    assert {yahoo_status_field({"status": value}) for value in ("O", "OFS", "NA", " q ", "P")} == {"EXPLICIT_STATUS"}
    assert yahoo_status_field({"status": "DTD"}) == "UNRECOGNIZED_NONBLANK"
    assert normalize_yahoo_status(" q ") == "Q" and normalize_yahoo_status("  ") is None and normalize_yahoo_status(None) is None
    assert recommendation_eligibility(normalize_yahoo_status(None)) == "unknown", "neither blank kind is a designation"


def test_yahoo_out_for_season_is_a_verified_unavailable_status_that_cannot_fill_a_lineup():
    # Verified in the 2026-11-14 production player pool: status "OFS" with status_full "Out For Season".
    from app.services.draft.player_status import YAHOO_STATUS_LABELS, recommendation_eligibility
    assert status_is_supported("OFS") and recommendation_eligibility("OFS") == "excluded"
    assert YAHOO_STATUS_LABELS["OFS"] == "Out For Season"
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 85, status="OFS", rostered=True),
        evidence_player(3, "SF", 50, rostered=True)]
    roster[1].components.player_value = None
    ctx = roster_ctx(roster, [evidence_player(11, "C", 75)], slots_of(PG=1, C=1, BN=1, IL=1),
        {1: "PG", 2: "C", 3: "BN"}, eligible={2: ["C", "UTIL", "IL"]})
    out = next(row for row in ctx.roster_capacity.assignments if row.player_id == 2)
    assert out.injured and not out.lineup_eligible, "an out-for-season player cannot fill a lineup slot"
    assert ctx.roster_capacity.transaction_shape == "MOVE_TO_IL_THEN_ADD"


def test_sample_gate_names_the_player_and_window_that_fail_and_keeps_the_status_gate_visible():
    # Real-data regression (2026-11-14): a 12-game add read "Below seven supported current-season games" when the
    # failing count was the drop's 6 games in the last 14 days, and blank statuses were not mentioned at all.
    ctx, drop, add = decision_context()
    add.player_name, drop.player_name = "Twelve Game Add", "Six Recent Drop"
    add.current_season_games, add.recent.games = 12, 7
    drop.current_season_games, drop.recent.games = 12, 6
    # Five minutes observations: the drop's role is not qualified, so its LIMITED sample cannot be corroborated.
    drop.opportunity = current_role(role_logs([20, 20, 20, 27, 27]), None, "2026-27", NOW, NOW.date())
    pair = enrich(ctx, add, drop.player_id)
    assert pair.recommended_action == "WATCH"
    note = pair.evidence_blockers[0]
    assert note.startswith("Sample gate: Six Recent Drop 6 games in the last 14 days (LIMITED SAMPLE: 0 of 4 corroborations "
        "passed, 2 needed; missing requirement: qualified current role).") and "Twelve Game Add" not in note
    assert "need" in note and "Below seven supported current-season games" not in " ".join(pair.evidence_blockers)
    add.yahoo_status = drop.yahoo_status = None
    blank = enrich(ctx, add, drop.player_id)
    assert blank.recommended_action == "WATCH", "explaining the status gate does not change the decision"
    assert "Yahoo status gate: Twelve Game Add blank (UNKNOWN); Six Recent Drop blank (UNKNOWN)." in " ".join(blank.evidence_blockers)
    add.recent.games = drop.recent.games = 7
    status_only = enrich(ctx, add, drop.player_id)
    assert status_only.recommended_action == "INSUFFICIENT EVIDENCE", "blank status still fails closed"
    assert any(item.startswith("Yahoo status gate: Twelve Game Add blank (UNKNOWN)") for item in status_only.evidence_blockers)
    ctx.mode = "ros"
    add.ros.games, add.current_season_games = 5, 5
    season = enrich(ctx, add, drop.player_id)
    assert season.evidence_blockers[0].startswith("Sample gate: Twelve Game Add 5 games this season (LIMITED SAMPLE).")


YAHOO_FIELDS = {"PTS": 1, "REB": 1.2, "AST": 1.5, "BLK": 3, "STL": 3, "TOV": -1}


def form_logs(days_and_points, minutes=30, imported_at=None):
    """Persisted-shape logs: (days ago, PTS) pairs; other Yahoo stats fixed so fantasy points = PTS + 8."""
    return [PlayerGameLog(nba_player_id="form", game_id=f"form-{days}", season="2026-27", season_type="Regular Season",
        game_date=NOW.date() - timedelta(days=days),
        stats_payload={"PTS": points, "REB": 5, "AST": 2, "BLK": 0, "STL": 0, "TOV": 1,
            "MIN": minutes(days) if callable(minutes) else minutes},
        source_payload={}, imported_at=imported_at or NOW) for days, points in days_and_points]


def with_form(row, logs, season_games=None):
    """Attach backend form windows built by the production function from `logs` (no season rows)."""
    from app.features.waivers.service import recent_form
    row.form = recent_form(logs, None, None, YAHOO_FIELDS, NOW, NOW.date(), recent_quality=None, season_quality=None,
        starts=None, season_usage=None)
    if season_games is not None:
        row.current_season_games = season_games
    return row


# Depth: 6 games in the last 14 days and 6 earlier in 30 days, hot Last 14 Days and falling minutes, so only the
# 10+ games in 30 days can corroborate from form evidence.
DEPTH_ONLY = [*((day, 40) for day in (1, 3, 5, 7, 9, 11)), *((day, 20) for day in (16, 18, 20, 22, 24, 26))]


@pytest.mark.parametrize(("recent", "season", "role_minutes", "depth", "passes", "tier"), [
    (2, 12, [20, 20, 20, 27, 27, 27], True, False, "INSUFFICIENT"),
    (3, 12, [20, 20, 20, 27, 27, 27], True, False, "VERY_LOW"),
    (4, 12, [20, 20, 20, 27, 27, 27], True, False, "VERY_LOW"),
    (5, 12, [20, 20, 20, 27, 27], True, False, "LIMITED"),  # five games cannot qualify a 3 vs 3 role
    (6, 6, [20, 20, 20, 27, 27, 27], True, False, "LIMITED"),  # needs 7+ current-season games
    (6, 12, [30, 30, 30, 23, 23, 23], True, False, "LIMITED"),  # FALLING role: 10+ in 30 days alone is one corroboration
    (6, 12, [20, 20, 20, 27, 27, 27], False, False, "LIMITED"),  # RISING role alone; 10+ season games never count
    (6, 12, [20, 20, 20, 27, 27, 27], True, True, "LIMITED"),  # 10+ games in 30 days and a RISING role
    (7, 7, [20, 20, 20, 27, 27, 27], False, True, "SUPPORTED"),
])
def test_tiered_recent_sample_promotes_only_a_corroborated_limited_sample(recent, season, role_minutes, depth, passes, tier):
    from app.features.waivers.sample import assess_sample
    ctx, drop, add = decision_context()
    if depth:
        with_form(drop, form_logs(DEPTH_ONLY, minutes=lambda days: 24 if days <= 14 else 30))
    drop.current_season_games, drop.recent.games = season, recent
    drop.opportunity = current_role(role_logs(role_minutes), None, "2026-27", NOW, NOW.date())
    # A large prior season never rescues a small current sample.
    drop.ros.games, drop.ranking_value.historical_games, drop.ranking_value.historical_value = 82, 82, 100
    assessment = assess_sample(drop, "this_week")
    assert (assessment.tier, assessment.passes, assessment.relevant_games) == (tier, passes, recent)
    pair = enrich(ctx, add, drop.player_id)
    assert pair.recommended_action == ("ADD" if passes else "WATCH")
    assert sufficient_sample(drop, "next_14_days") is passes
    if tier == "LIMITED" and passes:
        assert assessment.corroborated and assessment.corroborations_passed >= 2
        assert {check.key for check in assessment.corroborations if check.passed} == {"last_30_games", "role_direction"}
        assert not any(note.startswith("Sample gate") for note in pair.evidence_blockers)


def test_limited_sample_with_enough_corroborations_names_the_missing_requirement_not_a_count_shortfall():
    # Real-data wording regression (2026-11-14): Kelly Oubre Jr. read "not corroborated, 3 of 2 corroborations".
    # Real-data policy regression (same day): 10+ season games also counted as a corroboration, so the same games
    # behind 10+ in 30 days counted twice. Only four independent corroborations exist.
    from app.features.waivers.sample import assess_sample
    ctx, drop, add = decision_context()
    drop.player_name, drop.current_season_games, drop.recent.games = "Five Recent Drop", 12, 5
    drop.opportunity = current_role(role_logs([20, 20, 20, 27, 27]), None, "2026-27", NOW, NOW.date())
    # 11 games in 30 days and steady PPG corroborate; a 5-minute drop and the unqualified role do not.
    with_form(drop, form_logs([(day, 30) for day in (1, 3, 5, 8, 10, 16, 18, 20, 23, 25, 27)],
        minutes=lambda days: 25 if days <= 14 else 30))
    assessment = assess_sample(drop, "this_week")
    assert (assessment.passes, assessment.corroborations_passed) == (False, 2)
    assert [check.key for check in assessment.corroborations] == ["last_30_games", "role_direction", "ppg_corroboration", "minutes_stable"]
    assert {check.key for check in assessment.corroborations if check.passed} == {"last_30_games", "ppg_corroboration"}
    assert assessment.detail == ("5 games in the last 14 days (LIMITED SAMPLE: gate not met; 2 of 4 corroborations passed, "
        "2 needed; missing requirement: qualified current role)")
    note = enrich(ctx, add, drop.player_id).evidence_blockers[0]
    assert note.startswith("Sample gate: Five Recent Drop 5 games in the last 14 days (LIMITED SAMPLE: 2 of 4 corroborations "
        "passed, 2 needed; missing requirement: qualified current role).")
    assert "not corroborated" not in note and "of 2 corroborations" not in note


def test_limited_season_sample_is_never_corroborated_in_rest_of_season_outlook():
    from app.features.waivers.sample import assess_sample
    ctx, drop, add = decision_context()
    ctx.mode = "ros"
    add.current_season_games, add.ros.games = 6, 6
    with_form(add, form_logs([(day, 30) for day in range(1, 13)]))
    assessment = assess_sample(add, "ros")
    assert (assessment.tier, assessment.passes, assessment.window) == ("LIMITED", False, "CURRENT_SEASON")
    assert "cannot be corroborated" in assessment.detail
    assert enrich(ctx, add, drop.player_id).recommended_action == "WATCH"


def test_corroboration_uses_form_windows_tolerance_and_minutes_without_zero_filling():
    from app.features.waivers.sample import FORM_PPG_TOLERANCE, assess_sample
    ctx, drop, add = decision_context()
    # 6 games in the last 14 days, 6 more in days 15-30; FALLING role so only form evidence can corroborate.
    drop.opportunity = current_role(role_logs([30, 30, 30, 23, 23, 23]), None, "2026-27", NOW, NOW.date())
    drop.recent.games = 6
    steady = form_logs([*((day, 20) for day in (1, 3, 5, 7, 9, 11)), *((day, 20) for day in (16, 18, 20, 22, 24, 26))])
    with_form(drop, steady, season_games=8)
    checks = {check.key: check for check in assess_sample(drop, "this_week").corroborations}
    assert checks["last_30_games"].passed and checks["ppg_corroboration"].passed and checks["minutes_stable"].passed
    assert "season_games" not in checks and not checks["role_direction"].passed
    assert assess_sample(drop, "this_week").passes
    # Last-14 PPG far above Last-30 PPG fails the evidence-based tolerance; collapsed minutes fail the minutes check.
    hot = form_logs([*((day, 40) for day in (1, 3, 5, 7, 9, 11)), *((day, 10) for day in (16, 18, 20, 22, 24, 26))],
        minutes=lambda days: 20 if days < 15 else 30)
    with_form(drop, hot, season_games=8)
    checks = {check.key: check for check in assess_sample(drop, "this_week").corroborations}
    assert not checks["ppg_corroboration"].passed and f"tolerance {FORM_PPG_TOLERANCE * 100:.0f}%" in checks["ppg_corroboration"].detail
    assert not checks["minutes_stable"].passed and "-10.0" in checks["minutes_stable"].detail
    assert not assess_sample(drop, "this_week").passes and enrich(ctx, add, drop.player_id).recommended_action == "WATCH"
    # A missing scoring statistic is never zero-filled: fantasy PPG is unavailable, so PPG cannot corroborate.
    for log in steady[:2]:
        log.stats_payload = {key: value for key, value in log.stats_payload.items() if key != "BLK"}
    with_form(drop, steady, season_games=8)
    window = next(row for row in drop.form.windows if row.key == "LAST_14_DAYS")
    assert window.fantasy_ppg is None and window.state == "missing" and "BLK" in window.detail
    assert not {check.key: check for check in assess_sample(drop, "this_week").corroborations}["ppg_corroboration"].passed


@pytest.mark.parametrize(("recent_points", "recent_minutes", "expected"), [
    (30, 34, "IMPROVING"), (30, 30, "IMPROVING"), (20, 34, "IMPROVING"),
    (10, 26, "DECLINING"), (20, 30, "STABLE"), (30, 26, "MIXED"),
])
def test_form_trend_needs_ppg_and_minutes_on_non_overlapping_windows(recent_points, recent_minutes, expected):
    from app.features.waivers.service import form_trend
    logs = form_logs([*((day, recent_points) for day in (1, 4, 8)), *((day, 20) for day in (16, 20, 25))],
        minutes=lambda days: recent_minutes if days < 15 else 30)
    trend = form_trend(logs, YAHOO_FIELDS, NOW, NOW.date())
    assert trend.trend == expected, trend.detail
    assert (trend.recent_games, trend.baseline_games) == (3, 3)
    short = form_trend(logs[:4], YAHOO_FIELDS, NOW, NOW.date())
    assert short.trend == "INSUFFICIENT EVIDENCE" and short.minutes_change is None
    stale = form_trend(form_logs([(1, 30), (4, 30), (8, 30), (16, 20), (20, 20), (25, 20)], imported_at=NOW - timedelta(days=9)),
        YAHOO_FIELDS, NOW, NOW.date())
    assert stale.trend == "INSUFFICIENT EVIDENCE", "stale imports never establish a trend"


def test_form_windows_report_games_ppg_minutes_and_never_invent_recent_starts_or_usage():
    from app.features.waivers.service import recent_form
    logs = form_logs([(0, 30), (2, 20), (6, 10), (10, 20), (13, 20), (20, 40), (29, 0)], minutes=lambda days: 20 + days)
    form = recent_form(logs, None, None, YAHOO_FIELDS, NOW, NOW.date(), recent_quality=None, season_quality=None,
        starts=None, season_usage=None)
    windows = {row.key: row for row in form.windows}
    assert [row.key for row in form.windows] == ["LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "CURRENT_SEASON", "PREVIOUS_SEASON"]
    assert [windows[key].games for key in ("LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS")] == [3, 5, 7]
    assert windows["LAST_7_DAYS"].fantasy_ppg == pytest.approx((38 + 28 + 18) / 3)
    assert (windows["LAST_7_DAYS"].window_start, windows["LAST_7_DAYS"].window_end) == (NOW.date() - timedelta(days=7), NOW.date())
    assert windows["LAST_30_DAYS"].minutes_median == 30 and windows["LAST_30_DAYS"].sample_tier == "SUPPORTED"
    assert windows["LAST_14_DAYS"].sample_label == "LIMITED SAMPLE" and windows["LAST_7_DAYS"].sample_label == "VERY LOW SAMPLE"
    for key in ("LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS"):
        assert windows[key].starts is None and windows[key].usage is None
        assert "not in the persisted game logs" in windows[key].starts_detail
    assert windows["CURRENT_SEASON"].state == windows["PREVIOUS_SEASON"].state == "missing"
    assert any("not Next 14 Days" in item for item in form.limitations)


def test_next_14_days_is_a_forward_window_with_its_own_schedule_counts():
    from app.features.waivers.service import window_end_date
    today = date(2026, 11, 14)
    assert window_end_date(today, 2026, "next_14_days") == date(2026, 11, 27)
    assert window_end_date(today, 2026, "next_7_days") == date(2026, 11, 20)
    assert window_end_date(today, 2026, "ros") == date(2027, 6, 30)
    rows = [SimpleNamespace(game_date=today + timedelta(days=offset), game_status="7:00 pm ET", opponent_team_id="b",
        imported_at=NOW) for offset in (0, 1, 3, 6, 7, 10, 13, 14, 20)]
    schedule = resolve_schedule(rows, today, today + timedelta(days=13), NOW, Counter(), {"b": "BOS"},
        nba_mapped=True, team_mapped=True)
    assert (schedule.games_remaining, schedule.next_7_days_games, schedule.next_14_days_games) == (7, 4, 7)
    assert schedule.rest_of_season_games == 9 and schedule.back_to_backs == 2 and schedule.coverage == "PARTIAL"
    assert schedule.window_end == today + timedelta(days=13) and schedule.opponents == ["BOS"] * 7


@pytest.mark.parametrize(("mode", "intent"), [
    ("this_week", "STREAM"), ("next_7_days", "STREAM"), ("next_14_days", "TWO_WEEK_STREAM"), ("ros", "LONGER_TERM_ADD"),
])
def test_supported_moves_carry_a_horizon_intent_without_changing_the_decision(mode, intent):
    ctx, drop, add, analyze = optimizer_context()
    ctx.mode = mode
    best = analyze(ctx).best_transaction
    assert best.decision == "ADD" and best.add_player.move_intent == intent and best.add_player.move_intent_detail
    add.components.player_value = 1
    held = enrich(ctx, add, drop.player_id)
    assert (held.recommended_action_type, held.move_intent) == ("HOLD", "HOLD")
    add.components.player_value = 90
    add.current_season_games = add.recent.games = add.ros.games = 3
    assert enrich(ctx, add, drop.player_id).move_intent == "WATCH"


def test_short_term_intent_without_persisted_horizon_games_says_production_led_and_asserts_no_zero():
    # Real-data regression (2026-11-14): a supported Rest of Week ADD with no persisted weekend games read only
    # "Short-term move supported in Rest of Week", implying a schedule edge the evidence does not show.
    ctx, drop, add, analyze = optimizer_context()
    ctx.mode = "this_week"
    add.schedule = add.schedule.model_copy(update={"games_remaining": 2, "diagnostic_reason": "SCHEDULE_ROWS_PRESENT"})
    scheduled = analyze(ctx).best_transaction.add_player
    assert scheduled.move_intent == "STREAM" and "not established" not in scheduled.move_intent_detail
    add.schedule = add.schedule.model_copy(update={"games_remaining": None, "diagnostic_reason": "SCHEDULE_SOURCE_INCOMPLETE"})
    best = analyze(ctx).best_transaction
    assert (best.decision, best.add_player.move_intent) == ("ADD", "STREAM"), "the decision and intent are unchanged"
    # 2026-11-21 audit (WC-05): the reason comes from the measured contributions; fit did not change, so it is never
    # claimed, and the static "measured production and roster fit" wording is gone.
    detail = best.add_player.move_intent_detail
    assert detail.startswith("Short-term move in Rest of Week. Main reason: Production: ")
    assert detail.endswith(f"Games for {add.player_name} in Rest of Week are not established (SCHEDULE_SOURCE_INCOMPLETE), "
        "so the schedule is not part of this support.")
    assert "roster fit" not in detail.lower()
    ctx.mode = "next_14_days"
    detail = analyze(ctx).best_transaction.add_player.move_intent_detail
    assert detail.startswith("Two-week move. Main reason: Production: ") and "roster" not in detail.lower()
    assert detail.endswith(f"Games for {add.player_name} in Next 14 Days are not established (SCHEDULE_SOURCE_INCOMPLETE), "
        "so the schedule is not part of this support.")


def test_next_14_days_intent_names_only_the_evidence_that_supports_the_move():
    # Wording cleanup (2026-11-14): the deployed STREAM text read "by schedule and opportunity and the persisted
    # two-week schedule". Role is named only for role-gated STREAM moves; the schedule only when it has games.
    ctx, drop, add, analyze = optimizer_context()
    ctx.mode = "next_14_days"
    add.schedule = add.schedule.model_copy(update={"games_remaining": 7, "diagnostic_reason": "SCHEDULE_ROWS_PRESENT"})
    production = analyze(ctx).best_transaction
    assert (production.decision, production.add_player.move_intent) == ("ADD", "TWO_WEEK_STREAM")
    # 2026-11-21 audit (WC-05): only components with a positive measured contribution are named. Here production
    # carries the move; schedule and fit are unchanged, so neither is claimed.
    assert production.add_player.move_intent_detail.startswith("Two-week move. Main reason: Production: ")
    assert not any(word in production.add_player.move_intent_detail.lower() for word in ("schedule", "roster", "role"))
    other = add.model_copy(deep=True, update={"player_id": 3, "player_name": "Schedule add"})
    other.components.player_value, other.components.schedule, add.components.schedule = 80, 100, 1
    ctx.players[3] = other
    ctx.weights = {**WEIGHTS, "player_value": .1, "schedule": .7}
    stream = analyze(ctx).best_transaction
    assert (stream.add_player.player_id, stream.decision, stream.add_player.move_intent) == (3, "STREAM", "TWO_WEEK_STREAM")
    # Role gates a STREAM but its contribution is zero here (equal opportunity), so it is never named as a reason.
    assert stream.add_player.move_intent_detail.startswith("Two-week move. Main reason: Schedule: 7 games")
    assert "role" not in stream.add_player.move_intent_detail.lower()
    for text in (production.add_player.move_intent_detail, stream.add_player.move_intent_detail):
        assert not any(word in text.lower() for word in ("two-week schedule", "project", "guarantee", "matchup", "complete"))


def test_decision_support_names_the_recent_window_for_a_seven_game_player():
    # Real-data regression (2026-11-14): a Q player with 7 current-season games but 3 in the last 14 days was told
    # "Below seven supported current-season games".
    ctx = one_open_spot_context(watch_games=7)
    row = ctx.players[13]
    row.recent.games = 3
    row.measured = measured_production(mode="this_week", season="2026-27", recent_value=row.recent.value,
        recent_games=3, recent_as_of=NOW, recent_latest_game=NOW.date(), current_value=row.recent.value,
        current_games=7, current_as_of=NOW, prior_value=row.recent.value, prior_games=60, prior_season="2025-26",
        scoring_available=True, now=NOW, today=NOW.date())
    assert row.measured.basis == "RECENT" and row.measured.comparable
    support = decision_support_for(support_ctx(ctx), board_candidates(ctx))
    option = options_by_id(support)[13]
    assert option.blockers, "featured players list their blockers"
    assert any("3 games in the last 14 days" in item for item in option.blockers), option.blockers
    assert not any("Below seven supported current-season games" in item for item in option.blockers)


def test_out_for_season_player_never_enters_the_waiver_pool(persisted):
    # Real-data regression (2026-11-14): three Yahoo OFS players were eligible candidates with actionable
    # availability and the label "not a recognized status".
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            row = (await session.execute(select(LeaguePlayer).where(
                LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["out"]))).scalar_one()
            row.source_payload = {**row.source_payload, "status": "OFS", "status_full": "Out For Season"}
        await engine.dispose()
    asyncio.run(change())
    for mode in ("this_week", "next_7_days", "ros"):
        result = board(f, mode=mode)
        assert f.ids["out"] not in result["eligible_candidate_ids"]
        assert f.ids["out"] not in {row["player_id"] for row in result["decision_support"]["options"]}
        assert result["availability_summary"]["counts"]["EXCLUDED_STATUS"] == 2
    candidate = f.client.get(f"/api/v1/waivers/{f.ids['out']}/impact").json()["candidate"]
    assert (candidate["availability_classification"], candidate["availability_evidence"]["label"]) == (
        "EXCLUDED_STATUS", "EXCLUDED (YAHOO O/OFS/NA)")
    assert candidate["recommended_action_type"] == "INSUFFICIENT_EVIDENCE"
    assert any("Out For Season" in reason for reason in candidate["reasons"])


def test_missing_status_field_with_a_conflicting_identity_status_stays_unknown_and_is_never_a_supplied_blank(persisted):
    # Real-data audit (2026-11-14): Yahoo omitted the `status` field for all 426 undesignated players, yet the waiver
    # diagnostic said "Yahoo supplied a blank status". The fixture identity still says "O", so this absence is a
    # normalization defect: it stays UNKNOWN and changes no decision.
    f = persisted

    def impact():
        return f.client.get(f"/api/v1/waivers/{f.ids['unknown']}/impact").json()["candidate"]

    supplied, coverage_before = impact(), board(f)["coverage"]["pool"]["status"]
    assert (supplied["status_diagnostic"], supplied["raw_yahoo_status"]) == ("YAHOO_SUPPLIED_BLANK", "")

    async def change():
        async with SessionFactory() as session, session.begin():
            row = (await session.execute(select(LeaguePlayer).where(
                LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["unknown"]))).scalar_one()
            row.source_payload = {key: value for key, value in row.source_payload.items() if key != "status"}
        await engine.dispose()
    asyncio.run(change())
    missing, coverage_after = impact(), board(f)["coverage"]["pool"]["status"]
    assert (missing["status_diagnostic"], missing["raw_yahoo_status"], missing["yahoo_status"]) == ("STATUS_FIELD_MISSING", None, None)
    assert (missing["status_field_state"], missing["decision_status_state"], missing["status_reason"]) == (
        "STATUS_FIELD_MISSING", "UNKNOWN", "NORMALIZATION_DEFECT")
    assert (missing["status_label"], missing["status_gate_supported"]) == ("UNKNOWN", False)
    assert (supplied["status_reason"], supplied["status_label"], supplied["status_gate_supported"]) == (
        "YAHOO_SUPPLIED_BLANK", "UNKNOWN", False)
    status = missing["data_quality"]["status"]
    assert status["state"] == "unknown" and "no status field" in status["detail"] and "not healthy" in status["detail"]
    assert "supplied" not in status["detail"]
    for key in ("eligible", "availability_classification", "recommended_action", "recommended_action_type",
            "net_improvement", "evidence_blockers", "overall_score"):
        assert missing[key] == supplied[key], key
    assert coverage_after["field_missing"]["count"] == coverage_before["field_missing"]["count"] + 1
    assert coverage_after["yahoo_blank"]["count"] == coverage_before["yahoo_blank"]["count"] - 1
    assert coverage_after["no_current_designation"]["count"] == coverage_before["no_current_designation"]["count"] == 0


# User-approved policy (2026-11-14): a fresh Yahoo player record with no `status` key means NO CURRENT YAHOO
# DESIGNATION and may pass the status gate, only when every condition below holds. It is never a health claim.
FORBIDDEN_STATUS_WORDS = ("HEALTHY", "ACTIVE", "CLEARED", "NO INJURY")


def status_interpretation(payload=None, **overrides):
    from app.services.draft.player_status import interpret_yahoo_status
    values = dict(identity_yahoo_player_id="77", identity_status=None, player_pool_observation=True,
        observation_fresh=True, identity_resolved=True, mapping_conflict=False, rosters_complete=True)
    values.update(overrides)
    return interpret_yahoo_status({"player_id": "77", "name": {"full": "Fixture"}} if payload is None else payload, **values)


def no_designation(row):
    """A candidate as load_context builds it from a fresh, fully verified record without a `status` key."""
    from app.services.draft.player_status import NO_CURRENT_DESIGNATION_DETAIL, NO_CURRENT_DESIGNATION_LABEL
    row.yahoo_status = row.raw_yahoo_status = None
    row.status_field_state = row.status_diagnostic = "STATUS_FIELD_MISSING"
    row.decision_status_state = row.status_reason = "NO_CURRENT_YAHOO_DESIGNATION"
    row.status_label, row.status_detail = NO_CURRENT_DESIGNATION_LABEL, NO_CURRENT_DESIGNATION_DETAIL
    row.status_gate_supported = True
    row.data_quality["status"] = FRESH.model_copy(update={"detail": NO_CURRENT_DESIGNATION_DETAIL})
    return row


def test_fresh_verified_missing_status_field_is_no_current_yahoo_designation_and_never_a_health_claim():
    result = status_interpretation()
    assert (result.status, result.raw_status, result.field_state) == (None, None, "STATUS_FIELD_MISSING")
    assert (result.decision_state, result.reason) == ("NO_CURRENT_YAHOO_DESIGNATION", "NO_CURRENT_YAHOO_DESIGNATION")
    assert result.label == "NO CURRENT YAHOO DESIGNATION"
    assert result.detail == ("Yahoo's current player record contains no explicit injury/status designation. "
        "This is not a medical-health guarantee.")
    assert not any(word in f"{result.label} {result.detail}".upper() for word in FORBIDDEN_STATUS_WORDS)
    # The Yahoo id is read with the importer's own parser, so a player_key-only record links the same way.
    assert status_interpretation({"player_key": "466.p.77"}).decision_state == "NO_CURRENT_YAHOO_DESIGNATION"


@pytest.mark.parametrize(("payload", "overrides", "reason"), [
    ({"player_id": "77"}, {"player_pool_observation": False}, "PLAYER_OBSERVATION_MISSING"),
    ({"player_id": "77"}, {"observation_fresh": False}, "STALE_PLAYER_POOL_IMPORT"),
    ({"player_id": "77"}, {"identity_resolved": False}, "MAPPING_ISSUE"),
    ({"player_id": "77"}, {"mapping_conflict": True}, "MAPPING_ISSUE"),
    ({"player_id": "78"}, {}, "MAPPING_ISSUE"),
    ({"name": {"full": "No Yahoo id"}}, {}, "MAPPING_ISSUE"),
    ({"player_id": "77"}, {"identity_status": "O"}, "NORMALIZATION_DEFECT"),
    ({"player_id": "77", "status_full": "Out"}, {}, "NORMALIZATION_DEFECT"),
    ({"player_id": "77", "injury_note": "Knee"}, {}, "NORMALIZATION_DEFECT"),
    ({"player_id": "77", "on_disabled_list": "1"}, {}, "NORMALIZATION_DEFECT"),
    ({"player_id": "77"}, {"rosters_complete": False}, "ROSTER_SNAPSHOT_INCOMPLETE"),
    ({"player_id": "77", "status": ""}, {}, "YAHOO_SUPPLIED_BLANK"),
    ({"player_id": "77", "status": None}, {}, "YAHOO_SUPPLIED_BLANK"),
    ({"player_id": "77", "status": "  "}, {}, "YAHOO_SUPPLIED_BLANK"),
    ({"player_id": "77", "status": "DTD"}, {}, "UNRECOGNIZED_NONBLANK"),
])
def test_missing_status_field_stays_unknown_unless_every_condition_holds(payload, overrides, reason):
    result = status_interpretation(payload, **overrides)
    assert (result.decision_state, result.reason) == ("UNKNOWN", reason)
    assert result.status is None or result.status == "DTD"
    assert result.label.endswith("UNKNOWN") and "NO CURRENT YAHOO DESIGNATION" not in result.detail.upper()
    if result.field_state == "STATUS_FIELD_MISSING":
        assert "no status field" in result.detail and "not healthy" in result.detail


@pytest.mark.parametrize(("status", "state", "label"), [
    ("O", "EXCLUDED", "O · Out (short-term injury)"), ("OFS", "EXCLUDED", "OFS · Out For Season"),
    ("NA", "EXCLUDED", "NA · Not Active"), ("Q", "UNCERTAIN", "Q · Questionable"), ("P", "UNCERTAIN", "P · Probable"),
])
def test_explicit_yahoo_designations_keep_their_behavior_under_the_missing_field_policy(status, state, label):
    # The missing-field conditions never apply to an explicit token: identity, roster and mapping flags are ignored.
    fresh = status_interpretation({"player_id": "77", "status": f" {status.lower()} "}, identity_status="Q",
        identity_resolved=False, mapping_conflict=True, rosters_complete=False, player_pool_observation=False)
    assert (fresh.status, fresh.raw_status, fresh.field_state) == (status, f" {status.lower()} ", "EXPLICIT_STATUS")
    assert (fresh.decision_state, fresh.reason, fresh.label) == (state, "EXPLICIT_DESIGNATION", label)
    stale = status_interpretation({"player_id": "77", "status": status}, observation_fresh=False)
    assert (stale.decision_state, stale.reason, stale.label) == (
        "EXCLUDED" if state == "EXCLUDED" else "UNKNOWN", "STALE_PLAYER_POOL_IMPORT", label)


def test_candidates_without_a_status_interpretation_fail_closed():
    from app.features.waivers.service import status_gap
    row = candidate(1)
    assert (row.status_field_state, row.decision_status_state, row.status_reason) == (None, "UNKNOWN", None)
    assert (row.status_gate_supported, row.status_label, row.status_detail) == (False, None, None)
    row.data_quality["status"] = FRESH.model_copy()
    assert status_gap(row, NOW) == "blank (UNKNOWN)", "fresh evidence alone never turns a blank into a designation"
    no_designation(row)
    assert status_gap(row, NOW) is None
    for update in ({"state": "unknown"}, {"state": "stale"}, {"as_of": NOW - timedelta(days=2)}):
        row.data_quality["status"] = FRESH.model_copy(update=update)
        assert status_gap(row, NOW) is not None, update


@pytest.mark.parametrize("side", ["add", "drop", "both"])
def test_fresh_missing_status_field_lets_a_status_only_blocked_pair_become_a_supported_add(side):
    ctx, drop, add, analyze = optimizer_context()
    rows = {"add": [add], "drop": [drop], "both": [add, drop]}[side]
    for row in rows:
        unknown_status(row)
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    assert "Add or drop Yahoo status is unknown, unrecognized or stale" in transaction_blockers(ctx, add, drop)
    assert analyze(ctx).best_transaction is None
    for row in rows:
        no_designation(row)
    pair = enrich(ctx, add, drop.player_id)
    assert pair.recommended_action == "ADD" and pair.comparison.net_improvement > 0
    assert not any("Yahoo status" in note for note in pair.evidence_blockers)
    assert transaction_blockers(ctx, pair, drop) == []
    best = analyze(ctx).best_transaction
    assert (best.add_player.player_id, best.drop_player.player_id, best.decision) == (add.player_id, drop.player_id, "ADD")
    assert best.comparison == pair.comparison


@pytest.mark.parametrize("short", ["add", "drop"])
def test_no_current_designation_never_bypasses_the_sample_gate(short):
    ctx, drop, add = decision_context()
    for row in (add, drop):
        no_designation(row)
    low = add if short == "add" else drop
    low.current_season_games = low.recent.games = 4
    result = enrich(ctx, add, drop.player_id)
    assert result.recommended_action == "WATCH"
    assert any(note.startswith("Sample gate: ") and low.player_name in note for note in result.evidence_blockers)
    assert not any(note.startswith("Yahoo status gate: ") for note in result.evidence_blockers)
    assert "Insufficient fresh current-season sample for add or drop" in transaction_blockers(ctx, result, drop)


def test_nonpositive_pair_with_no_current_designation_is_pass_and_the_optimizer_holds():
    ctx, drop, add, analyze = optimizer_context()
    for row in (add, drop):
        no_designation(row)
    add.components.player_value = 1
    pair = enrich(ctx, add, drop.player_id)
    assert pair.comparison.net_improvement < 0 and pair.recommended_action == "PASS"
    result = analyze(ctx)
    assert result.best_transaction is None and result.decision == "HOLD" and result.recommended_action_type == "HOLD"
    assert result.supported_pair_count == 1 and not result.top_supported_transactions[0].comparison.net_improvement > 0


def test_decision_support_shows_the_backend_designation_label_and_no_blank_status_blocker():
    from app.services.draft.player_status import NO_CURRENT_DESIGNATION_DETAIL, NO_CURRENT_DESIGNATION_LABEL
    ctx = one_open_spot_context(watch_games=7)
    for pid in (12, 13):
        del ctx.players[pid]
    no_designation(ctx.players[11])
    support_ctx(ctx)
    candidates = board_candidates(ctx)
    assert candidates[0].recommended_action_type == "ADD_ONLY"
    option = options_by_id(decision_support_for(ctx, candidates))[11]
    assert option.classification == "SUPPORTED_ACTION"
    assert (option.status_label, option.status_detail, option.decision_status_state) == (
        NO_CURRENT_DESIGNATION_LABEL, NO_CURRENT_DESIGNATION_DETAIL, "NO_CURRENT_YAHOO_DESIGNATION")
    # A not-yet-supported option keeps its other blockers but never asks to confirm a status it already has.
    ctx.players[11].current_season_games = ctx.players[11].recent.games = 5
    measure(ctx.players[11])
    option = options_by_id(decision_support_for(ctx, board_candidates(ctx)))[11]
    assert option.classification != "SUPPORTED_ACTION" and option.status_label == NO_CURRENT_DESIGNATION_LABEL
    assert not any("UNKNOWN" in item or "Yahoo status" in item for item in option.blockers), option.blockers
    assert "Current Yahoo status" not in option.confirm
    assert any("Current-season sample is 5 games" in item for item in option.blockers)


def drop_status_field(f, *names):
    """Persist fresh Yahoo records for `names` with no `status` key; the importer's identity status follows."""
    async def change():
        async with SessionFactory() as session, session.begin():
            for name in names:
                for model in (LeaguePlayer, RosterEntry):
                    for row in (await session.execute(select(model).where(
                            model.league_key == f.league, model.player_identity_id == f.ids[name]))).scalars().all():
                        row.source_payload = {key: value for key, value in row.source_payload.items() if key != "status"}
                (await session.get(PlayerIdentity, f.ids[name])).status = None
        await engine.dispose()
    asyncio.run(change())


def test_fresh_missing_status_field_clears_the_status_gate_identically_on_every_surface(persisted):
    f = persisted
    blocked = f.client.get("/api/v1/waivers/transactions", params={"mode": "ros"}).json()
    assert blocked["best_transaction"] is None, "supplied-blank drop statuses block every pair"
    assert blocked["excluded_pair_reasons"]["Add or drop Yahoo status is unknown, unrecognized or stale"] > 0
    drop_status_field(f, "unknown", "guard", "weak", "opponent")
    statements = []

    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        result = board(f, mode="ros")
        rows = {row["player_name"]: row for row in result["candidates"]}
        unknown = rows["unknown"]
        assert (unknown["raw_yahoo_status"], unknown["yahoo_status"], unknown["status_diagnostic"]) == (None, None, "STATUS_FIELD_MISSING")
        assert (unknown["status_field_state"], unknown["decision_status_state"], unknown["status_reason"]) == (
            "STATUS_FIELD_MISSING", "NO_CURRENT_YAHOO_DESIGNATION", "NO_CURRENT_YAHOO_DESIGNATION")
        assert (unknown["status_label"], unknown["status_gate_supported"]) == ("NO CURRENT YAHOO DESIGNATION", True)
        assert unknown["data_quality"]["status"]["state"] == "available"
        assert unknown["data_quality"]["status"]["detail"] == unknown["status_detail"]
        assert unknown["reasons"][0] == f"Current Yahoo status: NO CURRENT YAHOO DESIGNATION. {unknown['status_detail']}"
        assert (rows["center"]["decision_status_state"], rows["center"]["status_label"], rows["center"]["status_gate_supported"]) == (
            "UNCERTAIN", "Q · Questionable", True)
        assert (rows["unmapped"]["decision_status_state"], rows["unmapped"]["status_reason"]) == ("UNKNOWN", "YAHOO_SUPPLIED_BLANK")
        coverage = result["coverage"]["pool"]["status"]
        assert (coverage["field_missing"]["count"], coverage["no_current_designation"]["count"]) == (4, 4)
        assert f.ids["opponent"] not in result["eligible_candidate_ids"], "no designation never makes another team's player available"
        assert f.client.get(f"/api/v1/waivers/{f.ids['opponent']}/impact", params={"mode": "ros"}).status_code == 409
        assert f.client.get(f"/api/v1/waivers/{f.ids['weak']}/impact", params={"mode": "ros"}).status_code == 409
        manager = {row["player_id"]: row for row in result["roster_capacity"]["assignments"]}
        assert {manager[f.ids[name]]["status_label"] for name in ("guard", "weak")} == {"NO CURRENT YAHOO DESIGNATION"}
        assert result["team_needs_analysis"]["unknown_status_player_ids"] == []

        analysis = f.client.get("/api/v1/waivers/transactions", params={"mode": "ros"}).json()
        best = analysis["best_transaction"]
        assert best is not None and best["decision"] in {"ADD", "STREAM"} and analysis["decision"] == best["decision"]
        assert best["drop_player"]["decision_status_state"] == "NO_CURRENT_YAHOO_DESIGNATION"
        status_blocked = "Add or drop Yahoo status is unknown, unrecognized or stale"
        assert blocked["excluded_pair_reasons"][status_blocked] > analysis["excluded_pair_reasons"][status_blocked] == 2, (
            "only the supplied-blank add (unmapped) against each of the two drops stays status-blocked")
        add_id, drop_id = best["add_player"]["player_id"], best["drop_player"]["player_id"]
        assert add_id in result["eligible_candidate_ids"]
        replacement = next(row for row in board(f, mode="ros", drop_player_id=drop_id)["candidates"] if row["player_id"] == add_id)
        impact = f.client.get(f"/api/v1/waivers/{add_id}/impact", params={"mode": "ros", "drop_player_id": drop_id}).json()
        assert replacement["comparison"] == impact["comparison"] == best["comparison"]
        assert replacement["recommended_action"] == impact["candidate"]["recommended_action"] == best["decision"]
        f.no_yahoo.assert_not_called()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)


def test_stale_pool_or_incomplete_rosters_keep_a_missing_status_field_unknown_through_the_api(persisted):
    f = persisted
    drop_status_field(f, "unknown", "guard", "weak")

    def unknown():
        return f.client.get(f"/api/v1/waivers/{f.ids['unknown']}/impact", params={"mode": "ros"}).json()["candidate"]

    assert unknown()["decision_status_state"] == "NO_CURRENT_YAHOO_DESIGNATION"

    async def stale_other_roster():
        async with SessionFactory() as session, session.begin():
            (await session.get(FantasyTeam, f.team2)).imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        await engine.dispose()
    asyncio.run(stale_other_roster())
    incomplete = unknown()
    assert (incomplete["decision_status_state"], incomplete["status_reason"]) == ("UNKNOWN", "ROSTER_SNAPSHOT_INCOMPLETE")
    assert incomplete["status_gate_supported"] is False and incomplete["status_label"] == "UNKNOWN"
    assert incomplete["data_quality"]["status"]["state"] == "unknown"
    assert incomplete["recommended_action_type"] == "INSUFFICIENT_EVIDENCE"
    assert f.client.get("/api/v1/waivers/transactions", params={"mode": "ros"}).json()["best_transaction"] is None

    async def stale_pool():
        async with SessionFactory() as session, session.begin():
            (await session.get(FantasyTeam, f.team2)).imported_at = datetime.now(timezone.utc)
            row = (await session.execute(select(LeaguePlayer).where(
                LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["unknown"]))).scalar_one()
            row.imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        await engine.dispose()
    asyncio.run(stale_pool())
    stale = unknown()
    assert (stale["decision_status_state"], stale["status_reason"], stale["status_gate_supported"]) == (
        "UNKNOWN", "STALE_PLAYER_POOL_IMPORT", False)
    assert stale["data_quality"]["status"]["state"] == "stale"
    assert stale["recommended_action_type"] == "INSUFFICIENT_EVIDENCE"
    f.no_yahoo.assert_not_called()


def test_data_gaps_keep_supported_root_causes_and_truthful_unknowns():
    rows = [candidate(1), candidate(2), candidate(3)]
    resolved = "EXACT_NAME_TEAM"
    rows[0].identity_mapping_state = "NO_MATCH"
    rows[0].schedule.diagnostic_reason = "NO_PLAYER_SCHEDULE_ROWS"
    rows[0].status_diagnostic = "YAHOO_SUPPLIED_BLANK"
    rows[0].raw_yahoo_status = ""
    rows[0].data_quality = {
        "recent": Evidence(state="missing", source="Fixture", as_of=NOW,
            detail="Recent production is missing because no eligible persisted NBA game/stat observations exist in the selected window."),
        "ros": Evidence(state="unsupported", source="Fixture", as_of=NOW,
            detail="Season Evidence production is unsupported because persisted Yahoo points modifiers are unavailable."),
        "status": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Yahoo supplied a blank status."),
    }
    rows[1].identity_mapping_state = resolved
    rows[1].schedule.coverage = "UNKNOWN"
    rows[1].schedule.diagnostic_reason = "NO_GAMES_IN_WINDOW"
    rows[1].status_diagnostic = "UNRECOGNIZED_STATUS"
    rows[1].raw_yahoo_status = "HEALTHY"
    rows[1].data_quality = {
        "recent": Evidence(state="stale", source="Fixture", as_of=NOW-timedelta(days=8), detail="Stale recent data."),
        "ros": Evidence(state="missing", source="Fixture", as_of=NOW,
            detail="Season Evidence is unavailable because persisted NBA observations lack required scoring fields: REB."),
        "status": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Unrecognized status token."),
    }
    rows[2].identity_mapping_state = resolved
    rows[2].schedule.diagnostic_reason = "NO_PLAYER_SCHEDULE_ROWS"
    rows[2].data_quality = {
        "recent": Evidence(state="available", source="Fixture", as_of=NOW, detail="Complete recent data."),
        "ros": Evidence(state="available", source="Fixture", as_of=NOW, detail="Complete season data."),
        "status": Evidence(state="available", source="Fixture", as_of=NOW, detail="Supported Yahoo status."),
    }
    rows[2].raw_yahoo_status = "Q"
    rows[2].yahoo_status = "Q"
    quality = {
        "settings": Evidence(state="available", source="Fixture", as_of=NOW, detail="Settings"),
        "roster": Evidence(state="available", source="Fixture", as_of=NOW, detail="Roster"),
        "acquisition_value": Evidence(state="unknown", source="Fixture", as_of=NOW, detail="Unverified"),
    }
    ctx = Context(SimpleNamespace(), "team", "this_week", NOW,
        {row.player_id: row for row in rows}, [], [], 0, True, WEIGHTS, quality)

    coverage_result, gaps = board_coverage(ctx)
    causes = {(gap.field, gap.root_cause) for gap in gaps}
    assert ("Yahoo ↔ NBA identity mapping", "MISSING_MAPPING") in causes
    assert ("Player schedule rows blocked by identity", "MISSING_MAPPING") in causes
    assert ("Player schedule rows missing", "MISSING_EXISTING_SOURCE_FIELD") in causes
    assert ("Recent production", "REQUIRES_MORE_GAMES") in causes
    assert ("Recent production", "STALE_EXISTING_SOURCE") in causes
    assert ("Season Evidence", "SOURCE_CONTRACT_UNVERIFIED") in causes
    assert ("Season Evidence", "MISSING_EXISTING_SOURCE_FIELD") in causes
    assert ("Game-level usage", "SOURCE_CONTRACT_UNVERIFIED") in causes
    assert not any(gap.field == "Yahoo player status" for gap in gaps)
    assert coverage_result.pool.status.yahoo_blank.count == 1
    assert coverage_result.pool.schedule.unknown.count == 3
    assert all(row.schedule.coverage != "COMPLETE" for row in rows)


@pytest.mark.parametrize("field", ["settings", "roster", "recent", "availability", "status"])
def test_stale_critical_evidence_blocks_add(field):
    ctx, drop, add = decision_context()
    target = ctx.quality if field in {"settings", "roster"} else add.data_quality
    target[field] = Evidence(state="stale", source="Fixture", as_of=NOW - timedelta(days=8), detail="Stale")
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


@pytest.mark.parametrize("field", ["schedule", "opportunity"])
def test_stream_requires_schedule_and_opportunity_evidence(field):
    ctx, drop, add = decision_context()
    add.hold_type = "streamer"
    add.opportunity.minutes_trend = 2
    add.schedule.games_remaining = 3
    assert enrich(ctx, add, drop.player_id).recommended_action == "STREAM"
    add.data_quality[field].state = "missing"
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


@pytest.mark.parametrize("side", ["add", "drop"])
@pytest.mark.parametrize("state", ["unavailable", "partial", "stale"])
def test_missing_partial_or_stale_role_blocks_stream_and_opportunity_led_add(side, state):
    ctx, drop, add = decision_context()
    row = add if side == "add" else drop
    row.opportunity.current_role.quality.state = state
    add.hold_type = "streamer"
    add.schedule.games_remaining = 4
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    add.hold_type = "undetermined"
    ctx.mode = "ros"
    add.components.player_value = drop.components.player_value
    add.components.opportunity = 100
    drop.components.opportunity = 10
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"
    row.opportunity.current_role.quality.state = "available"
    assert enrich(ctx, add, drop.player_id).recommended_action == "ADD"
    row.opportunity.current_role.quality.as_of = NOW-timedelta(days=8)
    assert enrich(ctx, add, drop.player_id).recommended_action == "INSUFFICIENT EVIDENCE"


def test_phase3_evidence_consistent_and_bulk_derived_before_pair_expansion(persisted, monkeypatch):
    import app.features.waivers.service as service
    calls, sql = [], []
    original = service.current_role
    def derive(*args):
        logs, season_stats = args[:2]
        calls.append(logs[0].nba_player_id if logs else season_stats.nba_player_id if season_stats else None)
        return original(*args)
    def statement(*args):
        sql.append(args[2])
        assert args[2].lstrip().upper().startswith("SELECT")
    monkeypatch.setattr(service, "current_role", derive)
    event.listen(engine.sync_engine, "before_cursor_execute", statement)
    try:
        selected = board(persisted, drop_player_id=persisted.ids["weak"])
        board_calls, board_queries = len(calls), len(sql)
        assert board_calls == len(set(calls))
        assert board_calls >= len(selected["roster"]) + len(selected["candidates"])
        calls.clear()
        sql.clear()
        response = persisted.client.get("/api/v1/waivers/transactions")
        assert response.status_code == 200
        transactions = response.json()
        assert transactions["evaluated_pair_count"] > len(calls)
        assert len(calls) == board_calls
        assert len(sql) == board_queries
        for swap in transactions["watch_transactions"] + transactions["top_supported_transactions"]:
            add, drop = swap["add_player"], swap["drop_player"]
            replacements = persisted.client.get("/api/v1/waivers/replacements", params={"drop_player_id": drop["player_id"]}).json()
            replacement = next(row for row in replacements["candidates"] if row["player_id"] == add["player_id"])
            impact = persisted.client.get(f"/api/v1/waivers/{add['player_id']}/impact", params={"drop_player_id": drop["player_id"]}).json()
            assert swap["comparison"] == replacement["comparison"] == impact["comparison"]
            assert add["opportunity"] == replacement["opportunity"] == impact["candidate"]["opportunity"]
        for row in selected["candidates"] + selected["roster"]:
            for key in ("role", "minutes", "usage", "starts", "status", "schedule"):
                quality = row["data_quality"][key]
                assert quality["state"] in {"available", "partial", "unknown", "unavailable", "stale"}
                assert quality["source"] and quality["detail"]
                assert quality["sample_count"] is not None
            assert row["components"]["opportunity"] is None
            assert row["opportunity"]["score"] is None
            assert row["opportunity"]["current_role"]["trend"] == "INSUFFICIENT EVIDENCE"
        q, p = (next(row for row in selected["candidates"] if row["player_name"] == name) for name in ("center", "star"))
        assert q["data_quality"]["status"]["state"] == p["data_quality"]["status"]["state"] == "partial"
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", statement)


def test_phase3_schedule_counts_partial_coverage_and_absent_rows_not_zero(persisted):
    result = board(persisted, mode="next_7_days")
    center = next(row for row in result["candidates"] if row["player_name"] == "center")
    schedule = center["schedule"]
    assert schedule["games_remaining"] == schedule["off_day_games"] == 2
    assert schedule["back_to_backs"] == 1
    assert len(schedule["opponents"]) == 2
    assert schedule["coverage"] == "PARTIAL" and schedule["imported_at"]
    assert "difficulty" not in center["components"]
    unknown = next(row for row in result["candidates"] if row["player_name"] == "unmapped")
    assert unknown["mapping_diagnostic"] == "NBA_ID_UNMAPPED"
    assert unknown["schedule"]["coverage"] == "UNKNOWN"
    assert unknown["schedule"]["diagnostic_reason"] == "NBA_ID_UNMAPPED"
    assert unknown["schedule"]["games_remaining"] is None
    async def remove_future_rows():
        async with SessionFactory() as session, session.begin():
            await session.execute(delete(NbaGame).where(NbaGame.game_id.in_(
                select(NbaGame.game_id).where(NbaGame.game_id.like(persisted.league.split(".")[-1] + "g%")))))
        await engine.dispose()
    asyncio.run(remove_future_rows())
    missing = board(persisted, mode="next_7_days")
    for row in missing["candidates"]:
        assert row["schedule"]["games_remaining"] is None
        assert row["schedule"]["off_day_games"] is None
        assert row["schedule"]["back_to_backs"] is None
        assert row["schedule"]["coverage"] == "UNKNOWN"
        assert row["schedule"]["imported_at"] is None
        assert row["data_quality"]["schedule"]["state"] == "unavailable"


def test_schedule_resolution_distinguishes_mapping_rows_freshness_and_windows():
    from types import SimpleNamespace

    today = date(2026, 10, 26)
    now = datetime(2026, 10, 26, 12, tzinfo=timezone.utc)
    daily = Counter({today: 6, today + timedelta(days=1): 5, today + timedelta(days=2): 4})

    def row(day, opponent="B", imported_at=now, status="Scheduled"):
        return SimpleNamespace(
            game_date=day, opponent_team_id=opponent, imported_at=imported_at,
            game_status=status, game_id=f"{opponent}-{day}",
        )

    upcoming = [row(today), row(today + timedelta(days=1)), row(today + timedelta(days=2))]
    mapped = resolve_schedule(upcoming, today, today + timedelta(days=2), now, daily,
        {"B": "BOS"}, nba_mapped=True, team_mapped=True)
    assert mapped.diagnostic_reason == "SCHEDULE_ROWS_PRESENT"
    assert mapped.coverage == "PARTIAL" and mapped.freshness == "fresh"
    assert mapped.games_remaining == mapped.next_7_days_games == 3
    assert mapped.source_row_count == 3
    assert mapped.off_day_games == 2
    assert mapped.back_to_backs == 2
    assert mapped.opponents == ["BOS", "BOS", "BOS"]

    no_games = resolve_schedule([row(today + timedelta(days=10))], today, today + timedelta(days=2),
        now, daily, {"B": "BOS"}, nba_mapped=True, team_mapped=True)
    assert no_games.diagnostic_reason == "SCHEDULE_SOURCE_INCOMPLETE"
    assert no_games.coverage == "UNKNOWN" and no_games.games_remaining is None
    assert no_games.source_row_count == 1

    unmapped = resolve_schedule([], today, today + timedelta(days=2), now, daily, {},
        nba_mapped=False, team_mapped=False)
    assert unmapped.diagnostic_reason == "NBA_ID_UNMAPPED"
    assert unmapped.coverage == "UNKNOWN" and unmapped.games_remaining is None

    missing_team = resolve_schedule(upcoming, today, today + timedelta(days=2), now, daily,
        {"B": "BOS"}, nba_mapped=True, team_mapped=False)
    assert missing_team.diagnostic_reason == "TEAM_MAPPING_MISSING"
    assert missing_team.coverage == "PARTIAL" and missing_team.games_remaining == 3

    stale = resolve_schedule([row(today, imported_at=now - timedelta(days=8))],
        today, today + timedelta(days=2), now, daily, {"B": "BOS"},
        nba_mapped=True, team_mapped=True)
    assert stale.diagnostic_reason == "SCHEDULE_STALE"
    assert stale.coverage == "STALE" and stale.games_remaining is None

    no_rows = resolve_schedule([], today, today + timedelta(days=2), now, daily, {},
        nba_mapped=True, team_mapped=True)
    assert no_rows.diagnostic_reason == "NO_PLAYER_SCHEDULE_ROWS"
    assert no_rows.coverage == "UNKNOWN" and no_rows.games_remaining is None


@pytest.mark.parametrize(("changes", "expected"), [
    ({"yahoo_id": None}, "YAHOO_ID_MISSING"),
    ({"nba_id": None}, "NBA_ID_UNMAPPED"),
    ({"nba_player_present": False}, "NBA_PLAYER_MISSING"),
    ({"team_mapped": False}, "TEAM_MAPPING_MISSING"),
    ({"has_game_logs": False}, "GAME_LOGS_MISSING"),
    ({"has_season_stats": False}, "SEASON_STATS_MISSING"),
    ({"has_schedule_rows": False}, "SCHEDULE_ROWS_MISSING"),
    ({"schedule_stale": True}, "SCHEDULE_STALE"),
    ({}, "COMPLETE_MAPPING"),
])
def test_identity_chain_returns_first_broken_mapping_state(changes, expected):
    values = dict(yahoo_id="y1", nba_id="n1", nba_player_present=True, team_mapped=True,
        has_game_logs=True, has_season_stats=True, has_schedule_rows=True, schedule_stale=False)
    assert identity_chain_diagnostic(**(values | changes)) == expected


def test_read_endpoints_have_no_writes_or_acquisition_scoring(persisted):
    statements = []
    def record_statement(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
        assert statement.lstrip().upper().startswith("SELECT"), statement
    event.listen(engine.sync_engine, "before_cursor_execute", record_statement)
    try:
        result = board(persisted, drop_player_id=persisted.ids["guard"])
        for row in result["candidates"]:
            assert row["components"]["acquisition_value"] is None
            assert "acquisition_value" not in row["effective_weights"]
            assert not any("faab" in key.lower() for key in row)
            assert "faab" not in row["data_quality"]
        assert statements
        assert result["best_add_for_team_id"] is None
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", record_statement)


def test_negative_selected_drop_set_holds_and_never_names_least_negative_best_add(monkeypatch):
    from app.features.waivers.service import get_waivers
    ctx, drop, add = decision_context()
    ctx.league.league_key = "fixture"
    add.components.player_value = 1
    drop.eligible = False
    drop.availability = "rostered"
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, ctx.mode, drop.player_id))
    assert result.selected_player_result == "HOLD Player 1"
    assert result.top_measured_candidate_id == add.player_id
    assert result.best_add_for_team_id is None
    assert result.candidates[0].recommended_action == "PASS"
    assert result.candidates[0].net_improvement < 0


def explicit_drop_variant(template, pid, value, games=None, **updates):
    """An add sharing `template`'s fresh evidence with its own player value (and optionally a smaller sample)."""
    row = template.model_copy(deep=True, update={"player_id": pid, "player_name": f"Player {pid}",
        "yahoo_player_id": str(pid), **updates})
    row.components.player_value = value
    if games is not None:
        row.current_season_games = row.recent.games = games
    row.overall_score, row.effective_weights = aggregate(row.components, WEIGHTS)
    return row


def test_explicit_drop_replacements_rank_supported_before_watch_even_when_watch_nets_more(monkeypatch):
    # Real-data regression (2026-11-14): for an explicitly selected drop, WATCH DeMar DeRozan (+0.847) was listed above
    # the supported Jerami Grant (+0.728) because the list ranked net improvement alone.
    from app.features.waivers.service import get_waivers
    ctx, drop, add, analyze = optimizer_context()
    tied = explicit_drop_variant(add, 5, 90)  # same evidence as the add: equal net, so the lower player ID ranks first
    lower = explicit_drop_variant(add, 7, 70)
    watch = explicit_drop_variant(add, 3, 99, games=2)
    smaller_watch = explicit_drop_variant(add, 8, 95, games=2)
    nonpositive = explicit_drop_variant(add, 4, 10)
    unverified = explicit_drop_variant(add, 6, 98, yahoo_status="D")
    for row in (tied, lower, watch, smaller_watch, nonpositive, unverified):
        ctx.players[row.player_id] = row
    attach_capacity(ctx)
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, ctx.mode, drop.player_id))
    rows = {row.player_id: row for row in result.candidates}
    # Supported (net then ID), WATCH, supported nonpositive HOLD, then insufficient evidence; decisions are untouched.
    assert [(row.player_id, row.recommended_action, row.recommended_action_type) for row in result.candidates] == [
        (2, "ADD", "ADD_DROP"), (5, "ADD", "ADD_DROP"), (7, "ADD", "ADD_DROP"), (3, "WATCH", "WATCH"),
        (8, "WATCH", "WATCH"), (4, "PASS", "HOLD"), (6, "INSUFFICIENT EVIDENCE", "INSUFFICIENT_EVIDENCE")]
    assert rows[3].net_improvement > rows[8].net_improvement > rows[2].net_improvement == rows[5].net_improvement
    assert rows[6].net_improvement > rows[2].net_improvement > rows[7].net_improvement > 0 > rows[4].net_improvement
    # The selected drop is fixed and every comparison is the exact-pair math.
    assert result.selected_drop_player_id == drop.player_id
    for row in result.candidates:
        assert row.comparison == compare(ctx, ctx.players[row.player_id], drop.player_id)
        assert [option.player_id for option in row.best_drop_options] == [drop.player_id]
    # The list's first card is the supported winner, which is the global optimizer's and the board's best pair.
    best = analyze(ctx).best_transaction
    board = asyncio.run(get_waivers(None, "fixture", ctx.team_key, ctx.mode, None))
    assert result.best_add_for_team_id == result.candidates[0].player_id == best.add_player.player_id == 2
    assert (board.best_add_for_team_id, board.best_drop_for_team_id) == (2, drop.player_id)
    assert result.candidates[0].comparison == best.comparison == enrich(ctx, ctx.players[2], drop.player_id).comparison
    assert result.top_measured_candidate_id == 3 and result.selected_player_result == "ADD"


def test_explicit_drop_list_keeps_the_top_measured_watch_when_supported_moves_fill_it(monkeypatch):
    from app.features.waivers.service import BOARD_CANDIDATE_LIMIT, get_waivers
    ctx, drop, add, _ = optimizer_context()
    for pid in range(10, 10 + BOARD_CANDIDATE_LIMIT):
        ctx.players[pid] = explicit_drop_variant(add, pid, 80)
    ctx.players[99] = explicit_drop_variant(add, 99, 99, games=2)
    attach_capacity(ctx)
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, ctx.mode, drop.player_id))
    shown = result.candidates[:BOARD_CANDIDATE_LIMIT]
    assert all(row.recommended_action_type == "ADD_DROP" for row in shown)
    # The page names the top measured option from the list, so the out-of-window WATCH is appended last, still WATCH.
    assert result.top_measured_candidate_id == 99
    assert [(row.player_id, row.recommended_action) for row in result.candidates[BOARD_CANDIDATE_LIMIT:]] == [(99, "WATCH")]


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
def test_two_game_candidate_cannot_be_board_best_add(monkeypatch, mode):
    from app.features.waivers.service import get_waivers
    ctx, drop, add = decision_context(2)
    ctx.mode = mode
    ctx.league.league_key = "fixture"
    drop.eligible = False
    drop.availability = "rostered"
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    result = asyncio.run(get_waivers(None, "fixture", ctx.team_key, mode, drop.player_id))
    assert result.best_add_for_team_id is None
    assert result.selected_player_result == "WATCH"
    assert result.candidates[0].recommended_action == "WATCH"


def optimizer_context(games=7):
    from app.features.waivers.service import analyze_transactions
    ctx, drop, add = decision_context(games)
    ctx.league.league_key = "fixture"
    drop.availability = "rostered"
    drop.eligible = False
    attach_capacity(ctx)
    return ctx, drop, add, analyze_transactions


def test_optimizer_multiple_adds_drops_deterministic_global_fit_and_same_math():
    ctx, drop, add, analyze = optimizer_context()
    strong = drop.model_copy(deep=True, update={"player_id": 3, "player_name": "Strong guard", "position": "PG"})
    strong.components.player_value = 95
    drop.position = "PG"
    add.position = "C"
    overall = add.model_copy(deep=True, update={"player_id": 4, "player_name": "Best overall guard", "position": "PG"})
    overall.components.player_value = 99
    ctx.players.update({3: strong, 4: overall})
    ctx.roster_ids = [1, 3]
    ctx.slots = ["PG", "C"]
    attach_capacity(ctx)
    result = analyze(ctx)
    assert result.evaluated_pair_count == 4
    best = result.best_transaction
    assert best is not None
    assert best.add_player.player_id == add.player_id
    assert best.drop_player.player_id == drop.player_id
    assert best.decision == "ADD"
    assert best.comparison == compare(ctx, add, drop.player_id)
    assert best.comparison == enrich(ctx, add, drop.player_id).comparison
    assert best.add_player.comparison == best.comparison
    assert best.add_player.best_drop_options == [best.comparison]
    assert 0 <= best.comparison.component_after.roster_fit <= 100
    assert best.comparison.component_deltas.roster_fit == 50
    ctx.players = dict(reversed(list(ctx.players.items())))
    ctx.roster_ids.reverse()
    assert analyze(ctx) == result


def test_optimizer_all_nonpositive_is_hold_with_supported_pass_pairs():
    ctx, drop, add, analyze = optimizer_context()
    add.components.player_value = 1
    result = analyze(ctx)
    assert result.decision == "HOLD"
    assert result.best_transaction is None
    assert result.supported_pair_count == 1
    assert result.top_supported_transactions[0].decision == "PASS"
    assert result.top_supported_transactions[0].comparison.net_improvement < 0
    assert result.watch_transactions == []


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
@pytest.mark.parametrize("games", [0, 2, 5])
def test_optimizer_history_never_bypasses_current_gate(mode, games):
    ctx, drop, add, analyze = optimizer_context(games)
    ctx.mode = mode
    add.ros.games = drop.ros.games = 82
    add.ranking_value.historical_games = 82
    result = analyze(ctx)
    assert result.best_transaction is None
    assert result.decision == "HOLD"
    assert result.excluded_pair_count == result.evaluated_pair_count == 1
    assert result.supported_pair_count == 0
    if games:
        assert result.watch_pair_count == 1
        assert result.watch_transactions[0].decision == "WATCH"
    else:
        assert result.watch_pair_count == 0


@pytest.mark.parametrize("field", ["settings", "roster", "recent", "availability", "status"])
def test_optimizer_critical_stale_excluded_from_strong_pool(field):
    ctx, drop, add, analyze = optimizer_context()
    target = ctx.quality if field in {"settings", "roster"} else add.data_quality
    target[field] = Evidence(state="stale", source="Fixture", as_of=NOW - timedelta(days=8), detail="Stale")
    result = analyze(ctx)
    assert result.best_transaction is None
    assert result.supported_pair_count == 0
    assert result.excluded_pair_count == 1
    assert result.excluded_pair_reasons


def test_optimizer_mode_changes_best_supported_pair_and_stream_needs_evidence():
    ctx, drop, add, analyze = optimizer_context()
    other = add.model_copy(deep=True, update={"player_id": 3, "player_name": "Other add"})
    other.components.player_value = 80
    other.components.schedule = 100
    add.components.schedule = 1
    for row in (add, other):
        row.schedule.games_remaining = 4
    ctx.players[3] = other
    ctx.weights = {**WEIGHTS, "player_value": .1, "schedule": .7}
    ctx.mode = "next_7_days"
    assert analyze(ctx).best_transaction.add_player.player_id == 3
    assert analyze(ctx).best_transaction.decision == "STREAM"
    other.data_quality["schedule"].state = "missing"
    assert all(row.add_player.player_id != 3 for row in analyze(ctx).top_supported_transactions)
    other.data_quality["schedule"].state = "available"
    other.data_quality["opportunity"].state = "missing"
    assert all(row.add_player.player_id != 3 for row in analyze(ctx).top_supported_transactions)
    ctx.mode = "ros"
    ctx.weights = {**WEIGHTS, "schedule": 0}
    assert analyze(ctx).best_transaction.add_player.player_id == add.player_id
    assert analyze(ctx).best_transaction.decision == "ADD"


@pytest.mark.parametrize("status", ["O", "NA", "Q", "P", None])
def test_optimizer_yahoo_status_contract(status):
    ctx, drop, add, analyze = optimizer_context()
    add.yahoo_status = status
    add.eligible = status not in {"O", "NA"}
    result = analyze(ctx)
    if status in {"Q", "P"}:
        assert result.best_transaction.add_player.yahoo_status == status
        assert result.best_transaction.decision == "ADD"
    else:
        assert result.best_transaction is None
    assert result.acquisition_context.current_priority is None
    assert result.acquisition_context.weekly_adds_used is None
    assert result.acquisition_context.weekly_adds_remaining is None
    assert result.acquisition_context.claim_clear_at is None
    assert all(row.add_player.components.acquisition_value is None for row in result.top_supported_transactions)


def test_optimizer_positive_tie_uses_add_then_drop_id():
    ctx, drop, add, analyze = optimizer_context()
    twin_drop = drop.model_copy(deep=True, update={"player_id": 3})
    twin_add = add.model_copy(deep=True, update={"player_id": 4})
    ctx.players.update({3: twin_drop, 4: twin_add})
    ctx.roster_ids = [3, 1]
    attach_capacity(ctx)
    result = analyze(ctx)
    assert [(row.add_player.player_id, row.drop_player.player_id) for row in result.top_supported_transactions] == [(2, 1), (2, 3), (4, 1), (4, 3)]
    assert result.evaluated_pair_count == 4
    assert result.supported_pair_count + result.excluded_pair_count == 4


def test_transactions_endpoint_loads_once_select_only_and_matches_selected_drop(persisted, monkeypatch):
    import app.features.waivers.service as service
    calls = []
    original = service.load_context
    async def load(*args, **kwargs):
        calls.append(1)
        return await original(*args, **kwargs)
    monkeypatch.setattr(service, "load_context", load)
    statements = []
    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        response = persisted.client.get("/api/v1/waivers/transactions", params={"mode": "next_7_days"})
        assert response.status_code == 200, response.text
        result = response.json()
        assert calls == [1]
        assert result["team_key"] == persisted.team1
        assert result["decision"] == "HOLD"
        assert result["best_transaction"] is None
        assert result["evaluated_pair_count"] > 2
        assert result["supported_pair_count"] + result["excluded_pair_count"] == result["evaluated_pair_count"]
        watch = result["watch_transactions"][0]
        add_id, drop_id = watch["add_player"]["player_id"], watch["drop_player"]["player_id"]
        # The exact-pair explanation travels inside the comparison, so the equalities below cover it on every surface.
        explanation = watch["comparison"]["explanation"]
        assert explanation["contributions"] and explanation["statement"]
        assert next(check for check in explanation["checks"] if check["key"] == "ARITHMETIC")["passed"]
        assert watch["add_player"]["verdict"] == "WATCH_ONLY" and watch["add_player"]["evidence_dimensions"]
        selected = board(persisted, mode="next_7_days", drop_player_id=drop_id)
        pair = next(row for row in selected["candidates"] if row["player_id"] == add_id)
        assert pair["comparison"] == watch["comparison"]
        impact = persisted.client.get(f"/api/v1/waivers/{add_id}/impact",
            params={"mode": "next_7_days", "drop_player_id": drop_id}).json()
        assert impact["comparison"] == watch["comparison"]
        assert len(statements) < 150
        assert persisted.client.get("/api/v1/waivers/transactions", params={"team_key": persisted.team2}).status_code == 422
        assert persisted.client.get("/api/v1/waivers/transactions", params={"mode": "fake"}).status_code == 422
        persisted.no_yahoo.assert_not_called()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)


FRESH = Evidence(state="available", source="Fixture", as_of=NOW, detail="Verified fresh fixture evidence")


def evidence_player(pid, position, value=60, games=7, status="P", rostered=False):
    row = candidate(pid, position, value, schedule=20)
    row.player_name = f"{position.replace(',', '/')} {pid}"
    row.components.opportunity = 20
    row.identity_mapping_state = "EXACT_NAME_TEAM"
    row.current_season_games = row.recent.games = games
    row.evidence_quality = sample_label(games)
    row.yahoo_status = status
    row.opportunity = current_role(role_logs([20, 20, 20, 27, 27, 27]), None, "2026-27", NOW, NOW.date())
    row.data_quality = {key: FRESH.model_copy() for key in
        ("recent", "ros", "status", "availability", "schedule", "opportunity")}
    row.overall_score, row.effective_weights = aggregate(row.components, WEIGHTS)
    if rostered:
        row.availability, row.eligible = "rostered", False
    return row


def roster_ctx(roster, pool, positions, assignments, eligible=None, mode="this_week", roster_state="available"):
    players = {row.player_id: row for row in [*roster, *pool]}
    for row in roster:
        row.availability, row.eligible = "rostered", False
    config, problems = slot_configuration(positions)
    assert not problems
    slots = starting_slot_list(config)
    ctx = Context(SimpleNamespace(league_key="fixture"), "t1", mode, NOW, players,
        [row.player_id for row in roster], slots,
        sum(slot.count for slot in config if slot.kind in {"starting", "bench"}),
        roster_state == "available", WEIGHTS,
        {"settings": FRESH, "roster": FRESH.model_copy(update={"state": roster_state}), "acquisition_value": FRESH})
    entries = [RosterEntryEvidence(
        player_id=row.player_id, player_name=row.player_name, positions=row.position,
        roster_slot=assignments.get(row.player_id),
        eligible_positions=tuple((eligible or {}).get(row.player_id, [*(row.position or "").split(","), "UTIL"])),
        yahoo_status=row.yahoo_status,
        status_state=row.data_quality["status"].state if "status" in row.data_quality else "missing",
    ) for row in roster]
    ctx.roster_capacity = analyze_roster_capacity(
        roster_positions=positions, settings_state="available", roster_state=roster_state,
        roster_as_of=NOW, status_as_of=NOW, entries=entries, today=NOW.date())
    ctx.team_needs = analyze_team_needs(
        capacity=ctx.roster_capacity, players=players, roster_ids=ctx.roster_ids, starting_slots=slots,
        mode=mode, window_start=NOW.date(), window_end=NOW.date() + timedelta(days=6),
        roster_state=roster_state, settings_state="available")
    return ctx


def slots_of(**counts):
    return [{"position": position, "count": count} for position, count in counts.items()]


def two_injured_in_il_context():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "SG", 65, rostered=True),
        evidence_player(3, "SF", 55, rostered=True),
        evidence_player(4, "C", 80, status="O", rostered=True), evidence_player(5, "PF,C", 75, status="O", rostered=True)]
    for injured in roster[3:]:
        # Out for weeks: no supported recent production must not block no-drop measurement.
        injured.components.player_value = None
    pool = [evidence_player(11, "C", 80), evidence_player(12, "PG", 90), evidence_player(13, "C", 60)]
    ctx = roster_ctx(roster, pool, slots_of(PG=1, SG=1, C=1, UTIL=1, BN=1, IL=2),
        {1: "PG", 2: "SG", 3: "BN", 4: "IL", 5: "IL"},
        eligible={4: ["C", "UTIL", "IL"], 5: ["PF", "C", "UTIL", "IL"]})
    return ctx


def test_two_injured_in_il_with_two_open_spots_are_two_ranked_no_drop_additions():
    ctx = two_injured_in_il_context()
    capacity = ctx.roster_capacity
    assert capacity.state == "available" and capacity.transaction_shape == "ADD_ONLY"
    assert (capacity.non_injury_capacity, capacity.occupied_roster_spots, capacity.open_roster_spots) == (5, 3, 2)
    assert capacity.no_drop_additions_available == 2 and capacity.requires_drop is False
    assert capacity.open_active_slots == ["C", "UTIL"]
    assert capacity.injured_players_in_injury_slots == [4, 5]
    assert capacity.injured_players_outside_injury_slots == []
    assert capacity.transaction_legality_quality.state == "partial"
    assert "Yahoo confirmation" in capacity.transaction_legality_quality.detail
    needs = ctx.team_needs
    assert needs.open_starting_slots == ["C"] and needs.weakened_positions == ["C"]
    assert needs.needs[0].slot == "C" and needs.needs[0].kind == "INJURY_WEAKENED"
    assert any(need.kind == "BENCH_DEPTH" for need in needs.needs)
    analysis = analyze_transactions(ctx)
    assert analysis.evaluated_pair_count == 0 and analysis.best_transaction is None
    assert analysis.recommended_action_type == "ADD_ONLY" and analysis.decision == "ADD"
    assert [fill.add_player.player_id for fill in analysis.add_only_recommendations] == [11, 12]
    assert [fill.target_roster_position for fill in analysis.add_only_recommendations] == ["C", "BN"]
    for fill in analysis.add_only_recommendations:
        assert fill.action_type == "ADD_ONLY" and fill.requires_drop is False
        assert fill.comparison.player_id is None and fill.comparison.comparison_type == "ADD_ONLY"
        assert fill.comparison.net_improvement > 0
        assert fill.add_player.best_drop_options == [] and fill.add_player.requires_drop is False
        assert "No player needs to be dropped" in fill.label
    assert analysis.best_addition == analysis.add_only_recommendations[0]
    assert "cover C" in analysis.action_label


def test_injured_player_in_active_slot_moves_to_open_il_then_add_without_drop():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 85, status="O", rostered=True),
        evidence_player(3, "SF", 50, rostered=True)]
    roster[1].components.player_value = None
    ctx = roster_ctx(roster, [evidence_player(11, "C", 75), evidence_player(12, "PG", 80)],
        slots_of(PG=1, C=1, BN=1, IL=1), {1: "PG", 2: "C", 3: "BN"}, eligible={2: ["C", "UTIL", "IL"]})
    capacity = ctx.roster_capacity
    assert capacity.transaction_shape == "MOVE_TO_IL_THEN_ADD"
    assert capacity.open_roster_spots == 0 and capacity.open_injury_slots == 1
    assert capacity.requires_drop is False and capacity.requires_roster_move is True
    move = capacity.move_to_injury_slot_options[0]
    assert (move.player_id, move.from_slot, move.to_slot, move.released_slot, move.certainty) == (2, "C", "IL", "C", "conditional")
    analysis = analyze_transactions(ctx)
    fill = analysis.best_addition
    assert analysis.recommended_action_type == "MOVE_TO_IL_THEN_ADD" and analysis.evaluated_pair_count == 0
    assert fill.add_player.player_id == 11 and fill.target_roster_position == "C"
    assert fill.suggested_injury_move == move and fill.requires_drop is False
    assert fill.label.startswith("MOVE C 2 TO IL, THEN ADD C 11") and "stays on your roster" in fill.label
    assert fill.comparison.comparison_type == "MOVE_TO_IL_THEN_ADD"
    assert fill.comparison.player_id is None and fill.comparison.moved_to_injury_slot_player_id == 2
    assert fill.comparison.net_improvement > 0
    assert fill.add_player.best_drop_options == []
    assert 2 in ctx.roster_ids
    detail = enrich(ctx, ctx.players[11])
    assert detail.recommended_action_type == "MOVE_TO_IL_THEN_ADD" and detail.requires_injury_slot_move
    assert detail.comparison == fill.comparison


@pytest.mark.parametrize("case", ["not_il_eligible", "il_full", "questionable"])
def test_injured_player_without_a_legal_il_slot_gets_no_move_and_an_explained_blocker(case):
    roster = [evidence_player(1, "PG", 70, rostered=True),
        evidence_player(2, "C", 85, status="Q" if case == "questionable" else "O", rostered=True),
        evidence_player(3, "SF", 50, rostered=True)]
    positions = slots_of(PG=1, C=1, BN=1, IL=1)
    assignments = {1: "PG", 2: "C", 3: "BN"}
    eligible = {2: ["C", "UTIL"] if case != "il_full" else ["C", "UTIL", "IL"]}
    if case == "il_full":
        roster.append(evidence_player(4, "PF", 40, status="O", rostered=True))
        assignments[4] = "IL"
        eligible[4] = ["PF", "UTIL", "IL"]
    ctx = roster_ctx(roster, [evidence_player(11, "C", 75)], positions, assignments, eligible=eligible)
    capacity = ctx.roster_capacity
    assert capacity.move_to_injury_slot_options == []
    assert capacity.transaction_shape == "ADD_DROP" and capacity.requires_drop is True
    if case == "questionable":
        assert capacity.injured_players == [] and capacity.injury_move_blockers == []
        assert 2 in ctx.team_needs.uncertain_status_player_ids
    else:
        blocker = capacity.injury_move_blockers[0]
        assert blocker.player_id == 2
        assert ("does not include an injury slot" if case == "not_il_eligible" else "no eligible injury slot is open") in blocker.reason
        assert blocker.reason in capacity.drop_requirement_reason


def test_full_roster_without_legal_il_move_uses_exact_add_drop_optimizer():
    roster = [evidence_player(1, "PG", 60, rostered=True), evidence_player(2, "C", 10, rostered=True)]
    add = evidence_player(11, "C", 90)
    ctx = roster_ctx(roster, [add], slots_of(PG=1, C=1), {1: "PG", 2: "C"})
    assert ctx.roster_capacity.transaction_shape == "ADD_DROP"
    analysis = analyze_transactions(ctx)
    best = analysis.best_transaction
    assert analysis.evaluated_pair_count == 2 and analysis.recommended_action_type == "ADD_DROP"
    assert analysis.best_addition is None and analysis.add_only_recommendations == []
    assert (best.add_player.player_id, best.drop_player.player_id, best.decision) == (11, 2, "ADD")
    assert best.comparison == compare(ctx, add, 2) == enrich(ctx, add, 2).comparison
    assert best.comparison.target_roster_position == "C"
    # Dropping the PG uncovers PG; a C-only add cannot inherit that slot, so no position is claimed.
    assert compare(ctx, add, 1).target_roster_position is None
    assert best.add_player.recommended_action_type == "ADD_DROP" and best.add_player.requires_drop is True
    assert analysis.action_label == "ADD C 11 + DROP C 2: Your roster is full."
    generic = enrich(ctx, add)
    assert generic.best_drop_options and generic.comparison.player_id == 2


def full_roster_with_sample_blocked_best_drop():
    """Full roster (ADD + DROP). The add's highest-net drop, the weakest roster player, has a VERY LOW recent
    sample, so that pair is only WATCH; a lower-net drop is fully supported (the 2026-11-14 Next 7 Days case)."""
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 30, rostered=True),
        evidence_player(3, "C", 10, games=3, rostered=True)]
    ctx = support_ctx(roster_ctx(roster, [evidence_player(11, "C", 90)], slots_of(PG=1, C=1, BN=1), {1: "PG", 2: "C", 3: "BN"}))
    ctx.league = SimpleNamespace(league_key="fixture", settings=None)
    return ctx


def test_board_supported_pair_is_the_optimizer_best_transaction_not_the_highest_net_unsupported_drop():
    from app.features.waivers.service import build_board
    ctx = full_roster_with_sample_blocked_best_drop()
    add = ctx.players[11]
    assert ctx.roster_capacity.transaction_shape == "ADD_DROP"
    watch, supported = enrich(ctx, add, 3), enrich(ctx, add, 2)
    assert watch.comparison.net_improvement > supported.comparison.net_improvement > 0
    assert (watch.recommended_action, supported.recommended_action) == ("WATCH", "ADD")
    best = analyze_transactions(ctx).best_transaction
    assert (best.add_player.player_id, best.drop_player.player_id, best.decision) == (11, 2, "ADD")
    board = build_board(ctx, "fixture", "t1", ctx.mode, None)
    assert (board.best_add_for_team_id, board.best_drop_for_team_id, board.recommended_action_type) == (11, 2, "ADD_DROP")
    row = next(row for row in board.candidates if row.player_id == 11)
    assert (row.recommended_action, row.recommended_action_type, row.comparison) == ("ADD", "ADD_DROP", best.comparison)
    assert row.best_drop_options[0].player_id == 2, "the supported drop leads; higher-net unsupported drops follow"
    support = board.decision_support
    assert (support.state, support.supported_count, support.best_measured_ids) == ("SUPPORTED_ACTION", 1, [])
    assert options_by_id(support)[11].classification == "SUPPORTED_ACTION"
    assert support.headline == "1 supported move available."
    # Impact without a drop and replacements for that drop show the same pair and decision.
    assert enrich(ctx, add).comparison == best.comparison
    selected = build_board(ctx, "fixture", "t1", ctx.mode, 2)
    pick = next(row for row in selected.candidates if row.player_id == 11)
    assert (pick.comparison, pick.recommended_action, selected.best_add_for_team_id) == (best.comparison, "ADD", 11)
    # Without any supported pair the add keeps its highest-net measured comparison (unchanged behavior).
    ctx.players[2].current_season_games = ctx.players[2].recent.games = 3
    assert enrich(ctx, add).comparison.player_id == 3 and analyze_transactions(ctx).best_transaction is None
    held = build_board(ctx, "fixture", "t1", ctx.mode, None)
    assert (held.best_add_for_team_id, held.best_drop_for_team_id) == (None, None)


def one_open_spot_context(watch_games=2):
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "PG", 60, rostered=True)]
    pool = [evidence_player(11, "C", 60), evidence_player(12, "PG", 95), evidence_player(13, "C", 99, games=watch_games)]
    return roster_ctx(roster, pool, slots_of(PG=1, C=1, BN=1), {1: "PG", 2: "BN"})


def test_one_open_spot_selects_add_only_by_need_and_evidence_with_before_after_impact():
    ctx = one_open_spot_context()
    assert ctx.roster_capacity.open_active_slots == ["C"]
    analysis = analyze_transactions(ctx)
    fill = analysis.best_addition
    assert fill.add_player.player_id == 11
    comparison = fill.comparison
    assert comparison.comparison_type == "ADD_ONLY" and comparison.target_roster_position == "C"
    assert (comparison.open_roster_spots_before, comparison.open_roster_spots_after, comparison.roster_spots_basis) == (1, 0, 3)
    assert (comparison.starting_slots_before, comparison.starting_slots_after) == (1, 2)
    assert comparison.component_before.player_value == pytest.approx((70 + 60) / 3)
    assert comparison.component_after.player_value == pytest.approx((70 + 60 + 60) / 3)
    assert (comparison.component_before.roster_fit, comparison.component_after.roster_fit) == (50, 100)
    assert comparison.net_improvement == pytest.approx(comparison.after_score - comparison.before_score, abs=1e-6)
    assert [row.add_player.player_id for row in analysis.watch_additions] == [13]
    assert 13 not in {row.add_player.player_id for row in analysis.add_only_recommendations}
    enriched = [enrich(ctx, ctx.players[pid]) for pid in (11, 12, 13)]
    groups = option_groups(ctx, enriched)
    assert groups.by_need[0].slot == "C" and groups.by_need[0].candidate_id == 11
    assert groups.watch_candidate_ids == [13]


def test_open_spot_hold_counts_player_specific_gate_notes_under_one_reason():
    # Gate notes name each player (2026-11-14); the no-drop HOLD summary must still count them as one reason.
    ctx = one_open_spot_context()
    for pid in (11, 12, 13):
        ctx.players[pid].current_season_games = ctx.players[pid].recent.games = 3
    gated = sum(any(note.startswith("Sample gate: ") for note in enrich(ctx, ctx.players[pid]).evidence_blockers)
        for pid in (11, 12, 13))
    assert gated >= 2
    analysis = analyze_transactions(ctx)
    assert analysis.best_addition is None and analysis.decision == "HOLD"
    assert [reason for reason in analysis.decision_reasons if reason.startswith("Sample gate")] == [
        "Sample gate: recent sample below the supported tier (under 7 games in the last 14 days or this season, and "
        f"not corroborated) ({gated} players)."], analysis.decision_reasons


def test_multiple_open_needs_are_filled_in_order_without_stacking_one_need():
    roster = [evidence_player(1, "SF", 60, rostered=True), evidence_player(2, "SF", 55, rostered=True)]
    pool = [evidence_player(11, "C", 90), evidence_player(12, "C", 85), evidence_player(13, "PG", 70)]
    ctx = roster_ctx(roster, pool, slots_of(PG=1, SF=1, C=1, BN=1), {1: "SF", 2: "BN"})
    assert ctx.team_needs.open_starting_slots == ["PG", "C"]
    assert [need.slot for need in ctx.team_needs.needs[:2]] == ["PG", "C"]
    analysis = analyze_transactions(ctx)
    assert [(fill.add_player.player_id, fill.target_roster_position) for fill in analysis.add_only_recommendations] == [(11, "C"), (13, "PG")]
    pool[2].current_season_games = pool[2].recent.games = 2
    blocked = analyze_transactions(ctx)
    assert [fill.add_player.player_id for fill in blocked.add_only_recommendations] == [11]
    assert blocked.unfilled_needs == ["PG"]
    assert any("covers PG" in reason for reason in blocked.decision_reasons)


def test_multi_position_player_covers_more_than_one_open_need():
    roster = [evidence_player(1, "C", 60, rostered=True), evidence_player(2, "SF", 50, rostered=True)]
    pool = [evidence_player(11, "PG,SG", 70), evidence_player(12, "PG", 80), evidence_player(13, "SG", 75)]
    ctx = roster_ctx(roster, pool, slots_of(PG=1, SG=1, C=1, BN=1), {1: "C", 2: "BN"})
    flexible = enrich(ctx, pool[0])
    assert flexible.fills_needs == ["PG", "SG"]
    assert enrich(ctx, pool[1]).fills_needs == ["PG"]
    groups = option_groups(ctx, [enrich(ctx, row) for row in pool])
    assert groups.flexible_candidate_id == 11
    assert {option.slot for option in groups.by_need} == {"PG", "SG"}


@pytest.mark.parametrize(("status", "state", "expected"), [
    ("O", "available", "INSUFFICIENT_EVIDENCE"), ("NA", "available", "INSUFFICIENT_EVIDENCE"),
    ("Q", "partial", "ADD_ONLY"), ("P", "partial", "ADD_ONLY"),
    (None, "unknown", "INSUFFICIENT_EVIDENCE"), ("HEALTHY", "unknown", "INSUFFICIENT_EVIDENCE"),
    ("P", "stale", "INSUFFICIENT_EVIDENCE"), ("P", None, "INSUFFICIENT_EVIDENCE"),
])
def test_add_only_preserves_fail_closed_yahoo_status_semantics(status, state, expected):
    ctx = one_open_spot_context(watch_games=7)
    add = ctx.players[11]
    add.yahoo_status = status
    add.eligible = status not in {"O", "NA"}
    if state is None:
        del add.data_quality["status"]
    else:
        add.data_quality["status"] = FRESH.model_copy(update={"state": state})
    result = enrich(ctx, add)
    assert result.recommended_action_type == expected
    assert result.requires_drop is False and result.best_drop_options == []
    if expected != "ADD_ONLY":
        assert result.recommended_action == "INSUFFICIENT EVIDENCE"
        assert 11 not in {fill.add_player.player_id for fill in analyze_transactions(ctx).add_only_recommendations}


def test_roster_statuses_drive_lineup_eligibility_without_inventing_health():
    roster = [evidence_player(1, "PG", 70, status="O", rostered=True), evidence_player(2, "C", 60, status="Q", rostered=True),
        evidence_player(3, "SF", 50, status=None, rostered=True)]
    roster[2].data_quality["status"] = FRESH.model_copy(update={"state": "unknown"})
    ctx = roster_ctx(roster, [], slots_of(PG=1, C=1, SF=1), {1: "PG", 2: "C", 3: "SF"}, eligible={1: ["PG", "UTIL"]})
    assignment = {row.player_id: row for row in ctx.roster_capacity.assignments}
    assert assignment[1].injured and not assignment[1].lineup_eligible
    assert assignment[2].lineup_eligible and assignment[3].lineup_eligible
    assert ctx.team_needs.open_starting_slots == ["PG"]
    assert ctx.team_needs.uncertain_status_player_ids == [2]
    assert ctx.team_needs.unknown_status_player_ids == [3]


@pytest.mark.parametrize("case", ["missing_assignment", "stale_roster", "overfilled", "healthy_in_il"])
def test_stale_missing_or_conflicting_roster_slots_never_create_a_false_open_spot(case):
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 60, rostered=True)]
    positions = slots_of(PG=1, C=1, BN=1, IL=1)
    assignments = {1: "PG", 2: "C"}
    eligible = None
    if case == "missing_assignment":
        assignments = {1: "PG"}
    elif case == "overfilled":
        assignments = {1: "PG", 2: "PG"}
    elif case == "healthy_in_il":
        assignments = {1: "PG", 2: "IL"}
        eligible = {2: ["C", "UTIL"]}
    ctx = roster_ctx(roster, [evidence_player(11, "C", 90)], positions, assignments, eligible=eligible,
        roster_state="stale" if case == "stale_roster" else "available")
    capacity = ctx.roster_capacity
    assert capacity.transaction_shape == "UNDETERMINED"
    assert capacity.state == {"missing_assignment": "missing", "stale_roster": "stale",
        "overfilled": "conflicting", "healthy_in_il": "conflicting"}[case]
    assert capacity.no_drop_additions_available is None and capacity.requires_drop is None
    assert capacity.move_to_injury_slot_options == []
    if case == "missing_assignment":
        assert capacity.open_roster_spots is None
        assert "selected_position" in capacity.blockers[0]
    result = enrich(ctx, ctx.players[11])
    assert result.recommended_action_type == "INSUFFICIENT_EVIDENCE"
    assert result.comparison is None and result.best_drop_options == []
    assert any("Roster capacity is undetermined" in blocker for blocker in result.evidence_blockers)
    analysis = analyze_transactions(ctx)
    assert analysis.decision == "INSUFFICIENT EVIDENCE" and analysis.recommended_action_type == "INSUFFICIENT_EVIDENCE"
    assert analysis.evaluated_pair_count == 0 and analysis.best_transaction is None and analysis.best_addition is None
    assert analysis.decision_reasons == capacity.blockers[:4]


def test_low_sample_positive_no_drop_addition_stays_watch_and_open_spot_holds():
    ctx = one_open_spot_context()
    for pid in (11, 12):
        del ctx.players[pid]
    watch = enrich(ctx, ctx.players[13])
    assert watch.recommended_action == "WATCH" and watch.recommended_action_type == "WATCH"
    assert watch.net_improvement > 0 and watch.comparison.player_id is None
    assert watch.action_label.startswith("WATCH: The measured fit is positive")
    analysis = analyze_transactions(ctx)
    assert analysis.best_addition is None and analysis.decision == "HOLD"
    assert analysis.recommended_action_type == "HOLD" and analysis.action_label.startswith("HOLD:")
    assert [row.add_player.player_id for row in analysis.watch_additions] == [13]


def test_no_drop_fit_is_whole_roster_bounded_and_never_marginal_inflation():
    covered = roster_ctx([evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 60, rostered=True)],
        [evidence_player(11, "PG,C", 80)], slots_of(PG=1, C=1, BN=2), {1: "PG", 2: "C"})
    full = enrich(covered, covered.players[11]).comparison
    assert full.component_before.roster_fit == full.component_after.roster_fit == 100
    assert full.component_deltas.roster_fit == 0 and full.target_roster_position == "BN"
    gaps = roster_ctx([evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "SF", 60, rostered=True)],
        [evidence_player(11, "SG,C", 80)], slots_of(PG=1, SG=1, SF=1, C=1), {1: "PG", 2: "SF"})
    bounded = enrich(gaps, gaps.players[11]).comparison
    assert gaps.team_needs.open_starting_slots == ["SG", "C"]
    assert bounded.component_deltas.roster_fit == 25
    assert (bounded.starting_slots_before, bounded.starting_slots_after) == (2, 3)
    for comparison in (full, bounded):
        for side in (comparison.component_before, comparison.component_after):
            for value in side.model_dump().values():
                assert value is None or 0 <= value <= 100


def test_add_only_api_board_transactions_impact_are_exact_select_only_and_manager_scoped(persisted):
    f = persisted
    today = datetime.now(timezone.utc).astimezone(WAIVER_TIMEZONE).date().isoformat()

    async def move_weak_to_il():
        async with SessionFactory() as session, session.begin():
            settings = await session.get(LeagueSettings, f.league)
            settings.roster_positions = [*settings.roster_positions, {"position": "IL", "count": "1"}]
            entry = (await session.scalars(select(RosterEntry).where(
                RosterEntry.team_key == f.team1, RosterEntry.player_identity_id == f.ids["weak"]))).one()
            entry.roster_position = "IL"
            entry.source_payload = {**entry.source_payload,
                "eligible_positions": [{"position": "PG"}, {"position": "Util"}, {"position": "IL"}],
                "selected_position": {"coverage_type": "date", "date": today, "position": "IL"}}
            pool = (await session.scalars(select(LeaguePlayer).where(
                LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids["weak"]))).one()
            pool.source_payload = {**pool.source_payload, "status": "O"}
        await engine.dispose()
    asyncio.run(move_weak_to_il())
    statements = []

    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        result = board(f)
        capacity = result["roster_capacity"]
        assert capacity["transaction_shape"] == "ADD_ONLY" and capacity["state"] == "available"
        assert capacity["no_drop_additions_available"] == 1 and capacity["requires_drop"] is False
        assert capacity["open_active_slots"] == ["C"] and capacity["assignment_as_of"] == today
        assert capacity["injured_players_in_injury_slots"] == [f.ids["weak"]]
        assert result["team_needs_analysis"]["open_starting_slots"] == ["C"]
        assert result["option_groups"]["by_need"][0]["slot"] == "C"
        assert result["candidates"]
        for row in result["candidates"]:
            assert row["best_drop_options"] == [] and row["requires_drop"] is False
            assert row["comparison"]["player_id"] is None and row["comparison"]["comparison_type"] == "ADD_ONLY"
        transactions = f.client.get("/api/v1/waivers/transactions").json()
        assert transactions["model_version"] == MODEL_VERSION
        assert transactions["evaluated_pair_count"] == 0 and transactions["best_transaction"] is None
        assert transactions["evaluated_addition_count"] >= len(result["candidates"])
        center = next(row for row in result["candidates"] if row["player_name"] == "center")
        watch = next(row for row in transactions["watch_additions"] if row["add_player"]["player_id"] == center["player_id"])
        impact = f.client.get(f"/api/v1/waivers/{center['player_id']}/impact").json()
        assert center["comparison"] == watch["comparison"] == impact["comparison"]
        assert impact["roster_capacity"] == capacity
        explicit = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["guard"]}).json()
        option = next(row for row in explicit["candidates"] if row["player_id"] == center["player_id"])
        assert option["comparison"]["player_id"] == f.ids["guard"] and option["recommended_action_type"] != "ADD_ONLY"
        assert option["add_only_impact"] == center["comparison"]
        assert any("Dropping is optional" in reason for reason in option["reasons"])
        il_drop = f.client.get("/api/v1/waivers/replacements", params={"drop_player_id": f.ids["weak"]}).json()
        assert all(row["comparison"]["net_improvement"] is None for row in il_drop["candidates"])
        assert "injury slot" in il_drop["candidates"][0]["comparison"]["reasons"][0]
        assert statements
        for path, params in (("/api/v1/waivers", {}), ("/api/v1/waivers/transactions", {}),
                ("/api/v1/waivers/replacements", {"drop_player_id": f.ids["guard"]}),
                (f"/api/v1/waivers/{center['player_id']}/impact", {})):
            assert f.client.get(path, params={**params, "team_key": f.team2}).status_code == 422
            for method in ("post", "put", "delete"):
                assert getattr(f.client, method)(path, params=params).status_code == 405
        f.no_yahoo.assert_not_called()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)


def test_structured_409_contract_errors_stay_errors_on_every_waiver_endpoint(persisted, monkeypatch):
    detail = {"message": "Persisted league contract mismatch; waiver analysis blocked",
        "mismatches": ["roster positions disagree"]}

    def mismatch(league):
        raise HTTPException(409, detail)
    monkeypatch.setattr("app.features.waivers.service.verify_league_contract", mismatch)
    for path, params in (("/api/v1/waivers", {}), ("/api/v1/waivers/transactions", {}),
            ("/api/v1/waivers/replacements", {"drop_player_id": persisted.ids["guard"]}),
            (f"/api/v1/waivers/{persisted.ids['center']}/impact", {})):
        response = persisted.client.get(path, params=params)
        assert response.status_code == 409
        assert response.json()["detail"] == detail
        assert "HOLD" not in response.text


def measure(row, value=None, games=None, prior=None, mode="this_week", age_days=0):
    """Attach decision-support production built by the production function itself."""
    games = row.current_season_games if games is None else games
    row.measured = measured_production(
        mode=mode, season="2026-27", recent_value=None, recent_games=0, recent_as_of=None, recent_latest_game=None,
        current_value=row.recent.value if value is None else value, current_games=games,
        current_as_of=NOW - timedelta(days=age_days), prior_value=prior, prior_games=60 if prior is not None else 0,
        prior_season="2025-26" if prior is not None else None, scoring_available=True, now=NOW, today=NOW.date(),
        earlier_value=row.recent.value if value is None else value, earlier_games=games)
    return row


def support_ctx(ctx, availability="available"):
    """Inputs load_context supplies to decision support: measured players, need slots, league availability."""
    for row in ctx.players.values():
        if row.measured.value is None:
            measure(row)
    ctx.needs_slots = list(ctx.slots)
    ctx.quality["availability"] = FRESH.model_copy(update={"state": availability})
    return ctx


def board_candidates(ctx):
    return [enrich(ctx, row) for row in ctx.players.values()
        if row.availability in {"free_agent", "waivers", "unrostered"} and row.eligible]


def options_by_id(support):
    return {option.player_id: option for option in support.options}


def unknown_status(row, status=None):
    row.yahoo_status = status
    row.data_quality["status"] = FRESH.model_copy(update={"state": "unknown"})
    return row


def test_measured_production_shrinks_small_samples_labels_staleness_and_needs_current_games():
    common = dict(season="2026-27", recent_value=None, recent_games=0, recent_as_of=None, recent_latest_game=None,
        scoring_available=True, now=NOW, today=NOW.date())
    shrunk = measured_production(mode="this_week", current_value=40.0, current_games=2,
        current_as_of=NOW - timedelta(days=10), prior_value=20.0, prior_games=70, prior_season="2025-26",
        earlier_value=40.0, earlier_games=2, **common)
    assert shrunk.basis == "CURRENT_SEASON" and shrunk.comparable and shrunk.state == "stale"
    assert shrunk.value == pytest.approx((2 * 40 + 2 * 20) / 4, abs=0.01)
    assert shrunk.current_weight == pytest.approx(2 / 4, abs=1e-4)
    assert shrunk.math == "(2 x 40.00 earlier this season + 2 x 20.00 2025-26) / 4 = 30.00"
    assert "(stale)" in shrunk.detail and "not a projection" in shrunk.detail
    # Rest of Season Outlook decision support keeps its season shrinkage (ten prior games); the math says so.
    season_shrunk = measured_production(mode="ros", current_value=40.0, current_games=2, current_as_of=NOW,
        prior_value=20.0, prior_games=70, prior_season="2025-26", **common)
    assert season_shrunk.value == pytest.approx((2 * 40 + 10 * 20) / 12, abs=0.01)
    assert season_shrunk.math == "(2 x 40.00 this season + 10 x 20.00 2025-26) / 12 = 23.33"
    rookie = measured_production(mode="ros", current_value=45.0, current_games=MIN_UNSHRUNK_GAMES - 1,
        current_as_of=NOW, prior_value=None, prior_games=0, prior_season=None, **common)
    assert rookie.value == 45.0 and not rookie.comparable and rookie.state == "available"
    inactive = measured_production(mode="ros", current_value=None, current_games=0, current_as_of=None,
        prior_value=30.0, prior_games=70, prior_season="2025-26", **common)
    assert inactive.value is None and not inactive.comparable and inactive.prior_value == 30.0
    assert inactive.detail.startswith("No current-season NBA games")
    recent = measured_production(mode="next_7_days", season="2026-27", recent_value=30.0, recent_games=5,
        recent_as_of=NOW, recent_latest_game=NOW.date(), current_value=25.0, current_games=12, current_as_of=NOW,
        prior_value=None, prior_games=0, prior_season=None, scoring_available=True, now=NOW, today=NOW.date(),
        earlier_value=150 / 7, earlier_games=7)
    # Every current-season game counts once: 5 Last 14 Days games at 30 and 7 earlier games at 21.43 are this season's 25.
    assert (recent.basis, recent.value, recent.state, recent.comparable) == ("RECENT", 25.0, "available", True)
    assert (recent.current_games, recent.current_value, recent.current_weight) == (12, 25.0, 1.0)
    season = measured_production(mode="ros", season="2026-27", recent_value=30.0, recent_games=5, recent_as_of=NOW,
        recent_latest_game=NOW.date(), current_value=25.0, current_games=12, current_as_of=NOW,
        prior_value=None, prior_games=0, prior_season=None, scoring_available=True, now=NOW, today=NOW.date())
    assert (season.basis, season.value) == ("CURRENT_SEASON", 25.0)
    unsupported = measured_production(mode="ros", current_value=25.0, current_games=12, current_as_of=NOW,
        prior_value=None, prior_games=0, prior_season=None, **(common | {"scoring_available": False}))
    assert unsupported.state == "unsupported" and unsupported.value is None and not unsupported.comparable


def test_need_summary_is_plain_language_and_util_or_bench_are_depth_not_positions():
    needs = two_injured_in_il_context().team_needs
    assert [(row.priority, row.label, row.level) for row in needs.summary] == [(1, "C", "HIGH"), (2, "PG / SG", "MEDIUM")]
    assert needs.summary[0].reason.startswith("Injury coverage needed")
    assert "one absence leaves it open" in needs.summary[1].reason
    assert "bench depth" in needs.depth_note
    redundant = roster_ctx([evidence_player(pid, "PG,SG", rostered=True) for pid in (1, 2, 3)]
        + [evidence_player(pid, "C", rostered=True) for pid in (4, 5)], [],
        slots_of(PG=1, SG=1, C=1, BN=2), {1: "PG", 2: "SG", 4: "C", 3: "BN", 5: "BN"}).team_needs
    assert [(row.label, row.level) for row in redundant.summary] == [("PG / SG", "COVERED"), ("C", "COVERED")]
    assert redundant.depth_note is None
    short = roster_ctx([evidence_player(1, "PG", rostered=True)], [], slots_of(PG=1, UTIL=1), {1: "PG"}).team_needs
    assert [row.family for row in short.summary] == ["GUARD"]
    assert all("UTIL" not in row.slots and "BN" not in row.slots for row in [*needs.summary, *short.summary])
    assert short.depth_note.startswith("1 UTIL starting slot")


def test_decision_support_keeps_supported_add_only_first_and_never_relabels_strict_actions():
    ctx = support_ctx(one_open_spot_context(watch_games=2))
    assert ctx.roster_capacity.headline == "1 OPEN ROSTER SPOT — NO DROP REQUIRED"
    candidates = board_candidates(ctx)
    before = [row.model_dump() for row in candidates]
    support = decision_support_for(ctx, candidates)
    assert [row.model_dump() for row in candidates] == before
    first = support.options[0]
    assert support.state == "SUPPORTED_ACTION" and support.supported_count == 1
    assert (first.player_id, first.classification, first.action_type, first.decision_rank) == (11, "SUPPORTED_ACTION", "ADD_ONLY", 1)
    analysis = analyze_transactions(ctx)
    assert first.player_id == analysis.best_addition.add_player.player_id
    assert next(row for row in candidates if row.player_id == 11).comparison == analysis.best_addition.comparison
    assert support.best_measured_ids == [] and first.blockers == [] and first.confirm == []
    watch = options_by_id(support)[13]
    assert watch.classification == "WATCH" and watch.action_type == "WATCH"
    assert [option.decision_rank for option in support.options] == list(range(1, len(support.options) + 1))


def test_two_open_spots_show_two_supported_fills_or_a_best_measured_option_for_the_unfilled_spot():
    ctx = support_ctx(two_injured_in_il_context())
    assert ctx.roster_capacity.headline == "2 OPEN ROSTER SPOTS — NO DROP REQUIRED"
    support = decision_support_for(ctx, board_candidates(ctx))
    assert support.supported_count == 2 and support.best_measured_ids == []
    assert [(option.player_id, option.action_type) for option in support.options[:2]] == [(11, "ADD_ONLY"), (12, "ADD_ONLY")]
    for pid in (12, 13):
        unknown_status(ctx.players[pid])
    support = decision_support_for(ctx, board_candidates(ctx))
    assert support.state == "SUPPORTED_ACTION" and support.supported_count == 1
    assert support.best_measured_ids == [12]
    best = options_by_id(support)[12]
    assert best.classification == "BEST_MEASURED_OPTION" and best.action_type == "INSUFFICIENT_EVIDENCE"
    assert best.status_label == "UNKNOWN" and any("UNKNOWN (blank)" in item for item in best.blockers)
    assert [option.player_id for option in support.options[:2]] == [11, 12]


def test_il_move_stays_the_supported_move_and_the_headline_names_the_player():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 85, status="O", rostered=True),
        evidence_player(3, "SF", 50, rostered=True)]
    roster[1].components.player_value = None
    ctx = support_ctx(roster_ctx(roster, [evidence_player(11, "C", 75), evidence_player(12, "PG", 80)],
        slots_of(PG=1, C=1, BN=1, IL=1), {1: "PG", 2: "C", 3: "BN"}, eligible={2: ["C", "UTIL", "IL"]}))
    assert ctx.roster_capacity.headline == "MOVE C 2 TO IL TO OPEN A ROSTER SPOT"
    assert "not a drop" in ctx.roster_capacity.short_reason
    support = decision_support_for(ctx, board_candidates(ctx))
    first = support.options[0]
    assert (first.player_id, first.action_type, first.classification) == (11, "MOVE_TO_IL_THEN_ADD", "SUPPORTED_ACTION")
    assert analyze_transactions(ctx).best_addition.add_player.player_id == 11


def test_full_roster_keeps_add_drop_primary_and_a_measured_option_must_beat_the_roster_floor():
    roster = [evidence_player(1, "PG", 60, rostered=True), evidence_player(2, "C", 10, rostered=True)]
    add = evidence_player(11, "C", 90)
    ctx = support_ctx(roster_ctx(roster, [add], slots_of(PG=1, C=1), {1: "PG", 2: "C"}))
    assert ctx.roster_capacity.headline == "ROSTER FULL — AN ADD REQUIRES A DROP"
    support = decision_support_for(ctx, board_candidates(ctx))
    assert support.state == "SUPPORTED_ACTION" and support.options[0].action_type == "ADD_DROP"
    best = analyze_transactions(ctx).best_transaction
    assert best.comparison == compare(ctx, add, 2) == enrich(ctx, add, 2).comparison
    unknown_status(add)
    ctx.players[12] = measure(evidence_player(12, "C", 5))
    support = decision_support_for(ctx, board_candidates(ctx))
    assert support.state == "BEST_MEASURED_OPTION" and support.best_measured_ids == [11]
    assert (support.roster_floor_ppg, support.roster_floor_player_id) == (10, 2)
    option = options_by_id(support)[11]
    # 2026-11-21 audit (WC-07): a full-roster option names its exact best drop instead of asking the user to guess.
    assert not any("Which roster player you would drop" in item for item in option.confirm)
    assert option.roster_rank_if_added == 1
    assert option.pair is not None and option.pair.drop_player_id == 2 and option.pair.net > 0
    assert option.verdict == "CANNOT_EVALUATE" and option.headline.startswith("CANNOT EVALUATE — Yahoo status gate:")
    assert analyze_transactions(ctx).best_transaction is None


def test_undetermined_capacity_still_names_a_best_measured_option_with_exact_blockers():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 60, rostered=True)]
    ctx = support_ctx(roster_ctx(roster, [evidence_player(11, "C", 90), evidence_player(12, "PG", 40)],
        slots_of(PG=1, C=1, BN=1, IL=1), {1: "PG"}))
    capacity = ctx.roster_capacity
    assert capacity.transaction_shape == "UNDETERMINED"
    assert capacity.headline == "ROSTER CAPACITY NEEDS A YAHOO REFRESH"
    assert capacity.short_reason == "Yahoo roster slots are not saved for 1 of 2 players."
    candidates = board_candidates(ctx)
    assert {row.recommended_action_type for row in candidates} == {"INSUFFICIENT_EVIDENCE"}
    support = decision_support_for(ctx, candidates)
    assert support.state == "BEST_MEASURED_OPTION" and support.best_measured_ids == [11]
    assert support.headline == "Best measured option: C 11 — not yet a supported add."
    best = options_by_id(support)[11]
    assert best.action_type == "INSUFFICIENT_EVIDENCE" and best.user_action == "CHECK IN YAHOO"
    assert best.blockers[0] == f"Roster capacity is undetermined: {capacity.short_reason}"
    assert "Whether you have an open roster spot" in best.confirm and best.why
    assert analyze_transactions(ctx).decision == "INSUFFICIENT EVIDENCE"


def test_stale_league_rosters_list_potential_targets_as_unverified_and_never_supported():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "C", 60, rostered=True)]
    pool = [evidence_player(11, "C", 90), evidence_player(12, "SF", 80), evidence_player(13, "PG", 99, rostered=True)]
    for row in pool[:2]:
        row.availability, row.eligible = "unknown", False
    ctx = support_ctx(roster_ctx(roster, pool, slots_of(PG=1, C=1, BN=1), {1: "PG", 2: "C"}), availability="partial")
    candidates = board_candidates(ctx)
    assert candidates == []
    assert enrich(ctx, ctx.players[11]).recommended_action_type == "INSUFFICIENT_EVIDENCE"
    support = decision_support_for(ctx, candidates)
    options = options_by_id(support)
    assert set(options) == {11, 12} and support.potential_target_count == 2
    # Unconfirmed availability is never featured: no best option, group pick or WATCH, only targets to check.
    assert support.state == "POTENTIAL_TARGETS" and support.best_measured_ids == [] and support.watch_ids == []
    assert all(group.player_id is None for group in support.groups)
    assert support.potential_target_ids == [11, 12]
    for option in options.values():
        assert option.availability_label == "AVAILABILITY UNVERIFIED" and not option.availability_confirmed
        assert option.classification == "POTENTIAL_TARGET" and option.action_type == "INSUFFICIENT_EVIDENCE"
    assert "Yahoo availability (free agent or waivers)" in options[11].confirm
    assert "not on any saved league roster" in support.availability_note
    assert support.not_comparable_reasons["On another team's saved roster (not a target)"] == 1


@pytest.mark.parametrize("status", [None, "HEALTHY"])
def test_blank_or_unrecognized_status_can_be_best_measured_but_never_a_supported_action(status):
    ctx = one_open_spot_context(watch_games=7)
    for pid in (12, 13):
        del ctx.players[pid]
    unknown_status(ctx.players[11], status)
    support_ctx(ctx)
    candidates = board_candidates(ctx)
    assert candidates[0].recommended_action == "INSUFFICIENT EVIDENCE"
    support = decision_support_for(ctx, candidates)
    option = options_by_id(support)[11]
    assert support.state == "BEST_MEASURED_OPTION" and option.classification == "BEST_MEASURED_OPTION"
    assert option.action_type not in {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD", "ADD_DROP"}
    assert support.supported_count == 0 and "Current Yahoo status" in option.confirm
    if status is None:
        assert option.status_label == "UNKNOWN"
        assert option.status_detail == "Yahoo did not provide an explicit current status. Confirm the player in Yahoo before acting."
    else:
        assert option.status_label == "HEALTHY · UNKNOWN"


def test_out_and_not_active_players_never_enter_any_decision_support_group():
    roster = [evidence_player(1, "PG", 70, rostered=True), evidence_player(2, "SF", 60, rostered=True)]
    pool = [evidence_player(11, "C", 99, status="O"), evidence_player(12, "C", 98, status="NA"), evidence_player(13, "C", 50)]
    pool[0].eligible = pool[1].eligible = False
    unknown_out = evidence_player(14, "PG", 97, status="O")
    unknown_out.availability, unknown_out.eligible = "unknown", False
    ctx = support_ctx(roster_ctx(roster, [*pool, unknown_out], slots_of(PG=1, SF=1, C=1, BN=1), {1: "PG", 2: "SF"}),
        availability="partial")
    support = decision_support_for(ctx, board_candidates(ctx))
    assert {11, 12, 14}.isdisjoint(options_by_id(support))
    assert support.not_comparable_reasons["Yahoo O/OFS/NA status"] == 1
    featured = [*support.best_measured_ids, *support.watch_ids, *support.potential_target_ids,
        *(group.player_id for group in support.groups)]
    assert {11, 12, 14}.isdisjoint(featured)


def test_unresolved_identity_is_never_a_measured_target():
    ctx = one_open_spot_context(watch_games=7)
    ctx.players[12].identity_mapping_state = "AMBIGUOUS"
    unknown = evidence_player(14, "C", 99)
    unknown.availability, unknown.eligible, unknown.identity_mapping_state = "unknown", False, "NO_MATCH"
    ctx.players[14] = unknown
    support = decision_support_for(support_ctx(ctx, availability="partial"), board_candidates(ctx))
    options = options_by_id(support)
    assert options[12].classification == "UNAVAILABLE" and options[12].measured.value is None
    featured = [*support.best_measured_ids, *support.watch_ids, *support.potential_target_ids,
        *(group.player_id for group in support.groups)]
    assert 12 not in featured and 14 not in options
    assert support.not_comparable_reasons["Unresolved Yahoo-to-NBA identity"] == 2


def test_board_decision_support_is_backend_ranked_select_only_and_names_the_open_need(persisted):
    f = persisted
    statements = []

    def guard(connection, cursor, statement, parameters, context, executemany):
        assert statement.lstrip().upper().startswith("SELECT"), statement
        statements.append(statement)
    event.listen(engine.sync_engine, "before_cursor_execute", guard)
    try:
        result = board(f)
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", guard)
    support = result["decision_support"]
    options = {row["player_id"]: row for row in support["options"]}
    assert [row["decision_rank"] for row in support["options"]] == list(range(1, len(options) + 1))
    assert {row["player_id"]: row["decision_rank"] for row in result["candidates"]} == {
        pid: row["decision_rank"] for pid, row in options.items()}
    assert support["availability_state"] == "available" and support["potential_target_ids"] == []
    assert {f.ids[name] for name in ("out", "inactive", "guard", "weak", "opponent")}.isdisjoint(options)
    assert all(row["classification"] != "SUPPORTED_ACTION" for row in support["options"])
    assert result["best_add_for_team_id"] is None
    assert support["state"] == "BEST_MEASURED_OPTION" and support["best_measured_ids"] == [f.ids["center"]]
    center = options[f.ids["center"]]
    assert (center["fills"], center["fills_level"], center["status_label"]) == (["C"], "HIGH", "Q · Questionable")
    assert options[f.ids["unmapped"]]["classification"] == "UNAVAILABLE"
    assert options[f.ids["unknown"]]["status_label"] == "UNKNOWN"
    assert result["roster_capacity"]["headline"] == "ROSTER FULL — AN ADD REQUIRES A DROP"
    assert {row["source"] for row in result["evidence_freshness"]} >= {"Yahoo league settings", "NBA game logs"}
    assert statements
    f.no_yahoo.assert_not_called()


def test_stale_league_rosters_become_unverified_potential_targets_through_the_api(persisted):
    f = persisted

    async def stale_other_roster():
        async with SessionFactory() as session, session.begin():
            other = (await session.scalars(select(FantasyTeam).where(FantasyTeam.team_key == f.team2))).one()
            other.imported_at = datetime.now(timezone.utc) - timedelta(days=2)
        await engine.dispose()
    asyncio.run(stale_other_roster())
    result = board(f)
    support = result["decision_support"]
    options = {row["player_id"]: row for row in support["options"]}
    assert result["candidates"] == [] and support["availability_state"] == "partial"
    assert set(options) == {f.ids[name] for name in ("center", "star", "unknown")}
    for option in options.values():
        assert option["availability_label"] == "SAVED ROSTERS STALE — CHECK IN YAHOO"
        assert option["classification"] != "SUPPORTED_ACTION" and option["action_type"] == "INSUFFICIENT_EVIDENCE"
    assert support["not_comparable_reasons"]["Yahoo O/OFS/NA status"] == 2
    assert support["not_comparable_reasons"]["Unresolved Yahoo-to-NBA identity"] == 1
    assert support["potential_target_count"] == 3 and support["state"] == "POTENTIAL_TARGETS"
    assert support["best_measured_ids"] == [] and support["watch_ids"] == []
    assert {option["classification"] for option in options.values()} == {"POTENTIAL_TARGET"}
    assert {option["availability_classification"] for option in options.values()} == {"SOURCE_STALE"}
    impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact")
    assert impact.status_code == 200
    assert impact.json()["candidate"]["recommended_action_type"] == "INSUFFICIENT_EVIDENCE"
    assert any("availability" in item for item in impact.json()["candidate"]["evidence_blockers"])
    f.no_yahoo.assert_not_called()


def classify(**overrides):
    from app.features.waivers.service import classify_availability
    arguments = dict(in_manager_roster=False, in_other_roster=False, ownership=None, manager_team_key="t1",
        excluded_status=False, observation_at=NOW, observation_fresh=True, snapshots_expected=12,
        snapshots_current=12, snapshots_missing=0, oldest_snapshot=NOW)
    return classify_availability(**{**arguments, **overrides})


def test_availability_classes_keep_explicit_fa_and_waiver_state_separate_and_fail_closed():
    fa, fa_legacy, fa_evidence = classify(ownership={"ownership_type": "freeagents"})
    assert (fa, fa_legacy, fa_evidence.yahoo_ownership_state, fa_evidence.actionable) == ("CONFIRMED_FA", "free_agent", "FA", True)
    waiver, waiver_legacy, waiver_evidence = classify(ownership={"ownership_type": "waivers", "waiver_date": "2026-11-15"})
    assert (waiver, waiver_legacy, waiver_evidence.yahoo_ownership_state) == ("CONFIRMED_WAIVER", "waivers", "W")
    assert waiver_evidence.waiver_clear_date == date(2026, 11, 15) and fa_evidence.waiver_clear_date is None
    assert "until 2026-11-15" in waiver_evidence.eligibility_reason
    unrostered, legacy, evidence = classify()
    assert (unrostered, legacy) == ("UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT", "unrostered")
    assert evidence.label == "UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO" and evidence.actionable
    assert evidence.yahoo_ownership_state is None and "confirm the FA/waiver state in Yahoo" in evidence.detail
    # Rostered beats explicit FA state and status; another team's player is never a target.
    assert classify(in_other_roster=True, ownership={"ownership_type": "freeagents"})[0] == "ROSTERED_BY_OTHER_TEAM"
    assert classify(ownership={"ownership_type": "team", "owner_team_key": "t7"})[0] == "ROSTERED_BY_OTHER_TEAM"
    assert classify(in_manager_roster=True)[0] == "ROSTERED_BY_MANAGER"
    assert classify(excluded_status=True, ownership={"ownership_type": "freeagents"})[:2] == ("EXCLUDED_STATUS", "free_agent")
    # Explicit FA/W state still needs every league roster snapshot current and complete.
    stale, stale_legacy, stale_evidence = classify(snapshots_current=11, ownership={"ownership_type": "waivers"})
    assert (stale, stale_legacy, stale_evidence.actionable) == ("SOURCE_STALE", "unknown", False)
    assert stale_evidence.yahoo_ownership_state == "W", "explicit state is preserved even when not actionable"
    assert classify(observation_fresh=False)[0] == "SOURCE_STALE"
    assert classify(snapshots_missing=1, snapshots_current=11)[0] == "AVAILABILITY_UNVERIFIED"
    assert classify(observation_at=None, observation_fresh=False)[0] == "AVAILABILITY_UNVERIFIED"
    assert classify(snapshots_expected=0, snapshots_current=0)[0] == "AVAILABILITY_UNVERIFIED"


def test_explicit_yahoo_fa_and_waiver_states_reach_the_board_separately(persisted):
    f = persisted

    async def change():
        async with SessionFactory() as session, session.begin():
            for name, ownership in (("center", {"ownership_type": "freeagents"}),
                    ("star", {"ownership_type": "waivers", "waiver_date": "2026-11-16"})):
                row = (await session.execute(select(LeaguePlayer).where(
                    LeaguePlayer.league_key == f.league, LeaguePlayer.player_identity_id == f.ids[name]))).scalar_one()
                row.source_payload = {**row.source_payload, "ownership": ownership}
        await engine.dispose()
    asyncio.run(change())
    result = board(f)
    options = {row["player_id"]: row for row in result["decision_support"]["options"]}
    center, star = options[f.ids["center"]], options[f.ids["star"]]
    assert (center["availability_classification"], center["availability_label"]) == ("CONFIRMED_FA", "FREE AGENT (YAHOO)")
    assert star["availability_classification"] == "CONFIRMED_WAIVER"
    assert star["availability_evidence"]["waiver_clear_date"] == "2026-11-16"
    assert center["availability_evidence"]["waiver_clear_date"] is None
    unknown = options[f.ids["unknown"]]
    assert unknown["availability_classification"] == "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT"
    assert {f.ids["center"], f.ids["star"], f.ids["unknown"]} <= set(result["eligible_candidate_ids"])
    assert result["availability_summary"]["explicit_state_supplied"] and result["availability_summary"]["source_gap"] is None


@pytest.mark.parametrize("mode", ["this_week", "next_7_days", "ros"])
def test_every_recommended_player_is_a_current_eligible_candidate(persisted, mode):
    from app.features.waivers.service import board_recommended_ids
    from app.features.waivers.contracts import WaiverBoard
    f = persisted
    result = board(f, mode=mode)
    eligible = set(result["eligible_candidate_ids"])
    assert eligible and result["candidate_count"] == len(eligible) >= len(result["candidates"])
    recommended = board_recommended_ids(WaiverBoard.model_validate(result))
    assert {pid for ids in recommended.values() for pid in ids} <= eligible
    assert {f.ids[name] for name in ("guard", "weak", "opponent", "out", "inactive")}.isdisjoint(eligible)
    options = result["decision_support"]["options"]
    assert f.ids["opponent"] not in {row["player_id"] for row in options}, "another team's player is never listed"
    analysis = f.client.get("/api/v1/waivers/transactions", params={"mode": mode}).json()
    adds = [swap["add_player"]["player_id"] for swap in [*analysis["top_supported_transactions"], *analysis["watch_transactions"]]]
    assert set(adds) <= eligible


def test_recommendation_outside_the_eligible_set_is_withheld_as_a_contract_error():
    from app.features.waivers.service import RecommendationContractError, assert_board_recommendation_invariant, build_board
    ctx = support_ctx(one_open_spot_context(watch_games=7))
    ctx.league = SimpleNamespace(league_key="fixture", settings=None)
    result = build_board(ctx, "fixture", "t1", "this_week", None)
    assert_board_recommendation_invariant(result)
    assert result.best_add_for_team_id in result.eligible_candidate_ids
    tampered = result.model_copy(deep=True)
    tampered.decision_support.best_measured_ids = [1]  # a rostered player
    with pytest.raises(RecommendationContractError) as error:
        assert_board_recommendation_invariant(tampered)
    assert error.value.status_code == 500
    assert error.value.detail["code"] == "RECOMMENDATION_CONTRACT_VIOLATION"
    assert any("best_measured: player 1" in item for item in error.value.detail["violations"])
    tampered = result.model_copy(deep=True)
    tampered.decision_support.potential_target_ids = [result.eligible_candidate_ids[0]]
    with pytest.raises(RecommendationContractError):
        assert_board_recommendation_invariant(tampered)


def test_thirteen_regular_players_plus_two_in_il_leave_one_il_slot_but_no_regular_spot():
    positions = slots_of(PG=1, SG=1, G=1, SF=1, PF=1, F=1, C=2, UTIL=2, BN=3, IL=3)
    order = ["PG", "SG", "G", "SF", "PF", "F", "C", "C", "UTIL", "UTIL", "BN", "BN", "BN"]
    shapes = {"PG": "PG", "SG": "SG", "G": "PG,SG", "SF": "SF", "PF": "PF", "F": "SF,PF", "C": "C", "UTIL": "PG", "BN": "SF"}
    roster = [evidence_player(index + 1, shapes[slot], 60, rostered=True) for index, slot in enumerate(order)]
    injured = [evidence_player(14, "PG", 80, status="O", rostered=True), evidence_player(15, "SF,PF", 75, status="O", rostered=True)]
    for row in injured:
        row.components.player_value = None
    assignments = {index + 1: slot for index, slot in enumerate(order)} | {14: "IL", 15: "IL"}
    eligible = {14: ["PG", "UTIL", "IL"], 15: ["SF", "PF", "UTIL", "IL"]}
    ctx = support_ctx(roster_ctx([*roster, *injured], [evidence_player(21, "C", 90)], positions, assignments, eligible))
    capacity = ctx.roster_capacity
    assert (capacity.non_injury_capacity, capacity.occupied_roster_spots, capacity.open_roster_spots) == (13, 13, 0)
    assert (capacity.injury_slot_capacity, capacity.occupied_injury_slots, capacity.open_injury_slots) == (3, 2, 1)
    assert capacity.injured_players_in_injury_slots == [14, 15] and capacity.move_to_injury_slot_options == []
    assert (capacity.transaction_shape, capacity.requires_drop) == ("ADD_DROP", True)
    assert capacity.headline == "ROSTER FULL — AN ADD REQUIRES A DROP"
    add = enrich(ctx, ctx.players[21])
    assert add.requires_drop is True and add.recommended_action_type in {"ADD_DROP", "WATCH", "HOLD", "INSUFFICIENT_EVIDENCE"}
    assert add.recommended_action_type not in {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD"}
    assert add.best_drop_options and all(option.player_id not in {14, 15} for option in add.best_drop_options), \
        "IL occupants are never the drop that opens a regular spot"


def test_weekly_adds_and_waiver_priority_come_only_from_one_consistent_yahoo_import():
    from app.features.waivers.service import acquisition_context_for
    settings_payload = {"fantasy_content": {"league": [{"league_key": "478.l.1"}, {"settings": [{"max_weekly_adds": "4"}]}]}}
    league = SimpleNamespace(league_key="478.l.1", source_payload={"current_week": 4},
        settings=SimpleNamespace(source_payload=settings_payload))
    team = SimpleNamespace(imported_at=NOW, source_payload={"waiver_priority": 4,
        "roster_adds": {"coverage_type": "week", "coverage_value": 4, "value": "2"}})
    context = acquisition_context_for(league, team, NOW, ["4 adds/week"])
    assert (context.weekly_adds_used, context.weekly_add_limit, context.weekly_adds_remaining) == (2, 4, 2)
    assert (context.current_priority, context.yahoo_week, context.state, context.as_of) == (4, 4, "available", NOW)
    assert context.detail.startswith("Yahoo reports 2 of 4 weekly adds used in Yahoo week 4 (2 remaining), waiver priority 4")
    league.source_payload = {"current_week": 5}
    mismatch = acquisition_context_for(league, team, NOW, [])
    assert mismatch.weekly_adds_used is None and mismatch.weekly_adds_remaining is None
    assert mismatch.state == "partial" and mismatch.current_priority == 4
    stale = acquisition_context_for(SimpleNamespace(league_key="478.l.1", source_payload={"current_week": 4},
        settings=league.settings), SimpleNamespace(imported_at=NOW - timedelta(days=2), source_payload=team.source_payload), NOW, [])
    assert stale.state == "stale" and "older than 24 hours" in stale.detail
    missing = acquisition_context_for(league, SimpleNamespace(imported_at=NOW, source_payload={}), NOW, [])
    assert missing.state == "missing" and missing.weekly_adds_used is None and missing.current_priority is None


def test_waiver_reads_carry_request_id_and_server_timing_and_log_no_player_payloads(persisted, caplog):
    f = persisted
    caplog.set_level("INFO", logger="uvicorn.error")
    response = f.client.get("/api/v1/waivers", params={"mode": "next_7_days"}, headers={"X-Request-ID": "proxy-req-12345"})
    assert response.status_code == 200
    assert response.headers["x-request-id"] == "proxy-req-12345"
    timing = response.headers["server-timing"]
    assert "load;dur=" in timing and "analyze;dur=" in timing and "total;dur=" in timing
    generated = f.client.get("/api/v1/waivers/transactions")
    assert len(generated.headers["x-request-id"]) == 16 and "analyze;dur=" in generated.headers["server-timing"]
    lines = [record.getMessage() for record in caplog.records if record.getMessage().startswith("request_timing")]
    assert any("request_id=proxy-req-12345" in line and "mode=next_7_days" in line and "candidates=" in line for line in lines)
    assert not any(name in line for line in lines for name in ("center", "star", "guard"))


# ---- Heavy-read admission (2026-11-15 incident) ----------------------------------------------------------------------
# Production evidence: reads whose browser (499) or nginx (504) had already given up kept computing for up to 472 s,
# and each page load, retry and horizon switch added another full-context load to the single API worker.


def _asgi_get(path, query=""):
    return {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"}, "http_version": "1.1", "method": "GET",
        "scheme": "http", "path": path, "raw_path": path.encode(), "root_path": "", "query_string": query.encode(),
        "headers": [(b"host", b"test")], "client": ("127.0.0.1", 50000), "server": ("test", 80)}


class _RawClient:
    """One raw ASGI GET against the full app whose client can leave mid-flight, as a browser abort or nginx 504 does."""

    def __init__(self, path, query="mode=this_week"):
        self.gone, self.messages, self._delivered = asyncio.Event(), [], False

        async def receive():
            if not self._delivered:
                self._delivered = True
                return {"type": "http.request", "body": b"", "more_body": False}
            await self.gone.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            self.messages.append(message)

        self.task = asyncio.create_task(app(_asgi_get(path, query), receive, send))

    @property
    def status(self):
        return next((message["status"] for message in self.messages if message["type"] == "http.response.start"), None)


@pytest.fixture
def heavy_reads(monkeypatch):
    """The real waiver router and timing middleware with slow in-memory reads; no database or provider is touched."""
    from app.features.waivers import router as waiver_router
    state = SimpleNamespace(seconds=0.4, started=[], cancelled=[], finished=[], running=0, peak=0, sessions=0)

    class FixtureSession:
        async def get(self, model, key):
            return SimpleNamespace(team_key=key, league_key=key.rsplit(".t.", 1)[0], team_name="Fixture team")

    async def session_override():
        state.sessions += 1
        yield FixtureSession()

    def slow(kind):
        async def read(*args, **kwargs):
            state.started.append(kind)
            state.running += 1
            state.peak = max(state.peak, state.running)
            try:
                await asyncio.sleep(state.seconds)
            except asyncio.CancelledError:
                state.cancelled.append(kind)
                raise
            finally:
                state.running -= 1
            state.finished.append(kind)
            raise HTTPException(409, f"{kind} read finished")  # completion marker without building a full board
        return read

    monkeypatch.setitem(app.dependency_overrides, get_session, session_override)
    monkeypatch.setattr(waiver_router, "get_waivers", slow("board"))
    monkeypatch.setattr(waiver_router, "get_transactions", slow("transactions"))
    monkeypatch.setattr(waiver_router, "get_impact", slow("impact"))
    return state


def test_waiver_read_stops_when_its_client_disconnects(heavy_reads, caplog):
    state = heavy_reads
    state.seconds = 1.0
    caplog.set_level("INFO", logger="uvicorn.error")

    async def scenario():
        client = _RawClient("/api/v1/waivers")
        while not state.started:
            await asyncio.sleep(0.01)
        client.gone.set()
        await asyncio.wait_for(client.task, 5)
        return client

    client = asyncio.run(scenario())
    assert state.cancelled == ["board"] and state.finished == [], "an abandoned read must stop instead of running to completion"
    assert client.status == 499
    assert any("path=/api/v1/waivers " in record.getMessage() and "status=499" in record.getMessage() for record in caplog.records)


def test_heavy_waiver_reads_run_one_at_a_time_and_queued_reads_hold_no_database_session(heavy_reads):
    state = heavy_reads

    async def scenario():
        clients = [_RawClient("/api/v1/waivers"), _RawClient("/api/v1/waivers/transactions"), _RawClient("/api/v1/waivers/7/impact")]
        while not state.started:
            await asyncio.sleep(0.01)
        await asyncio.sleep(0.1)
        sessions_while_queued = state.sessions
        await asyncio.wait_for(asyncio.gather(*(client.task for client in clients)), 10)
        return clients, sessions_while_queued

    clients, sessions_while_queued = asyncio.run(scenario())
    assert state.peak == 1, "a page view's board, best-move and impact reads must not load contexts concurrently"
    assert sessions_while_queued == 1, "queued reads wait without a database session"
    assert sorted(state.finished) == ["board", "impact", "transactions"] and state.cancelled == []
    assert [client.status for client in clients] == [409, 409, 409], "queued reads still run and keep their own results"


def test_queued_waiver_read_whose_client_leaves_never_loads(heavy_reads):
    state = heavy_reads
    state.seconds = 0.8

    async def scenario():
        running = _RawClient("/api/v1/waivers")
        while not state.started:
            await asyncio.sleep(0.01)
        queued = _RawClient("/api/v1/waivers/transactions")
        await asyncio.sleep(0.1)
        queued.gone.set()  # e.g. a horizon switch aborts the page's pending best-move read
        await asyncio.sleep(0.2)
        left_promptly = queued.task.done() and not running.task.done()
        await asyncio.wait_for(asyncio.gather(running.task, queued.task), 5)
        return running, queued, left_promptly

    running, queued, left_promptly = asyncio.run(scenario())
    assert left_promptly, "the queued read answers as soon as its client leaves"
    assert queued.status == 499 and state.started == ["board"] and state.sessions == 1
    assert running.status == 409 and state.finished == ["board"]


def test_cancelled_board_read_stops_its_query_and_returns_the_pooled_connection(persisted, monkeypatch):
    """Real PostgreSQL and the application's pooled engine: a read cancelled mid-query frees its connection and
    backend query, and the next read still answers."""
    import json
    from sqlalchemy import text
    from app.features.waivers import service as waiver_service
    monkeypatch.delitem(app.dependency_overrides, get_session)
    original = waiver_service.load_context
    entered = []

    async def slow_first_load(session, *args, **kwargs):
        entered.append(True)
        if len(entered) == 1:
            await session.execute(text("SELECT pg_sleep(30)"))
        return await original(session, *args, **kwargs)

    monkeypatch.setattr(waiver_service, "load_context", slow_first_load)

    async def scenario():
        await app_engine.dispose(close=False)
        try:
            client = _RawClient("/api/v1/waivers")
            while not entered:
                await asyncio.sleep(0.01)
            await asyncio.sleep(0.5)
            client.gone.set()
            await asyncio.wait_for(client.task, 10)
            await asyncio.sleep(0.5)
            checked_out = app_engine.pool.checkedout()
            async with app_engine.connect() as connection:
                sleeping = await connection.scalar(text("SELECT count(*) FROM pg_stat_activity "
                    "WHERE query LIKE '%pg_sleep(30)%' AND state = 'active' AND pid <> pg_backend_pid()"))
            follow = _RawClient("/api/v1/waivers")
            await asyncio.wait_for(follow.task, 60)
            body = json.loads(b"".join(message.get("body", b"") for message in follow.messages
                if message["type"] == "http.response.body"))
            return client.status, checked_out, sleeping, follow.status, body
        finally:
            await app_engine.dispose()

    status, checked_out, sleeping, follow_status, body = asyncio.run(scenario())
    assert status == 499
    assert checked_out == 0, "the cancelled read returned its pooled connection"
    assert sleeping == 0, "the cancelled read's query no longer runs on PostgreSQL"
    assert follow_status == 200 and body["model_version"] == MODEL_VERSION


# --- 2026-11-21 audit: decision integrity (model waiver-decision-integrity-phase7) -----------------------------------
# Synthetic, name-neutral fixtures. Real-data trace (read-only): a Rest of Season ADD backed only by a 63-vs-66
# remaining-games edge (9.8th vs 96.6th percentile) outweighed a 7.7 FP/G production loss; the same mechanism made
# dropping the roster's best scorer a "supported" move. Nothing here names or protects a player.

def integrity_player(pid, position, *, ppg, games, pct, schedule_pct, rostered=False, l14=None, season_ppg=None,
        prior=None, weight=None, opportunity=20):
    from app.features.waivers.contracts import RankingEvidence
    row = evidence_player(pid, position, value=pct, rostered=rostered)
    row.components.schedule, row.components.opportunity = schedule_pct, opportunity
    row.ranking_value = RankingEvidence(value=ppg, recent_weight=weight, historical_value=prior,
        historical_games=70 if prior is not None else 0, historical_season="2025-26" if prior is not None else None)
    row.recent = row.recent.model_copy(update={"value": ppg if l14 is None else l14, "season": "2026-27"})
    row.ros = ValueEvidence(value=ppg if season_ppg is None else season_ppg, games=15, season="2026-27",
        label="Season Evidence")
    row.schedule = Schedule(window_start=NOW.date(), window_end=NOW.date() + timedelta(days=6), games_remaining=games,
        coverage="PARTIAL", diagnostic_reason="SCHEDULE_ROWS_PRESENT")
    row.overall_score, row.effective_weights = aggregate(row.components, WEIGHTS)
    return row


def integrity_ctx(add, drop_ppg=30, drop_games=2, mode="next_7_days", extra=()):
    """Full two-slot roster (PG + C): an elite-production center with few games and a guard; `add` is a center."""
    drop = integrity_player(1, "C", ppg=drop_ppg, games=drop_games, pct=90, schedule_pct=10, rostered=True)
    keeper = integrity_player(2, "PG", ppg=20, games=3, pct=50, schedule_pct=50, rostered=True)
    ctx = roster_ctx([drop, keeper], [add, *extra], slots_of(PG=1, C=1), {1: "C", 2: "PG"}, mode=mode)
    assert ctx.roster_capacity.transaction_shape == "ADD_DROP"
    return ctx, drop


def test_lower_production_add_is_supported_only_with_quantified_window_arithmetic():
    add = integrity_player(11, "C", ppg=23, games=4, pct=70, schedule_pct=90)
    ctx, drop = integrity_ctx(add)
    pair = enrich(ctx, add, drop.player_id)
    explanation = pair.comparison.explanation
    assert pair.recommended_action == "STREAM" and pair.verdict == "SUPPORTED_ADD"
    # Exact arithmetic: weighted contributions reproduce the returned net.
    contributions = {row.component: row.weighted_contribution for row in explanation.contributions}
    assert sum(contributions.values()) == pytest.approx(pair.comparison.net_improvement, abs=1e-5)
    assert contributions["player_value"] == pytest.approx(-10 * .25 / .9, abs=1e-5)
    assert contributions["schedule"] == pytest.approx(40 * .15 / .9, abs=1e-5)
    assert explanation.favorable == ["schedule"] and explanation.compensating == ["schedule"] and not explanation.refuted
    # The compensating schedule claim holds in Yahoo fantasy points: 4 x 23 = 92 vs 2 x 30 = 60.
    assert (explanation.add_window_points, explanation.drop_window_points, explanation.window_points_gap) == (92, 60, 32)
    assert explanation.net_without["schedule"] < 0, "the move depends on schedule, and the card says so"
    assert explanation.statement.startswith(f"Although {add.player_name} scores 7.0 fewer Yahoo FP/G than {drop.player_name}")
    assert "2 more scheduled games in Next 7 Days (4 vs 2)" in explanation.statement
    assert "4 x 23.0 = 92.0 vs 2 x 30.0 = 60.0 Yahoo fantasy points (+32.0)" in explanation.statement
    assert not any(word in explanation.statement.lower() for word in ("role", "opportunity", "roster fit"))
    assert not explanation.fragile and "acquisition_value" in explanation.omitted
    # The same arithmetic with less than one add-game of margin is flagged FRAGILE, not hidden.
    add.ranking_value.value = 16
    fragile = compare(ctx, add, drop.player_id).explanation
    assert fragile.consistent and fragile.fragile and fragile.primary_tradeoff.startswith("FRAGILE: the window edge is +4.0")


def test_schedule_edge_that_loses_window_points_fails_closed_on_every_surface():
    from app.features.waivers.service import build_board
    add = integrity_player(11, "C", ppg=14, games=4, pct=70, schedule_pct=90)
    ctx, drop = integrity_ctx(add)
    pair = enrich(ctx, add, drop.player_id)
    assert pair.comparison.net_improvement > 0, "the index alone still favors the swap"
    assert pair.recommended_action == "INSUFFICIENT EVIDENCE", "4 x 14 = 56 < 2 x 30 = 60: never a supported move"
    explanation = pair.comparison.explanation
    assert explanation.refuted.keys() == {"schedule"} and not explanation.consistent
    assert explanation.reconciled_net < 0 and explanation.add_window_points == 56 and explanation.drop_window_points == 60
    assert pair.recommended_action == "INSUFFICIENT EVIDENCE" and pair.verdict == "DO_NOT_ADD"
    assert pair.verdict_text.startswith(f"DO NOT ADD — ADD {add.player_name} / DROP {drop.player_name} shows +")
    assert any(note.startswith("Explanation-consistency gate:") for note in pair.evidence_blockers)
    analysis = analyze_transactions(ctx)
    assert analysis.best_transaction is None and analysis.decision == "HOLD"
    assert any(reason.startswith("Explanation-consistency gate:") for reason in analysis.excluded_pair_reasons)
    assert all(swap.drop_player.player_id != drop.player_id for swap in analysis.watch_transactions)
    board_view = build_board(ctx, "fixture", "t1", ctx.mode, None)
    assert board_view.best_add_for_team_id is None
    assert next(row for row in board_view.roster if row.player_id == drop.player_id).roster_decision == "keep_on_measured_model"
    selected = build_board(ctx, "fixture", "t1", ctx.mode, drop.player_id)
    assert next(row for row in selected.candidates if row.player_id == add.player_id).verdict == "DO_NOT_ADD"


def test_role_edge_cannot_offset_a_production_loss_and_a_refuted_near_zero_net_is_not_a_tie():
    add = integrity_player(11, "C", ppg=23, games=2, pct=70, schedule_pct=10, opportunity=90)
    ctx, drop = integrity_ctx(add)
    pair = enrich(ctx, add, drop.player_id)
    assert pair.comparison.net_improvement > 0 and "opportunity" in pair.comparison.explanation.refuted
    assert pair.verdict == "DO_NOT_ADD" and pair.recommended_action == "INSUFFICIENT EVIDENCE"
    # A model net near zero only because a refuted schedule edge offsets a real loss is DO NOT ADD, never a near tie.
    weak = integrity_player(12, "C", ppg=14, games=4, pct=70, schedule_pct=10 + 2 * (10 * .25 / .9) / (.15 / .9) + .006)
    ctx, drop = integrity_ctx(weak)
    held = enrich(ctx, weak, drop.player_id)
    assert abs(held.comparison.net_improvement) < .005 and held.comparison.explanation.reconciled_net < -1
    assert not held.comparison.explanation.near_tie and held.verdict == "DO_NOT_ADD"
    # The tiny net keeps its sign and size in the text; it never reads as a "+0.00"/"-0.00" tie.
    assert f"{held.comparison.net_improvement:+.4f}" in held.verdict_text
    assert not any(token in held.verdict_text for token in ("+0.00 ", "-0.00 ", "+0.00.", "-0.00.", "+0.00,", "-0.00,"))


@pytest.mark.parametrize("delta", [.0005, -.0005])
def test_a_net_below_the_display_precision_is_a_near_tie_never_a_supported_move(delta):
    add = integrity_player(11, "C", ppg=30, games=2, pct=90 + 2 * delta / (.25 / .9), schedule_pct=10)
    ctx, drop = integrity_ctx(add)
    pair = enrich(ctx, add, drop.player_id)
    assert abs(pair.comparison.net_improvement) < .005
    assert pair.comparison.explanation.near_tie and pair.verdict == "NEAR_TIE"
    assert pair.verdict_text.startswith("NEAR TIE — NO STRONG PREFERENCE")
    assert pair.recommended_action_type not in {"ADD_DROP", "WATCH"}
    assert analyze_transactions(ctx).best_transaction is None


def blended_evidence(row, recent, earlier=(0, None), prior=None):
    """Attach weekly ranking evidence built by the production function itself."""
    from app.features.waivers.contracts import RankingEvidence
    from app.features.waivers.production import season_blend
    blend = season_blend(recent_games=recent[0], recent_value=recent[1], earlier_games=earlier[0],
        earlier_value=earlier[1], prior_games=prior[0] if prior else 0, prior_value=prior[1] if prior else None,
        prior_season="2025-26" if prior else None, season="2026-27")
    row.ranking_value = RankingEvidence(value=blend.value, recent_weight=blend.buckets[0].share,
        prior_weight=blend.prior_share if prior else None, historical_value=prior[1] if prior else None,
        historical_games=prior[0] if prior else 0, historical_season="2025-26" if prior else None, buckets=blend.buckets)
    row.recent = row.recent.model_copy(update={"value": recent[1], "games": recent[0], "season": "2026-27"})
    return row


def test_prior_season_driven_production_edge_stays_flagged_with_the_bucket_math():
    # Two current games beside a strong prior season still outrank a 14-game current-season producer.
    add = integrity_player(11, "C", ppg=26, games=2, pct=95, schedule_pct=10, l14=12, season_ppg=12)
    blended_evidence(add, recent=(2, 12.0), prior=(70, 40.0))
    ctx, drop = integrity_ctx(add, drop_ppg=14)
    blended_evidence(drop, recent=(7, 14.0), earlier=(7, 14.0))
    pair = enrich(ctx, add, drop.player_id)
    explanation = pair.comparison.explanation
    assert explanation.prior_season_driven and pair.verdict == "WATCH_ONLY", "a 2-game sample is never supported"
    assert explanation.add_production.basis == "CURRENT_SEASON_BLENDED"
    assert explanation.add_production.math == "(2 x 12.00 last 14 days + 2 x 40.00 2025-26) / 4 = 26.00"
    assert explanation.drop_production.basis == "CURRENT_SEASON_ONLY"
    assert explanation.drop_production.math == "(7 x 14.00 last 14 days + 7 x 14.00 earlier this season) / 14 = 14.00"
    assert explanation.primary_tradeoff == (f"PRIOR-SEASON DRIVEN: {add.player_name}'s 26.0 is 50% 2025-26 (40.0); "
        f"{drop.player_name}'s 14.0 has no prior-season component. On current-season evidence {add.player_name} "
        "trails: last 14 days 12.0 vs 14.0, this season 12.0 vs 14.0 Yahoo FP/G.")
    # The drop's prior can decide the order too: a weak prior that drags the drop below an add with no prior.
    rookie = integrity_player(12, "C", ppg=13, games=2, pct=95, schedule_pct=10, l14=13, season_ppg=13)
    blended_evidence(rookie, recent=(7, 13.0), earlier=(7, 13.0))
    ctx, drop = integrity_ctx(rookie, drop_ppg=14)
    blended_evidence(drop, recent=(1, 14.0), prior=(70, 4.0))
    flagged = enrich(ctx, rookie, drop.player_id).comparison.explanation
    assert flagged.prior_season_driven and flagged.primary_tradeoff.startswith("PRIOR-SEASON DRIVEN:")
    assert f"{drop.player_name}'s 7.3 is 67% 2025-26 (4.0)" in flagged.primary_tradeoff


def test_one_game_blend_shows_its_basis_and_weights():
    from app.features.waivers.explanation import production_basis
    row = evidence_player(11, "PG", games=1)
    blended_evidence(row, recent=(1, 3.2), prior=(44, 16.0))
    basis = production_basis(row, "this_week")
    assert basis.math == "(1 x 3.20 last 14 days + 2 x 16.00 2025-26) / 3 = 11.73"
    assert basis.prior_weight == pytest.approx(2 / 3, abs=1e-4) and basis.label.endswith("mostly previous-season evidence")
    assert [(bucket.key, bucket.games, bucket.weight_games) for bucket in basis.buckets] == [
        ("RECENT", 1, 1), ("EARLIER", 0, 0), ("PRIOR", 44, 2)]
    sample = next(item for item in evidence_dimensions_for(row) if item.key == "PRODUCTION_SAMPLE")
    assert sample.state == "TOO_SMALL" and sample.text.startswith("1-GAME SAMPLE — WATCH ONLY")


def evidence_dimensions_for(row, mode="this_week"):
    from app.features.waivers.service import evidence_dimensions
    ctx, _ = integrity_ctx(integrity_player(12, "C", ppg=20, games=2, pct=50, schedule_pct=50), mode=mode)
    return evidence_dimensions(ctx, row)


def test_form_windows_name_the_reason_a_value_is_missing_instead_of_na():
    from app.features.waivers.decision_support import option_form
    from app.features.waivers.service import recent_form
    def windows(logs, **context):
        form = recent_form(logs, None, None, YAHOO_FIELDS, NOW, NOW.date(), recent_quality=None, season_quality=None,
            starts=None, season_usage=None, **context)
        return {window.key: window for window in form.windows}
    recent_only = windows(form_logs([(20, 10)]))
    assert recent_only["LAST_30_DAYS"].fantasy_ppg is not None and recent_only["LAST_30_DAYS"].reason is None
    assert recent_only["LAST_7_DAYS"].reason_label == "No games played in window"
    assert recent_only["PREVIOUS_SEASON"].reason == "NO_PREVIOUS_SEASON"
    assert windows([], mapped=False)["LAST_14_DAYS"].reason_label == "Mapping unresolved"
    assert windows([], logs_current=False)["LAST_7_DAYS"].reason_label == "Data stale"
    assert windows([], logs_complete=False)["LAST_7_DAYS"].reason_label == "Game logs missing"
    partial = [PlayerGameLog(nba_player_id="form", game_id="x", season="2026-27", season_type="Regular Season",
        game_date=NOW.date(), stats_payload={"PTS": 10}, source_payload={}, imported_at=NOW)]
    assert windows(partial)["LAST_7_DAYS"].reason_label == "Required scoring field missing"
    row = with_form(evidence_player(11, "PG"), form_logs([(20, 10)]))
    compact = option_form(row)
    assert (compact.last_7_ppg, compact.last_7_reason, compact.last_30_reason) == (None, "No games played in window", None)


def test_lineup_gap_counts_dates_never_slot_instances():
    def player(pid, position, dates):
        row = evidence_player(pid, position, rostered=True)
        row.schedule = Schedule(window_start=NOW.date(), window_end=NOW.date() + timedelta(days=6), games_remaining=len(dates),
            coverage="PARTIAL", diagnostic_reason="SCHEDULE_ROWS_PRESENT", game_dates=[NOW.date() + timedelta(days=d) for d in dates])
        return row
    # Two C slots; the only centers play on days 0 and 1, so both C slots are open on the other five dates.
    roster = [player(1, "C", [0, 1]), player(2, "C", [0, 1]), player(3, "PG", range(7))]
    ctx = roster_ctx(roster, [], slots_of(PG=1, C=2), {1: "C", 2: "C", 3: "PG"})
    gap = next(need for need in ctx.team_needs.needs if need.slot == "C")
    assert (gap.kind, gap.count) == ("LINEUP_DAY_GAP", 5), "dates, never more than the 7 window dates"
    assert gap.slot_games == 10
    assert gap.reason == ("C has no lineup-eligible player with a persisted game on 5 of 7 dates in this window "
        "(10 open C slot-games across its 2 slots).")
    coverage = next(row for row in ctx.team_needs.slot_coverage if row.slot == "C")
    assert (coverage.open_slot_days, coverage.open_slot_games) == (5, 10)
    assert all(need.count <= len(ctx.team_needs.lineup_days) for need in ctx.team_needs.needs if need.kind == "LINEUP_DAY_GAP")


def test_schedule_rows_after_the_selected_horizon_never_count():
    today = NOW.date()
    rows = [SimpleNamespace(game_date=today + timedelta(days=day), game_status="Scheduled", opponent_team_id="B",
        imported_at=NOW) for day in (0, 3, 6, 7, 13, 20)]
    schedule = resolve_schedule(rows, today, today + timedelta(days=6), NOW, Counter(), {"B": "BOS"},
        nba_mapped=True, team_mapped=True)
    assert schedule.games_remaining == 3 and max(schedule.game_dates) <= today + timedelta(days=6)
    assert schedule.next_14_days_games == 5


def test_full_roster_other_good_options_name_the_exact_drop_and_a_qualified_verdict():
    supported = integrity_player(11, "C", ppg=33, games=3, pct=95, schedule_pct=60)
    second = integrity_player(12, "C", ppg=32, games=3, pct=93, schedule_pct=60)
    watch = integrity_player(13, "PG", ppg=34, games=3, pct=97, schedule_pct=60)
    watch.current_season_games = watch.recent.games = 3
    hold = integrity_player(14, "PG", ppg=5, games=3, pct=5, schedule_pct=60)
    ctx, drop = integrity_ctx(supported, extra=(second, watch, hold))
    support = support_ctx(ctx)
    candidates = board_candidates(support)
    decision = decision_support_for(support, candidates)
    options = options_by_id(decision)
    featured = {group.key: group for group in decision.groups if group.player_id is not None}
    assert featured, "groups feature players"
    for group in featured.values():
        option = options[group.player_id]
        assert option.pair is not None and option.pair.drop_player_id is not None, "a full-roster card names its drop"
        assert option.verdict == group.verdict and option.headline == option.verdict_text
        assert not any("Which roster player you would drop" in item for item in option.confirm)
        if option.verdict == "SUPPORTED_ADD":
            assert group.title.startswith("BEST SUPPORTED ")
        else:
            assert "—" in group.title and not group.title.startswith("BEST SUPPORTED")
    verdicts = {options[group.player_id].player_id: options[group.player_id].verdict for group in featured.values()}
    assert verdicts.get(second.player_id) == "SUPPORTED_ADD", "a second supported add is an other good option"
    assert verdicts.get(watch.player_id) == "WATCH_ONLY"
    assert options[watch.player_id].headline.startswith("WATCH ONLY — No supported positive add/drop combination was found.")
    held = enrich(support, hold)
    assert held.verdict == "DO_NOT_ADD" and held.verdict_text.endswith("Keep your current roster under this model.")


def test_roster_drop_labels_follow_the_same_gated_pair_decisions():
    from app.features.waivers.service import build_board
    watch = integrity_player(11, "C", ppg=33, games=3, pct=97, schedule_pct=60)
    watch.current_season_games = watch.recent.games = 3
    ctx, drop = integrity_ctx(watch)
    labels = {row.player_id: row.roster_decision for row in build_board(ctx, "fixture", "t1", ctx.mode, None).roster}
    assert labels[drop.player_id] == "watch_replacement", "positive but sample-blocked is WATCH, never 'unavailable'"
    watch.current_season_games = watch.recent.games = 7
    labels = {row.player_id: row.roster_decision for row in build_board(ctx, "fixture", "t1", ctx.mode, None).roster}
    assert labels[drop.player_id] == "review_replacement"
    watch.components.player_value = 1
    labels = {row.player_id: row.roster_decision for row in build_board(ctx, "fixture", "t1", ctx.mode, None).roster}
    assert labels[drop.player_id] == "keep_on_measured_model"


# --- 2026-11-21 Phase 7.1: gate-aware Compare a Specific Drop summary -------------------------------------------------
# Deployed-acceptance regression (read-only, 13 of 64 drop x horizon views): for an explicit drop the page named the
# highest raw-net pair "Top measured option" and answered INSUFFICIENT EVIDENCE although the explanation gate rejects
# that exact pair (DO NOT ADD); the answer is HOLD. Synthetic fixtures; nothing here names or protects a player.

def refuted_add(pid=11):
    """Raw net > 0 only from a schedule edge that loses Yahoo window points (4 x 14 = 56 < 2 x 30 = 60)."""
    return integrity_player(pid, "C", ppg=14, games=4, pct=70, schedule_pct=90)


def drop_board(ctx, drop):
    from app.features.waivers.service import build_board
    return build_board(ctx, "fixture", "t1", ctx.mode, drop.player_id)


def drop_summary_of(board_view, drop):
    summary = board_view.drop_summary
    assert summary is not None and summary.drop_player_id == drop.player_id
    assert summary.result == board_view.selected_player_result
    label = next(row.roster_decision for row in board_view.roster if row.player_id == drop.player_id)
    assert summary.decision == label, "the drop summary and the roster label are one gated decision"
    return summary


def test_explicit_drop_refuted_raw_leader_is_not_the_answer_and_the_drop_is_held():
    add = refuted_add()
    ctx, drop = integrity_ctx(add)
    board_view = drop_board(ctx, drop)
    row = board_view.candidates[0]
    explanation = row.comparison.explanation
    assert row.player_id == add.player_id and row.net_improvement > 0 > explanation.reconciled_net
    assert row.verdict == "DO_NOT_ADD" and row.recommended_action == "INSUFFICIENT EVIDENCE"
    assert board_view.selected_player_result == f"HOLD {drop.player_name}", "never INSUFFICIENT EVIDENCE"
    assert board_view.best_add_for_team_id is None
    summary = drop_summary_of(board_view, drop)
    assert summary.decision == "keep_on_measured_model" and summary.best_valid_replacement_id is None
    assert summary.headline == (f"No supported or WATCH replacement exists for DROP {drop.player_name}; 1 positive raw "
        f"model comparison did not pass the decision gates (1 DO NOT ADD). Keep {drop.player_name} under this model.")
    # The rejected pair stays visible as subordinate evidence, with its numbers and the gate that rejected it.
    raw = summary.highest_raw_comparison
    assert raw.candidate_id == add.player_id == board_view.top_measured_candidate_id
    assert raw.verdict == "DO_NOT_ADD" and raw.raw_net == row.net_improvement
    assert raw.reconciled_net == explanation.reconciled_net
    assert raw.reason == explanation.blocker and raw.reason.startswith("Explanation-consistency gate: ")


def test_explicit_drop_best_valid_replacement_is_the_first_supported_pair_in_gate_aware_order():
    from app.features.waivers.service import build_board
    refuted = refuted_add(11)
    supported = integrity_player(12, "C", ppg=33, games=2, pct=95, schedule_pct=10)
    twin = integrity_player(10, "C", ppg=33, games=2, pct=95, schedule_pct=10)
    watch = integrity_player(13, "C", ppg=34, games=2, pct=97, schedule_pct=10)
    watch.current_season_games = watch.recent.games = 3
    ctx, drop = integrity_ctx(refuted, extra=(supported, twin, watch))
    board_view = drop_board(ctx, drop)
    rows = {row.player_id: row for row in board_view.candidates}
    assert rows[11].net_improvement > rows[13].net_improvement > rows[12].net_improvement == rows[10].net_improvement > 0
    # The gate-aware tier precedes raw net; within a tier raw net, then the lower player ID.
    assert [(row.player_id, row.verdict) for row in board_view.candidates] == [
        (10, "SUPPORTED_ADD"), (12, "SUPPORTED_ADD"), (13, "WATCH_ONLY"), (11, "DO_NOT_ADD")]
    summary = drop_summary_of(board_view, drop)
    assert summary.decision == "review_replacement"
    assert summary.best_valid_replacement_id == board_view.best_add_for_team_id == 10
    assert summary.result == rows[10].recommended_action and summary.headline == rows[10].verdict_text
    raw = summary.highest_raw_comparison
    assert (raw.candidate_id, raw.verdict) == (11, "DO_NOT_ADD"), "the higher raw net never outranks the valid pair"
    best = analyze_transactions(ctx).best_transaction
    assert (best.add_player.player_id, best.drop_player.player_id) == (10, drop.player_id)
    assert build_board(ctx, "fixture", "t1", ctx.mode, None).drop_summary is None, "explicit drops only"


def test_explicit_drop_with_only_rejected_or_nonpositive_pairs_holds_instead_of_insufficient_evidence():
    refuted = refuted_add(11)
    weaker = integrity_player(12, "C", ppg=20, games=2, pct=60, schedule_pct=10)
    ctx, drop = integrity_ctx(refuted, extra=(weaker,))
    board_view = drop_board(ctx, drop)
    assert [(row.player_id, row.verdict) for row in board_view.candidates] == [(12, "DO_NOT_ADD"), (11, "DO_NOT_ADD")]
    assert board_view.candidates[0].net_improvement < 0 < board_view.candidates[1].net_improvement
    assert board_view.selected_player_result == f"HOLD {drop.player_name}"
    summary = drop_summary_of(board_view, drop)
    assert summary.decision == "keep_on_measured_model"
    assert summary.best_valid_replacement_id is None and summary.watch_candidate_id is None
    assert summary.highest_raw_comparison.candidate_id == 11


def test_explicit_drop_watch_only_answers_watch_and_is_never_promoted():
    refuted = refuted_add(11)
    watch = integrity_player(13, "C", ppg=34, games=2, pct=97, schedule_pct=10)
    watch.current_season_games = watch.recent.games = 3
    ctx, drop = integrity_ctx(refuted, extra=(watch,))
    board_view = drop_board(ctx, drop)
    rows = {row.player_id: row for row in board_view.candidates}
    assert board_view.selected_player_result == "WATCH" and board_view.best_add_for_team_id is None
    summary = drop_summary_of(board_view, drop)
    assert summary.decision == "watch_replacement" and summary.best_valid_replacement_id is None
    assert summary.watch_candidate_id == 13 and summary.headline == rows[13].verdict_text
    assert summary.headline.startswith("WATCH ONLY — ")
    assert summary.highest_raw_comparison.candidate_id == 11
    # When the WATCH pair is itself the raw leader there is nothing else to explain.
    watch.components.schedule = 90
    watch.overall_score, watch.effective_weights = aggregate(watch.components, WEIGHTS)
    summary = drop_summary_of(drop_board(ctx, drop), drop)
    assert summary.watch_candidate_id == 13 and summary.highest_raw_comparison is None


@pytest.mark.parametrize("delta", [.0005, -.0005])
def test_explicit_drop_near_tie_keeps_its_verdict_and_is_not_promoted(delta):
    add = integrity_player(11, "C", ppg=30, games=2, pct=90 + 2 * delta / (.25 / .9), schedule_pct=10)
    ctx, drop = integrity_ctx(add)
    board_view = drop_board(ctx, drop)
    row = board_view.candidates[0]
    assert row.verdict == "NEAR_TIE" and row.verdict_text.startswith("NEAR TIE — NO STRONG PREFERENCE")
    assert board_view.selected_player_result == f"HOLD {drop.player_name}"
    summary = drop_summary_of(board_view, drop)
    assert summary.decision == "keep_on_measured_model" and summary.best_valid_replacement_id is None
    raw = summary.highest_raw_comparison
    assert (raw.candidate_id, raw.verdict) == (11, "NEAR_TIE") and raw.reason.startswith("Near tie: ")


def test_explicit_drop_without_a_measured_comparison_cannot_be_evaluated():
    from app.features.waivers.service import build_board
    ctx = two_injured_in_il_context()
    injured = ctx.players[4]
    board_view = build_board(ctx, "fixture", "t1", ctx.mode, injured.player_id)
    assert board_view.candidates and all(row.net_improvement is None for row in board_view.candidates)
    assert board_view.top_measured_candidate_id is None
    assert board_view.selected_player_result == "CANNOT EVALUATE"
    summary = drop_summary_of(board_view, injured)
    assert summary.decision == "unavailable" and summary.highest_raw_comparison is None
    assert summary.best_valid_replacement_id is None and summary.watch_candidate_id is None
    assert summary.headline.startswith(f"No measured comparison exists for DROP {injured.player_name}: ")
    assert "occupies an injury slot" in summary.headline


def test_explicit_drop_summary_card_impact_and_verdict_are_one_exact_pair(monkeypatch):
    from app.features.waivers.service import evaluate_pair, get_impact, get_waivers
    refuted = refuted_add(11)
    supported = integrity_player(12, "C", ppg=33, games=2, pct=95, schedule_pct=10)
    ctx, drop = integrity_ctx(refuted, extra=(supported,))
    monkeypatch.setattr("app.features.waivers.service.load_context", AsyncMock(return_value=ctx))
    board_view = asyncio.run(get_waivers(None, "fixture", "t1", ctx.mode, drop.player_id))
    summary = drop_summary_of(board_view, drop)
    raw = summary.highest_raw_comparison
    assert (summary.best_valid_replacement_id, raw.candidate_id) == (12, 11)
    for pid in (12, 11):
        card = next(row for row in board_view.candidates if row.player_id == pid)
        impact = asyncio.run(get_impact(None, "fixture", "t1", pid, drop.player_id, ctx.mode))
        assert impact.comparison == impact.candidate.comparison == card.comparison
        assert impact.comparison.player_id == drop.player_id, "the selected drop stays fixed"
        assert (impact.candidate.verdict, impact.candidate.verdict_text) == (card.verdict, card.verdict_text)
        assert evaluate_pair(ctx, ctx.players[pid], drop.player_id).pair.comparison == card.comparison
    card = next(row for row in board_view.candidates if row.player_id == 11)
    assert (raw.raw_net, raw.reconciled_net, raw.verdict, raw.reason) == (card.comparison.net_improvement,
        card.comparison.explanation.reconciled_net, card.verdict, card.comparison.explanation.blocker)


def test_decision_modules_contain_no_player_specific_rules():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "app" / "features" / "waivers"
    names = ("Allen", "Dunn", "Jackson", "Keldon", "Dončić", "Doncic", "DeRozan", "Huerter")
    for module in ("service.py", "explanation.py", "decision_support.py", "sample.py", "capacity.py", "contracts.py",
            "production.py"):
        text = (root / module).read_text()
        assert not any(name in text for name in names), module


# --- 2026-11-24 audit: weekly production blend (model waiver-season-blend-phase8) ---------------------------------------
# Read-only audit of the persisted snapshot (qa-work/2026-11-24-weekly-blend-audit): the shipped weekly value shrank only
# the Last 14 Days toward the prior season with ten games of weight, so the prior kept at least 55% of every weekly value
# all season (the window never holds ten games) and earlier current-season games never counted; 11 SUPPORTED ADD pairs
# ranked an add above a drop who led on both Last 14 Days and the current season. Every current-season game now counts
# once, in exactly one bucket, and the prior season counts as PRIOR_GAMES games. Synthetic, name-neutral fixtures.

def previous_season(season):
    year = int(season[:4])
    return f"{year - 1}-{str(year)[-2:]}"


def reseed_season(f, name, *, recent, earlier, prior=None):
    """Replace `name`'s persisted current-season games. `recent` / `earlier` are (days before today, Yahoo points)
    tuples, one game each with its own game ID ({nba id}-r{i} / -e{i}): RECENT games fall inside the last 14 days and
    EARLIER games before them, so every game belongs to exactly one bucket. The current-season row matches the logs.
    `prior` = (games, points per game) adds the previous regular season."""
    async def change():
        async with SessionFactory() as session, session.begin():
            identity = await session.get(PlayerIdentity, f.ids[name])
            nba_id = identity.nba_player_id
            logs = list((await session.scalars(select(PlayerGameLog).where(PlayerGameLog.nba_player_id == nba_id))).all())
            season = logs[0].season
            for row in logs:
                await session.delete(row)
            current = (await session.scalars(select(NbaPlayerSeasonStats).where(
                NbaPlayerSeasonStats.nba_player_id == nba_id, NbaPlayerSeasonStats.season == season))).one()
            games = [*recent, *earlier]
            current.games_played = len(games)
            current.base_stats = {"PTS": round(sum(points for _, points in games) / len(games), 1) if games else 0}
            player = await session.get(NbaPlayer, nba_id)
            other = next(row for row in (await session.scalars(select(NbaTeam).where(
                NbaTeam.nba_team_id.like(f"{f.league.split('.')[1]}%")))).all() if row.nba_team_id != player.team_id)
            today = datetime.now(timezone.utc).astimezone(WAIVER_TIMEZONE).date()
            for prefix, rows in (("r", recent), ("e", earlier)):
                for index, (days, points) in enumerate(rows):
                    game_id, played = f"{nba_id}-{prefix}{index}", today - timedelta(days=days)
                    session.add(NbaGame(game_id=game_id, season=season, game_date=played, home_team_id=player.team_id,
                        away_team_id=other.nba_team_id, source_payload={}, imported_at=datetime.now(timezone.utc)))
                    await session.flush()
                    session.add(PlayerGameLog(nba_player_id=nba_id, game_id=game_id, season=season,
                        season_type="Regular Season", game_date=played, stats_payload={"PTS": points, "MIN": 30},
                        source_payload={}, imported_at=datetime.now(timezone.utc)))
            if prior is not None:
                await session.merge(NbaPlayerSeasonStats(nba_player_id=nba_id, season=previous_season(season),
                    season_type="Regular Season", games_played=prior[0], games_started=prior[0],
                    base_stats={"PTS": prior[1]}, advanced_stats={}, source_payload={},
                    imported_at=datetime.now(timezone.utc)))
        await engine.dispose()
    asyncio.run(change())


def test_weekly_value_counts_every_current_season_game_once_on_every_surface(persisted):
    f = persisted
    drop_status_field(f, "star", "center", "guard", "weak")
    # Add (star): Last 14 Days 7 x 16, earlier 6 x 19, prior season 77 games at 30. Drop (weak): 7 x 17, 7 x 29.5, 82
    # games at 20.5. The add trails on Last 14 Days (16 < 17) and this season (17.4 < 23.3); the old blend still put it
    # ahead (24.24 vs 19.06) because the prior kept 59% of both values.
    reseed_season(f, "star", recent=[(day, 16) for day in range(1, 8)], earlier=[(day, 19) for day in range(20, 26)],
        prior=(77, 30))
    reseed_season(f, "weak", recent=[(day, 17) for day in range(1, 8)], earlier=[(day, 29.5) for day in range(20, 27)],
        prior=(82, 20.5))
    # A clear upgrade on every view, so the optimizer reports a supported pair against the same drop.
    reseed_season(f, "center", recent=[(day, 40) for day in range(1, 8)], earlier=[(day, 38) for day in range(20, 25)],
        prior=(70, 35))
    today = datetime.now(timezone.utc).astimezone(WAIVER_TIMEZONE).date()
    result = board(f)
    rows = {row["player_name"]: row for row in [*result["candidates"], *result["roster"]]}
    star, weak, center = rows["star"], rows["weak"], rows["center"]
    assert star["ranking_value"]["value"] == pytest.approx((7 * 16 + 6 * 19 + 2 * 30) / 15)
    assert weak["ranking_value"]["value"] == pytest.approx((7 * 17 + 7 * 29.5 + 2 * 20.5) / 16)
    assert center["ranking_value"]["value"] == pytest.approx((7 * 40 + 5 * 38 + 2 * 35) / 14)
    assert star["ranking_value"]["value"] < weak["ranking_value"]["value"], "both current views favor the drop"
    from app.features.waivers.production import PRIOR_GAMES
    assert PRIOR_GAMES == 2
    buckets = {row["key"]: row for row in star["ranking_value"]["buckets"]}
    assert [row["key"] for row in star["ranking_value"]["buckets"]] == ["RECENT", "EARLIER", "PRIOR"]
    assert [(buckets[key]["games"], buckets[key]["weight_games"]) for key in ("RECENT", "EARLIER", "PRIOR")] == [
        (7, 7), (6, 6), (77, 2)]
    assert [buckets[key]["value"] for key in ("RECENT", "EARLIER", "PRIOR")] == [16, 19, 30]
    assert [buckets[key]["share"] for key in ("RECENT", "EARLIER", "PRIOR")] == pytest.approx([7 / 15, 6 / 15, 2 / 15],
        abs=1e-4)
    assert buckets["PRIOR"]["season"] == previous_season(buckets["RECENT"]["season"])
    # Each game in exactly one bucket: RECENT is the Last 14 Days window, EARLIER ends before it; together they are the
    # whole current season.
    assert (buckets["RECENT"]["first_game"], buckets["RECENT"]["last_game"]) == (
        (today - timedelta(days=7)).isoformat(), (today - timedelta(days=1)).isoformat())
    assert (buckets["EARLIER"]["first_game"], buckets["EARLIER"]["last_game"]) == (
        (today - timedelta(days=25)).isoformat(), (today - timedelta(days=20)).isoformat())
    windows = {row["key"]: row for row in star["form"]["windows"]}
    assert buckets["RECENT"]["games"] == windows["LAST_14_DAYS"]["games"] == star["recent"]["games"] == 7
    assert buckets["RECENT"]["games"] + buckets["EARLIER"]["games"] == windows["CURRENT_SEASON"]["games"] == 13
    assert star["sample"]["relevant_games"] == 7, "the eligibility sample is still the Last 14 Days"

    impact = f.client.get(f"/api/v1/waivers/{f.ids['star']}/impact", params={"drop_player_id": f.ids["weak"]}).json()
    explanation = impact["comparison"]["explanation"]
    add_basis = explanation["add_production"]
    assert add_basis["basis"] == "CURRENT_SEASON_BLENDED" and add_basis["buckets"] == star["ranking_value"]["buckets"]
    assert add_basis["math"] == "(7 x 16.00 last 14 days + 6 x 19.00 earlier this season + 2 x 30.00 2025-26) / 15 = 19.07"
    assert "weight" not in add_basis["math"] and "10/" not in add_basis["math"]
    contributions = {row["component"]: row["weighted_contribution"] for row in explanation["contributions"]}
    assert contributions["player_value"] < 0, "an established current season is not reversed by the old season"
    assert not explanation["prior_season_driven"]
    assert not any(text.startswith("PRIOR-SEASON DRIVEN") for text in explanation["tradeoffs"])
    # One production basis on every surface: board, optimizer, replacements, impact and the decision-support details.
    analysis = f.client.get("/api/v1/waivers/transactions").json()
    best = analysis["best_transaction"]
    assert (best["add_player"]["player_id"], best["drop_player"]["player_id"]) == (f.ids["center"], f.ids["weak"])
    replacements = {row["player_id"]: row for row in board(f, drop_player_id=f.ids["weak"])["candidates"]}
    center_impact = f.client.get(f"/api/v1/waivers/{f.ids['center']}/impact",
        params={"drop_player_id": f.ids["weak"]}).json()
    assert best["comparison"] == replacements[f.ids["center"]]["comparison"] == center_impact["comparison"]
    assert best["add_player"]["ranking_value"] == center["ranking_value"] == center_impact["candidate"]["ranking_value"]
    assert replacements[f.ids["star"]]["comparison"] == impact["comparison"]
    assert replacements[f.ids["star"]]["ranking_value"] == impact["candidate"]["ranking_value"] == star["ranking_value"]
    assert center_impact["comparison"]["explanation"]["drop_production"] == explanation["drop_production"]
    options = {row["player_id"]: row for row in result["decision_support"]["options"]}
    assert options[f.ids["star"]]["measured"]["value"] == round(star["ranking_value"]["value"], 2)
    assert options[f.ids["star"]]["measured"]["buckets"] == star["ranking_value"]["buckets"]
    assert options[f.ids["star"]]["measured"]["current_games"] == 13
    # The weekly value does not depend on the horizon; only schedule does.
    for mode in ("next_7_days", "next_14_days"):
        other = next(row for row in board(f, mode=mode)["candidates"] if row["player_id"] == f.ids["star"])
        assert other["ranking_value"] == star["ranking_value"]
    f.no_yahoo.assert_not_called()


def test_weekly_value_needs_current_games_and_never_lets_the_prior_stand_in(persisted):
    f = persisted
    # No game in the last 14 days: the weekly ranking stays unavailable (the eligibility rule is unchanged); decision
    # support still describes the season, every earlier game counted once beside the prior.
    reseed_season(f, "star", recent=[], earlier=[(day, 30) for day in range(16, 25)], prior=(70, 40))
    result = board(f)
    star = next(row for row in result["candidates"] if row["player_id"] == f.ids["star"])
    assert star["ranking_value"]["value"] is None and star["components"]["player_value"] is None
    option = next(row for row in result["decision_support"]["options"] if row["player_id"] == f.ids["star"])
    measured = option["measured"]
    assert measured["basis"] == "CURRENT_SEASON" and measured["current_games"] == 9
    assert measured["value"] == pytest.approx((9 * 30 + 2 * 40) / 11, abs=0.01)
    assert [(row["key"], row["games"]) for row in measured["buckets"]] == [("RECENT", 0), ("EARLIER", 9), ("PRIOR", 70)]
    assert measured["buckets"][0]["value"] is None and measured["buckets"][0]["share"] == 0, "empty is never zero"
    assert any("No persisted games in the last 14 days" in item for item in option["blockers"])
    # No current-season game at all: the prior season alone never becomes a current value.
    reseed_season(f, "star", recent=[], earlier=[], prior=(70, 40))
    result = board(f)
    star = next(row for row in result["candidates"] if row["player_id"] == f.ids["star"])
    option = next(row for row in result["decision_support"]["options"] if row["player_id"] == f.ids["star"])
    assert star["ranking_value"]["value"] is None and option["measured"]["value"] is None
    assert option["measured"]["detail"].startswith("No current-season NBA games")
    f.no_yahoo.assert_not_called()


def test_season_blend_counts_each_game_once_and_the_prior_decays_with_every_game():
    from app.features.waivers.production import PRIOR_GAMES, season_blend

    def blend(recent=(0, None), earlier=(0, None), prior=(0, None)):
        return season_blend(recent_games=recent[0], recent_value=recent[1], earlier_games=earlier[0],
            earlier_value=earlier[1], prior_games=prior[0], prior_value=prior[1], prior_season="2025-26")

    # Tiny current sample: the prior still stabilizes it (one 5-point game beside a 30-point season).
    tiny = blend(recent=(1, 5.0), prior=(70, 30.0))
    assert tiny.value == pytest.approx((5 + 2 * 30) / 3) and tiny.prior_share == pytest.approx(2 / 3)
    # Growing current season: the prior's share falls with every game, and the value converges to this season.
    shares, values = [], []
    for games in range(1, 83):
        row = blend(recent=(min(games, 7), 20.0), earlier=(max(games - 7, 0), 20.0 if games > 7 else None),
            prior=(70, 40.0))
        shares.append(row.prior_share)
        values.append(row.value)
        assert row.prior_share == pytest.approx(PRIOR_GAMES / (games + PRIOR_GAMES))
    assert all(later < earlier for earlier, later in zip(shares, shares[1:]))
    assert all(20 < later < earlier for earlier, later in zip(values, values[1:]))
    # Recent breakout and slump move the value by exactly their own games, never a second time through the season mean.
    steady = blend(earlier=(10, 20.0), prior=(70, 20.0))
    breakout = blend(recent=(5, 40.0), earlier=(10, 20.0), prior=(70, 20.0))
    slump = blend(recent=(5, 5.0), earlier=(10, 20.0), prior=(70, 20.0))
    assert steady.value == pytest.approx(20)
    assert breakout.value == pytest.approx((5 * 40 + 10 * 20 + 2 * 20) / 17)
    assert slump.value == pytest.approx((5 * 5 + 10 * 20 + 2 * 20) / 17)
    assert slump.value < steady.value < breakout.value
    for row in (breakout, slump):
        shares = {bucket.key: bucket.share for bucket in row.buckets}  # presentation-rounded to 4 decimals
        assert shares["RECENT"] == pytest.approx(5 / 17, abs=1e-4) and shares["EARLIER"] == pytest.approx(10 / 17, abs=1e-4)
        assert sum(shares.values()) == pytest.approx(1, abs=1e-3)
        assert row.current_games == 15 and row.current_value == pytest.approx((5 * row.buckets[0].value + 200) / 15)
    # Missing prior season: the current season alone, unchanged; missing earlier bucket: deterministic two-bucket mean.
    rookie = blend(recent=(3, 25.0), earlier=(9, 15.0))
    assert rookie.value == pytest.approx((3 * 25 + 9 * 15) / 12) and rookie.prior_share == 0
    assert [bucket.key for bucket in rookie.buckets] == ["RECENT", "EARLIER", "PRIOR"]
    assert rookie.buckets[2].games == 0 and rookie.buckets[2].value is None and rookie.buckets[2].share == 0
    early = blend(recent=(2, 50.0), prior=(60, 10.0))
    assert early.value == pytest.approx((2 * 50 + 2 * 10) / 4) == blend(recent=(2, 50.0), prior=(60, 10.0)).value
    assert early.buckets[1].games == 0 and early.buckets[1].value is None and early.buckets[1].share == 0
    # No current-season evidence: no value, whatever the prior; a bucket with games but no Yahoo value fails honestly.
    assert blend(prior=(82, 45.0)).value is None
    assert blend(recent=(4, 20.0), earlier=(3, None), prior=(70, 30.0)).value is None
    assert blend(recent=(4, None), prior=(70, 30.0)).value is None


def test_a_better_production_estimate_never_turns_a_small_recent_sample_into_a_supported_add():
    from app.features.waivers.production import season_blend
    from app.features.waivers.contracts import RankingEvidence
    for recent_games in (1, 2, 3, 4):
        add = integrity_player(11, "C", ppg=38, games=4, pct=99, schedule_pct=90)
        blend = season_blend(recent_games=recent_games, recent_value=40.0, earlier_games=14, earlier_value=38.0,
            prior_games=70, prior_value=36.0, prior_season="2025-26")
        add.ranking_value = RankingEvidence(value=blend.value, recent_weight=blend.buckets[0].share,
            prior_weight=blend.prior_share, historical_value=36.0, historical_games=70, historical_season="2025-26",
            buckets=blend.buckets)
        add.recent = add.recent.model_copy(update={"games": recent_games})
        add.current_season_games = 14 + recent_games
        add.sample = None
        ctx, drop = integrity_ctx(add)
        pair = enrich(ctx, add, drop.player_id)
        assert pair.comparison.net_improvement > 0 and pair.comparison.explanation.consistent
        assert pair.verdict == "WATCH_ONLY" and pair.recommended_action_type == "WATCH", recent_games
        assert any(note.startswith("Sample gate: ") for note in pair.evidence_blockers)
        assert analyze_transactions(ctx).best_transaction is None

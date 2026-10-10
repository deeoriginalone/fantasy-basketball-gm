from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import asyncio
import httpx
import pytest

from app.services.draft.market_diagnostics import (
    build_market_coverage_report,
    summarize_unmatched_records,
)
from app.services.draft.market_providers.fantrax import (
    FANTRAX_ADP_URL,
    FantraxDraftMarketProvider,
    FantraxTransientError,
    parse_fantrax_adp,
)
from app.services.draft.market_sync import match_market_records
from app.services.draft.market_providers.yahoo import parse_yahoo_player_payloads


def test_parse_fantrax_records_preserves_only_published_market_fields() -> None:
    fetched_at = datetime(2026, 10, 10, tzinfo=timezone.utc)
    records = parse_fantrax_adp(
        [{"id": "03e75", "name": "Jokic, Nikola", "pos": "C", "ADP": 1.44}],
        "2026-27",
        player_metadata={"03e75": {"fantraxId": "03e75", "team": "DEN", "position": "C"}},
        fetched_at=fetched_at,
    )
    assert len(records) == 1
    assert records[0].source_player_id == "03e75"
    assert records[0].player_name == "Jokic, Nikola"
    assert records[0].team == "DEN"
    assert records[0].positions == ("C",)
    assert records[0].adp == 1.44
    assert records[0].draft_rank is None
    assert records[0].xrank is None
    assert records[0].draft_frequency is None
    assert records[0].sample_size is None
    assert records[0].fetched_at == fetched_at
    assert records[0].source_updated_at is None


def test_fantrax_identity_matching_rejects_ambiguous_and_unmatched_players() -> None:
    records = parse_fantrax_adp([
        {"id": "1", "name": "Smith, John", "pos": "PG", "ADP": 25},
        {"id": "2", "name": "Unknown, Player", "pos": "C", "ADP": 90},
        {"id": "3", "name": "Roe, Jane", "pos": "SG", "ADP": 75},
    ], "2026-27", player_metadata={
        "1": {"fantraxId": "1", "team": "BOS", "position": "PG"},
        "2": {"fantraxId": "2", "team": "DEN", "position": "C"},
        "3": {"fantraxId": "3", "team": "FA", "position": "SG"},
    })
    identities = [
        {"id": 101, "player_name": "John Smith", "position": "PG", "team": "BOS"},
        {"id": 102, "player_name": "John Smith", "position": "PG,SG", "team": "BOS"},
    ]
    matches, ambiguous, unmatched = match_market_records(records, identities)
    assert matches == []
    assert ambiguous == 1
    assert unmatched == 2


def test_fantrax_team_alias_and_suffix_normalization_still_requires_unique_match() -> None:
    records = parse_fantrax_adp([
        {"id": "1", "name": "Towns, Karl-Anthony", "pos": "C", "ADP": 17},
        {"id": "2", "name": "Murphy, Trey", "pos": "SF", "ADP": 32},
    ], "2026-27", player_metadata={
        "1": {"fantraxId": "1", "team": "NY", "position": "C"},
        "2": {"fantraxId": "2", "team": "NO", "position": "SF"},
    })
    identities = [
        {"id": 201, "player_name": "Karl-Anthony Towns", "position": "PF,C", "team": "NYK"},
        {"id": 202, "player_name": "Trey Murphy III", "position": "SF,PF", "team": "NOP"},
    ]
    matches, ambiguous, unmatched = match_market_records(records, identities)
    assert [(record.internal_player_id, player_id) for record, player_id in matches] == [
        (201, 201), (202, 202)
    ]
    assert ambiguous == 0
    assert unmatched == 0


@pytest.mark.parametrize("payload", [[], {}, [{"id": "x", "name": "A Player", "pos": "PG", "ADP": "nan"}]])
def test_parse_fantrax_rejects_invalid_or_empty_feed(payload) -> None:
    with pytest.raises(ValueError):
        parse_fantrax_adp(payload, "2026-27")


def test_fantrax_provider_retries_rate_limit_without_logging_response_data(caplog) -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        assert request.url.params.get("sport") == "NBA"
        if request.url.path.endswith("getAdp"):
            attempts += 1
            if attempts == 1:
                return httpx.Response(429, headers={"Retry-After": "0"}, text="private")
            return httpx.Response(200, json=[{"id": "03e75", "name": "Jokic, Nikola", "pos": "C", "ADP": 1.44}])
        return httpx.Response(200, json={
            "03e75": {"fantraxId": "03e75", "name": "Jokic, Nikola", "team": "DEN", "position": "C"}
        })

    provider = FantraxDraftMarketProvider(
        transport=httpx.MockTransport(respond),
        base_retry_delay=0,
    )
    records = asyncio.run(provider.fetch("2026-27"))
    assert attempts == 2
    assert records[0].adp == 1.44
    assert records[0].team == "DEN"
    assert "private" not in caplog.text


def test_fantrax_provider_stops_after_bounded_transport_retries() -> None:
    attempts = 0

    def timeout(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("timed out", request=request)

    provider = FantraxDraftMarketProvider(
        transport=httpx.MockTransport(timeout),
        max_attempts=2,
        base_retry_delay=0,
    )
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(provider.fetch("2026-27"))
    assert attempts == 2


def test_yahoo_rank_and_ownership_do_not_become_adp_or_draft_frequency() -> None:
    parsed = parse_yahoo_player_payloads(
        [{
            "player_key": "nba.p.123",
            "name": {"full": "Example Player"},
            "editorial_team_abbr": "BOS",
            "eligible_positions": ["PG", "SG"],
            "rank": 12,
            "percent_owned": 85,
        }],
        "2026-27",
        fetched_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    assert parsed == []


def test_yahoo_market_fields_remain_separate_and_unmatched() -> None:
    fetched_at = datetime(2026, 10, 10, tzinfo=timezone.utc)
    parsed = parse_yahoo_player_payloads(
        [{
            "player_key": "nba.p.123",
            "name": {"full": "Example Player"},
            "editorial_team_abbr": "BOS",
            "eligible_positions": ["SG", "PG"],
            "adp": 22.5,
            "draft_rank": 20,
            "xrank": 18.0,
            "draft_frequency": 74,
            "sample_size": 40,
        }],
        "2026-27",
        fetched_at=fetched_at,
    )
    assert len(parsed) == 1
    assert parsed[0].internal_player_id is None
    assert parsed[0].adp == 22.5
    assert parsed[0].draft_rank == 20
    assert parsed[0].xrank == 18
    assert parsed[0].draft_frequency == 74
    assert parsed[0].sample_size == 40
    assert parsed[0].positions == ("PG", "SG")
    assert parsed[0].fetched_at == fetched_at


def test_yahoo_zero_draft_frequency_is_valid() -> None:
    parsed = parse_yahoo_player_payloads(
        [{
            "player_key": "nba.p.123",
            "name": {"full": "Example Player"},
            "adp": 180,
            "draft_frequency": 0,
        }],
        "2026-27",
        fetched_at=datetime(2026, 10, 10, tzinfo=timezone.utc),
    )
    assert parsed[0].draft_frequency == 0


def test_market_diagnostics_preserve_unknown_freshness_and_report_coverage() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    rows = [SimpleNamespace(
        player_id=101,
        adp=22.5,
        draft_rank=20,
        draft_frequency=None,
        last_updated=now - timedelta(hours=2),
    )]
    latest_run = SimpleNamespace(
        status="success",
        completed_at=now - timedelta(hours=1),
        provider_records_fetched=1,
        matched_players=1,
        ambiguous_matches=0,
        unmatched_players=0,
    )
    report = build_market_coverage_report([101, 102], rows, now=now, latest_run=latest_run)
    assert report["provider_records_fetched"] == 1
    assert report["matched_players"] == 1
    assert report["ambiguous_matches"] == 0
    assert report["adp_coverage_percentage"] == 50
    assert report["rank_coverage_percentage"] == 50
    assert report["draft_frequency_coverage_percentage"] == 0
    assert report["stale_records"] == 0
    assert report["source_age_seconds"] is None
    assert report["latest_successful_retrieval_age_seconds"] == 3600
    assert report["players_missing_market_data"] == [102]
    assert report["players_missing_adp"] == [102]


def test_market_diagnostics_reports_failed_attempt_and_last_success_separately() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    rows = [SimpleNamespace(
        player_id=101,
        adp=22.5,
        draft_rank=None,
        draft_frequency=None,
        last_updated=now - timedelta(hours=1),
    )]
    last_success = SimpleNamespace(
        status="success",
        completed_at=now - timedelta(hours=1),
        provider_records_fetched=1,
        matched_players=1,
        ambiguous_matches=0,
        unmatched_players=0,
    )
    latest_attempt = SimpleNamespace(status="failed", error_type="TimeoutError")
    report = build_market_coverage_report(
        [101], rows, now=now, latest_run=last_success, latest_attempt=latest_attempt
    )
    assert report["provider_status"] == "failed"
    assert report["latest_attempt_error_type"] == "TimeoutError"
    assert report["matched_players"] == 1
    assert report["latest_successful_retrieval_age_seconds"] == 3600


def test_unmatched_diagnostics_retain_record_identity_reason_and_staleness() -> None:
    now = datetime(2026, 10, 10, tzinfo=timezone.utc)
    report = summarize_unmatched_records([
        SimpleNamespace(
            source_player_id="fx-1",
            player_name="Example Player",
            team=None,
            positions=["C"],
            adp=200.0,
            rejection_reason="source_team_missing",
            fetched_at=now - timedelta(days=3),
        ),
    ], now=now)
    assert report["unmatched_provider_record_count"] == 1
    assert report["unmatched_provider_records_by_reason"] == {"source_team_missing": 1}
    assert report["unmatched_provider_records_stale"] == 1
    assert report["unmatched_provider_records"][0]["source_player_id"] == "fx-1"
    assert report["unmatched_provider_records"][0]["rejection_reason"] == "source_team_missing"
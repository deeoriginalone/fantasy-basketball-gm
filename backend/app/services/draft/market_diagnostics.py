import argparse
import asyncio
import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, engine
from app.features.draft.models import (
    DraftMarketData,
    DraftMarketSyncRun,
    DraftMarketUnmatchedRecord,
)
from app.features.players.models import PlayerIdentity
from app.services.draft.market_sync import MARKET_STALE_AFTER

MARKET_SOURCE = "fantrax"


def _field(row: Any, name: str) -> Any:
    return row.get(name) if isinstance(row, Mapping) else getattr(row, name)


def summarize_unmatched_records(
    unmatched_rows: Iterable[Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    if now.tzinfo is None:
        raise ValueError("now must include a timezone")
    rows = list(unmatched_rows)
    reasons = Counter(_field(row, "rejection_reason") for row in rows)
    stale_records = 0
    details = []
    for row in rows:
        fetched_at = _field(row, "fetched_at")
        if fetched_at.tzinfo is None:
            fetched_at = fetched_at.replace(tzinfo=timezone.utc)
        if now - fetched_at > MARKET_STALE_AFTER:
            stale_records += 1
        details.append({
            "source_player_id": _field(row, "source_player_id"),
            "player_name": _field(row, "player_name"),
            "team": _field(row, "team"),
            "positions": _field(row, "positions"),
            "adp": _field(row, "adp"),
            "rejection_reason": _field(row, "rejection_reason"),
            "fetched_at": fetched_at.isoformat(),
        })
    return {
        "unmatched_provider_record_count": len(rows),
        "unmatched_provider_records_by_reason": dict(sorted(reasons.items())),
        "unmatched_provider_records_stale": stale_records,
        "unmatched_provider_records": details,
    }


def build_market_coverage_report(
    player_ids: Iterable[int],
    market_rows: Iterable[Any],
    *,
    now: datetime | None = None,
    latest_run: Any | None = None,
    latest_attempt: Any | None = None,
    unmatched_rows: Iterable[Any] = (),
) -> dict[str, Any]:
    identity_ids = sorted(set(player_ids))
    rows = list(market_rows)
    rows_by_player: dict[int, list[Any]] = {}
    for row in rows:
        rows_by_player.setdefault(_field(row, "player_id"), []).append(row)

    denominator = len(identity_ids)

    def coverage(field: str) -> float:
        covered = sum(
            any(_field(row, field) is not None for row in rows_by_player.get(player_id, []))
            for player_id in identity_ids
        )
        return round(100.0 * covered / denominator, 2) if denominator else 0.0

    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        raise ValueError("now must include a timezone")
    latest_local_update = max((_field(row, "last_updated") for row in rows), default=None)
    if latest_local_update is not None and latest_local_update.tzinfo is None:
        latest_local_update = latest_local_update.replace(tzinfo=timezone.utc)
    latest_run_completed = _field(latest_run, "completed_at") if latest_run is not None else None
    if latest_run_completed is not None and latest_run_completed.tzinfo is None:
        latest_run_completed = latest_run_completed.replace(tzinfo=timezone.utc)
    age_seconds = (
        max(0, int((current_time - latest_run_completed).total_seconds()))
        if latest_run_completed is not None and _field(latest_run, "status") == "success"
        else None
    )
    stale_records = sum(
        latest_local_update is not None
        and (current_time - (
            _field(row, "last_updated").replace(tzinfo=timezone.utc)
            if _field(row, "last_updated").tzinfo is None
            else _field(row, "last_updated")
        )).total_seconds() > MARKET_STALE_AFTER.total_seconds()
        for row in rows
    )

    players_with_rows = set(rows_by_player)
    players_with_adp = {
        player_id for player_id, player_rows in rows_by_player.items()
        if any(_field(row, "adp") is not None for row in player_rows)
    }
    return {
        "provider_status": (
            _field(latest_attempt, "status") if latest_attempt is not None
            else "available_not_yet_synced"
        ),
        "latest_attempt_error_type": (
            _field(latest_attempt, "error_type") if latest_attempt is not None else None
        ),
        "selected_provider": MARKET_SOURCE,
        "provider_records_fetched": (
            _field(latest_run, "provider_records_fetched") if latest_run is not None else None
        ),
        "stored_market_rows": len(rows),
        "matched_players": _field(latest_run, "matched_players") if latest_run is not None else None,
        "ambiguous_matches": _field(latest_run, "ambiguous_matches") if latest_run is not None else None,
        "unmatched_players": _field(latest_run, "unmatched_players") if latest_run is not None else None,
        "coverage_population": denominator,
        "adp_coverage_percentage": coverage("adp"),
        "rank_coverage_percentage": coverage("draft_rank"),
        "draft_frequency_coverage_percentage": coverage("draft_frequency"),
        "stale_records": stale_records,
        "freshness_policy": "stale after 48 hours from successful retrieval",
        "source_age_seconds": None,
        "source_age_note": "The provider publishes no source-updated timestamp; retrieval age is available instead.",
        "latest_successful_retrieval_age_seconds": age_seconds,
        "players_missing_market_data": sorted(set(identity_ids) - players_with_rows),
        "players_missing_adp": sorted(set(identity_ids) - players_with_adp),
        **summarize_unmatched_records(unmatched_rows, now=current_time),
    }


async def collect_market_diagnostics(session: AsyncSession, season: str) -> dict[str, Any]:
    player_ids = list((await session.scalars(select(PlayerIdentity.__table__.c.id))).all())
    market_rows = list((await session.execute(
        select(DraftMarketData.__table__).where(
            DraftMarketData.__table__.c.season == season,
            DraftMarketData.__table__.c.source == MARKET_SOURCE,
        )
    )).mappings().all())
    run_table = DraftMarketSyncRun.__table__
    latest_attempt = (await session.execute(
        select(run_table)
        .where(run_table.c.season == season, run_table.c.source == MARKET_SOURCE)
        .order_by(run_table.c.completed_at.desc())
        .limit(1)
    )).mappings().first()
    latest_run = (await session.execute(
        select(run_table)
        .where(
            run_table.c.season == season,
            run_table.c.source == MARKET_SOURCE,
            run_table.c.status == "success",
        )
        .order_by(run_table.c.completed_at.desc())
        .limit(1)
    )).mappings().first()
    unmatched_table = DraftMarketUnmatchedRecord.__table__
    unmatched_rows = list((await session.execute(
        select(unmatched_table).where(
            unmatched_table.c.season == season,
            unmatched_table.c.source == MARKET_SOURCE,
        ).order_by(unmatched_table.c.rejection_reason, unmatched_table.c.player_name)
    )).mappings().all())
    return {
        "season": season,
        **build_market_coverage_report(
            player_ids,
            market_rows,
            latest_run=latest_run,
            latest_attempt=latest_attempt,
            unmatched_rows=unmatched_rows,
        ),
    }


async def _run(season: str) -> None:
    async with SessionFactory() as session:
        report = await collect_market_diagnostics(session, season)
    print(json.dumps(report, sort_keys=True))
    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read-only draft market coverage and freshness diagnostics")
    parser.add_argument("--season", required=True, help="NBA season, e.g. 2026-27")
    args = parser.parse_args()
    asyncio.run(_run(args.season))


if __name__ == "__main__":
    main()
import argparse
import asyncio
import json
import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, engine, initialize_schema
from app.features.draft.models import (
    DraftMarketData,
    DraftMarketProviderSnapshot,
    DraftMarketSyncRun,
    DraftMarketUnmatchedRecord,
)
from app.features.players.models import PlayerIdentity
from app.services.draft.market_providers.base import DraftMarketProvider, DraftMarketRecord
from app.services.draft.market_providers.fantrax import FantraxDraftMarketProvider

logger = logging.getLogger(__name__)
MARKET_STALE_AFTER = timedelta(hours=48)
TEAM_ABBREVIATION_ALIASES = {
    "NY": "NYK",
    "PHO": "PHX",
    "GS": "GSW",
    "SA": "SAS",
    "NO": "NOP",
}
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def _normalized_name(value: str) -> str:
    name = value.strip()
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(char for char in decomposed if not unicodedata.combining(char))
    parts = re.sub(r"[^a-z0-9]+", " ", ascii_name.lower()).split()
    while parts and parts[-1] in NAME_SUFFIXES:
        parts.pop()
    return " ".join(parts)


def _normalized_team(value: str | None) -> str | None:
    if value is None:
        return None
    team = value.strip().upper()
    return TEAM_ABBREVIATION_ALIASES.get(team, team)


def _expanded_positions(positions: Iterable[str] | str | None) -> set[str]:
    if isinstance(positions, str):
        values = re.split(r"[,/]", positions)
    else:
        values = positions or []
    expanded: set[str] = set()
    for value in values:
        position = str(value).strip().upper()
        if position == "G":
            expanded.update(("PG", "SG"))
        elif position == "F":
            expanded.update(("SF", "PF"))
        elif position == "SGF":
            expanded.update(("SG", "SF"))
        elif position == "PFC":
            expanded.update(("PF", "C"))
        elif position:
            expanded.add(position)
    return expanded


def match_market_records_detailed(
    records: Iterable[DraftMarketRecord],
    identities: Iterable[Any],
) -> tuple[list[tuple[DraftMarketRecord, int]], dict[str, list[DraftMarketRecord]]]:
    identities_by_name: dict[str, list[Any]] = defaultdict(list)
    for identity in identities:
        name = identity.get("player_name") if hasattr(identity, "get") else identity.player_name
        identities_by_name[_normalized_name(str(name))].append(identity)

    matches: list[tuple[DraftMarketRecord, int]] = []
    rejected: dict[str, list[DraftMarketRecord]] = defaultdict(list)
    matched_player_ids: set[int] = set()
    for record in records:
        candidates = identities_by_name.get(_normalized_name(record.player_name), [])
        source_team = _normalized_team(record.team) or ""
        if source_team in {"", "FA", "N/A", "(N/A)", "FREE AGENT"}:
            rejected["source_team_missing"].append(record)
            continue
        candidates = [
            identity for identity in candidates
            if _normalized_team(identity.get("team") if hasattr(identity, "get") else identity.team)
            == source_team
        ]
        source_positions = _expanded_positions(record.positions)
        candidates = [
            identity for identity in candidates
            if source_positions & _expanded_positions(
                identity.get("position") if hasattr(identity, "get") else identity.position
            )
        ]
        if len(candidates) == 1:
            identity = candidates[0]
            player_id = identity.get("id") if hasattr(identity, "get") else identity.id
            player_id = int(player_id)
            if player_id in matched_player_ids:
                rejected["duplicate_internal_player_match"].append(record)
            else:
                matches.append((replace(record, internal_player_id=player_id), player_id))
                matched_player_ids.add(player_id)
        elif len(candidates) > 1:
            rejected["ambiguous_name_team_position"].append(record)
        else:
            if not identities_by_name.get(_normalized_name(record.player_name)):
                reason = "no_name_match"
            elif not any(
                _normalized_team(identity.get("team") if hasattr(identity, "get") else identity.team)
                == source_team
                for identity in identities_by_name[_normalized_name(record.player_name)]
            ):
                reason = "team_mismatch"
            else:
                reason = "position_mismatch"
            rejected[reason].append(record)
    return matches, dict(rejected)


def match_market_records(
    records: Iterable[DraftMarketRecord],
    identities: Iterable[Any],
) -> tuple[list[tuple[DraftMarketRecord, int]], int, int]:
    matches, rejected = match_market_records_detailed(records, identities)
    ambiguous = sum(
        len(rejected.get(reason, []))
        for reason in ("ambiguous_name_team_position", "duplicate_internal_player_match")
    )
    unmatched = sum(
        len(records) for reason, records in rejected.items()
        if reason not in {"ambiguous_name_team_position", "duplicate_internal_player_match"}
    )
    return matches, ambiguous, unmatched


def _coverage(count: int, denominator: int) -> float:
    return round(100.0 * count / denominator, 2) if denominator else 0.0


async def sync_market_data(
    session: AsyncSession,
    provider: DraftMarketProvider,
    season: str,
    *,
    started_at: datetime | None = None,
) -> dict[str, Any]:
    started = started_at or datetime.now(timezone.utc)
    records = list(await provider.fetch(season))
    if not records:
        raise ValueError("Provider returned no draft-market records")
    if any(record.season != season or record.source != provider.name for record in records):
        raise ValueError("Provider returned records for an unexpected season or source")
    if any(record.adp is None for record in records):
        raise ValueError("Provider returned a market record without ADP")

    identity_table = PlayerIdentity.__table__
    identities = list((await session.execute(select(identity_table))).mappings().all())
    matches, rejected_records = match_market_records_detailed(records, identities)
    ambiguous = sum(
        len(rejected_records.get(reason, []))
        for reason in ("ambiguous_name_team_position", "duplicate_internal_player_match")
    )
    unmatched = sum(
        len(rejected) for reason, rejected in rejected_records.items()
        if reason not in {"ambiguous_name_team_position", "duplicate_internal_player_match"}
    )
    matched_at = datetime.now(timezone.utc)
    market_rows = [{
        "player_id": player_id,
        "season": season,
        "source": record.source,
        "adp": record.adp,
        "draft_rank": record.draft_rank,
        "draft_frequency": record.draft_frequency,
        "last_updated": record.fetched_at,
    } for record, player_id in matches]
    snapshot_rows = [{
        "player_id": player_id,
        "season": season,
        "source": record.source,
        "source_player_id": record.source_player_id,
        "player_name": record.player_name,
        "team": record.team,
        "positions": list(record.positions),
        "xrank": record.xrank,
        "sample_size": record.sample_size,
        "fetched_at": record.fetched_at,
        "source_updated_at": record.source_updated_at,
    } for record, player_id in matches]
    unresolved_rows = [{
        "source_player_id": record.source_player_id,
        "season": season,
        "source": provider.name,
        "player_name": record.player_name,
        "team": record.team,
        "positions": list(record.positions),
        "adp": record.adp,
        "rejection_reason": reason,
        "fetched_at": record.fetched_at,
    } for reason, rejected in rejected_records.items() for record in rejected]

    if market_rows:
        table = DraftMarketData.__table__
        statement = insert(table).values(market_rows)
        statement = statement.on_conflict_do_update(
            index_elements=[table.c.player_id, table.c.season, table.c.source],
            set_={key: getattr(statement.excluded, key) for key in (
                "adp", "draft_rank", "draft_frequency", "last_updated"
            )},
        )
        await session.execute(statement)

        snapshot_table = DraftMarketProviderSnapshot.__table__
        snapshot_statement = insert(snapshot_table).values(snapshot_rows)
        snapshot_statement = snapshot_statement.on_conflict_do_update(
            index_elements=[
                snapshot_table.c.player_id,
                snapshot_table.c.season,
                snapshot_table.c.source,
            ],
            set_={key: getattr(snapshot_statement.excluded, key) for key in (
                "source_player_id", "player_name", "team", "positions", "xrank",
                "sample_size", "fetched_at", "source_updated_at",
            )},
        )
        await session.execute(snapshot_statement)

    unmatched_table = DraftMarketUnmatchedRecord.__table__
    matched_source_ids = [record.source_player_id for record, _ in matches]
    if matched_source_ids:
        await session.execute(unmatched_table.delete().where(
            unmatched_table.c.season == season,
            unmatched_table.c.source == provider.name,
            unmatched_table.c.source_player_id.in_(matched_source_ids),
        ))
    if unresolved_rows:
        unresolved_statement = insert(unmatched_table).values(unresolved_rows)
        unresolved_statement = unresolved_statement.on_conflict_do_update(
            index_elements=[
                unmatched_table.c.source_player_id,
                unmatched_table.c.season,
                unmatched_table.c.source,
            ],
            set_={key: getattr(unresolved_statement.excluded, key) for key in (
                "player_name", "team", "positions", "adp", "rejection_reason", "fetched_at",
            )},
        )
        await session.execute(unresolved_statement)

    market_table = DraftMarketData.__table__
    current_rows = list((await session.execute(select(market_table).where(
        market_table.c.season == season,
        market_table.c.source == provider.name,
    ))).mappings().all())
    now = datetime.now(timezone.utc)
    adp_players = {row["player_id"] for row in current_rows if row["adp"] is not None}
    rank_players = {row["player_id"] for row in current_rows if row["draft_rank"] is not None}
    frequency_players = {
        row["player_id"] for row in current_rows if row["draft_frequency"] is not None
    }
    stale_records = sum(
        (now - row["last_updated"]).total_seconds() > MARKET_STALE_AFTER.total_seconds()
        for row in current_rows
    )
    identity_ids = {int(identity["id"]) for identity in identities}
    matched_ids = {player_id for _, player_id in matches}
    completed_at = datetime.now(timezone.utc)
    latest_fetched_at = max(record.fetched_at for record in records)
    source_retrieval_age_seconds = max(
        0, int((now - latest_fetched_at).total_seconds())
    )
    report = {
        "season": season,
        "provider_status": "success",
        "selected_provider": provider.name,
        "provider_records_fetched": len(records),
        "matched_players": len(matches),
        "ambiguous_matches": ambiguous,
        "unmatched_players": unmatched,
        "unmatched_by_reason": {
            reason: len(rejected) for reason, rejected in rejected_records.items()
        },
        "adp_coverage_percentage": _coverage(len(adp_players & identity_ids), len(identity_ids)),
        "rank_coverage_percentage": _coverage(len(rank_players & identity_ids), len(identity_ids)),
        "draft_frequency_coverage_percentage": _coverage(
            len(frequency_players & identity_ids), len(identity_ids)
        ),
        "stale_records": stale_records,
        "source_age_seconds": None,
        "source_age_note": "Fantrax does not publish a source-updated timestamp.",
        "latest_successful_retrieval_age_seconds": source_retrieval_age_seconds,
        "source_updated_at": None,
        "freshness_policy": "stale after 48 hours from successful retrieval",
        "players_missing_market_data": sorted(identity_ids - matched_ids),
        "players_missing_adp": sorted(identity_ids - adp_players),
    }
    session.add(DraftMarketSyncRun(
        season=season,
        source=provider.name,
        status="success",
        started_at=started,
        completed_at=completed_at,
        provider_records_fetched=len(records),
        matched_players=len(matches),
        ambiguous_matches=ambiguous,
        unmatched_players=unmatched,
        adp_coverage_percentage=report["adp_coverage_percentage"],
        rank_coverage_percentage=report["rank_coverage_percentage"],
        draft_frequency_coverage_percentage=report["draft_frequency_coverage_percentage"],
        stale_records=stale_records,
        source_updated_at=None,
        error_type=None,
    ))
    await session.flush()
    return report


async def record_market_sync_failure(
    session: AsyncSession,
    season: str,
    source: str,
    started_at: datetime,
    error: Exception,
) -> None:
    session.add(DraftMarketSyncRun(
        season=season,
        source=source,
        status="failed",
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        provider_records_fetched=None,
        matched_players=None,
        ambiguous_matches=None,
        unmatched_players=None,
        adp_coverage_percentage=None,
        rank_coverage_percentage=None,
        draft_frequency_coverage_percentage=None,
        stale_records=None,
        source_updated_at=None,
        error_type=type(error).__name__[:80],
    ))
    await session.flush()


async def _run(season: str) -> int:
    await initialize_schema()
    provider = FantraxDraftMarketProvider()
    started_at = datetime.now(timezone.utc)
    try:
        async with SessionFactory() as session:
            async with session.begin():
                report = await sync_market_data(session, provider, season, started_at=started_at)
    except Exception as error:
        logger.error(
            "Fantrax market sync failed",
            extra={"event": "fantrax_market_sync_failed", "error_type": type(error).__name__},
        )
        async with SessionFactory() as session:
            async with session.begin():
                await record_market_sync_failure(
                    session, season, provider.name, started_at, error
                )
        print(json.dumps({"season": season, "selected_provider": provider.name,
                          "provider_status": "failed", "error_type": type(error).__name__}))
        await engine.dispose()
        return 1
    print(json.dumps(report, sort_keys=True))
    await engine.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync current Fantrax NBA ADP into draft-market storage")
    parser.add_argument("--season", required=True, help="NBA season, e.g. 2026-27")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(_run(args.season)))


if __name__ == "__main__":
    main()
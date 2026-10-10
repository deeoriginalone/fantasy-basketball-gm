import argparse
import asyncio
import csv
import re
import sys
from math import isfinite
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionFactory, engine, initialize_schema
from app.features.draft.models import DraftMarketData
from app.features.players.models import PlayerIdentity


def _optional_float(value: Any, field: str, *, minimum: float | None = None, maximum: float | None = None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError as error:
        raise ValueError(f"Invalid {field}: {text}") from error
    if not isfinite(number):
        raise ValueError(f"{field} must be finite")
    if minimum is not None and number < minimum:
        raise ValueError(f"{field} must be at least {minimum}")
    if maximum is not None and number > maximum:
        raise ValueError(f"{field} must be at most {maximum}")
    return number


def _optional_int(value: Any, field: str) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        number = int(text)
    except ValueError as error:
        raise ValueError(f"Invalid {field}: {text}") from error
    if number <= 0:
        raise ValueError(f"{field} must be positive")
    return number


def parse_market_rows(rows: list[dict[str, Any]], season: str, source: str) -> list[dict[str, Any]]:
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season must use YYYY-YY format")
    source = source.strip()
    if not source or len(source) > 80:
        raise ValueError("source must contain 1 to 80 characters")
    normalized = []
    seen_player_ids = set()
    for line_number, row in enumerate(rows, start=2):
        try:
            player_id = int(str(row.get("player_id", "")).strip())
        except ValueError as error:
            raise ValueError(f"Line {line_number}: player_id must be an internal player identity ID") from error
        if player_id <= 0:
            raise ValueError(f"Line {line_number}: player_id must be positive")
        if player_id in seen_player_ids:
            raise ValueError(f"Line {line_number}: duplicate player_id {player_id}")
        seen_player_ids.add(player_id)

        adp = _optional_float(row.get("adp"), "adp", minimum=0.001)
        draft_rank = _optional_int(row.get("draft_rank"), "draft_rank")
        draft_frequency = _optional_float(row.get("draft_frequency"), "draft_frequency", minimum=0, maximum=100)
        if adp is None and draft_rank is None and draft_frequency is None:
            raise ValueError(f"Line {line_number}: provide at least one of adp, draft_rank, or draft_frequency")
        normalized.append({
            "player_id": player_id,
            "season": season,
            "source": source,
            "adp": adp,
            "draft_rank": draft_rank,
            "draft_frequency": draft_frequency,
            "last_updated": datetime.now(timezone.utc),
        })
    if not normalized:
        raise ValueError("CSV contains no market rows")
    return normalized


async def import_market_rows(session: AsyncSession, rows: list[dict[str, Any]]) -> int:
    player_ids = {row["player_id"] for row in rows}
    identities = set((await session.scalars(
        select(PlayerIdentity.id).where(PlayerIdentity.id.in_(player_ids))
    )).all())
    missing = player_ids - identities
    if missing:
        raise ValueError(f"Unknown internal player identity IDs: {sorted(missing)[:10]}")
    statement = insert(DraftMarketData).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[DraftMarketData.player_id, DraftMarketData.season, DraftMarketData.source],
        set_={key: getattr(statement.excluded, key) for key in (
            "adp", "draft_rank", "draft_frequency", "last_updated"
        )},
    )
    await session.execute(statement)
    await session.flush()
    return len(rows)


async def _run(args: argparse.Namespace) -> int:
    await initialize_schema()
    rows = parse_market_rows(list(csv.DictReader(sys.stdin)), args.season, args.source)
    async with SessionFactory() as session:
        async with session.begin():
            imported = await import_market_rows(session, rows)
    print(f"market_rows_upserted={imported} season={args.season} source={args.source}")
    await engine.dispose()
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import manual/player-provider draft market CSV from stdin")
    parser.add_argument("--season", required=True, help="NBA season, e.g. 2026-27")
    parser.add_argument("--source", required=True, help="Market data source label, e.g. manual or provider-name")
    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()

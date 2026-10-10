import re
from datetime import datetime, timezone
from math import isfinite
from typing import Any

from app.services.draft.market_providers.base import DraftMarketRecord

YAHOO_SOURCE = "yahoo-fantasy"


def _number(
    value: Any,
    field: str,
    *,
    minimum: float = 0,
    allow_minimum: bool = False,
) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid Yahoo {field}") from error
    below_minimum = parsed < minimum or (parsed == minimum and not allow_minimum)
    if not isfinite(parsed) or below_minimum:
        comparison = "at least" if allow_minimum else "greater than"
        raise ValueError(f"Yahoo {field} must be finite and {comparison} {minimum}")
    return parsed


def _positive_int(value: Any, field: str) -> int | None:
    parsed = _number(value, field)
    if parsed is None:
        return None
    if not parsed.is_integer():
        raise ValueError(f"Yahoo {field} must be an integer")
    return int(parsed)


def _name(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("full")
    return str(value or "").strip()


def _positions(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict):
        value = value.get("position", value.get("positions", []))
    if isinstance(value, str):
        values = value.replace("/", ",").split(",")
    elif isinstance(value, list):
        values = [entry.get("position", "") if isinstance(entry, dict) else entry for entry in value]
    else:
        values = []
    return tuple(sorted({str(position).strip().upper() for position in values if str(position).strip()}))


def _source_updated_at(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("Invalid Yahoo source_updated_at") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_yahoo_player_payloads(
    payloads: list[dict[str, Any]],
    season: str,
    *,
    fetched_at: datetime | None = None,
) -> list[DraftMarketRecord]:
    if not re.fullmatch(r"\d{4}-\d{2}", season):
        raise ValueError("season must use YYYY-YY format")
    retrieval_time = fetched_at or datetime.now(timezone.utc)
    if retrieval_time.tzinfo is None:
        raise ValueError("fetched_at must include a timezone")

    records = []
    for payload in payloads:
        player = payload.get("player", payload)
        if not isinstance(player, dict):
            continue

        adp = _number(player.get("adp"), "adp")
        draft_rank = _positive_int(player.get("draft_rank"), "draft_rank")
        xrank = _number(player.get("xrank"), "xrank")
        frequency = player.get("draft_frequency")
        draft_frequency = _number(frequency, "draft_frequency", allow_minimum=True)
        if draft_frequency is not None and draft_frequency > 100:
            raise ValueError("Yahoo draft_frequency must be at most 100")
        sample_size = _positive_int(player.get("sample_size"), "sample_size")
        if all(value is None for value in (adp, draft_rank, xrank, draft_frequency, sample_size)):
            continue

        source_player_id = str(player.get("player_key") or player.get("player_id") or "").strip()
        player_name = _name(player.get("name"))
        if not source_player_id or not player_name:
            raise ValueError("Yahoo market record is missing its player ID or name")
        records.append(DraftMarketRecord(
            internal_player_id=None,
            source_player_id=source_player_id,
            player_name=player_name,
            team=str(player.get("editorial_team_abbr") or "").strip() or None,
            positions=_positions(player.get("eligible_positions") or player.get("display_position")),
            adp=adp,
            draft_rank=draft_rank,
            xrank=xrank,
            draft_frequency=draft_frequency,
            sample_size=sample_size,
            source=YAHOO_SOURCE,
            season=season,
            fetched_at=retrieval_time,
            source_updated_at=_source_updated_at(player.get("source_updated_at")),
        ))
    return records
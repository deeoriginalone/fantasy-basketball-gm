from typing import Any

from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.models import NbaTeam


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_team(record: dict[str, Any]) -> dict[str, Any]:
    team_id = _text(record.get("id") or record.get("TEAM_ID"))
    abbreviation = _text(record.get("abbreviation") or record.get("TEAM_ABBREVIATION"))
    full_name = _text(record.get("full_name") or record.get("TEAM_NAME"))
    if not team_id or not abbreviation or not full_name:
        raise HTTPException(status_code=502, detail="nba_api returned a team without its required identity fields")
    year_founded = record.get("year_founded")
    try:
        year_founded = int(year_founded) if year_founded is not None else None
    except (TypeError, ValueError):
        year_founded = None
    return {
        "nba_team_id": team_id,
        "abbreviation": abbreviation.upper(),
        "full_name": full_name,
        "city": _text(record.get("city") or record.get("TEAM_CITY")),
        "nickname": _text(record.get("nickname")),
        "state": _text(record.get("state")),
        "year_founded": year_founded,
        "source_payload": record,
    }


async def import_teams(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> int:
    teams_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        team = normalize_team(record)
        existing = teams_by_id.get(team["nba_team_id"])
        if existing is not None and existing["abbreviation"] != team["abbreviation"]:
            raise HTTPException(status_code=502, detail="nba_api returned conflicting records for one team ID")
        teams_by_id[team["nba_team_id"]] = team
    if not teams_by_id:
        raise HTTPException(status_code=502, detail="nba_api returned no teams")

    rows = list(teams_by_id.values())
    statement = insert(NbaTeam).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[NbaTeam.nba_team_id],
        set_={key: getattr(statement.excluded, key) for key in (
            "abbreviation", "full_name", "city", "nickname", "state", "year_founded", "source_payload", "imported_at"
        )},
    )
    await session.execute(statement)
    await session.flush()
    return len(rows)

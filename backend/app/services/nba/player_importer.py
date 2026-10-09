from collections import defaultdict
import re
from typing import Any
import unicodedata

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.models import NbaPlayer, NbaTeam
from app.features.players.models import PlayerIdentity


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _id(value: Any) -> str | None:
    text = _text(value)
    if text in (None, "0", "0.0"):
        return None
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    return text


def _name_key(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", decomposed.casefold()).split())


def normalize_player(record: dict[str, Any]) -> dict[str, Any]:
    player_id = _id(record.get("PERSON_ID") or record.get("nba_player_id"))
    player_name = _text(record.get("DISPLAY_FIRST_LAST") or record.get("player_name"))
    if not player_id or not player_name:
        raise HTTPException(status_code=502, detail="nba_api returned a player without its required identity fields")
    team_id = _id(record.get("TEAM_ID") or record.get("team_id"))
    team_abbreviation = _text(record.get("TEAM_ABBREVIATION") or record.get("team_abbreviation"))
    try:
        roster_status = int(record["ROSTERSTATUS"]) if record.get("ROSTERSTATUS") is not None else None
    except (TypeError, ValueError):
        roster_status = None
    return {
        "nba_player_id": player_id,
        "player_name": player_name,
        "team_id": team_id,
        "team_abbreviation": team_abbreviation.upper() if team_abbreviation else None,
        "roster_status": roster_status,
        "from_year": _text(record.get("FROM_YEAR")),
        "to_year": _text(record.get("TO_YEAR")),
        "source_payload": record,
    }


async def link_player_identities(session: AsyncSession) -> int:
    team_rows = list((await session.scalars(select(NbaTeam))).all())
    valid_abbreviations = {team.abbreviation for team in team_rows}
    nba_players = list((await session.scalars(select(NbaPlayer))).all())
    source_candidates: dict[tuple[str, str], list[str]] = defaultdict(list)
    for player in nba_players:
        abbreviation = player.team_abbreviation
        name_key = _name_key(player.player_name)
        if abbreviation in valid_abbreviations and name_key:
            source_candidates[(name_key, abbreviation)].append(player.nba_player_id)

    identities = list((await session.scalars(select(PlayerIdentity))).all())
    identity_candidates: dict[tuple[str, str], list[PlayerIdentity]] = defaultdict(list)
    assigned_nba_ids = {identity.nba_player_id for identity in identities if identity.nba_player_id}
    for identity in identities:
        team = _text(identity.team)
        name_key = _name_key(identity.player_name)
        if identity.nba_player_id is None and team and team.upper() in valid_abbreviations and name_key:
            identity_candidates[(name_key, team.upper())].append(identity)

    mappings_added = 0
    for key, source_ids in source_candidates.items():
        candidates = identity_candidates.get(key, [])
        if len(source_ids) != 1 or len(candidates) != 1:
            continue
        nba_player_id = source_ids[0]
        if nba_player_id in assigned_nba_ids:
            continue
        candidates[0].nba_player_id = nba_player_id
        assigned_nba_ids.add(nba_player_id)
        mappings_added += 1
    await session.flush()
    return mappings_added


async def import_players(
    session: AsyncSession,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    players_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        player = normalize_player(record)
        existing = players_by_id.get(player["nba_player_id"])
        if existing is not None and (
            existing["player_name"] != player["player_name"]
            or existing["team_abbreviation"] != player["team_abbreviation"]
        ):
            raise HTTPException(status_code=502, detail="nba_api returned conflicting records for one player ID")
        players_by_id[player["nba_player_id"]] = player
    if not players_by_id:
        raise HTTPException(status_code=502, detail="nba_api returned no current-season players")

    team_rows = list((await session.scalars(select(NbaTeam))).all())
    teams_by_id = {team.nba_team_id: team.abbreviation for team in team_rows}
    for player in players_by_id.values():
        if player["team_id"] not in teams_by_id:
            player["team_id"] = None

    rows = list(players_by_id.values())
    statement = insert(NbaPlayer).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[NbaPlayer.nba_player_id],
        set_={key: getattr(statement.excluded, key) for key in (
            "player_name", "team_id", "team_abbreviation", "roster_status", "from_year", "to_year", "source_payload", "imported_at"
        )},
    )
    await session.execute(statement)
    await session.flush()
    mappings_added = await link_player_identities(session)
    return len(players_by_id), mappings_added

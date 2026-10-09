from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.models import NbaGame, NbaPlayer, NbaTeam, PlayerGameLog


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


def _game_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _text(value)
    if text:
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
        except ValueError:
            for date_format in ("%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(text, date_format).date()
                except ValueError:
                    pass
    raise HTTPException(status_code=502, detail="nba_api returned a game log without a valid date")


def normalize_game_log(record: dict[str, Any], season: str) -> dict[str, Any]:
    nba_player_id = _id(record.get("PLAYER_ID") or record.get("nba_player_id"))
    game_id = _text(record.get("GAME_ID") or record.get("game_id"))
    game_date = _game_date(record.get("GAME_DATE") or record.get("game_date"))
    if not nba_player_id or not game_id:
        raise HTTPException(status_code=502, detail="nba_api returned a game log without player/game IDs")
    team_id = _id(record.get("TEAM_ID") or record.get("team_id"))
    season_type = _text(record.get("SEASON_TYPE") or record.get("season_type")) or "Regular Season"
    stats_payload = {
        key: value
        for key, value in record.items()
        if key not in {"PLAYER_ID", "GAME_ID", "GAME_DATE", "SEASON_TYPE"}
    }
    return {
        "nba_player_id": nba_player_id,
        "game_id": game_id,
        "season": season,
        "season_type": season_type,
        "game_date": game_date,
        "team_id": team_id,
        "stats_payload": stats_payload,
        "source_payload": record,
    }


async def import_game_logs(
    session: AsyncSession,
    season: str,
    records: list[dict[str, Any]],
) -> tuple[int, int]:
    logs_by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        log = normalize_game_log(record, season)
        key = (log["nba_player_id"], log["game_id"])
        existing = logs_by_key.get(key)
        if existing is not None and existing["stats_payload"] != log["stats_payload"]:
            raise HTTPException(status_code=502, detail="nba_api returned conflicting records for one player game")
        logs_by_key[key] = log
    if not logs_by_key:
        return 0, 0

    teams = list((await session.scalars(select(NbaTeam))).all())
    teams_by_id = {team.nba_team_id: team.abbreviation for team in teams}
    existing_player_ids = set((await session.scalars(select(NbaPlayer.nba_player_id))).all())
    supplemental_players: dict[str, dict[str, Any]] = {}
    for log in logs_by_key.values():
        player_id = log["nba_player_id"]
        if player_id in existing_player_ids:
            continue
        source_record = log["source_payload"]
        player_name = _text(source_record.get("PLAYER_NAME"))
        if not player_name:
            raise HTTPException(status_code=502, detail="nba_api game log omitted a name for an unlisted player")
        team_id = log["team_id"] if log["team_id"] in teams_by_id else None
        player = {
            "nba_player_id": player_id,
            "player_name": player_name,
            "team_id": team_id,
            "team_abbreviation": teams_by_id.get(team_id) if team_id else None,
            "roster_status": None,
            "from_year": None,
            "to_year": None,
            "source_payload": {"source": "nba_api.LeagueGameLog", "record": source_record},
        }
        existing = supplemental_players.get(player_id)
        if existing is not None and existing["player_name"] != player_name:
            raise HTTPException(status_code=502, detail="nba_api returned conflicting names for a log-only player")
        supplemental_players[player_id] = player

    if supplemental_players:
        statement = insert(NbaPlayer).values(list(supplemental_players.values()))
        statement = statement.on_conflict_do_nothing(index_elements=[NbaPlayer.nba_player_id])
        await session.execute(statement)
        await session.flush()

    player_ids = set((await session.scalars(select(NbaPlayer.nba_player_id))).all())
    game_ids = set((await session.scalars(select(NbaGame.game_id))).all())
    team_ids = set(teams_by_id)
    if any(player_id not in player_ids or game_id not in game_ids for player_id, game_id in logs_by_key):
        raise HTTPException(status_code=502, detail="nba_api game logs referenced a player/game absent from prior imports")

    rows = list(logs_by_key.values())
    for row in rows:
        if row["team_id"] not in team_ids:
            row["team_id"] = None
    statement = insert(PlayerGameLog).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[PlayerGameLog.nba_player_id, PlayerGameLog.game_id],
        set_={key: getattr(statement.excluded, key) for key in (
            "season", "season_type", "game_date", "team_id", "stats_payload", "source_payload", "imported_at"
        )},
    )
    await session.execute(statement)
    await session.flush()
    return len(rows), len(supplemental_players)

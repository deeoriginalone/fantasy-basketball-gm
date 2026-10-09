from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.models import NbaGame, NbaPlayer, NbaTeam, PlayerSchedule

BULK_INSERT_BATCH_SIZE = 500


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


def _game_date(record: dict[str, Any]) -> date:
    value = record.get("gameDateEst") or record.get("gameDate") or record.get("GAME_DATE")
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
    raise HTTPException(status_code=502, detail="nba_api returned a game without a valid date")


def normalize_game(record: dict[str, Any], season: str) -> dict[str, Any]:
    game_id = _text(record.get("gameId") or record.get("GAME_ID"))
    home_team_id = _id(record.get("homeTeam_teamId") or record.get("HOME_TEAM_ID"))
    away_team_id = _id(record.get("awayTeam_teamId") or record.get("VISITOR_TEAM_ID") or record.get("AWAY_TEAM_ID"))
    if not game_id or (home_team_id and home_team_id == away_team_id):
        raise HTTPException(status_code=502, detail="nba_api returned a game without valid game/team IDs")
    return {
        "game_id": game_id,
        "season": season,
        "game_date": _game_date(record),
        "game_status": _text(record.get("gameStatusText") or record.get("GAME_STATUS_TEXT") or record.get("gameStatus")),
        "home_team_id": home_team_id,
        "away_team_id": away_team_id,
        "source_payload": record,
    }


async def rebuild_player_schedule(
    session: AsyncSession,
    season: str,
    as_of: date,
) -> int:
    games = list((await session.scalars(
        select(NbaGame).where(NbaGame.season == season).order_by(NbaGame.game_date, NbaGame.game_id)
    )).all())
    players = list((await session.execute(select(NbaPlayer.nba_player_id, NbaPlayer.team_id))).all())
    player_rows = []
    for nba_player_id, team_id in players:
        if not team_id:
            continue
        for game in games:
            if game.game_date < as_of or not game.home_team_id or not game.away_team_id:
                continue
            if team_id == game.home_team_id:
                opponent_team_id, is_home = game.away_team_id, True
            elif team_id == game.away_team_id:
                opponent_team_id, is_home = game.home_team_id, False
            else:
                continue
            player_rows.append({
                "nba_player_id": nba_player_id,
                "game_id": game.game_id,
                "season": season,
                "game_date": game.game_date,
                "team_id": team_id,
                "opponent_team_id": opponent_team_id,
                "is_home": is_home,
                "game_status": game.game_status,
                "source_payload": {
                    "game_id": game.game_id,
                    "game_date": game.game_date.isoformat(),
                    "team_id": team_id,
                    "opponent_team_id": opponent_team_id,
                    "is_home": is_home,
                },
            })

    await session.execute(delete(PlayerSchedule).where(PlayerSchedule.season == season))
    for offset in range(0, len(player_rows), BULK_INSERT_BATCH_SIZE):
        schedule_statement = insert(PlayerSchedule).values(
            player_rows[offset:offset + BULK_INSERT_BATCH_SIZE]
        )
        schedule_statement = schedule_statement.on_conflict_do_update(
            index_elements=[PlayerSchedule.nba_player_id, PlayerSchedule.game_id],
            set_={key: getattr(schedule_statement.excluded, key) for key in (
                "season", "game_date", "team_id", "opponent_team_id", "is_home", "game_status", "source_payload", "imported_at"
            )},
        )
        await session.execute(schedule_statement)
    await session.flush()
    return len(player_rows)


async def import_schedule(
    session: AsyncSession,
    season: str,
    records: list[dict[str, Any]],
    as_of: date,
) -> tuple[int, int]:
    games_by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        game = normalize_game(record, season)
        existing = games_by_id.get(game["game_id"])
        if existing is not None and (
            existing["home_team_id"] != game["home_team_id"]
            or existing["away_team_id"] != game["away_team_id"]
            or existing["game_date"] != game["game_date"]
        ):
            raise HTTPException(status_code=502, detail="nba_api returned conflicting records for one game ID")
        games_by_id[game["game_id"]] = game
    if not games_by_id:
        raise HTTPException(status_code=502, detail="nba_api returned no schedule games")

    teams = set((await session.scalars(select(NbaTeam.nba_team_id))).all())
    unresolved_team_references = 0
    for game in games_by_id.values():
        for field in ("home_team_id", "away_team_id"):
            team_id = game[field]
            if team_id is not None and team_id not in teams:
                unresolved_team_references += 1
                game[field] = None

    game_rows = list(games_by_id.values())
    statement = insert(NbaGame).values(game_rows)
    statement = statement.on_conflict_do_update(
        index_elements=[NbaGame.game_id],
        set_={key: getattr(statement.excluded, key) for key in (
            "season", "game_date", "game_status", "home_team_id", "away_team_id", "source_payload", "imported_at"
        )},
    )
    await session.execute(statement)
    await session.flush()
    player_schedule_entries = await rebuild_player_schedule(session, season, as_of)
    return len(game_rows), player_schedule_entries, unresolved_team_references

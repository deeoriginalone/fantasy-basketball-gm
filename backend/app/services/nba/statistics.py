from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.nba.models import NbaPlayer, NbaPlayerSeasonStats, NbaTeam


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _integer(value: Any, *, field: str) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=502, detail=f"nba_api returned invalid {field}") from error


def _number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def import_player_season_stats(
    session: AsyncSession,
    season: str,
    season_type: str,
    records: list[dict[str, Any]],
) -> int:
    stats_by_player: dict[str, dict[str, Any]] = {}
    for record in records:
        player_id = _text(record.get("nba_player_id"))
        if not player_id:
            raise HTTPException(status_code=502, detail="nba_api season statistics omitted a player ID")
        existing = stats_by_player.get(player_id)
        if existing is not None and existing != record:
            raise HTTPException(status_code=502, detail="nba_api returned duplicate season rows for one player")
        stats_by_player[player_id] = record
    if not stats_by_player:
        return 0

    teams = list((await session.scalars(select(NbaTeam))).all())
    teams_by_id = {team.nba_team_id: team.abbreviation for team in teams}
    existing_ids = set((await session.scalars(select(NbaPlayer.nba_player_id))).all())
    supplemental_players = []
    for player_id, record in stats_by_player.items():
        if player_id in existing_ids:
            continue
        player_name = _text(record.get("player_name"))
        if not player_name:
            raise HTTPException(status_code=502, detail="nba_api season statistics omitted a name for an unlisted player")
        source_team_id = _text(record.get("team_id"))
        team_id = source_team_id if source_team_id in teams_by_id else None
        supplemental_players.append({
            "nba_player_id": player_id,
            "player_name": player_name,
            "team_id": team_id,
            "team_abbreviation": teams_by_id.get(team_id) if team_id else None,
            "roster_status": None,
            "from_year": None,
            "to_year": None,
            "source_payload": {
                "source": "nba_api.LeagueDashPlayerStats",
                "season": season,
                "season_type": season_type,
                "record": record.get("source_payload") or record,
            },
        })
    if supplemental_players:
        statement = insert(NbaPlayer).values(supplemental_players)
        statement = statement.on_conflict_do_nothing(index_elements=[NbaPlayer.nba_player_id])
        await session.execute(statement)
        await session.flush()

    rows = []
    for player_id, record in stats_by_player.items():
        games_played = _integer(record.get("games_played"), field="games played")
        games_started = min(_integer(record.get("games_started"), field="games started"), games_played)
        rows.append({
            "nba_player_id": player_id,
            "season": season,
            "season_type": season_type,
            "games_played": games_played,
            "games_started": games_started,
            "minutes_per_game": _number(record.get("minutes_per_game")),
            "usage_pct": _number(record.get("usage_pct")),
            "base_stats": record.get("base_stats") or {},
            "advanced_stats": record.get("advanced_stats") or {},
            "source_payload": record.get("source_payload") or record,
        })
    statement = insert(NbaPlayerSeasonStats).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=[
            NbaPlayerSeasonStats.nba_player_id,
            NbaPlayerSeasonStats.season,
            NbaPlayerSeasonStats.season_type,
        ],
        set_={key: getattr(statement.excluded, key) for key in (
            "games_played", "games_started", "minutes_per_game", "usage_pct", "base_stats", "advanced_stats", "source_payload", "imported_at"
        )},
    )
    await session.execute(statement)
    await session.flush()
    return len(rows)

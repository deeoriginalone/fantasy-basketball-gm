from collections import defaultdict
from math import ceil
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.draft.contracts import DraftMetricsResult
from app.features.draft.models import DraftPlayerMetric
from app.features.leagues.models import LeagueSettings, Team
from app.features.nba.models import NbaPlayerSeasonStats, PlayerGameLog
from app.features.players.models import LeaguePlayer, PlayerIdentity

CORE_POSITIONS = ("PG", "SG", "SF", "PF", "C")
STAT_ID_FIELDS = {
    "12": "PTS",
    "15": "REB",
    "16": "AST",
    "17": "STL",
    "18": "BLK",
    "19": "TOV",
}
STAT_NAME_FIELDS = {
    "PTS": "PTS",
    "POINTS": "PTS",
    "REB": "REB",
    "REBOUNDS": "REB",
    "TOTAL REBOUNDS": "REB",
    "AST": "AST",
    "ASSISTS": "AST",
    "ST": "STL",
    "STL": "STL",
    "STEALS": "STL",
    "BLK": "BLK",
    "BLOCKS": "BLK",
    "BLOCKED SHOTS": "BLK",
    "TO": "TOV",
    "TOV": "TOV",
    "TURNOVERS": "TOV",
    "3PTM": "FG3M",
    "3PM": "FG3M",
    "THREE-POINTERS MADE": "FG3M",
    "OREB": "OREB",
    "OFFENSIVE REBOUNDS": "OREB",
    "DREB": "DREB",
    "DEFENSIVE REBOUNDS": "DREB",
    "FGM": "FGM",
    "FIELD GOALS MADE": "FGM",
    "FGA": "FGA",
    "FIELD GOALS ATTEMPTED": "FGA",
    "FTM": "FTM",
    "FREE THROWS MADE": "FTM",
    "FTA": "FTA",
    "FREE THROWS ATTEMPTED": "FTA",
    "PF": "PF",
    "PERSONAL FOULS": "PF",
    "PLUS/MINUS": "PLUS_MINUS",
}


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _position_set(value: str | None) -> set[str]:
    if not value:
        return set()
    return {part.strip().upper() for part in value.replace("/", ",").split(",") if part.strip()}


def _canonical_position(position: str) -> set[str]:
    normalized = position.upper()
    if normalized == "G":
        return {"PG", "SG"}
    if normalized == "F":
        return {"SF", "PF"}
    if normalized in CORE_POSITIONS:
        return {normalized}
    return set()


def _category_field(category: dict[str, Any]) -> str:
    stat_id = str(category.get("stat_id", ""))
    if stat_id in STAT_ID_FIELDS:
        return STAT_ID_FIELDS[stat_id]
    name = str(category.get("name") or "").strip().upper()
    if name in STAT_NAME_FIELDS:
        return STAT_NAME_FIELDS[name]
    raise HTTPException(
        status_code=422,
        detail=f"Draft metrics do not support Yahoo scoring category {name or stat_id or 'unknown'}",
    )


def _fantasy_value(stats: dict[str, Any], categories: list[dict[str, Any]]) -> float:
    return sum(_number(stats.get(_category_field(category))) * _number(category.get("value")) for category in categories)


def _season_year(season: str) -> int:
    try:
        return int(season[:4])
    except (TypeError, ValueError):
        return 0


def _logs_as_stats(logs: list[PlayerGameLog], categories: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not logs:
        return None
    fields = {_category_field(category) for category in categories}
    totals = {field: 0.0 for field in fields}
    for log in logs:
        for field in fields:
            totals[field] += _number(log.stats_payload.get(field))
    return {field: total / len(logs) for field, total in totals.items()}


def _select_production(
    rows: list[NbaPlayerSeasonStats],
    logs: list[PlayerGameLog],
    target_season: str,
    categories: list[dict[str, Any]],
) -> tuple[dict[str, Any], str, str, int, int, float, float] | None:
    target_year = _season_year(target_season)
    regular = [
        row for row in rows
        if row.season_type == "Regular Season" and _season_year(row.season) <= target_year and row.games_played > 0
    ]
    mature_regular = [row for row in regular if row.games_played >= 10]
    if mature_regular:
        selected = max(mature_regular, key=lambda row: (_season_year(row.season), row.games_played))
    elif regular:
        selected = max(regular, key=lambda row: (_season_year(row.season), row.games_played))
    else:
        preseason = [row for row in rows if row.season == target_season and row.season_type == "Pre Season" and row.games_played > 0]
        selected = max(preseason, key=lambda row: row.games_played) if preseason else None

    if selected is not None:
        return (
            selected.base_stats,
            selected.season,
            selected.season_type,
            selected.games_played,
            selected.games_started,
            _number(selected.minutes_per_game),
            _number(selected.usage_pct),
        )

    target_logs = [log for log in logs if log.season == target_season]
    log_stats = _logs_as_stats(target_logs, categories)
    if not log_stats:
        return None
    minutes = sum(_number(log.stats_payload.get("MIN")) for log in target_logs) / len(target_logs)
    return log_stats, target_season, "Recent Game Logs", len(target_logs), 0, minutes, 0.0


def _replacement_demand(roster_positions: list[dict[str, Any]], team_count: int) -> dict[str, float]:
    demand = {position: 0.0 for position in CORE_POSITIONS}
    for slot in roster_positions:
        if not bool(int(slot.get("is_starting_position", 1) or 0)):
            continue
        count = max(0, int(float(slot.get("count", 0) or 0))) * team_count
        position = str(slot.get("position") or "").upper()
        if position in demand:
            demand[position] += count
        elif position == "G":
            demand["PG"] += count / 2
            demand["SG"] += count / 2
        elif position == "F":
            demand["SF"] += count / 2
            demand["PF"] += count / 2
        elif position in {"UTIL", "UT"}:
            for core_position in CORE_POSITIONS:
                demand[core_position] += count / len(CORE_POSITIONS)
    return demand


def _selected_position_positions(positions: str | None) -> set[str]:
    result: set[str] = set()
    for position in _position_set(positions):
        result.update(_canonical_position(position))
    return result


def _percentile(value: float | None, distribution: list[float]) -> float:
    if not distribution or value is None:
        return 0.0
    if len(distribution) == 1:
        return 50.0
    below_or_equal = sum(item <= value for item in distribution)
    return 100.0 * (below_or_equal - 1) / (len(distribution) - 1)


async def recompute_draft_metrics(
    session: AsyncSession,
    league_key: str,
    season: str,
) -> DraftMetricsResult:
    async with session.begin():
        settings = await session.get(LeagueSettings, league_key)
        if settings is None:
            raise HTTPException(status_code=404, detail="Imported league settings were not found")
        scoring = settings.scoring_settings
        if "point" not in str(scoring.get("scoring_type", "")).lower():
            raise HTTPException(status_code=422, detail="Draft metrics currently require a Yahoo points league")
        categories = scoring.get("categories") or []
        if not categories:
            raise HTTPException(status_code=422, detail="Yahoo league scoring categories are required")
        for category in categories:
            _category_field(category)

        team_count = await session.scalar(
            select(func.count()).select_from(Team).where(Team.league_key == league_key)
        ) or 1
        player_rows = list((await session.execute(
            select(LeaguePlayer, PlayerIdentity)
            .join(PlayerIdentity, LeaguePlayer.player_identity_id == PlayerIdentity.id)
            .where(LeaguePlayer.league_key == league_key)
            .order_by(PlayerIdentity.id)
        )).all())
        identities_by_nba_id: dict[str, list[tuple[LeaguePlayer, PlayerIdentity]]] = defaultdict(list)
        missing_mapping_count = 0
        for observation, identity in player_rows:
            if identity.nba_player_id:
                identities_by_nba_id[identity.nba_player_id].append((observation, identity))
            else:
                missing_mapping_count += 1

        nba_ids = list(identities_by_nba_id)
        stats_rows = []
        logs_by_player: dict[str, list[PlayerGameLog]] = defaultdict(list)
        if nba_ids:
            stats_rows = list((await session.scalars(
                select(NbaPlayerSeasonStats).where(
                    NbaPlayerSeasonStats.nba_player_id.in_(nba_ids),
                    NbaPlayerSeasonStats.season <= season,
                )
            )).all())
            logs = list((await session.scalars(
                select(PlayerGameLog).where(
                    PlayerGameLog.nba_player_id.in_(nba_ids),
                    PlayerGameLog.season == season,
                )
            )).all())
            for log in logs:
                logs_by_player[log.nba_player_id].append(log)

        stats_by_player: dict[str, list[NbaPlayerSeasonStats]] = defaultdict(list)
        for row in stats_rows:
            stats_by_player[row.nba_player_id].append(row)

        candidates: list[dict[str, Any]] = []
        missing_stats_count = 0
        for nba_player_id, joined_rows in identities_by_nba_id.items():
            identity = joined_rows[0][1]
            production = _select_production(
                stats_by_player.get(nba_player_id, []),
                logs_by_player.get(nba_player_id, []),
                season,
                categories,
            )
            if production is None:
                missing_stats_count += len(joined_rows)
                continue
            base_stats, source_season, source_type, games_played, games_started, minutes, usage = production
            fantasy_value = _fantasy_value(base_stats, categories)
            positions = _selected_position_positions(identity.position)
            candidates.append({
                "identity": identity,
                "nba_player_id": nba_player_id,
                "fantasy_value": fantasy_value,
                "positions": positions,
                "source_season": source_season,
                "source_season_type": source_type,
                "games_played": games_played,
                "games_started": games_started,
                "minutes_per_game": minutes,
                "usage_pct": usage,
                "base_stats": base_stats,
            })

        demand = _replacement_demand(settings.roster_positions, int(team_count))
        position_values: dict[str, list[float]] = {position: [] for position in CORE_POSITIONS}
        position_supply = {position: 0 for position in CORE_POSITIONS}
        for candidate in candidates:
            for position in candidate["positions"]:
                position_values[position].append(candidate["fantasy_value"])
                position_supply[position] += 1
        replacement_by_position: dict[str, float] = {}
        scarcity_raw: dict[str, float] = {}
        for position in CORE_POSITIONS:
            values = sorted(position_values[position], reverse=True)
            if values:
                index = min(max(0, ceil(demand[position])), len(values) - 1)
                replacement_by_position[position] = values[index]
            else:
                replacement_by_position[position] = 0.0
            scarcity_raw[position] = demand[position] / max(1, position_supply[position])
        max_scarcity = max(scarcity_raw.values(), default=0.0)

        metric_rows = []
        usage_distribution = [candidate["usage_pct"] for candidate in candidates if candidate["usage_pct"] > 0]
        minutes_distribution = [candidate["minutes_per_game"] for candidate in candidates if candidate["minutes_per_game"] > 0]
        for candidate in candidates:
            positions = candidate["positions"]
            replacement_value = max(
                (candidate["fantasy_value"] - replacement_by_position[position] for position in positions),
                default=0.0,
            )
            positional_scarcity = max(
                (100.0 * scarcity_raw[position] / max_scarcity for position in positions),
                default=0.0,
            )
            games_played = candidate["games_played"]
            durability = min(100.0, 100.0 * games_played / 82.0)
            start_rate = candidate["games_started"] / games_played if games_played else 0.0
            risk = min(100.0, max(0.0, 100.0 - 0.7 * durability - 30.0 * start_rate))
            upside = 0.65 * _percentile(candidate["usage_pct"], usage_distribution) + 0.35 * _percentile(
                candidate["minutes_per_game"], minutes_distribution
            )
            metric_rows.append({
                "league_key": league_key,
                "player_identity_id": candidate["identity"].id,
                "season": season,
                "fantasy_value": candidate["fantasy_value"],
                "replacement_value": replacement_value,
                "positional_scarcity": positional_scarcity,
                "durability_score": durability,
                "risk_score": risk,
                "upside_score": upside,
                "sample_games": games_played,
                "source_season": candidate["source_season"],
                "source_season_type": candidate["source_season_type"],
                "source_payload": {
                    "scoring_categories": categories,
                    "positions": sorted(positions),
                    "minutes_per_game": candidate["minutes_per_game"],
                    "usage_pct": candidate["usage_pct"],
                    "games_started": candidate["games_started"],
                    "replacement_by_position": {
                        position: replacement_by_position[position] for position in sorted(positions)
                    },
                },
            })

        await session.execute(delete(DraftPlayerMetric).where(
            DraftPlayerMetric.league_key == league_key,
            DraftPlayerMetric.season == season,
        ))
        if metric_rows:
            await session.execute(insert(DraftPlayerMetric).values(metric_rows))
        await session.flush()
        return DraftMetricsResult(
            league_key=league_key,
            season=season,
            players_scored=len(metric_rows),
            players_missing_nba_mapping=missing_mapping_count,
            players_missing_stats=missing_stats_count,
        )

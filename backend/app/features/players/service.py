from collections.abc import Iterable
from datetime import datetime, timezone
import logging
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.features.leagues.models import League, Team
from app.features.players.contracts import PlayerChange, PlayerImportResult
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.players.normalization import NormalizedPlayer, normalize_yahoo_player
from app.services.yahoo.auth import YahooAuthService
from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.players import fetch_all_league_players, fetch_league_rosters

logger = logging.getLogger(__name__)
IDENTITY_FIELDS = ("player_name", "team", "position", "status")


def _merge_player_payload(primary: dict[str, Any], supplement: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in supplement.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_player_payload(current, value)
        elif current in (None, ""):
            merged[key] = value
    return merged


def _normalize_players(records: Iterable[dict[str, Any]]) -> dict[str, NormalizedPlayer]:
    normalized: dict[str, NormalizedPlayer] = {}
    for record in records:
        try:
            player = normalize_yahoo_player(record)
        except ValueError as error:
            logger.warning(
                "Yahoo player record lacks identity fields",
                extra={"event": "yahoo_player_identity_invalid"},
            )
            raise HTTPException(
                status_code=502,
                detail="Yahoo returned a player without a usable ID and name",
            ) from error
        existing = normalized.get(player.yahoo_player_id)
        if existing:
            player = normalize_yahoo_player(
                _merge_player_payload(existing.source_payload, player.source_payload)
            )
        normalized[player.yahoo_player_id] = player
    return normalized


def _roster_position(record: dict[str, Any]) -> str | None:
    value = record.get("selected_position") or record.get("roster_position")
    if isinstance(value, dict):
        value = value.get("position")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def import_yahoo_players(
    session: AsyncSession,
    settings: Settings,
    league_key: str | None = None,
    client: YahooFantasyClient | None = None,
) -> PlayerImportResult:
    access_token = await YahooAuthService(settings).access_token(session)
    await session.commit()
    statement = select(League).options(selectinload(League.teams)).order_by(League.league_key)
    if league_key:
        statement = statement.where(League.league_key == league_key)
    leagues = list((await session.scalars(statement)).all())
    if not leagues:
        raise HTTPException(status_code=404, detail="No imported Yahoo league was found")
    await session.commit()

    yahoo_client = client or YahooFantasyClient()
    league_batches: list[dict[str, Any]] = []
    global_players: dict[str, NormalizedPlayer] = {}
    roster_entry_count = 0

    for league in leagues:
        raw_players = await fetch_all_league_players(
            yahoo_client, access_token, league.league_key
        )
        team_keys = [team.team_key for team in league.teams]
        roster_records = await fetch_league_rosters(yahoo_client, access_token, team_keys)
        combined_records = list(raw_players)
        for team_records in roster_records.values():
            combined_records.extend(team_records)
        league_players = _normalize_players(combined_records)
        for yahoo_id, player in league_players.items():
            existing = global_players.get(yahoo_id)
            if existing:
                merged = _merge_player_payload(existing.source_payload, player.source_payload)
                global_players[yahoo_id] = normalize_yahoo_player(merged)
            else:
                global_players[yahoo_id] = player

        normalized_rosters: list[dict[str, Any]] = []
        for team_key, records in roster_records.items():
            team_players = _normalize_players(records)
            for yahoo_id, player in team_players.items():
                if yahoo_id not in global_players:
                    global_players[yahoo_id] = player
                normalized_rosters.append(
                    {
                    "team_key": team_key,
                    "yahoo_player_id": yahoo_id,
                        "roster_position": _roster_position(player.source_payload),
                        "source_payload": player.source_payload,
                    }
                )
        roster_entry_count += len(normalized_rosters)
        league_batches.append(
            {
                "league": league,
                "players": league_players,
                "rosters": normalized_rosters,
            }
        )

    imported_at = datetime.now(timezone.utc)
    identity_ids: dict[str, int] = {}
    created_count = 0
    updated_count = 0
    unchanged_count = 0
    changes: list[PlayerChange] = []

    try:
        async with session.begin():
            for batch in league_batches:
                current_league = batch["league"]
                await session.execute(delete(RosterEntry).where(RosterEntry.league_key == current_league.league_key))
                await session.execute(delete(LeaguePlayer).where(LeaguePlayer.league_key == current_league.league_key))
                await session.execute(delete(FantasyTeam).where(FantasyTeam.league_key == current_league.league_key))

                source_teams = list(
                    (
                        await session.scalars(
                            select(Team).where(Team.league_key == current_league.league_key)
                        )
                    ).all()
                )
                if source_teams:
                    await session.execute(
                        insert(FantasyTeam).values(
                            [
                                {
                                    "team_key": team.team_key,
                                    "league_key": team.league_key,
                                    "team_name": team.team_name,
                                    "source_payload": team.source_payload,
                                    "imported_at": imported_at,
                                }
                                for team in source_teams
                            ]
                        )
                    )

            for yahoo_id, normalized in global_players.items():
                identity = await session.scalar(
                    select(PlayerIdentity)
                    .where(PlayerIdentity.yahoo_player_id == yahoo_id)
                    .with_for_update()
                )
                values = {
                    "yahoo_player_id": yahoo_id,
                    "player_name": normalized.player_name,
                    "team": normalized.team,
                    "position": normalized.position,
                    "status": normalized.status,
                }
                if identity is None:
                    identity_id = await session.scalar(
                        insert(PlayerIdentity)
                        .values(**values)
                        .on_conflict_do_nothing(index_elements=[PlayerIdentity.yahoo_player_id])
                        .returning(PlayerIdentity.id)
                    )
                    if identity_id is not None:
                        identity_ids[yahoo_id] = int(identity_id)
                        created_count += 1
                        continue
                    identity = await session.scalar(
                        select(PlayerIdentity)
                        .where(PlayerIdentity.yahoo_player_id == yahoo_id)
                        .with_for_update()
                    )
                    if identity is None:
                        raise SQLAlchemyError("Player identity insert was not visible after conflict")

                changed_fields = [
                    field for field in IDENTITY_FIELDS if getattr(identity, field) != values[field]
                ]
                identity_ids[yahoo_id] = identity.id
                if changed_fields:
                    for field in changed_fields:
                        setattr(identity, field, values[field])
                    identity.updated_at = imported_at
                    updated_count += 1
                    changes.append(
                        PlayerChange(id=identity.id, yahoo_player_id=yahoo_id, fields=changed_fields)
                    )
                else:
                    unchanged_count += 1

            for batch in league_batches:
                current_league = batch["league"]
                player_rows = [
                    {
                        "league_key": current_league.league_key,
                        "yahoo_player_id": yahoo_id,
                        "player_identity_id": identity_ids[yahoo_id],
                        "source_payload": player.source_payload,
                        "imported_at": imported_at,
                    }
                    for yahoo_id, player in batch["players"].items()
                ]
                if player_rows:
                    await session.execute(insert(LeaguePlayer).values(player_rows))
                roster_rows = [
                    {
                        "league_key": current_league.league_key,
                        "team_key": entry["team_key"],
                        "yahoo_player_id": entry["yahoo_player_id"],
                        "player_identity_id": identity_ids[entry["yahoo_player_id"]],
                        "roster_position": entry["roster_position"],
                        "source_payload": entry["source_payload"],
                        "imported_at": imported_at,
                    }
                    for entry in batch["rosters"]
                ]
                if roster_rows:
                    await session.execute(insert(RosterEntry).values(roster_rows))
    except SQLAlchemyError as error:
        logger.exception(
            "Unable to persist Yahoo player import",
            extra={"event": "yahoo_player_import_persistence_failed", "league_key": league_key},
        )
        raise HTTPException(status_code=502, detail="Yahoo player data could not be persisted") from error

    logger.info(
        "Yahoo player import completed",
        extra={
            "event": "yahoo_player_import_completed",
            "league_count": len(league_batches),
            "players_seen": len(global_players),
            "created_count": created_count,
            "updated_count": updated_count,
            "unchanged_count": unchanged_count,
            "roster_entry_count": roster_entry_count,
        },
    )
    return PlayerImportResult(
        league_count=len(league_batches),
        players_seen=len(global_players),
        created_count=created_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        roster_entry_count=roster_entry_count,
        changes=changes,
    )


async def list_player_identities(session: AsyncSession) -> list[PlayerIdentity]:
    result = await session.scalars(select(PlayerIdentity).order_by(PlayerIdentity.player_name, PlayerIdentity.id))
    return list(result.all())


async def get_player_identity(session: AsyncSession, internal_id: int) -> PlayerIdentity | None:
    return await session.get(PlayerIdentity, internal_id)


async def list_persisted_rosters(session: AsyncSession) -> list[FantasyTeam]:
    statement = (
        select(FantasyTeam)
        .options(selectinload(FantasyTeam.roster_entries).selectinload(RosterEntry.identity))
        .order_by(FantasyTeam.league_key, FantasyTeam.team_key)
    )
    result = await session.scalars(statement)
    return list(result.all())
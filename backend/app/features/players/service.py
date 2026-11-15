from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import and_, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.core.database import batched
from app.features.leagues.models import League, Team
from app.features.players.contracts import PlayerChange, PlayerImportResult
from app.features.players.models import FantasyTeam, LeaguePlayer, PlayerIdentity, RosterEntry
from app.features.players.normalization import NormalizedPlayer, normalize_yahoo_player
from app.services.yahoo.auth import YahooAuthService
from app.services.yahoo.client import YahooFantasyClient
from app.services.yahoo.players import fetch_all_league_players, fetch_league_rosters

logger = logging.getLogger(__name__)
IDENTITY_FIELDS = ("player_name", "team", "position", "status")
# Yahoo Mock Practice creates local pseudo-leagues that copy a real league's pool; they are not Yahoo
# leagues, so requesting them from Yahoo fails and would abort the whole import. Each discriminator
# the practice workflow writes identifies one: key prefix, game key and source-payload marker.
PRACTICE_LEAGUE_PREFIX = "yahoo-mock-practice."
PRACTICE_GAME_KEY = "yahoo_mock_practice"
PRACTICE_SOURCE_MARKER = "practice_source"
# Called with "PLAYER_POOL" before the pool fetch and "LEAGUE_ROSTERS" before the roster fetch.
FetchCallback = Callable[[str], None]


def is_local_practice_league(league: League) -> bool:
    payload = league.source_payload if isinstance(league.source_payload, dict) else {}
    return (league.league_key.startswith(PRACTICE_LEAGUE_PREFIX) or league.game_key == PRACTICE_GAME_KEY
        or PRACTICE_SOURCE_MARKER in payload)


def real_yahoo_league_filter():
    return and_(
        ~League.league_key.startswith(PRACTICE_LEAGUE_PREFIX, autoescape=True),
        League.game_key != PRACTICE_GAME_KEY,
        ~League.source_payload.has_key(PRACTICE_SOURCE_MARKER),
    )


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
    if isinstance(value, list):
        # Yahoo JSON sub-resource: [{"coverage_type": ...}, {"position": ...}, ...]
        fragments = [fragment for fragment in value if isinstance(fragment, dict)]
        value = {key: item for fragment in fragments for key, item in fragment.items()}
    if isinstance(value, dict):
        value = value.get("position")
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def resolve_import_leagues(session: AsyncSession, league_key: str | None = None) -> list[League]:
    """Real Yahoo leagues to import. Local practice pseudo-leagues are never selected; naming one is a
    client error because Yahoo cannot serve it."""
    statement = select(League).options(selectinload(League.teams)).order_by(League.league_key)
    if league_key:
        league = (await session.scalars(statement.where(League.league_key == league_key))).first()
        if league is not None and is_local_practice_league(league):
            await session.commit()
            raise HTTPException(
                status_code=422,
                detail="This is a local Yahoo Mock Practice league; only real Yahoo leagues can be imported from Yahoo.",
            )
        leagues = [league] if league is not None else []
    else:
        leagues = list((await session.scalars(statement.where(real_yahoo_league_filter()))).all())
    await session.commit()
    if not leagues:
        raise HTTPException(status_code=404, detail="No imported Yahoo league was found")
    return leagues


@dataclass
class FetchedLeague:
    league: League
    team_keys: list[str]
    pool_record_count: int
    players: dict[str, NormalizedPlayer]
    rosters: list[dict[str, Any]]
    roster_counts: dict[str, int]


@dataclass
class YahooPlayerFetch:
    leagues: list[FetchedLeague] = field(default_factory=list)
    global_players: dict[str, NormalizedPlayer] = field(default_factory=dict)

    @property
    def roster_entry_count(self) -> int:
        return sum(len(batch.rosters) for batch in self.leagues)


async def fetch_yahoo_players(
    yahoo_client: YahooFantasyClient,
    access_token: str,
    leagues: list[League],
    on_fetch: FetchCallback | None = None,
) -> YahooPlayerFetch:
    """Fetch every league's player pool and every team roster before any write."""
    fetched = YahooPlayerFetch()
    global_players = fetched.global_players
    for league in leagues:
        if on_fetch is not None:
            on_fetch("PLAYER_POOL")
        raw_players = await fetch_all_league_players(yahoo_client, access_token, league.league_key)
        team_keys = [team.team_key for team in league.teams]
        if on_fetch is not None:
            on_fetch("LEAGUE_ROSTERS")
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
        roster_counts: dict[str, int] = {}
        for team_key, records in roster_records.items():
            team_players = _normalize_players(records)
            roster_counts[team_key] = len(team_players)
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
        fetched.leagues.append(FetchedLeague(
            league=league, team_keys=team_keys, pool_record_count=len(raw_players),
            players=league_players, rosters=normalized_rosters, roster_counts=roster_counts,
        ))
    return fetched


def validate_yahoo_snapshot(fetched: YahooPlayerFetch) -> list[str]:
    """A replacement snapshot must be complete before it may replace the persisted one."""
    problems: list[str] = []
    for batch in fetched.leagues:
        missing = [key for key in batch.team_keys if key not in batch.roster_counts]
        if missing:
            problems.append(f"{batch.league.league_key}: Yahoo returned no roster for {len(missing)} team(s)")
        unslotted = sum(1 for row in batch.rosters if not row["roster_position"])
        if unslotted:
            problems.append(f"{batch.league.league_key}: Yahoo omitted selected_position for {unslotted} roster player(s)")
    return problems


async def persist_yahoo_players(session: AsyncSession, fetched: YahooPlayerFetch) -> PlayerImportResult:
    """Replace each league's pool and roster snapshot in one transaction. Persisted counts are verified
    before commit, so a partial write never replaces the previous snapshot."""
    problems = validate_yahoo_snapshot(fetched)
    if problems:
        logger.warning("Yahoo roster snapshot failed validation", extra={"event": "yahoo_snapshot_invalid"})
        raise HTTPException(
            status_code=502,
            detail="Yahoo returned an incomplete roster snapshot; the previous snapshot was kept. " + "; ".join(problems),
        )
    global_players = fetched.global_players
    imported_at = datetime.now(timezone.utc)
    identity_ids: dict[str, int] = {}
    created_count = 0
    updated_count = 0
    unchanged_count = 0
    changes: list[PlayerChange] = []

    try:
        async with session.begin():
            for batch in fetched.leagues:
                current_league = batch.league
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

            for batch in fetched.leagues:
                current_league = batch.league
                player_rows = [
                    {
                        "league_key": current_league.league_key,
                        "yahoo_player_id": yahoo_id,
                        "player_identity_id": identity_ids[yahoo_id],
                        "source_payload": player.source_payload,
                        "imported_at": imported_at,
                    }
                    for yahoo_id, player in batch.players.items()
                ]
                for rows in batched(player_rows):
                    await session.execute(insert(LeaguePlayer).values(rows))
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
                    for entry in batch.rosters
                ]
                for rows in batched(roster_rows):
                    await session.execute(insert(RosterEntry).values(rows))
                await session.flush()
                persisted_players = await session.scalar(select(func.count()).select_from(LeaguePlayer).where(
                    LeaguePlayer.league_key == current_league.league_key, LeaguePlayer.imported_at == imported_at))
                persisted_rosters = await session.scalar(select(func.count()).select_from(RosterEntry).where(
                    RosterEntry.league_key == current_league.league_key, RosterEntry.imported_at == imported_at))
                if persisted_players != len(player_rows) or persisted_rosters != len(roster_rows):
                    raise SQLAlchemyError("Persisted Yahoo player or roster rows disagree with the fetched snapshot")
    except SQLAlchemyError as error:
        logger.exception(
            "Unable to persist Yahoo player import",
            extra={"event": "yahoo_player_import_persistence_failed"},
        )
        raise HTTPException(status_code=502, detail="Yahoo player data could not be persisted") from error

    logger.info(
        "Yahoo player import completed",
        extra={
            "event": "yahoo_player_import_completed",
            "league_count": len(fetched.leagues),
            "players_seen": len(global_players),
            "created_count": created_count,
            "updated_count": updated_count,
            "unchanged_count": unchanged_count,
            "roster_entry_count": fetched.roster_entry_count,
        },
    )
    return PlayerImportResult(
        league_count=len(fetched.leagues),
        players_seen=len(global_players),
        created_count=created_count,
        updated_count=updated_count,
        unchanged_count=unchanged_count,
        roster_entry_count=fetched.roster_entry_count,
        changes=changes,
        imported_at=imported_at,
    )


async def import_yahoo_players(
    session: AsyncSession,
    settings: Settings,
    league_key: str | None = None,
    client: YahooFantasyClient | None = None,
    on_fetch: FetchCallback | None = None,
) -> PlayerImportResult:
    access_token = await YahooAuthService(settings).access_token(session)
    await session.commit()
    leagues = await resolve_import_leagues(session, league_key)
    fetched = await fetch_yahoo_players(client or YahooFantasyClient(), access_token, leagues, on_fetch)
    return await persist_yahoo_players(session, fetched)


async def list_player_identities(session: AsyncSession) -> list[PlayerIdentity]:
    result = await session.scalars(select(PlayerIdentity).order_by(PlayerIdentity.player_name, PlayerIdentity.id))
    return list(result.all())


async def get_player_identity(session: AsyncSession, internal_id: int) -> PlayerIdentity | None:
    return await session.get(PlayerIdentity, internal_id)


async def list_roster_baselines(
    session: AsyncSession,
    league_key: str | None = None,
) -> list[tuple[Team, FantasyTeam | None]]:
    statement = (
        select(Team, FantasyTeam)
        .outerjoin(
            FantasyTeam,
            (FantasyTeam.team_key == Team.team_key)
            & (FantasyTeam.league_key == Team.league_key),
        )
        .options(selectinload(FantasyTeam.roster_entries).selectinload(RosterEntry.identity))
        .options(selectinload(Team.league).selectinload(League.settings))
        .order_by(Team.league_key, Team.team_key)
    )
    if league_key:
        statement = statement.where(Team.league_key == league_key)
    result = await session.execute(statement)
    return list(result.all())


def roster_data_status(
    team: Team,
    roster: FantasyTeam | None,
) -> Literal["available", "stale", "not_imported"]:
    if roster is None:
        return "not_imported"
    league_state_timestamps = [
        team.imported_at,
        team.league.imported_at,
    ]
    if team.league.settings is not None:
        league_state_timestamps.append(team.league.settings.imported_at)
    if roster.imported_at < max(league_state_timestamps):
        return "stale"
    return "available"
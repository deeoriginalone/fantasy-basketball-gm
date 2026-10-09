# ADR 0002: Canonical Player Identity

- Status: Accepted
- Date: 2026-10-09

## Context

All basketball features need a stable internal player identifier while external source IDs may be unavailable or disagree. Yahoo is the only enabled player source for this phase. NBA and ESPN mappings must not be guessed from name/team similarity.

## Decisions

- `player_identity` is the cross-feature canonical identity record. Its generated integer `id` is the internal ID; required unique `yahoo_player_id` anchors source identity. `nba_player_id` and `espn_player_id` remain nullable.
- Yahoo player names and source fields are normalized into canonical columns while the league-specific `players` table preserves Yahoo source payloads.
- Player identity is global; player observations are unique per league; roster entries link internal identity IDs to Yahoo fantasy teams.
- `fantasy_teams` references existing imported `teams` keys rather than replacing or rebuilding the completed league import.
- Yahoo's status is persisted as supplied. Missing status remains null and is never converted to `healthy`.
- Before the draft, a Yahoo roster with a valid explicit zero-player collection is a successful empty snapshot; fantasy teams and the separate available-player collection still persist. Missing/malformed collections fail closed and do not erase prior snapshots.
- Identity changes are detected by comparing canonical fields; only changed identities receive a new `updated_at`. Yahoo re-imports replace league player/roster snapshots transactionally and remain idempotent.
- API reads are PostgreSQL-only. Only `POST /api/v1/players/import` accesses Yahoo through the Yahoo service layer.
- New tables are added through the current SQLAlchemy metadata startup bootstrap. No versioned migration framework exists yet; introduce one before production schema evolution.

## Consequences

- Future Yahoo/NBA/ESPN adapters can attach authoritative IDs to the same internal player row without changing downstream contracts.
- NBA/ESPN IDs and any status/position absent from Yahoo remain unresolved rather than inferred.
- The existing Yahoo league/team import remains the prerequisite for player imports and is not modified by this ADR.
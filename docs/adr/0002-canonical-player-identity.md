# ADR 0002: Canonical Player Identity

- Status: Accepted
- Date: 2026-10-09

## Context

Basketball features need a stable internal player identifier while external source IDs may be unavailable or disagree. Yahoo is the only enabled player source in the completed milestone. NBA and ESPN mappings must not be guessed from name/team similarity.

## Decisions

- `player_identity` is the cross-feature canonical identity record. Its generated integer `id` is the internal ID; required unique `yahoo_player_id` anchors source identity. `nba_player_id` and `espn_player_id` remain nullable.
- Yahoo player names and source fields are normalized into canonical columns while league-specific player observations preserve Yahoo source payloads.
- Player identity is global; player observations are unique per league; roster entries link internal identity IDs to Yahoo fantasy teams.
- `fantasy_teams` references the imported Yahoo team keys.
- Persist Yahoo status as supplied. Missing status remains null and is never converted to `healthy`.
- Before the draft, a valid Yahoo roster with an explicit zero-player collection is a successful empty snapshot; fantasy teams and the separate available-player collection still persist. Missing, malformed, or contradictory collections fail closed.
- Identity changes are detected by comparing canonical fields. Yahoo re-imports replace league player/roster snapshots transactionally and remain idempotent.
- API reads are PostgreSQL-only; only player import accesses Yahoo through the Yahoo service layer.
- New tables currently use SQLAlchemy metadata bootstrap. Introduce versioned migrations before schema evolution.

## Consequences

- Future authoritative Yahoo/NBA/ESPN adapters can attach source IDs to the same internal identity without changing downstream contracts.
- NBA/ESPN IDs and any status or position absent from Yahoo remain unresolved rather than inferred.
- The completed Yahoo league/team import remains the prerequisite for player imports and is not replaced by this identity layer.

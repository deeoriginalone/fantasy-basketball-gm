# ADR 0003: NBA Data Foundation

- Status: Accepted
- Date: 2026-10-09

## Context

Yahoo provides the fantasy league, scoring rules, teams, and Yahoo player identities. Downstream basketball work needs locally persisted NBA teams, players, schedules, and game logs without calling an external provider from read routes. NBA player IDs may be joined to Yahoo identities only when the evidence is unambiguous.

## Decisions

- Use `nba_api` as the source for NBA teams, current-season players, schedules, and recent player game logs.
- Confine provider calls to `POST /api/v1/nba/import`. Execute synchronous `nba_api` calls off the async event loop; API reads must use PostgreSQL only.
- Persist source-backed data in `nba_teams`, `players_nba`, `nba_games`, `player_game_logs`, and `player_schedule`.
- Import in order: teams, current-season players, season schedule, then recent regular/preseason player game logs. Default the recent log window to 30 days, configurable from 1 to 90 days.
- Upsert by source IDs and use transactional writes so repeated imports do not duplicate records. Batch schedule inserts to stay below PostgreSQL parameter limits.
- Populate only null `player_identity.nba_player_id` values when normalized full name and known team abbreviation yield exactly one NBA candidate and one Yahoo identity. Never alter Yahoo IDs or Yahoo-derived name, team, position, or status; ambiguous and unmatched records remain unresolved.
- Preserve schedule source payloads when a participant is TBD or is not in the NBA franchise directory. Keep the normalized team reference null and report unknown nonzero team references instead of inventing a franchise.
- Include a player referenced by recent logs even when absent from the current-player endpoint; record its game-log provenance and include it in schedule rebuilding for that import.
- Keep projections, scoring, rankings, matchups, recommendations, transactions, and frontend work outside this foundation.

## Consequences

- NBA records and future player schedules are locally available in PostgreSQL; the current API adds no NBA read endpoints beyond the import operation.
- Current verified deployment imports 30 teams, 616 player records, 1,274 games, 720 recent game logs, and 51,048 player-schedule entries; 608 Yahoo identities have unique NBA links.
- A source-reported non-NBA exhibition opponent remains unresolved in the normalized schedule while its raw source payload is retained.
- Schema bootstrap uses the existing SQLAlchemy metadata mechanism. A versioned migration workflow remains necessary before broader production schema evolution.

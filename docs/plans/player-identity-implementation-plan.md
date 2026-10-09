# Canonical Player Identity Implementation Plan

## Verified Starting State

- Yahoo OAuth, league/settings import, PostgreSQL session handling, and `teams` persistence already exist and are out of scope for rebuild.
- No Yahoo player importer, player identity model, roster persistence, or player/roster read endpoints exist.
- The only schema bootstrap is SQLAlchemy `Base.metadata.create_all()` during API startup. There is no Alembic configuration or existing migration directory.
- Existing `teams` rows represent Yahoo teams for a league. `fantasy_teams` will be a player-domain mirror referencing these existing team keys; existing league imports remain unchanged.

## Files in Scope

- Add `backend/app/services/yahoo/players.py` for paginated league-player reads and per-team roster reads, using the existing Yahoo client/token service.
- Add `backend/app/features/players/{__init__,models,contracts,normalization,service,router}.py` for canonical identity records, per-league player observations, fantasy-team mirrors, roster entries, transactional import, change detection, and PostgreSQL-backed reads.
- Update `backend/app/core/database.py` to register the new model metadata and `backend/app/main.py` to mount the player API.
- Add `backend/tests/test_yahoo_players.py` for Yahoo player/roster parsing, paging, normalization, and source-missing behavior.
- Add `backend/tests/test_player_identity.py` for persistence creation/update/idempotency/duplicates/rosters. PostgreSQL integration cases use an explicitly configured test database and skip otherwise.
- Update README, ADR 0002, this plan, documentation plan, current state, next actions, project memory, and the dated session log.
- Do not modify OAuth, league import, projections, Yahoo NBA identity lookup, frontend, or decision features.

## Identity and Persistence Contract

- `player_identity.id` is the internal integer identity, generated from 10001 upward. `yahoo_player_id` is required and unique; NBA/ESPN IDs remain nullable until authoritative mappings are implemented.
- `player_name` comes from Yahoo's player name fields. `team`, `position`, and `status` are source-derived and may be null when Yahoo omits them. In particular, do not infer `healthy` from a missing Yahoo status.
- `players` stores a per-league Yahoo player observation and raw source payload, unique by `(league_key, yahoo_player_id)`, linked to `player_identity`.
- `fantasy_teams` mirrors the already-imported Yahoo `teams` rows and references their team keys.
- `rosters` links a Yahoo fantasy team to an internal identity, preserving roster slot and raw Yahoo player payload; uniqueness prevents duplicate player assignments per team.
- Canonical identity field changes update `updated_at` and are counted/reported. Unchanged re-imports leave canonical data and row cardinality stable. Replace per-league player and roster snapshots transactionally; preserve global identities.

## Yahoo Response Safety

- Treat an explicit Yahoo `players.count == 0` as a valid empty pre-draft roster/player collection. Reject a missing collection, invalid count, or positive count with no parseable records before replacing any stored snapshot.
- Keep fantasy-team persistence and the available-player pool independent of the current roster contents.
- Normalize scoring using Yahoo-provided stat IDs, category names, and weights; persist the full Yahoo settings response as the source payload.

## API Contract

- `POST /api/v1/players/import` optionally accepts `league_key`; without it, imports every locally imported league.
- `GET /api/v1/players` reads canonical identities from PostgreSQL.
- `GET /api/v1/player/{id}` reads one canonical identity by internal ID.
- `GET /api/v1/rosters` reads persisted fantasy teams and their identity-linked roster entries.
- Read routes do not call Yahoo. Yahoo access is limited to the import service.

## Validation Gates

1. Unit-test Yahoo's fragmented player and roster payloads, pagination, position/name normalization, and null status handling.
2. Test identity creation, changed-field detection, unchanged re-import, duplicate Yahoo ID prevention, team/roster persistence, and source-ID nullability against PostgreSQL.
3. Verify all three read routes use persisted data and return internal IDs.
4. Run full backend tests, Python compilation, Docker Compose config validation, and backend image build.
5. Do not call NBA/ESPN APIs or populate those IDs without authoritative integrations.

## Migration Note

No versioned migration framework exists in this repository. This batch adds SQLAlchemy models and uses the established startup metadata bootstrap to create the new tables. It does not alter or drop existing tables. A versioned migration system remains a deployment prerequisite before production schema evolution.

## Explicitly Deferred

NBA/ESPN ID crosswalk ingestion, NBA API, projection engine, rankings, waivers, trades, lineup recommendations, matchups, alerts, frontend, React, and Next.js.
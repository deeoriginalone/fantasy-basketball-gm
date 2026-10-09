# Yahoo OAuth and League Import Implementation Plan

## Verified Starting State

- Existing Yahoo OAuth performs authorization-code exchange, browser-bound state validation, and encrypted token persistence. Existing access-token retrieval refreshes expired tokens.
- Existing Yahoo client discovers an NBA game key and imports league/settings source payloads, but response normalization drops Yahoo's fragmented entity fields.
- Existing persistence has only `imported_leagues`; there are no `leagues`, `league_settings`, or `teams` tables, team requests, or league read endpoint.
- The workspace is not a Git repository. No project `.env` exists and required settings are not exported in the current shell. `.env.example` currently contains credential-shaped values and a callback URL that does not match the implemented route; replace those values with safe placeholders and rotate exposed Yahoo credentials.

## Objective and Boundaries

Complete the local API-backed Yahoo OAuth-to-league-import workflow. Yahoo remains authoritative. Keep raw source payloads, do not invent league settings, do not access Yahoo from a UI, and do not implement projections or decision features.

## Planned File Changes

- `.env.example`: remove credential values and correct the callback URL template.
- `backend/requirements.txt`: add bounded retry dependency.
- Add `backend/app/services/__init__.py` and `backend/app/services/yahoo/{__init__,auth,client,game_keys,leagues,normalization}.py` for OAuth reuse, retrying Yahoo requests, NBA game-key discovery, league/settings/team requests, and typed source normalization.
- Update `backend/app/features/leagues/{models,contracts,service,router}.py` to persist all leagues, settings, and teams idempotently and serve typed API responses.
- Update `backend/app/features/yahoo/{router,contracts}.py` to run the first import after OAuth token storage and return a non-secret import summary.
- Update `backend/app/core/database.py` and `backend/app/main.py` to register the new models and read routes.
- Update `backend/tests/test_yahoo_payloads.py`; add focused Yahoo retry, normalization, and import-flow tests.
- Update `README.md`, `docs/adr/0001-phase-1-yahoo-integration.md`, this plan, `docs/plans/documentation-plan.md`, `docs/status/current-state.md`, `docs/status/next-actions.md`, and `docs/sessions/2026-10-09.md`; create `docs/project-memory.md` because it is absent.

## API Contract

- `POST /api/v1/leagues/import`: refresh or retrieve the existing encrypted Yahoo credential, discover the active NBA game key from Yahoo, fetch every visible league plus its settings and teams, normalize, upsert, and return import counts.
- `GET /api/v1/league`: return `{league_key, league_name, season, scoring_settings, roster_positions, teams}` for the requested `league_key`; without a key, return the sole imported league or report ambiguity if multiple leagues are imported.
- `GET /api/v1/leagues`: return all imported league contracts.
- OAuth callback continues to validate browser-bound state and store encrypted tokens, then runs the initial league import; its response contains only connection/import status and non-secret league summaries.

## Persistence Contract

- `leagues`: Yahoo league identity, NBA game key, name, season, source payload, and import timestamp.
- `league_settings`: source-backed scoring settings, roster positions, and complete Yahoo settings payload keyed to the league.
- `teams`: Yahoo team identity and name, league foreign key, and raw Yahoo team payload.
- Upsert by Yahoo league/team key. Replace imported teams for a league in the same transaction as its league/settings update so removed teams do not remain stale.
- Keep existing `yahoo_credentials` and its Fernet encryption/refresh handling. The previous `imported_leagues` table is not dropped in this task.

## Validation Gates

1. Unit-test Yahoo's fragmented collection shapes, normalization, missing source values, and transient retry behavior without live credentials.
2. Run focused backend tests and syntax/type diagnostics available in the repository.
3. Run Docker Compose config validation/build and a PostgreSQL-backed mocked import/read round trip, including idempotent re-import.
4. Verify OAuth callback starts import with a mocked Yahoo API and never returns tokens.
5. A real Yahoo OAuth exchange/import can only be claimed if actual credentials and an authorized manager account are available; do not source credentials from `.env.example`.

## Explicitly Deferred

Frontend, NBA player statistics/imports, projections, the shared projection engine, Start/Sit, waiver, trade, draft, matchups, rankings, news/injuries, AI, dashboards, and transaction automation. Yahoo player identity/roster import is delivered separately in `player-identity-implementation-plan.md`.
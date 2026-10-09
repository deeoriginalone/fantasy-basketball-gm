# Fantasy Basketball GM

Docker-first FastAPI and PostgreSQL service for Yahoo Fantasy Basketball imports and roster-specific live draft utility. Yahoo remains the source of truth for league configuration and Yahoo player identities; `nba_api` supplies locally persisted NBA data.

## Verified Status

As of 2026-10-09, the live league is `478.l.50505` (`Driveway Dudes`, 2026) with 12 teams and 733 Yahoo player-pool records. The NBA import stores 30 teams, 717 NBA player records, 1,274 games, 720 recent game logs, 51,048 player schedules, and 1,054 season-stat rows. The pre-draft league has zero roster assignments, as expected.

The Draft Readiness Engine has stored metrics for 658 league players. 43 Yahoo players have no NBA identity mapping and 32 mapped players have no eligible stats; these 75 remain explicitly unscored.

## Run

1. Copy `.env.example` to `.env`, configure Yahoo credentials, a PostgreSQL password, OAuth state secret, encryption key, and the registered HTTPS callback.
2. Build and start the stack with `docker compose up --build`.
3. Open `https://192.168.0.85:18002/docs` for the API. Trust the local Caddy root certificate on the client before completing OAuth. Never commit `.env` or `caddy-root.crt`.

The API has no general user authentication and must stay on a trusted network.

## Draft Workflow

1. Refresh NBA data and season stats: `POST /api/v1/nba/import?season=2026-27&recent_days=30`.
2. Build league-specific per-player draft metrics: `POST /api/v1/draft/metrics?league_key=478.l.50505&season=2026-27`.
3. Submit the manager team, players already drafted, and available Yahoo-pool player identity IDs to `POST /api/v1/draft/utility`.

Example request body:

```json
{
  "league_key": "478.l.50505",
  "team_key": "478.l.50505.t.9",
  "season": "2026-27",
  "drafted_player_ids": [10001, 10002],
  "available_player_ids": [10003, 10004]
}
```

The endpoint returns one highest-utility eligible pick, component scores, and any available IDs it could not score. Draft input is evaluated but not saved; submit the current roster and player pool on each request.

Draft utility is a transparent heuristic based on Yahoo-weighted historical per-game production, replacement value, positional scarcity and need, durability, risk, upside, and roster-slot fit. It is not a projection or general player ranking.

## API

- `GET /api/v1/health`
- `GET /api/v1/yahoo/oauth/authorize`
- `GET /api/v1/league?league_key=...`
- `GET /api/v1/leagues`
- `POST /api/v1/players/import?league_key=...`
- `GET /api/v1/players`
- `GET /api/v1/player/{id}`
- `GET /api/v1/rosters`
- `POST /api/v1/nba/import`
- `POST /api/v1/draft/metrics`
- `POST /api/v1/draft/utility`

NBA provider calls happen only during imports. Player and league reads use PostgreSQL.

## Scope

No waivers, trades, matchup analysis, alerts, news, season management, AI summaries, start/sit, projections, draft simulation, or frontend are included. See [current state](docs/status/current-state.md), [next actions](docs/status/next-actions.md), [project memory](docs/project-memory.md), and [release notes](docs/releases/v0.1.0-yahoo-working.md) for boundaries and verified results.

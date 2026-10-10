# Fantasy Basketball GM

Docker-first FastAPI and PostgreSQL service for Yahoo Fantasy Basketball imports and roster-specific live draft utility. Yahoo remains the source of truth for league configuration and Yahoo player identities; `nba_api` supplies locally persisted NBA data.

## Verified Status

As of 2026-10-09, the live league is `478.l.50505` (`Driveway Dudes`, 2026) with 12 teams and 733 Yahoo player-pool records. The NBA import stores 30 teams, 717 NBA player records, 1,274 games, 720 recent game logs, 51,048 player schedules, and 1,054 season-stat rows. The pre-draft league has zero roster assignments, as expected.

The Draft Readiness Engine has stored metrics for 658 league players. 43 Yahoo players have no NBA identity mapping and 32 mapped players have no eligible stats; these 75 remain explicitly unscored.

Fantrax NBA ADP sync was live-verified on 2026-10-10: 334 provider records fetched, 312 uniquely matched, 22 unresolved (2 name misses, 11 position conflicts, 9 no-team records), and 0 ambiguous. Production stores 312 ADP rows for season `2026-27` (42.56% of Yahoo identities); 399 Yahoo identities are absent from the source ADP feed. Draft-rank and draft-frequency coverage are 0 because Fantrax does not provide those fields. The 22 unresolved provider records and reasons are retained by the diagnostics command.

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
  "draft_position": 9,
  "round_number": 2,
  "total_teams": 12,
  "drafted_player_ids": [10001, 10002],
  "available_player_ids": [10003, 10004],
  "recent_pick_player_ids": [10001, 10002],
  "adp_by_player_id": {"10003": 26.5, "10004": 40.0},
  "mode": "balanced"
}
```

The existing endpoint returns the roster-best pick, best value at risk before the next turn, snake timing, positional runs, per-player availability assessments, component scores, explanations, and any IDs it could not score. Draft input is evaluated but not saved; submit the current roster and player pool on each request. Recent pick IDs must be ordered oldest to newest; run detection examines the last ten. The response was extended in place; no endpoint was added.

For each player with ADP and draft timing, `market_value_delta = ADP - current_pick_number`: positive is a market reach, negative means the player has fallen past ADP. `reach_score` and `fall_score` range from 0 to 100 and scale each direction against one league round; they are descriptive heuristic indices, not probabilities or utility inputs. The response also includes `opportunity_cost_if_wait`, calculated as mode-adjusted roster utility multiplied by the estimated chance the player is gone at the next turn. `best_pick` maximizes team-specific utility; `best_value_before_next_pick` independently maximizes this at-risk value, so they can differ. Explanations separate roster fit, ADP, scarcity/run, survival, and wait cost.

The Yahoo player payloads currently do not contain market ADP, draft rank, XRank, or ownership fields. Supply ADP values for available internal player IDs in `adp_by_player_id`; players without ADP or draft timing have null next-pick survival estimates. Survival compares ADP with your next snake-draft pick and adjusts for league size, an available draft-frequency value, and active positional runs. Fantrax does not supply draft frequency, so that input remains null and does not alter its estimates. These are heuristic, uncalibrated estimates. Modes are `balanced`, `upside`, and `safe`.

### Draft-market sync and diagnostics

Fantrax's documented public REST API is the selected personal-use ADP source. Sync current NBA ADP without a manual file:

```bash
docker compose run --build --no-deps --rm api python -m app.services.draft.market_sync --season 2026-27
docker compose run --no-deps --rm api python -m app.services.draft.market_diagnostics --season 2026-27
```

The sync uses Fantrax's published `getAdp?sport=NBA` and `getPlayerIds?sport=NBA` JSON interfaces. It joins only on unique normalized name, current team, and position; no-team and ambiguous records are left unmatched. The player-ID endpoint supplies Fantrax ID, name, team, and position; the ADP endpoint supplies ADP, name, ID, and position. Neither endpoint supplies a source update timestamp, sample size, draft frequency, draft rank, or XRank. Data fetched more than 48 hours ago is treated as stale for survival. The provider's `ADP` field remains distinct from ranks and projections.

Fantrax's terms prohibit scraping and direct use through unpublished interfaces; this sync calls the two endpoints explicitly documented on Fantrax's developer page. The app is private and personal-use, not commercial, and the feed is not redistributed. The terms do not state a numeric API rate limit or an explicit data redistribution license; the implementation uses two sequential GETs, bounded retries, and no sharing. For any broader/commercial use, obtain written permission. The legacy manual CSV importer remains available but is not required for normal operation.

```csv
player_id,adp,draft_rank,draft_frequency
10001,24.5,20,82
10002,37.0,34,65
```

```bash
docker compose exec -T api python -m app.services.draft.market_import --season 2026-27 --source manual < draft-market.csv
```

Rows upsert by internal player, season, and source. Use a distinct `--source` label for each feed; imports never modify `player_identity`. This command requires a manually supplied file and is not the requested automatic solution.

Other candidates remain excluded: Yahoo's verified player pool has no ADP; ESPN publishes rankings/editorial draft material but its terms prohibit automated extraction absent express written permission; Sleeper's official docs did not establish an NBA ADP feed; Hashtag Basketball's public ADP is HTML and automated-use permission/stable feed were not verified; FantasyPros' free API tier is non-production; RotoWire prohibits automated extraction absent written consent; and the GitHub candidate has no declared license and predicts rather than reports ADP. No second free, documented, permitted machine-readable source has been verified. See [ADR 0004](docs/adr/0004-draft-market-source-selection.md).

Draft utility is a transparent heuristic based on Yahoo-weighted historical per-game production, replacement value, positional scarcity and need, durability, risk, upside, and roster-slot fit. It is not a projection or general player ranking.

Survival uses request ADP overrides first, then fresh Fantrax ADP, then no value. It also uses snake pick distance and recent positional runs. `draft_now` and `safe_to_wait` are the existing 50% heuristic threshold, not calibrated recommendations. Fantrax supplies no draft frequency, and the survival curve has not been calibrated against an evaluation dataset. Responses mark confidence as `heuristic_unvalidated`; missing or stale ADP stays unknown.

Historical Yahoo league `466.l.51267` and its `draftresults` endpoint returned HTTP 403, and the current league has not drafted. No historical engine-vs-ranking outperformance claim is available until real historical draft state, ADP snapshots, and season outcomes are supplied.

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

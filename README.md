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

The v1 endpoint returns the roster-best pick, best value at risk before the next turn, snake timing, positional runs, per-player availability assessments, component scores, explanations, and any IDs it could not score. It remains stateless and backward compatible. Recent pick IDs must be ordered oldest to newest; run detection examines the last ten.

For each player with ADP and draft timing, `market_value_delta = ADP - current_pick_number`: positive is a market reach, negative means the player has fallen past ADP. `reach_score` and `fall_score` range from 0 to 100 and scale each direction against one league round; they are descriptive heuristic indices, not probabilities or utility inputs. `expected_loss_if_gone` is the nonnegative `wait_utility_now` at stake. `expected_wait_cost` and its compatible alias `opportunity_cost_if_wait` use fallback expectation and can be positive, zero, negative, or unavailable. The best roster-fit player and the player with greatest positive expected wait cost are selected independently. Fantrax supplies no draft-rank field; the response says that comparison is unavailable. Opponent roster demand is not an input; only available pick history, market ADP, and the existing heuristic run signal inform survival.

### Persisted Draft Sessions (v2)

Use v2 when a live draft should survive reloads. `POST /api/v2/draft/sessions` creates a session from the imported Yahoo league and requires `team_slots` to explicitly map every imported team key to its 1-based draft slot. The mapping is not inferred. `GET /api/v2/draft/sessions/{session_id}` reloads picks, targets, session version, and the latest recommendation snapshot.

```json
{
  "league_key": "<imported-yahoo-league-key>",
  "season": "2026-27",
  "manager_team_key": "<manager-team-key>",
  "draft_position": 3,
  "total_teams": 4,
  "rounds": 13,
  "team_slots": {
    "<yahoo-team-key-for-slot-1>": 1,
    "<yahoo-team-key-for-slot-2>": 2,
    "<manager-team-key>": 3,
    "<yahoo-team-key-for-slot-4>": 4
  },
  "mode": "balanced"
}
```

Record the next overall pick with `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}` and `{ "selected_player_id": 10001, "expected_version": 0 }`. The service verifies that the player belongs to the imported Yahoo pool, derives the snake round/team slot from the overall pick, rejects out-of-order selections, and serializes updates with a session row lock. Repeating the same pick is idempotent. Stale versions return HTTP 409. Correct a pick with `PUT` on the same resource; undo only the latest pick with `POST .../{overall_pick}/undo`. Each mutation appends an audit event and a recommendation snapshot in the same transaction.

Targets use `PUT` and `DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}` with statuses `target`, `priority`, `watch`, or `avoid`; writes require the expected session version. Snapshots preserve the input state, ordered pick/source evidence, and calculation response. Process assessment and realized player outcomes are not yet evaluated.

For player A, the wait model uses the top five other scored candidates by `wait_utility_now` (roster utility plus mode adjustment, excluding the direct positional-run bonus). It estimates the fallback as the expected highest-utility alternative available at the next turn, assuming independent survival estimates. If alternatives are utility-ordered, `E_fallback = Σ_i [p_i × Π_{j<i}(1-p_j)] × U_i`; the probability no listed fallback survives contributes zero. Then `E_wait = P(A survives) × U(A) + P(A gone) × E_fallback`, and `expected_wait_cost = U(A) - E_wait`. Positive cost yields `draft_now`, zero/negative yields `wait`, and missing player/fallback survival yields `insufficient_evidence`. Run pressure affects pick ranking and survival but is excluded from `wait_utility_now`, so it is not added twice to wait value. Utility is held constant through intervening picks. These estimates are low-confidence, uncalibrated heuristics; no frequency or correlation data is available. The wait action does not apply the old 50% survival threshold. See [ADR 0006](docs/adr/0006-draft-survival-and-wait-method.md).

### PostgreSQL Migrations

The v2 draft tables are versioned separately from the legacy metadata bootstrap. Startup creates the established legacy tables, then applies pending migration revisions transactionally. Apply manually with:

```bash
docker compose run --build --rm --no-deps api python -m app.core.migrations upgrade
```

On a disposable database only, rollback the new draft tables with `docker compose run --rm --no-deps api python -m app.core.migrations downgrade base`; the next app startup reapplies pending migrations. This downgrade deletes draft sessions, picks, audit events, snapshots, and targets. Existing pre-v2 schema still uses the legacy bootstrap and is not covered by a baseline migration. See [ADR 0005](docs/adr/0005-draft-state-persistence.md).

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

Survival uses request ADP overrides first on v1; persisted v2 sessions use fresh stored Fantrax ADP. Both use snake pick distance and recent positional runs. Fantrax supplies no draft frequency, and the survival curve has not been calibrated against an evaluation dataset. Survival confidence is `heuristic_unvalidated`; missing or stale ADP stays unknown. v1 remains stateless and exposes survival independently; v2 action semantics use expected fallback loss.

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
- `POST /api/v2/draft/sessions`
- `GET /api/v2/draft/sessions/{session_id}`
- `POST|PUT /api/v2/draft/sessions/{session_id}/picks/{overall_pick}`
- `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}/undo`
- `PUT|DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}`

NBA provider calls happen only during imports. Player and league reads use PostgreSQL.

## Scope

This repository has no frontend, so the requested live Draft page is not implemented here. Category-league analytics, opponent roster demand, alert generation, room velocity, full sortable board/comparison UI, calibration, simulation, and retrospective decision-quality scoring remain deferred until those foundations exist and pass source-data validation. No external provider is called by v2 session reads or calculations. See [current state](docs/status/current-state.md), [next actions](docs/status/next-actions.md), [project memory](docs/project-memory.md), and [ADRs](docs/adr/0005-draft-state-persistence.md).

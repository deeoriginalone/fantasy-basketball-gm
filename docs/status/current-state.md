# Current State

## Yahoo Integration

Status: complete and live-verified.

- Yahoo OAuth and HTTPS callback completed; encrypted access and refresh tokens are stored and refresh works.
- Fantasy Sports API authorization and league/settings/team imports are verified.
- League `478.l.50505` (`Driveway Dudes`, 2026) has 12 fantasy teams.
- Yahoo player identity and pre-draft player-pool imports are verified: 733 available players; 0 roster assignments, expected before the draft.
- Yahoo player identities remain the authority for Yahoo ID, name, team, position, and status.

## NBA Data Foundation

Status: complete and live-verified for season `2026-27`.

- `POST /api/v1/nba/import` imports NBA teams, current-season players, the season schedule, and recent regular/preseason game logs.
- PostgreSQL tables: `nba_teams`, `players_nba`, `nba_games`, `player_game_logs`, and `player_schedule`.
- Verified persisted counts: 30 NBA teams; 616 NBA player records (615 current-player records plus 1 player present only in recent game logs); 1,274 schedule/game rows; 720 recent player game logs; 51,048 future player-schedule rows.
- 608 Yahoo `player_identity` rows received a unique NBA ID link. Existing Yahoo identity fields were not changed; ambiguous/unmatched identities remain nullable.
- One schedule side references a non-NBA exhibition opponent (`50015`); the original source payload is retained and the normalized relationship remains null.
- Recent game-log window defaults to 30 days and can be set from 1 to 90 days. Imports are transactional and idempotent; provider calls occur only on the POST import route.

## Draft Readiness Engine

Status: implemented and calculation paths verified; no draft state is persisted.

- PostgreSQL `nba_player_season_stats` stores Base per-game stats, Advanced minutes/usage, and starts for 2025-26 regular season plus 2026-27 regular/preseason: 1,054 rows.
- `POST /api/v1/draft/metrics?league_key=478.l.50505&season=2026-27` computes and persists 658 league-specific metrics from Yahoo's imported points weights and roster slots.
- Production metric coverage: 658 scored; 43 pool players lack an NBA ID; 32 mapped players lack usable stats. Unscored players are returned by ID and are not given inferred values.
- `POST /api/v1/draft/utility` accepts league key, manager team key, season, drafted internal player IDs, and available internal player IDs. It returns one highest-utility pick plus component scores and unscored IDs, not a general ranking list.
- Metrics select the most recent eligible regular-season sample with at least 10 games, else the latest regular season, else current preseason, else current-season game logs. Fantasy value is Yahoo-weighted per-game stats.
- Utility formula: `F * (1 + 0.05D + 0.05U - 0.05R) + 0.5V + max(|F|, 1) * (0.10N + 0.05SN + 0.05C)`, where `F` is fantasy value, `V` replacement value, `S` scarcity, `N` positional need, `D` durability, `R` risk, `U` upside, and `C` roster construction; percentage components are normalized to 0-1. Fixed-slot fit earns more construction credit than flex/bench placement.
- A live smoke test for manager team `478.l.50505.t.9` (“Box Score Bully”) used five simulated drafted players and the remaining 728 Yahoo pool entries; the engine returned Nikola Jokić. The simulated draft was not saved.

## Validation

- Full backend suite against isolated PostgreSQL: 30 passed, with one existing Starlette/httpx TestClient deprecation warning.
- Integration tests cover NBA teams, players, games, schedules, logs, season stats, draft metrics, roster-specific utility, duplicate prevention, idempotence, and non-destructive Yahoo identity linking.
- Live import returned HTTP 200. Existing Yahoo league read still returns HTTP 200 with all 12 teams after NBA imports.
- A second live import returned the same dataset counts, with 0 additional log-only players and 0 new identity links.
- API health returned HTTP 200; the NBA import route is present in OpenAPI.
- The five NBA tables are created by the existing SQLAlchemy startup metadata bootstrap; this repository does not yet have versioned migrations.
- The `nba_player_season_stats` and `draft_player_metrics` tables are created through the same metadata bootstrap; no versioned migration framework exists.

## Known Boundaries

- NBA data is stored in PostgreSQL; no NBA GET/read endpoints or frontend were added in this ingestion milestone.
- NBA/ESPN identity links are not guessed; only a unique normalized full-name and known-team match fills a null NBA ID.
- Draft fantasy value uses historical per-game stats with heuristic durability/risk/upside adjustments; it is not a statistical projection or injury assessment.
- No season projection model, waivers, trades, matchup analysis, alerts, news, season management, AI summaries, or frontend have been built.
- The API has no general user authentication and must remain on a trusted network.
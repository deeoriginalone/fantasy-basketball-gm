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
- Verified persisted counts: 30 NBA teams; 717 `players_nba` records; 1,274 schedule/game rows; 720 recent player game logs; 51,048 future player-schedule rows. The earlier 616 count was stale; the live database currently reports 717.
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
- `draft_market_data` stores optional ADP/rank/frequency per internal player, season, and source. Fantrax's documented public API is selected for this private personal app; an idempotent sync, provider snapshots, and sync-run diagnostics are implemented.
- Draft Room V2 accepts `draft_position`, `round_number`, `total_teams`, `recent_pick_player_ids` (oldest to newest), `adp_by_player_id`, and `mode` (`balanced`, `upside`, `safe`). Snake turn gap is computed from 1-based team position and round parity.
- Positional runs inspect the last 10 supplied picks and activate at 3 picks and at least 30% of the window. Matching candidates receive a bounded run-pressure utility bonus.
- The legacy stdin CSV importer remains available as an optional offline path; it is not required for normal operation. Sync with `python -m app.services.draft.market_sync --season 2026-27`; inspect persisted status with `python -m app.services.draft.market_diagnostics --season 2026-27`.
- Yahoo player payloads still contain no ADP, rank, XRank, or ownership. Fantrax provides ADP plus a separate ID/team/position crosswalk; draft rank, XRank, frequency, sample size, and upstream update time are not provided.
- Base survival is `sigmoid((ADP - next_pick_number) / max(total_teams / 2, 1))`, optionally multiplied by `(1 - 0.25 * draft_frequency)` and raised to `(1 + 0.12 * min(run_count, 8))`. Fantrax supplies no draft frequency, so the production path uses ADP, pick distance, and recent runs only. Availability also includes positional scarcity and picks until turn. It is explicitly uncalibrated.
- Response includes the roster-best player with explanation reasons and component scores, plus best value at risk before the next turn. The latter maximizes mode-adjusted utility times probability of being unavailable on the next turn; numeric `opportunity_cost_if_wait` is exposed, and this player may differ from the best roster fit. No draft picks are persisted.
- Each available player's existing response entry now includes `market_value_delta = ADP - current_pick_number`, plus 0-100 reach/fall indices scaled to one league round. These are descriptive, uncalibrated market-timing signals and do not directly alter utility. The explanation separates team fit, roster construction, ADP, scarcity/run pressure, survival, and wait cost. No route was added.
- Yahoo's current player payloads and `draft_analysis` probe have no ADP field. Fantrax sync is independent of Yahoo import; request ADP overrides fresh Fantrax ADP. Stale/missing ADP yields null survival and is listed in `adp_missing_available_player_ids`. Missing market values are never fabricated.
- Historical Yahoo league `466.l.51267` and its `draftresults` endpoint both returned HTTP 403. There are no historical draft states locally, so engine-vs-ranking outperformance is not yet validated; this success criterion remains blocked on real historical picks, ADP snapshots, and season outcomes.
- No historical replay result or recommendation audit table exists. Actual historical draft picks, ADP snapshots, and season outcomes are required to validate that the engine beats simple ranking.
- V2 run detection uses the last 10 chronological recent picks; a group is active with at least 3 picks and 30% of the window. Center/guard/forward pressure adds a bounded mode-adjusted bonus. Modes: `balanced`, `upside`, `safe`.
- A live smoke test for manager team `478.l.50505.t.9` (“Box Score Bully”) used five simulated drafted players and the remaining 728 Yahoo pool entries; the engine returned Nikola Jokić. The simulated draft was not saved.
- V2 live smoke test for the same manager team calculated slot 9, round 2, 12 teams as pick 16 with 16 intervening picks and next pick 33. A simulated three-center run activated; `upside` mode returned a best roster pick and a separate best-at-risk-before-next-turn pick using synthetic request ADPs. No draft state was saved.

## Validation

- Full backend suite against isolated PostgreSQL: 51 passed, with one existing Starlette/httpx TestClient deprecation warning. Final verification follows below.
- Integration tests cover NBA ingestion, draft metrics/utility, provider parsing, retry/timeout handling, conservative identity matching, idempotent sync, failure preservation, stale-data handling, request override precedence, and Yahoo identity non-mutation.
- Live import returned HTTP 200. Existing Yahoo league read still returns HTTP 200 with all 12 teams after NBA imports.
- A second live import returned the same dataset counts, with 0 additional log-only players and 0 new identity links.
- API health returned HTTP 200; the NBA import route is present in OpenAPI.
- Fantrax live API sync on 2026-10-10 fetched 334 records; 312 matched internal players; 0 ambiguous; 22 unresolved (2 `no_name_match`, 11 `position_mismatch`, 9 `source_team_missing`). Production has 312 unique Fantrax ADP rows, 0 draft-rank rows, and 0 frequency rows. ADP coverage is 42.56% of 733 identities; rank/frequency coverage is 0%. Stale rows: 0. Another 399 Yahoo identities are absent from the provider ADP response. Upstream source age is unavailable; successful retrieval age was under one minute at verification.
- A live `/api/v1/draft/utility` request for Yahoo-pool IDs 10069, 10148, and 10140 used Fantrax ADP values 1.44, 3.47, and 3.59. It returned fresh, `heuristic_unvalidated` survival values and `draft_now`/`safe_to_wait` explanations. Manager team `478.l.50505.t.9` remained readable after API recreation.
- After the decision-timing update, the existing route was rebuilt and live-checked with those same IDs at slot 9, round 1, 12 teams: pick 9, next pick 16, six intervening selections. Jokić was both best roster fit and highest value at risk in this candidate set; response included ADP 1.44, delta -7.6, fall 63/100, next-pick survival 8.1%, and `draft_now=true`. This is a live data-path smoke test, not a calibration or decision-accuracy claim.
- The five NBA tables are created by the existing SQLAlchemy startup metadata bootstrap; this repository does not yet have versioned migrations.
- The `nba_player_season_stats` and `draft_player_metrics` tables are created through the same metadata bootstrap; no versioned migration framework exists.

## Known Boundaries

- NBA data is stored in PostgreSQL; no NBA GET/read endpoints or frontend were added in this ingestion milestone.
- NBA/ESPN identity links are not guessed; only a unique normalized full-name and known-team match fills a null NBA ID.
- Draft fantasy value uses historical per-game stats with heuristic durability/risk/upside adjustments; it is not a statistical projection or injury assessment.
- No season projection model, waivers, trades, matchup analysis, alerts, news, season management, AI summaries, or frontend have been built.
- The API has no general user authentication and must remain on a trusted network.
- Survival values require current ADP and draft timing; without either, survival and the best-before-next-turn choice are unknown. Provider ADP older than 48 hours is not used for survival.
- Fantrax does not publish sample size, draft frequency, draft rank, XRank, or source-updated timestamp. Market coverage is partial; 421 identities remain without ADP (399 absent from the source plus 22 unresolved matches). The API terms do not state a numeric rate limit or grant redistribution rights. This installation uses documented interfaces for private personal use only and does not redistribute the feed.

## Draft-Market Source Discovery

As of 2026-10-10, Fantrax is selected for private personal use through its documented public `getAdp` and `getPlayerIds` REST endpoints. Two live GETs returned current machine-readable NBA ADP and a Fantrax ID/team/position crosswalk. Sync matches normalized name, team, and position uniquely and rejects missing-team/ambiguous records. Fantrax terms prohibit scraping but the sync uses the published API. No data is redistributed; broader use needs separate permission. Other source findings and exact field/term limits are in [ADR 0004](../adr/0004-draft-market-source-selection.md).

The final sync fetched 334 records, safely matched 312, and left 22 unresolved; 399 additional Yahoo identities are absent from the source feed. No other free, documented, machine-readable source with verified automated-use permission was found. ESPN has public rankings/editorial draft content, but Disney terms prohibit automated extraction without express written permission. Sleeper's official docs did not establish an NBA ADP endpoint. The source gap is retained as unknown; rankings, projections, mock drafts, and inferred values are not substituted for ADP.

Fantrax does not publish ADP sample size/frequency or source-updated time. Retrieval time is persisted; data is stale after 48 hours. Survival remains heuristic and uncalibrated, with explicit `heuristic_unvalidated` confidence and a 50% Draft Now/Safe to Wait threshold.
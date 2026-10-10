# Project Memory

## Product and Boundaries

- This greenfield repository is separate from the NFL/Fantasy Intelligence project.
- Yahoo Fantasy API is the source of truth for manager leagues, NBA game key, teams, and league rules/settings.
- Current foundations are the verified Yahoo integration, NBA ingestion/storage, and Draft Room Intelligence for roster-specific live picks. Do not add UI or features outside draft intelligence without separate approval.
- Draft flow: Yahoo player pool -> internal identity <- NBA player/stat data -> league-scoring metrics -> snake timing, run and availability context -> roster/mode utility. Runtime calculations read PostgreSQL only; ADP and recent picks are explicit request inputs.
- The existing Yahoo pool payload has no ADP, draft rank, XRank, or ownership fields, and no draft history. Never infer ADP or claim calibrated survival probabilities. Without caller-supplied ADP, leave next-pick survival and ADP-based availability null and report missing IDs.
- `draft_market_data` stores optional ADP, draft rank, draft frequency, source, and update timestamp by internal player/season/source. Fantrax is the selected personal-use source through documented `getAdp` and `getPlayerIds` endpoints. Sync with `python -m app.services.draft.market_sync --season YYYY-YY`; diagnostics with `python -m app.services.draft.market_diagnostics --season YYYY-YY`. The Fantrax feed supplies ADP only; rank/frequency/sample size/source update time remain null. Never scrape Fantrax pages or redistribute its feed; see ADR 0004.
- Market data is keyed to `player_identity.id`; never overwrite `player_identity` from an ADP feed. Fantrax matches require unique normalized full name, current team, and position; ambiguous/missing-team players remain unresolved. Utility priority is request ADP, then fresh Fantrax ADP, then unknown. Stored ADP older than 48 hours is stale and not used for survival.
- Existing utility response timing: `market_value_delta = ADP - current_pick_number`; positive means reach, negative means the player fell past market ADP. Reach/fall indices are 0-100, scaled to one league round, descriptive only. `opportunity_cost_if_wait = mode_adjusted_utility * (1 - survival_probability)`; the best roster-fit pick and highest at-risk pick are independently selected. Fantrax draft frequency is unavailable and must remain null. Keep survival explicitly `heuristic_unvalidated`; no calibration/history work is in scope.
- Verified 2026-10-10 source coverage is 312/733 identities (42.56%); 399 are absent from Fantrax and 22 source rows are unresolved (2 no-name, 11 position mismatch, 9 missing team). ESPN automation is disallowed by Disney terms absent express written permission; Sleeper's official docs did not establish NBA ADP. No other qualifying free feed is verified; never fill gaps with rankings/projections or guessed ADP.
- Yahoo's linked prior-season league/draftresults endpoint returned 403; no historical draft state/outcome is stored locally. Do not claim historical superiority until actual draft-pick/ADP/outcome data is supplied and replayed.
- Do not build waivers, trades, matchup analysis, alerts, news, season management, AI summaries, or UI without explicit approval.

## Integration Architecture

- Reuse `backend/app/features/yahoo/oauth.py` for OAuth code exchange, encrypted credential storage, and expiry-based refresh. Token encryption uses `backend/app/core/security.py`; database access uses `backend/app/core/database.py`.
- `backend/app/services/yahoo/` owns Yahoo HTTP calls, NBA game-key discovery, league/settings/team retrieval, and Yahoo response normalization.
- `backend/app/features/leagues/` owns typed application contracts, PostgreSQL persistence, and league read/import routes.
- PostgreSQL owns `yahoo_credentials`, `leagues`, `league_settings`, and `teams`. Preserve Yahoo source payloads and do not invent values for missing league settings.
- Imports are idempotent by Yahoo keys and replace a league's team snapshot transactionally.
- Yahoo resource GETs retry transient transport, 429, and 5xx failures with bounded backoff; logs carry structured path/status metadata and never include tokens.
- OAuth callback persists encrypted tokens and starts the initial league import; `POST /api/v1/leagues/import` supports later retries.
- `backend/app/services/yahoo/players.py` reads all player pages and each imported Yahoo team's roster; it uses the existing OAuth/token service and Yahoo HTTP client.
- `player_identity.id` is the internal player ID and `yahoo_player_id` is the required unique source key. NBA and ESPN IDs remain nullable until authoritative mapping sources exist.
- `players` stores per-league Yahoo observations; `fantasy_teams` mirrors existing `teams`; `rosters` links fantasy teams to internal player identities. Snapshot refresh and identity changes are transactional and idempotent.
- `backend/app/services/nba/` owns the `nba_api` adapter and team, player, schedule, and recent game-log imports. Persist source records in `nba_teams`, `players_nba`, `nba_games`, `player_game_logs`, and `player_schedule`.
- `POST /api/v1/nba/import` fetches teams, current-season players, season schedule, then recent regular/preseason player game logs; all writes run transactionally and are idempotent. External calls are import-only; database reads never invoke `nba_api`.
- NBA identity linking fills only null `player_identity.nba_player_id` values when normalized full name and known team abbreviation match uniquely on both sides. Never change Yahoo IDs or Yahoo-derived identity fields; leave ambiguous/unmatched links null.
- Preserve unknown or TBD schedule-team references as null normalized team IDs with the original `nba_games.source_payload` intact; report nonzero unresolved references in the import result.
- `nba_player_season_stats` stores Base per-game production, Advanced minutes/usage, and starter-filter starts by NBA player, season, and season type. Import prior completed regular season plus current regular/preseason snapshots.
- `backend/app/services/draft/metrics.py` derives league-specific per-game fantasy value from Yahoo point weights, replacement value from roster-slot demand, positional scarcity from demand versus eligible supply, durability from games played, risk from durability/start rate, and upside from usage/minutes percentiles.
- `backend/app/services/draft/utility.py` scores only the supplied available players against the supplied drafted roster and Yahoo roster slots. The formula is a transparent heuristic, not a predictive projection model.
- Snake turn timing uses the manager's 1-based draft position, current round, league team count, and alternating round direction. Run detection examines the last 10 caller-supplied picks; an active group needs at least 3 picks and 30% of the window. Run pressure adjusts the mode-adjusted utility.
- `balanced`, `upside`, and `safe` modes change only the utility adjustment; the selected player still uses league metrics, roster need, replacement, scarcity, and fixed/flex slot fit. Utility returns one best roster pick and one at-risk value before the next turn, not a full ranked list.
- Draft endpoints accept internal player identity IDs from the Yahoo league pool; no draft state is saved. Unmapped or unscored players stay explicitly unscored and are never assigned guessed NBA data.
- Player/roster read routes return PostgreSQL data only. Missing Yahoo status stays null; never infer health from absence.
- Pre-draft rosters may be empty. Accept only structurally valid Yahoo collections with an explicit zero count; still persist fantasy teams and the separately fetched player pool. Reject malformed/contradictory collections before deleting or replacing snapshots. Re-import after the draft populates rosters idempotently.
- Normalized scoring categories join Yahoo's own stat IDs/names/weights; keep the full Yahoo settings response as the source payload. Never hardcode a league's scoring weights or roster positions.
- Uvicorn access logging is disabled so OAuth callback query parameters are not written to request logs. Never print or log credentials, OAuth state, authorization codes, or tokens.
- SQLAlchemy `Base.metadata.create_all()` remains the only schema bootstrap. There is no versioned migration framework; add one before production schema evolution.

## Operational Notes

- Configure secrets in an ignored local `.env` or deployment secret store; `.env.example` contains placeholders only. Never copy real credentials into example files or documentation.
- Yahoo's registered redirect URI must exactly match `YAHOO_REDIRECT_URI` and `/api/v1/yahoo/oauth/callback`.
- Docker Compose binds the API to `0.0.0.0:${API_PORT:-18002}` for trusted LAN access; the default callback uses the same port. Keep `YAHOO_REDIRECT_URI` and Yahoo developer-console callback registration aligned. Port 8000 may be occupied by Portainer on this host.
- The Compose API port is plain HTTP. If `YAHOO_REDIRECT_URI` uses HTTPS, TLS must terminate at the callback host/port and forward internally to Uvicorn. Never configure an HTTPS callback to the raw HTTP mapping or claim OAuth is verified from a redirect alone.
- Yahoo OAuth, the HTTPS callback, encrypted access/refresh storage, token refresh, Fantasy Sports authorization, and live Yahoo imports are verified for league `478.l.50505`.
- NBA Data Foundation live import is verified for season `2026-27`: 30 teams, 615 current-source players plus 1 game-log-only player, 1,274 games, 720 recent logs, 51,048 player schedule rows, and 608 unique Yahoo identity links. One source-reported non-NBA schedule opponent is preserved as unresolved.
- Draft readiness is live-verified for Yahoo league `478.l.50505`: 717 `players_nba` records, 1,054 season-stat snapshots, 658 league-specific metrics, and a manager-team utility request successfully returned a roster-specific pick. 43 Yahoo pool players lack NBA IDs and 32 mapped players lack eligible stats; both groups remain unscored.
- The API has no general user authentication. Do not expose the LAN binding beyond trusted networks or publicly; network firewalling remains an operational boundary.
- Verify OAuth/league network calls with mocked responses unless real credentials and an authorized account are explicitly available. Never claim a live Yahoo import based only on mocks.
- Keep `docs/status/current-state.md`, `docs/status/next-actions.md`, and the dated session note current for every completed coding task.
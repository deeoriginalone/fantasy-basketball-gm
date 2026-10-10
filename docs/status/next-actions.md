# Next Actions

## Current Boundary

The owner-approved scope includes persisted live draft state and a versioned API. Preserve Yahoo identity authority and fail-closed data behavior. No new provider or scraping is approved. The repository has no frontend; the requested live Draft page remains an implementation gap despite backend authorization.

## Operational Follow-up

- Refresh NBA teams, players, schedules, and the recent game-log window through `POST /api/v1/nba/import`; choose and document an operational cadence before scheduling automatic imports.
- Refresh league draft metrics with `POST /api/v1/draft/metrics` after NBA statistics or Yahoo scoring/roster settings change; utility requests also recompute metrics from PostgreSQL.
- For stateless evaluation, continue using `POST /api/v1/draft/utility`. For persisted drafts, create a v2 session with a complete explicit team-slot map, then use v2 read/pick/correction/undo and target routes. Pass the current version on each update. Picks must arrive in overall order and use internal IDs from the Yahoo league pool.
- Run `python -m app.services.draft.market_sync --season 2026-27` after deployment/rebuild and periodically during draft season. The job is idempotent, uses the documented Fantrax REST API, and leaves old good rows untouched on fetch failure.
- Inspect provider counts, match rejection, coverage, and retrieval freshness using `python -m app.services.draft.market_diagnostics --season 2026-27`.
- Fantrax has no published sample size/frequency or source update timestamp. Treat local retrieval age as freshness; data older than 48 hours yields unknown survival. Do not substitute rankings, ownership, XRank, or projections.
- Fantrax terms allow personal use through published interfaces but prohibit scraping; this app does not redistribute data. Re-check and obtain written permission before any broader use.
- Current verified source ceiling is 312 matched ADP rows (42.56% of 733 identities); 399 identities are absent from Fantrax and 22 returned records are unresolved. No additional free feed with documented access and verified automated-use permission was found. Keep missing ADP unknown; revisit only when a qualifying source or written permission becomes available.
- Provide real historical pick order/state, matching ADP snapshots, and completed-season outcomes before claiming historical draft validation or outperformance. The linked prior Yahoo league is inaccessible (403); no synthetic results should substitute.
- Use the returned `draft_timing.picks_until_next_turn` and run summary to understand timing pressure. Run detection uses the latest ten picks and is a heuristic, not a statistical trend model.
- Interpret survival as `heuristic_unvalidated` and decision confidence as low/unavailable; no calibration dataset exists. The v2 action compares current utility with expected fallback utility, assumes independent heuristic survival and unchanged utility, and leaves missing/stale survival unknown.
- Fantrax provides no draft-frequency field; keep frequency null and omit its optional survival adjustment rather than infer it.
- To complete historical validation, supply actual prior draft picks/order, ADP snapshots, and season outcomes. Yahoo returned 403 for linked previous-season league `466.l.51267`; do not substitute synthetic records or claim historical outperformance.
- Select `balanced`, `upside`, or `safe` when creating the v2 session. Review the stored recommendation snapshot, missing/stale diagnostics, fallback branches, position need, scarcity, and run signal.
- Review whether 43 unmapped Yahoo players and 32 mapped players without usable season stats need better source coverage. Leave them unscored until authoritative data is available.
- Monitor NBA source coverage and the one unresolved exhibition opponent; retain raw source evidence and do not infer team identity.
- Run migration downgrade only against a disposable database; downgrade removes all persisted v2 draft sessions, picks, events, snapshots, and targets. Legacy Yahoo/NBA schema still has no baseline migration.
- The next product batch is frontend implementation plus validated category, scarcity-tier, opponent-demand, room-intelligence, and alert calculation boundaries. Do not present these as implemented until the required data contracts and tests exist.

Projections, waivers, trades, matchup analysis, news, season management, AI summaries, calibrated survival, simulation, and retrospective process/outcome scoring remain deferred.
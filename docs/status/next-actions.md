# Next Actions

## Current Boundary

The owner-approved active scope is improving live draft timing advice inside the existing utility flow: draft now vs wait, market reach/fall, explanation, and value at risk. Do not add endpoints, providers, scraping, or excluded product features.

## Operational Follow-up

- Refresh NBA teams, players, schedules, and the recent game-log window through `POST /api/v1/nba/import`; choose and document an operational cadence before scheduling automatic imports.
- Refresh league draft metrics with `POST /api/v1/draft/metrics` after NBA statistics or Yahoo scoring/roster settings change; utility requests also recompute metrics from PostgreSQL.
- During the draft, submit manager team key, 1-based draft position, current round, imported team count, drafted IDs, available IDs, recent picks, and mode to `POST /api/v1/draft/utility`. Player IDs must come from the selected Yahoo league pool; recent picks are chronological, oldest to newest.
- Run `python -m app.services.draft.market_sync --season 2026-27` after deployment/rebuild and periodically during draft season. The job is idempotent, uses the documented Fantrax REST API, and leaves old good rows untouched on fetch failure.
- Inspect provider counts, match rejection, coverage, and retrieval freshness using `python -m app.services.draft.market_diagnostics --season 2026-27`.
- Fantrax has no published sample size/frequency or source update timestamp. Treat local retrieval age as freshness; data older than 48 hours yields unknown survival. Do not substitute rankings, ownership, XRank, or projections.
- Fantrax terms allow personal use through published interfaces but prohibit scraping; this app does not redistribute data. Re-check and obtain written permission before any broader use.
- Current verified source ceiling is 312 matched ADP rows (42.56% of 733 identities); 399 identities are absent from Fantrax and 22 returned records are unresolved. No additional free feed with documented access and verified automated-use permission was found. Keep missing ADP unknown; revisit only when a qualifying source or written permission becomes available.
- Provide real historical pick order/state, matching ADP snapshots, and completed-season outcomes before claiming historical draft validation or outperformance. The linked prior Yahoo league is inaccessible (403); no synthetic results should substitute.
- Use the returned `draft_timing.picks_until_next_turn` and run summary to understand timing pressure. Run detection uses the latest ten picks and is a heuristic, not a statistical trend model.
- Interpret survival confidence as `heuristic_unvalidated`; no calibration dataset exists. `draft_now` and `safe_to_wait` use a 50% heuristic threshold, not an empirically calibrated decision boundary.
- Fantrax provides no draft-frequency field; keep frequency null and omit its optional survival adjustment rather than infer it.
- To complete historical validation, supply actual prior draft picks/order, ADP snapshots, and season outcomes. Yahoo returned 403 for linked previous-season league `466.l.51267`; do not substitute synthetic records or claim historical outperformance.
- Select `balanced`, `upside`, or `safe` per pick. Review the returned reasons, position need, scarcity, run signal, and survival estimate; no draft state is saved between requests.
- Review whether 43 unmapped Yahoo players and 32 mapped players without usable season stats need better source coverage. Leave them unscored until authoritative data is available.
- Monitor NBA source coverage and the one unresolved exhibition opponent; retain raw source evidence and do not infer team identity.
- Add a versioned PostgreSQL migration workflow before production schema evolution.

Do not begin projections, waivers, trades, matchup analysis, alerts, news, season management, AI summaries, or UI until separately planned and explicitly approved.
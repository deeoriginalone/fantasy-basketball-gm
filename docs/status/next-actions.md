# Next Actions

## Current Boundary

The Draft Readiness Engine stops at per-player metrics and a roster-specific Draft Utility Score. Do not begin another feature until the owner reviews its assumptions and explicitly approves the next milestone.

## Operational Follow-up

- Refresh NBA teams, players, schedules, and the recent game-log window through `POST /api/v1/nba/import`; choose and document an operational cadence before scheduling automatic imports.
- Refresh league draft metrics with `POST /api/v1/draft/metrics` after NBA statistics or Yahoo scoring/roster settings change; utility requests also recompute metrics from PostgreSQL.
- During the draft, submit the manager team key, already-drafted internal player IDs, and remaining available IDs to `POST /api/v1/draft/utility`. Inputs must come from the selected Yahoo league pool.
- Review whether 43 unmapped Yahoo players and 32 mapped players without usable season stats need better source coverage. Leave them unscored until authoritative data is available.
- Monitor NBA source coverage and the one unresolved exhibition opponent; retain raw source evidence and do not infer team identity.
- Add a versioned PostgreSQL migration workflow before production schema evolution.

Do not begin projections, waivers, trades, matchup analysis, alerts, news, season management, AI summaries, or UI until separately planned and explicitly approved.
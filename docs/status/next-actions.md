# Next Actions

## Next Milestone: NBA Data Integration

Plan and implement the authoritative NBA data source before building downstream analysis. Do not begin this work as part of the Yahoo release.

## Future Phases

- `nba_api` ingestion
- NBA game logs
- NBA schedules
- Shared scoring engine
- Projections
- Start/sit decisions
- Waivers
- Trades
- Draft center

## Current Operational Follow-up

- After the Yahoo league drafts, rerun the league player import and verify roster assignments populate without duplicates.
- Keep OAuth secrets and token data out of documentation, logs, and commits.
- Add a versioned database migration workflow before production schema evolution.

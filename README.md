# Fantasy Basketball GM

Personal fantasy basketball GM and analytics platform using Yahoo Fantasy Sports data. Current status below reflects the verified running deployment as of 2026-10-09.

## Verified Capabilities

- Yahoo OAuth authorization and HTTPS callback complete; access and refresh tokens are stored.
- Fantasy Sports API authorization and live league import verified.
- League settings, 12 fantasy teams, and canonical Yahoo player identities imported.
- Available pre-draft player pool imported: 733 players.
- Pre-draft handling verified: 0 roster assignments is expected until the league drafts.

## Current Status

| Metric | Verified value |
| --- | --- |
| League key | `478.l.50505` |
| League | Driveway Dudes, 2026 |
| Fantasy teams | 12 |
| Available players | 733 |
| Draft status | Pre-draft |
| Roster assignments | 0 (expected) |

## Known Limitations

- Yahoo is the only integrated player-data source. NBA and ESPN player IDs are not mapped yet.
- This is an API backend, not a dashboard. The API has no general user authentication and should remain on a trusted network.
- No NBA data ingestion, game logs, schedules, scoring engine, projections, start/sit, waivers, trades, or draft-center features are included.
- Empty rosters are normal before the draft. Re-import after the draft to populate Yahoo roster assignments.

## Next Milestone

NBA Data Integration. Future phases include `nba_api` ingestion, game logs, schedules, a scoring engine, projections, start/sit, waivers, trades, and draft center. No NBA API work has started.

## Documentation

- [Project memory](docs/project-memory.md)
- [Current state](docs/status/current-state.md)
- [Next actions](docs/status/next-actions.md)
- [Architecture decisions](docs/adr/)
- [v0.1.0 release notes](docs/releases/v0.1.0-yahoo-working.md)

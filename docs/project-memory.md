# Project Memory

## Product and Boundaries

- Single-manager fantasy basketball support using Yahoo Fantasy Sports as the source of truth for leagues, teams, rules, and Yahoo player IDs.
- Do not infer player identity mappings, statuses, scoring rules, or roster positions when Yahoo does not supply them.
- Keep Yahoo networking behind backend services. Player and league read routes serve persisted PostgreSQL data only.
- No UI, projections, recommendations, or transaction automation is part of the completed Yahoo milestone.

## Integration Architecture

- `backend/app/features/yahoo/` owns OAuth code exchange, encrypted access/refresh token storage, and expiry-based refresh.
- `backend/app/services/yahoo/` owns Yahoo HTTP calls, game discovery, pagination, response normalization, and source payload handling.
- League records, settings, and teams are persisted by Yahoo keys. Player identities use a stable internal ID and a required unique Yahoo player ID; NBA and ESPN IDs remain nullable pending authoritative sources.
- League player observations, fantasy-team mirrors, and roster assignments are stored separately. Imports replace league snapshots transactionally and are idempotent.
- A valid explicit zero-player roster is expected before the draft. Import the separately fetched player pool and fantasy teams even when roster assignments are empty.
- Preserve missing Yahoo status as null; never infer health from missing data.

## Verified Milestone

First successful Yahoo Fantasy Basketball integration completed.

- OAuth authorization and callback completed; access and refresh tokens are stored.
- Fantasy Sports API authorization and live league/settings/team import were verified.
- Yahoo league `478.l.50505` (`Driveway Dudes`, 2026) imported with 12 fantasy teams.
- The pre-draft player import created 733 player identities and zero roster assignments, as expected before the draft.

## Operational Boundaries

- Keep credentials, OAuth state secrets, and encryption keys in ignored local environment configuration or a secret store. Never commit, print, or log them.
- The Yahoo callback must exactly match the registered callback and `YAHOO_REDIRECT_URI`.
- The API is unauthenticated beyond Yahoo's integration and must remain on a trusted network. Caddy provides HTTPS at the configured LAN endpoint.
- Schema bootstrap currently uses SQLAlchemy metadata; introduce versioned migrations before schema evolution.

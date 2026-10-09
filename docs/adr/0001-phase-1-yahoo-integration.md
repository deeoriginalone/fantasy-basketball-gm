# ADR 0001: Yahoo Fantasy Integration

- Status: Accepted
- Date: 2026-10-09

## Context

The first milestone connects one manager's Yahoo account and imports NBA fantasy league data without introducing a second source of truth, UI, or inferred rules. Yahoo responses may include additional league and settings fields, so source payloads must remain auditable.

## Decisions

- Yahoo Fantasy Sports is authoritative for game keys, manager leagues, teams, and league settings.
- Use the server-side OAuth 2 authorization-code flow. Bind signed, expiring state to the initiating browser and never return tokens from API responses.
- Encrypt persisted access and refresh tokens. Keep client credentials, OAuth state secrets, encryption keys, and database credentials in environment configuration.
- Persist league metadata, normalized settings, and teams by Yahoo keys. Preserve raw Yahoo payloads and do not replace absent Yahoo fields with local defaults.
- Keep Yahoo networking and response normalization in the backend service layer; feature persistence and API contracts remain in their owning modules.
- The OAuth callback stores tokens and imports leagues. Explicit import routes support retries.
- Retry bounded transient Yahoo GET failures; never include credentials or tokens in structured logs.
- Expose the API through Caddy HTTPS on a trusted LAN. This single-manager service has no general user authentication and is not intended for public exposure.
- Use SQLAlchemy metadata as the current schema bootstrap. Add versioned migrations before schema evolution.

## Consequences

- Connecting Yahoo requires an authorized Yahoo application, an exact registered redirect URI, and local secret configuration.
- Changing the encryption key makes stored tokens unreadable and requires reconnecting the account.
- Live OAuth, league, settings, team, and player imports are verified for the current deployment; offline tests remain necessary for failure and boundary cases.
- UI and recommendation features remain out of scope until their backend contracts and data dependencies are planned.

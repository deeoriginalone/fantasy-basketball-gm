# ADR 0001: Phase 1 Yahoo Integration

- Status: Accepted
- Date: 2026-10-09

## Context

Phase 1 needs to connect one manager's Yahoo account and import NBA fantasy leagues without introducing UI, inferred league rules, or a second source of truth. Yahoo API responses can contain additional league/settings fields, so retaining source payloads is necessary for auditability and later contract evolution.

## Decisions

- Yahoo Fantasy API is authoritative for the game key, manager leagues, and league settings. The NBA game key is discovered from Yahoo rather than assuming a season-specific identifier.
- Use server-side OAuth 2 authorization-code exchange. Sign and expire OAuth `state` values, bind them to the initiating browser with a short-lived HttpOnly cookie, and never return access or refresh tokens from API responses.
- Encrypt persisted access and refresh tokens with a configured Fernet key. Keep client credentials, state-signing secret, encryption key, and database credentials in environment configuration.
- Persist league metadata and both the extracted settings value and full Yahoo settings response in PostgreSQL. Do not replace absent Yahoo fields with local defaults.
- Normalize Yahoo's fragmented league/team collections into `leagues`, `league_settings`, and `teams`; preserve raw Yahoo entity payloads and make imports idempotent by Yahoo keys.
- Keep Yahoo networking and response normalization in `backend/app/services/yahoo/`; feature persistence and API contracts remain in `backend/app/features/leagues/`.
- The OAuth callback imports leagues immediately after encrypted token storage; a separate import route supports retrying the sync later.
- Yahoo GET calls retry bounded transient network, rate-limit, and server failures. Structured logs exclude credentials and token values.
- Disable Uvicorn access logging because Yahoo authorization codes and signed OAuth state arrive in callback query parameters.
- Use SQLAlchemy metadata creation as a Phase 1 local bootstrap. Add versioned migrations before schema evolution or production deployment.
- Bind the API to loopback in Docker Compose. This local single-manager phase does not provide general user authentication or public-deployment protections.

## Consequences

- Connecting Yahoo requires a registered Yahoo application and locally configured secrets.
- Changing the encryption key makes stored tokens unreadable and requires reconnecting the Yahoo account.
- League/settings import depends on live Yahoo authorization and API availability; offline tests cover local parsing and security behavior only.
- UI and recommendations remain blocked until backend contracts and later domain data contracts are established.
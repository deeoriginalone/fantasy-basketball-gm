# ADR 0005: Persisted Draft State and Migrations

- Status: Accepted
- Date: 2026-10-10

## Context

The prior draft utility was stateless, so a live room could not be resumed, corrections could overwrite history, and concurrent clients could not detect stale input. Existing production tables were bootstrapped with SQLAlchemy `create_all()` and had no migration ledger.

## Decisions

- Preserve `/api/v1/draft/utility` as the stateless compatibility path. Add versioned `/api/v2/draft/sessions` create/read, pick record/correction/undo, and target routes.
- Persist session configuration in `draft_sessions`; persist one row per overall pick in `draft_picks`; derive roster state from those picks rather than storing a second mutable roster snapshot.
- Require the caller to map every imported Yahoo team key to a unique 1-based draft slot. Do not infer draft order from Yahoo team import data.
- Validate every selected internal player ID against the imported league player pool. Derive the selected team and round from overall pick plus the explicit slot mapping.
- Serialize updates using a PostgreSQL session-row lock and require the caller's expected version. Identical pick replay is idempotent; out-of-order picks and stale mutations return conflicts.
- Append record/correction/undo events to `draft_pick_events`. Undo is limited to the latest pick so the pick sequence stays contiguous.
- Save a recommendation snapshot for each session version, including session configuration, ordered picks and source evidence, available/drafted IDs, and calculation response. Snapshots are contemporaneous and do not contain later outcome judgments.
- Persist target status (`target`, `priority`, `watch`, `avoid`) per session/player.
- Introduce tracked SQL revision `0001_draft_persistence`. Startup first provisions existing legacy tables, then applies unrecorded revisions transactionally. The migrated v2 tables are excluded from metadata `create_all()`.
- `python -m app.core.migrations downgrade base` removes the v2 session tables and their stored draft data. Only use downgrade on a disposable database or after an explicit data-retention decision.

## Consequences

- A session can be reloaded without reconstructing picks from a client. Stale writers cannot silently overwrite newer state.
- A draft can only start after the league/team import and requires an explicit team-slot order supplied by the user.
- Existing Yahoo/NBA schema still has no complete baseline migration; only the new v2 draft persistence is versioned.
- The API remains unauthenticated and must stay on a trusted network. Authorization and multi-manager ownership are not provided.

## Validation

Revision upgrade, downgrade, and re-upgrade are tested against a uniquely named disposable PostgreSQL database. Session lifecycle tests cover sequential validation, duplicate replay, correction, latest-pick undo, optimistic version conflict, target updates, snapshot reload, and concurrent writers.
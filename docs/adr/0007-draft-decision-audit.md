# ADR 0007: Contemporaneous Draft Decision Audit

- Status: Accepted
- Date: 2026-10-10

## Context

Recommendations need to be auditable at the time of a selection. Later injuries, role changes, or random outcomes must not rewrite the original evidence or retroactively change process-quality judgments.

## Decisions

- Store the complete calculation response and versioned input state in `draft_recommendation_snapshots` whenever a session is created or mutated.
- Preserve raw pick source evidence and append every record, correction, and undo to `draft_pick_events`; corrections never erase the prior event.
- Keep recommendation quality separate from player outcomes. No outcome records or retrospective assessment routes are added in this phase.
- Any future assessment must reference an immutable recommendation snapshot and store process assessment separately from realized outcome, allowing all four process/outcome combinations without changing the original recommendation.

## Consequences

- A stored recommendation can be reconstructed and reviewed with the contemporaneous pick order, market-derived estimates, and utility response.
- The database currently does not label decisions good/bad or outcomes good/bad; those evaluations require an explicit rubric and later outcome evidence.
- Later player results do not update the stored decision score because no such score is computed here.
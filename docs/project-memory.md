# Project Memory

## Product Boundaries

- Yahoo is authoritative for fantasy-league/player identity, configuration,
  and state. `player_identity.id` is the internal cross-feature key; market
  feeds never overwrite Yahoo identity fields.
- Persisted NBA sources are authoritative basketball inputs, including PTS,
  REB, AST, STL, BLK, TOV, MIN, game logs, schedules and supported aggregate
  usage/starts. Authorized external sources require a separate verified
  contract. Persist inputs before calculations; a gateway HTTP result alone
  is not evidence of successful persistence. Missing/stale data stays
  unavailable.
- The backend owns deterministic calculations, projections, simulation, and
  decisions. The frontend presents prioritized actions and explanations, not
  duplicate calculation logic. Future projections/simulation require explicit
  methods and validation; draft heuristics do not establish those capabilities.
- Decision history is the audit/learning layer. Preserve input/source evidence,
  versions, alternatives, and uncertainty; do not equate an audit trail with
  proven decision accuracy.
- Raw category totals/rates may be shown only as a clearly labelled roster
  baseline with source, coverage, and missing contributors. League-relative
  ranks and normalized positions are descriptive only; they are not evidence
  of a matchup advantage, recommendation, projection, or probability.
  Actionable claims still require verified roster/matchup context.
- Yahoo fantasy-state authority and NBA basketball-input authority remain
  separate. Yahoo is authoritative for fantasy identity/configuration/scoring,
  roster state, player status and fantasy availability; matchup, acquisition
  and waiver facts require separate verification. A Yahoo player payload
  without PTS/REB/AST/STL/BLK/TO is not evidence that NBA production or fantasy
  PPG is missing.
- Every UNKNOWN/UNAVAILABLE value should carry the most specific supported
  root cause. Distinguish missing, explicit zero, explicit empty, stale,
  unsupported and unverified. Use durable causes such as
  RESOLVABLE_INTERNAL_DEFECT, STALE_EXISTING_SOURCE, MISSING_MAPPING,
  MISSING_EXISTING_SOURCE_FIELD, SOURCE_DOES_NOT_SUPPLY,
  SOURCE_CONTRACT_UNVERIFIED, REQUIRES_MORE_GAMES, REQUIRES_NEW_SOURCE and
  INTENTIONALLY_UNSUPPORTED. Do not call legitimate source absence an
  application defect.
- Mapping corrections require stable evidence and never overwrite Yahoo
  identity with NBA, Fantrax or another provider data. Never auto-map on fuzzy
  name alone. Supported evidence may include exact ID, exact name/team,
  normalized name/team, known alias plus team, or source-supported team change.
  Unresolved/ambiguous/team-conflicting identities remain reviewable; explicit
  aliases and corrections require durable evidence. An NBA ID alone does not
  override unresolved identity quality. Never infer a trade or team change
  from disagreement.
- Schedule completeness must be proven by a source manifest/contract.
  `player_schedule` row count, all 30 teams, apparent date span and opponent
  presence do not establish COMPLETE. Rows present mean PARTIAL; no player
  rows or an empty selected window without proven completeness mean UNKNOWN;
  stale is STALE. `NO_PLAYER_SCHEDULE_ROWS` is distinct from an unverified
  empty window; neither implies verified zero games.
- Yahoo-supplied blank status is legitimate UNKNOWN, not healthy, stale,
  injured or automatically a missing-import defect. A missing Yahoo `status`
  field is NO CURRENT YAHOO DESIGNATION only when every condition of
  `interpret_yahoo_status()` holds (user-approved 2026-11-14; deployed with
  Phase 6); otherwise it is UNKNOWN too. Keep explicit status,
  supplied blank, missing status field (`STATUS_FIELD_MISSING`), stale import,
  missing observation, identity-mapping problem and normalization defect
  distinct. O/OFS/NA remain excluded; Q/P remain uncertain. Unrecognized
  nonblank Yahoo status is also UNKNOWN and cannot silently become confirmed
  healthy.
- Game-level usage and recent starts require explicit supported game-level
  fields. Season usage, season starter-filter aggregates and minutes cannot
  substitute for game-level usage or recent starts. Phase-3 descriptive role
  is delivered: qualified minutes may establish role while optional usage and
  starts remain independently unavailable.
- New providers require a documented source contract, permitted use, stable
  identity, freshness semantics, persistence, failure preservation, tests and
  a demonstrated material evidence gap. No additional reviewed source met the
  current evidence, usefulness and permission threshold; that is not a claim
  that every public API is unusable forever. Source reconciliation precedes
  model tuning.
- Draft functionality and persisted history are preserved modules after the
  final draft-era baseline. Championship HQ is the post-draft direction, not
  an already complete or validated product. Its initial Yahoo foundation
  surface reuses the existing league/settings/team and player/roster imports.
- Yahoo baseline reads are database-only. The roster API includes every
  persisted league team and distinguishes `not_imported`, `stale`, and
  `available`. `stale` means a later league/team/settings import is known to
  postdate the roster snapshot; it is not an age-based freshness threshold.
  An imported empty roster is valid and distinct from missing roster evidence.
  Category baseline reads are database-only and use only categories explicitly
  present in persisted Yahoo settings. Select the latest eligible regular
  season with mapped rostered-player stats, no later than the Yahoo league
  season when known; this is league-wide source selection, not a season
  intersection across players. Keep players without a selected-season row
  missing rather than falling back to an older season. Counting outputs sum
  player per-game stats; FG%/FT% use summed season makes divided by summed
  season attempts, derived from per-game components × games played. Never
  average percentages without their denominators. Missing mappings, source
  rows, fields, and percentage components remain visible with coverage counts;
  unsupported categories have no calculated value. Preserve lower-is-better
  category direction without changing raw totals.
- League-relative identity comparisons are backend-owned and compare only
  within the same league, configured Yahoo category, selected source season
  and stat type, and calculation version/type. Rank only fully covered,
  non-stale available team values; exclude partial, stale, unavailable, and
  unsupported values with reasons. Require at least three comparable teams.
  Competition ranking gives ties the same rank; normalized position is
  min-max scaled to 0–100 in the configured better direction, with equal
  values at 50. Strength/weakness thresholds are inclusive at 75/25; remaining
  sufficient results are neutral. Insufficient evidence is not ranked.
  Comparisons are descriptive, not projections or matchup/transaction
  analysis. Do not infer authenticated manager-team identity.
- The existing Yahoo adapter/fixtures establish game, league, settings, team,
  player, roster, and draft-results payloads only. A generic Yahoo HTTP client
  is not evidence for scoreboard/matchup, transaction, current-week, or
  current-login-team semantics. Require authorized representative payloads and
  verified normalization contracts before adding those persisted sources.
- Provider evidence capture requires separate authorization and must not
  refresh OAuth, mutate production or broaden scope as a side effect. Use only
  the existing authorized client and safe credential lifecycle; do not expose
  credentials or private payloads.
- Inspect existing league `teams` evidence first for explicit authenticated
  ownership, then candidate league `scoreboard`, then candidate league
  `transactions`. Path names and HTTP success do not establish semantics.
  Team names, persisted rosters, and Draft manager selections do not identify
  the current Yahoo login. No team may be labelled "My Team" without explicit
  verified ownership evidence. Yahoo source week/date fields must remain
  uninterpreted until their coverage semantics are verified; the local clock,
  NBA season, and Draft state are not substitutes.
- Structural capture is not representative semantic evidence: scalars are
  redacted except collection/pagination counts, unknown field names are
  redacted, and no pages are followed. An observed zero count is distinguished
  from missing/malformed/ambiguous structure but does not prove a complete
  league snapshot. Stable identifier mappings, week/date meaning, pagination,
  and correction/update behavior remain unverified. Keep capture code,
  reports, and synthetic safety tests local/ignored; never turn them into
  speculative provider fixtures or persisted source models.
- Authorization lifecycle: callback exchanges the code, encrypts and commits
  access/refresh credentials and expiry, then attempts league import. A later
  import failure does not roll back that credential commit. Normal token
  acquisition decrypts the stored access token when expiry is more than
  60 seconds away; otherwise the existing OAuth service refreshes and stores
  encrypted replacements. The Yahoo client sends the supplied bearer token
  and stops on 401; it does not trigger a refresh. Capture deliberately skips
  refresh, but uses the same stored access credential/decryption as the normal
  unexpired branch. Capture-side refresh is not a fix for rejected grants.
- Authorization and endpoint errors must be classified only from sanitized
  evidence. Do not infer revocation, expiry, misconfiguration or bearer-token
  defects from a generic failure. Resume source discovery only after an
  explicitly authorized normal OAuth flow and a supported fantasy-resource
  response; never change client configuration, callback, token endpoint or
  scopes without separate evidence.

## Waiver Center Invariants

- **Phase 6: horizons and evidence** (model `waiver-horizon-evidence-phase6`;
  **deployed** 2026-11-14 21:30 UTC, application-only with no migration or
  refresh; rollback images tagged `pre-phase6`; it carries the NO CURRENT
  YAHOO DESIGNATION policy below). On the same model, the ordering and
  wording cleanup below is **deployed** (2026-11-15 02:36 UTC; rollback
  images tagged `pre-phase6-cleanup`), and so is the API-only heavy-read
  admission (2026-11-15 14:50 UTC; rollback tag `pre-waiver-reliability`).
  Image and container identities are dated evidence in
  `docs/status/current-state.md`.
  - The board and the optimizer share one pair judgment (`evaluate_pair`)
    and one ordering (`pair_order`). Never rank a full-roster add against
    only its highest-net drop. `best_add_for_team_id` and
    `best_drop_for_team_id` must equal the analysis's best supported pair,
    and the best add is always in the board candidates. The page fails
    closed (contract error) on any mismatch and never shows "Next open spot"
    on a full roster.
  - Horizons look forward (Rest of Week, Next 7 Days, Next 14 Days =
    `next_14_days`, Rest of Season Outlook = `ros`); form windows look back
    (Last 7/14/30 Days, Current Season, Previous Season). Never interchange
    Next 14 Days and Last 14 Days. Log windows never invent starts or usage.
  - The recent-sample gate lives in `app/features/waivers/sample.py`. 7+
    relevant games are SUPPORTED. 5-6 LIMITED pass only in weekly horizons,
    with 7+ season games, fresh production, a qualified role and 2 of 4
    corroborations: 10+ games in 30 days, a STABLE or RISING role, FP/G
    within 13% and a minutes change above -3.0. 0-4 never pass, and a
    LIMITED Rest of Season Outlook sample is never corroborated.
  - Never add current-season games as a corroboration: Last 30 Days games
    are a subset of them, so the same games would count twice (found and
    removed in the 2026-11-14 acceptance). Prior seasons never corroborate.
  - Move intent (STREAM, TWO_WEEK_STREAM, LONGER_TERM_ADD, WATCH, HOLD,
    INSUFFICIENT_EVIDENCE) is descriptive and never changes a decision.
    Without persisted horizon games it says the support is production and
    roster fit, never "zero games".
    - Next 14 Days text names only the evidence behind the move (cleanup,
      deployed 2026-11-15 02:36 UTC): "Two-week move supported by current production,
      role, roster impact, and persisted Next 14 Days schedule evidence."
    - Role is named only for STREAM, which is role-gated; the schedule only
      when the add has persisted games in the window.
    - Never imply projections, starts, matchup weeks or complete schedules.
  - Explicit-drop replacement order (cleanup, deployed 2026-11-15 02:36 UTC)
    comes from one backend key, `replacement_order` in `service.py`:
    - The `ACTION_RANK` decision tier first (supported, WATCH, HOLD,
      insufficient evidence), then measured net (unavailable last), then
      player ID.
    - Unsupported measured upside never outranks a supported decision.
    - The first supported row equals the drop board's best add (`pair_order`
      for the fixed drop).
    - The list always includes the top measured option the page names.
    - The frontend never re-sorts it.
    - It does not touch the optimizer, the no-drop board or
      `decision_priority`.

- **Phase 5: one-click refresh and authoritative availability** (model
  `waiver-availability-phase5`; deployed 2026-11-14 08:26 UTC; first refresh
  job `629bd689b6f0` SUCCEEDED 08:31:29-08:33:05 UTC with all ten stages
  verified; post-refresh acceptance fixes deployed 11:40 UTC). Refresh job
  state lives only in the API process: any API restart or deploy drops the
  job record, and `GET /api/v1/waivers/refresh` then reports currency from
  persisted evidence (`last_complete_refresh_source: persisted_evidence`).
  That is not a reason to refresh. **REFRESH WAIVER DATA** sends one request,
  `POST /api/v1/waivers/refresh`, the Waiver Center's only mutation. One
  backend owner (`app/features/waivers/refresh.py`) runs, in order:
  LEAGUE_SETTINGS, PLAYER_POOL, LEAGUE_ROSTERS, ROSTER_SLOTS,
  YAHOO_AVAILABILITY_STATUS, NBA_TEAMS_PLAYERS, NBA_SCHEDULE, NBA_GAME_LOGS,
  NBA_SEASON_STATS and POST_REFRESH_VERIFICATION, for the league resolved from
  `WAIVER_MANAGER_TEAM_KEY`. Never chain provider imports from the frontend,
  never call a provider from a waiver GET, and never refresh providers on page
  load or on a schedule without a separate decision. Success requires a
  persisted re-read, never an HTTP 200 alone. Source boundaries (Yahoo league,
  Yahoo players/rosters, NBA) fetch and validate a complete replacement
  snapshot first, then write it in one transaction stamped with the database
  clock and verify the stamped counts before commit; a failed boundary keeps
  its previous snapshot, a Yahoo success survives an NBA failure
  (PARTIAL_FAILURE), and RETRY FAILED STAGE reruns only failed boundaries.
  At most one provider import runs at a time: a second POST rejoins the
  active job, and PostgreSQL advisory lock `7316405219660901117` (shared with
  the league, player and NBA import routes) returns 409
  `PROVIDER_IMPORT_IN_PROGRESS`. Job progress lives in the single API worker's
  memory; `GET /api/v1/waivers/refresh` is database-only and safe to poll.
  The Yahoo client used by the refresh refuses local practice leagues and any
  transaction resource; `yahoo_transactions_executed` is always 0.
- **Yahoo availability classes are authoritative.** Each player has one
  `availability_classification`: `CONFIRMED_FA`, `CONFIRMED_WAIVER` (with a
  claim-clear date when supplied), `UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT`,
  `ROSTERED_BY_OTHER_TEAM`, `ROSTERED_BY_MANAGER`, `AVAILABILITY_UNVERIFIED`,
  `EXCLUDED_STATUS` or `SOURCE_STALE`. Only the first three are actionable;
  they require every league roster snapshot current (24 hours and newer than
  the league/team/settings import) and complete, absence from all of them,
  explicit FA/W when Yahoo supplied it, and no O/OFS/NA. Without an FA/W field
  the label is UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO, never
  "confirmed available". `AVAILABILITY_UNVERIFIED` and `SOURCE_STALE` may
  appear only as POTENTIAL TARGET TO CHECK IN YAHOO; rostered and O/OFS/NA
  players never appear as any target. Never hard-code a player name (Jrue
  Holiday was only an acceptance example).
- **Yahoo status policy** lives only in `app/services/draft/player_status.py`
  (shared by draft and waivers). Supported tokens are those verified in
  persisted `status_full`: O, OFS ("Out For Season", verified 2026-11-14) and
  NA are excluded and cannot fill a lineup slot; Q/P are uncertain; blank and
  unrecognized values are UNKNOWN and fail closed, except a verified missing
  field (NO CURRENT YAHOO DESIGNATION, below). Add a new token only after
  seeing its `status_full` in persisted Yahoo data, and change UI/API wording
  ("O/OFS/NA") with it; the not-comparable key `Yahoo O/OFS/NA status` is
  shared with the frontend.
- **A fresh, verified missing Yahoo `status` field is NO CURRENT YAHOO
  DESIGNATION; every other blank is UNKNOWN.** `interpret_yahoo_status()` in
  `player_status.py` is the only interpreter (no waiver-only parser). It uses
  `yahoo_status_field()` (`EXPLICIT_STATUS`, `UNRECOGNIZED_NONBLANK`,
  `YAHOO_SUPPLIED_BLANK`, `STATUS_FIELD_MISSING`) and returns a typed
  decision state (`EXCLUDED`, `UNCERTAIN`, `NO_CURRENT_YAHOO_DESIGNATION`,
  `UNKNOWN`), the first failing reason, a label and a detail.
  - The missing field qualifies only on a configured-league pool record no
    older than 24 hours, linked by Yahoo ID to a resolved, team-consistent
    identity, with no other status evidence (`status_full`, `injury_note`,
    truthy `on_disabled_list`, stored identity status) and all league roster
    snapshots current. Adds still need actionable availability; the
    manager's own players qualify as drops.
  - The label is "NO CURRENT YAHOO DESIGNATION". The detail says it is not a
    medical-health guarantee. Never call it healthy, active, cleared or
    injury-free.
  - The status gate (`status_gap`, also used by `transaction_blockers`)
    passes a blank only for this loader-verified state with fresh status
    evidence. Candidate defaults fail closed (`UNKNOWN`, gate unsupported).
    The frontend shows the backend `status_label`/`status_detail` and never
    infers one.
  - History: the normalizer adds no keys, so key presence is what Yahoo
    sent. On 2026-11-14 Yahoo omitted `status` (with `status_full` and
    `injury_note`) for 426 of 744 records, and no supplied blank existed.
    Reading absence as "no designation" was first REJECTED that day, then
    explicitly approved by the user, and deployed with Phase 6 (2026-11-14
    21:30 UTC).
  - Real data (2026-11-14 snapshot): 425 of the 426 qualified. The
    decisions that followed are dated evidence in
    `docs/status/current-state.md`, not permanent facts.
- **Gate explanations are backend-owned and specific.** `enrich` names each
  failing player and window ("Sample gate: [player] N games in the last 14
  days" / "N games this season") and each unverified status ("Yahoo status
  gate: [player] blank (UNKNOWN)"); the frontend shows `evidence_blockers`
  and never rebuilds a reason from `current_season_games`. Decisions do not
  depend on this text.
- **Refresh verification must check the rows the model reads.** NBA season
  stats verify current-season Regular Season rows only (the model never reads
  preseason rows); game logs already were Regular Season only.
- **Recommendation invariant:** every supported move or featured player (best
  add, supported actions, best measured, OTHER GOOD OPTIONS groups, WATCHLIST,
  option groups and need options) must be in the board's
  `eligible_candidate_ids` with an actionable class. The backend asserts it
  for the board and transactions and returns 500
  `RECOMMENDATION_CONTRACT_VIOLATION` instead of a violating result; the UI
  checks each featured ID against the eligible map and fails closed with
  WAIVER MODEL CONTRACT ERROR. The frontend never reconstructs availability.
- **Import invariants:** player/roster imports never send local practice
  leagues to Yahoo (league key `yahoo-mock-practice.*`, game key
  `yahoo_mock_practice` or a `practice_source` payload) and an explicitly
  named practice league returns 422. A Yahoo snapshot must include every team
  roster and every roster player's `selected_position` before it replaces the
  previous one. NBA imports split fetch from persist, write every multi-row
  upsert in batches of `BULK_INSERT_BATCH_SIZE` (500) to stay under
  PostgreSQL's 32,767 bind parameters, and verify counts in the same
  transaction.
- **Acquisition context:** waiver priority and weekly adds (used, remaining,
  limit, Yahoo week) come from the existing supported Yahoo teams payload
  (`waiver_priority`, `roster_adds`) and settings (`max_weekly_adds`) with
  their import time. They are context only and never change ranking. Exact
  claim-clear times are unsupported, and `is_owned_by_current_login` is not
  authentication evidence.
- **Errors and performance:** the client normalizes failures to status, code,
  short message, retryable flag and request ID, and never renders non-JSON or
  HTML bodies. A 504 or timeout is WAIVER ANALYSIS TIMED OUT with RETRY
  ANALYSIS and REFRESH WAIVER DATA, never HOLD, and no earlier recommendation
  stays actionable after an error. `/api` responses carry `X-Request-ID`
  (assigned by nginx, reused by the API). Waiver GETs load one context per
  request with no per-player or per-pair queries, memoize comparisons per
  request, return full evidence for a bounded 12 candidates plus every
  eligible ID, run analysis off the event loop and log one `request_timing`
  line. Do not raise proxy timeouts to hide slow reads.
- **Phase 4 roster capacity and team needs are implemented** (model
  `waiver-capacity-phase4`). Capacity comes only from persisted Yahoo league
  roster positions plus each roster player's persisted Yahoo slot assignment
  (`selected_position`); never infer open spots from the number of rostered
  players. Shape precedence: an open non-injury spot is **ADD ONLY**; else a
  legal IL move is **MOVE [player] TO IL THEN ADD**; else **ADD + DROP**. An IL
  move requires persisted Yahoo eligible positions listing an open injury slot
  and status evidence that is not stale or missing; it is conditional on Yahoo
  and never a drop. IL occupants use no non-injury spot, cannot fill lineup
  slots and cannot be dropped to open one. Stale settings or roster (24-hour
  rule), missing or unknown slot assignments, over-filled slots, an IL
  occupant without IL eligibility, or unsupported slot types make capacity
  **UNDETERMINED**: return INSUFFICIENT EVIDENCE with exact blockers, never
  HOLD and never an assumed drop. Roster/game-time locks, claim timing and
  live IL eligibility remain unverified (weekly adds are context only); every
  action needs Yahoo confirmation.
- Action types are ADD ONLY, MOVE TO IL THEN ADD, ADD + DROP, WATCH, HOLD and
  INSUFFICIENT EVIDENCE. The capacity shape only decides which action an
  actionable result becomes; never lower or bypass the existing ADD/STREAM
  evidence gates. An UNKNOWN Yahoo status (any blank except a verified NO
  CURRENT YAHOO DESIGNATION) still blocks strong actions. Pairs are
  evaluated only for ADD + DROP; open capacity uses a sequential fill plan that
  re-measures uncovered starting slots after each pick. The no-drop
  comparison keeps the same weights, percentiles and common mask: non-fit
  components are summed over lineup-eligible non-injury members and divided
  by the fixed non-injury spots (open and O/OFS/NA-held spots contribute zero);
  fit is whole-lineup coverage measured once. For the same add/mode/shape,
  board == fill/watch item == no-drop impact comparison. Team needs describe
  open and injury-weakened starting slots, persisted-schedule date gaps,
  coverage and production context; never forecast injury return. Yahoo roster
  imports must persist the `selected_position` sibling block of each roster
  player payload.
- **Decision support is a separate, non-actionable layer** (2026-11-13,
  `decision_support.py`, same model version). It never changes
  `recommended_action_type` and never lowers a gate. Classes: SUPPORTED
  ACTION (the strict ADD ONLY / MOVE TO IL THEN ADD / ADD + DROP result,
  always ranked first), BEST MEASURED OPTION, WATCH, MEASURED and
  UNAVAILABLE; the backend `decision_rank` is the only decision order and
  frontend filters never create recommendations. BEST MEASURED OPTION, WATCH
  and potential targets say CHECK IN YAHOO and list exact blockers; never
  label them ADD, STREAM or MUST ADD. With ADD + DROP and no supported pair,
  a best measured option must out-produce the lowest-producing roster player.
- Measured production for comparison is Yahoo-rule PPG from the persisted,
  contract-verified scoring settings even when they are past the 24-hour
  rule; the 14-day sample (weekly modes, when present) or current season is
  shrunk toward prior-season production with weight n/(n+10); without prior
  history at least 4 current-season games are required. Staleness is
  labeled, never hidden. O/OFS/NA, unresolved identity and players on another
  team's saved roster are never targets.
- **POTENTIAL TARGETS TO CHECK IN YAHOO** exist only while league-wide
  availability is not current; they keep their `AVAILABILITY_UNVERIFIED` or
  `SOURCE_STALE` class, are listed separately and are never mixed into
  confirmed available candidates. UNKNOWN Yahoo status (a blank that is not
  a verified NO CURRENT YAHOO DESIGNATION) blocks supported actions but not
  BEST MEASURED, WATCH or potential-target listing.
- Positional needs are HIGH (family slot uncovered), MEDIUM (one absence or
  schedule gap uncovers it) or COVERED for Guard, Wing/Forward and Center;
  UTIL and bench are depth, not needs. Needs use the persisted slot
  configuration even when settings are stale, labeled in `basis`. The page
  order is TEAM SITUATION, BEST MOVES RIGHT NOW, OTHER GOOD OPTIONS, COMPARE
  A SPECIFIC DROP, FULL WAIVER LIST, ADVANCED EVIDENCE. The full list and
  advanced evidence start collapsed; the compare tool starts collapsed unless
  the roster is proven full or a drop is chosen, and nothing is preselected.
  The model version appears only in ADVANCED EVIDENCE.
- **Phase 3 evidence intelligence is implemented**, not projection. Derive
  current role once per player from bulk-loaded persisted inputs and reuse it
  across all pairs. Waiver GETs remain PostgreSQL-only: never call a provider,
  write history or execute Yahoo transactions. Do not infer future
  minutes/usage/starts, coach intent, injury replacement permanence or return
  dates.
- Role windows are the latest three and preceding three current-season
  regular-season games within the existing 14-day lookback. Each side needs
  three valid observations and fresh imports/latest game within seven days.
  Never zero-fill invalid/missing inputs or backfill fixed windows. Finite
  nonnegative MIN and fractional USG_PCT in [0,1] are the supported inputs.
  Compare six-decimal rounded deltas: both mean and median >=+3.0 minutes
  or >=+0.02 usage (two percentage points) establish rising direction;
  both <=-3.0 or <=-0.02 establish falling direction. These boundaries are
  inclusive; both strictly inside the metric's thresholds establish stable
  direction. A single outlier cannot establish RISING/FALLING.
  Opposing minutes/usage or disagreeing mean/median bands are
  insufficient evidence. Qualified minutes may establish role alone;
  missing optional usage/starts retain independent unavailable states.
  Without conflict, either supported metric rising gives RISING, either
  falling gives FALLING, otherwise STABLE. Import age exactly seven days and
  latest game exactly Pacific today minus seven days remain fresh; older
  evidence is stale. Yahoo status uses the inclusive 24-hour boundary.
- Expose averages, medians, deltas, exact supported/missing/stale game IDs,
  dates, counts and source timestamps. Recent starts remain unavailable
  without a supported game-level source. Current-season starts require
  explicit matching starter-filter GP; absent starter rows are not zero.
  Season starts/usage are separate context, not recent rotation/usage trends.
- Role/minutes/usage/starts/status/schedule independently expose available,
  partial, unavailable or stale quality. O/OFS/NA remain excluded, Q/P uncertain
  and blank status UNKNOWN. Schedule coverage is PARTIAL with rows and UNKNOWN
  without rows; no completeness claim without a manifest. Missing rows are
  not zero games; opponent identity never establishes matchup quality.
- Resolve schedule evidence from persisted per-player `player_schedule` rows
  via the saved identity/team chain, not from Yahoo team abbreviation plus
  general daily NBA games. Expose the first broken mapping state and separate
  schedule freshness/coverage reasons. No applicable player rows means unknown
  counts, never zero. Every Waiver Center surface must verify its expected
  model version; an incompatible version is non-decision-ready, and cached
  stale results cannot remain actionable after a mismatch or reload. Preserve
  structured HTTP 409 contract details as an error; never coerce a contract
  failure into HOLD, empty success data or another success-shaped fallback.
- The repeatable Yahoo/NBA reconciliation is a persisted-data-only report:
  explicitly set the SQL transaction READ ONLY and compare only overlapping
  persisted basketball fields, with provenance and mapping context. No
  comparable Yahoo/NBA stat pairs means CROSS-SOURCE COMPARISON UNAVAILABLE:
  no second Yahoo statistical dataset exists in the persisted evidence for
  independent cross-source value comparison. It does not mean NBA production,
  fantasy PPG or the scoring formula is missing. Do not zero-fill or
  success-shape comparison; do not call providers, write records, trigger
  OAuth or infer candidate fixture presence from external data.
- Opportunity uses each supported input once: minutes level, optional usage
  change and optional explicit fresh season start rate; no separate
  minutes-change score. Unqualified role supplies no score, not neutral
  opportunity. Opportunity-led ADD (more than half of weighted positive gains)
  and STREAM require qualified fresh role for both players; STREAM also
  requires fresh supported schedule and opportunity. Evidence quality controls
  decisions, not merely warnings. Role cannot bypass production sample gates.
- **Phase 2 global supported optimization is implemented**, not future work.
  `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros` analyzes
  hypothetical add/drop pairs only when persisted capacity shows a full
  roster, never Yahoo history or execution.
  Load the context/evidence once; assess the waiver pool against all persisted
  manager roster drops in memory with the same Phase-1 `enrich` / `compare`
  engine, fixed percentiles/common mask, weights and bounded whole-roster fit.
  No second transaction formula or category-weakness optimization.
- For an identical add/drop/mode, **global optimizer comparison ==
  selected-drop replacement comparison == impact comparison**. Preserve
  exact pair identity as well as before/after indices, component evidence and
  deltas, including identical enriched role/opportunity evidence.
  Detail views cannot substitute another add/drop pair.
- Evidence eligibility precedes optimization. Both sides require supported
  current-season samples, production freshness and Yahoo status. A positive
  index cannot promote a low-sample WATCH or unsupported pair into Best
  Transaction. Prior history cannot bypass the Phase-1 gate.
  Supported nonpositive pairs are PASS; no supported positive pair means
  HOLD and null best transaction. HOLD is a successful evidence-based decision,
  not an error, optimizer failure or empty-ranking fallback. WATCH is a
  positive measured swap blocked by evidence quality, not actionable advice.
  Missing/stale mandatory evidence fails closed. MUST ADD remains unused without a validated
  stronger threshold. This is descriptive evidence, not confidence/projection.
- Order pairs by net improvement descending, add ID ascending, drop ID
  ascending. Return the best supported positive pair, top five supported
  pairs and top five WATCH pairs; expose full evaluated/supported/excluded/
  WATCH counts. Assessed counts include pre-ineligible/unknown-availability
  adds, which are excluded from the supported pool. WATCH is a separate
  excluded subset; exclusion reason counts overlap.
- Page order is decision-first: TEAM SITUATION, BEST MOVES RIGHT NOW, OTHER
  GOOD OPTIONS (groups, WATCHLIST, potential targets), COMPARE A SPECIFIC
  DROP, FULL WAIVER LIST, ADVANCED EVIDENCE; no drop is ever preselected.
  Analysis dialogs render the exact
  returned addition, fill step or add/drop/comparison, independent of any
  roster player chosen in the compare tool. Never substitute a
  preferred drop, unsupported positive result or least-negative pair.
  Mode/reload changes invalidate old global results; read errors are visible,
  not success-shaped HOLD fallbacks. Maintain modal focus/return and mobile
  accessibility. Wide tables sit in `.waiver-table-scroll`; any flex or grid
  item that can contain one needs `min-width: 0`, or an open details widens a
  390 px page (2026-11-14: 589 px). Check overflow against the configured
  viewport width: under mobile emulation an overflowing page zooms out and
  `window.innerWidth` grows with it, so `scrollWidth <= innerWidth` alone
  cannot detect it. Factual acquisition context has no priority/weekly usage/
  clear timestamp unless verified; no cost penalty or FAAB.
- The Waiver Center is **PC-only** (user decision, 2026-11-15). Validate and
  accept it at desktop **1440 × 1000** only, one Playwright project and one
  worker (`--project=desktop`); do not run mobile/390 px projects for waiver
  validation. Earlier mobile results remain historical evidence, and the
  mobile tests stay in the repository.
- Driveway Dudes `478.l.50505` is **Head-to-Head Points**, 12 teams.
  Persisted normalized settings and saved Yahoo source must agree with the
  verified scoring/roster/waiver contract or fail closed with explicit 409
  mismatches. Never silently prefer hard-coded settings. Fantasy PPG uses
  persisted `PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO`; Yahoo TO
  maps to NBA TOV. All six NBA fields are required, never zero-filled.
  Expose inputs, modifiers and contributions; generic NBA PPG is not fantasy PPG.
  Roster is `PG SG G SF PF F C C UTIL UTIL BN BN BN IL IL IL`.
- Continual rolling list, Standard, two-day waivers, four adds/week, no season
  limit, Daily - Today, post-draft waiver rules, direct injury-slot additions.
  **No FAAB** and no planned FAAB feature for this configured league. Historical
  FAAB references are obsolete/general exploration only. Current waiver
  priority and weekly adds are context read from the persisted Yahoo teams
  payload (never inferred from league rules); acquisition value stays
  unavailable and excluded from ranking. Do not invent priority, remaining
  adds, exact clear times or fake acquisition cost.
- Phase-1 decision semantics remain backend-owned and unchanged through `waiver-availability-phase5` and `waiver-horizon-evidence-phase6`: MUST ADD, ADD, STREAM,
  WATCH, PASS, INSUFFICIENT EVIDENCE. Never force MUST ADD or invent AVOID.
  Current-season evidence quality: >=20 EXCELLENT, 10-19 GOOD, 7-9 LIMITED,
  4-6 VERY LIMITED, 1-3 INSUFFICIENT FOR STRONG RECOMMENDATION,
  zero NO CURRENT-SEASON EVIDENCE. These labels are not probability/confidence.
  Below seven games cannot support ADD/STREAM/MUST ADD or Best Add, including
  Season Evidence mode; prior-season shrinkage cannot bypass this invariant
  (Phase 6: only a corroborated 5-6-game weekly sample, above).
  Missing/stale critical settings, roster, availability, stats or unknown/stale
  Yahoo status blocks strong decisions. STREAM also needs fresh persisted
  schedule and opportunity evidence, with partial coverage disclosed.
  Unrecognized nonblank Yahoo status remains UNKNOWN and cannot support a
  strong action or PASS; a supplied blank or unverifiable missing field
  remains legitimate UNKNOWN, not healthy. An
  incompatible model version makes the affected surface non-decision-ready.
  Preserve structured HTTP 409 contract failures as errors, never HOLD or
  empty-success fallbacks.
  Unresolved or disputed Yahoo-to-NBA identity cannot support ADD, STREAM,
  MUST ADD or PASS; do not auto-map or alter identity/team rows during analysis.
  All measured nonpositive selected-drop swaps produce HOLD [selected player],
  never a least-negative Best Add. Positive low-sample swaps remain WATCH.
  User-facing `ros` is **Season Evidence**, historical/stat-based, never a projection
  (Phase 6 labels the horizon Rest of Season Outlook).
- Box Score Bully is the configured manager analysis team for the personal
  application; this configuration is not Yahoo-authenticated ownership evidence.
  `/waivers` opens directly with no league/team selectors, default Rest of Week
  (`mode=this_week`),
  and persisted team display name. `WAIVER_MANAGER_TEAM_KEY` defaults to
  `478.l.50505.t.9`; its persisted Team association supplies league
  `478.l.50505`. All waiver APIs resolve this target server-side.
  Optional caller league/team keys must match or return 422; never fall back
  to a different roster when configured evidence is missing. The frontend sends
  no arbitrary team keys or URL/saved-state selection.
  `GET /api/v1/waivers/{player_id}/impact` uses the internal player identity ID;
  without a drop it returns the no-drop comparison when capacity supports one
  and no comparison otherwise, never a silently chosen drop.
  `GET /api/v1/waivers/replacements?drop_player_id=...` is the optional exact
  roster-player comparison; the full roster is included in board responses.
  An explicit drop controls the ranking and detailed impact, never a silently
  substituted preferred drop or no-drop/open-slot comparison.
  Reads/calculations use PostgreSQL only, never provider refreshes
  or Yahoo/NBA provider calls or writes. Yahoo identity/configuration/state and persisted NBA
  basketball inputs retain their separate authority.
- Availability requires fresh affirmative persisted Yahoo ownership or absence
  from every fresh imported league roster. Absence means `unrostered`, not
  verified free-agent or waiver timing. Unknown availability is withheld.
  O/OFS/NA are excluded, Q/P remain uncertain, blank Yahoo status is unknown.
- Waiver roster/settings/availability gates use 24-hour import freshness;
  later league/team/settings imports also invalidate older roster snapshots.
  This does not change the foundation roster API's source-order-only stale
  definition. Missing/stale evidence cannot supply numeric scoring/fit/impact;
  historical raw values may remain visible with explicit quality.
- Rest of Week (`this_week`) is always the UI label for Pacific today through
  Sunday inclusive, not a verified Yahoo matchup week. With fewer than two
  inclusive dates remaining it adds a limited-days warning; Sunday is one day.
  Next 7 Days is a separate view/ranking covering
  Pacific today through today plus six dates, not a Yahoo matchup period
  (Phase 6: Next 14 Days covers today through today plus 13).
  Season Evidence schedule ends June 30 following the league
  season start year, or today if that date has passed. Count only persisted
  non-final/non-postponed/non-cancelled games. Coverage remains partial; no
  in-window rows with persisted source rows is UNKNOWN with
  `SCHEDULE_SOURCE_INCOMPLETE`; no player rows is the separate
  `NO_PLAYER_SCHEDULE_ROWS` cause. Both have null counts and neither is a
  zero-game claim. Expose persisted source-row count/import time. Off-days mean
  at most five persisted NBA games that date; opponents do not establish
  difficulty.
- Board coverage is backend-owned and reports explicit count/denominator/
  percentage metrics for the full persisted Yahoo pool, eligible candidates
  and configured roster. DATA GAPS are grouped as FIXABLE DATA ISSUE, WAITING
  FOR MORE GAMES, SOURCE DOES NOT SUPPLY, NEW SOURCE REQUIRED and UNVERIFIED
  YAHOO CONTEXT. Preserve raw Yahoo status and Yahoo/NBA teams independently.
  Blank Yahoo status remains UNKNOWN, not healthy, unless it is a verified NO
  CURRENT YAHOO DESIGNATION. Preserve distinct status
  causes for explicit Yahoo status, Yahoo-supplied blank, stale player-pool
  import, missing player observation, identity mapping issue and normalization
  defect.
- Identity state/reason is separate from the legacy downstream mapping
  diagnostic. Resolve only from existing stable identity evidence; same-name
  candidates or team changes do not authorize automatic mapping. Preserve
  unresolved records in a review worklist with exact normalized-name matches
  and reasons; never mutate identity or team as part of a read-only board.
- Persisted Yahoo player-pool stats are not required production inputs. The
  reconciliation utility compares only overlapping persisted fields;
  `NO_COMPARABLE_STAT_FIELDS` means CROSS-SOURCE COMPARISON UNAVAILABLE, not a
  Court IQ production defect. `PARTIAL_STAT_OVERLAP` is separate from a
  complete six-stat comparison, which requires the six supported fields on
  both sides and matching identity/team/season context. No source option is
  cleared without both evidence coverage and verified terms.
- Waiver display timestamps and date/calendar boundaries use
  `America/Los_Angeles` with automatic PST/PDT. Preserve UTC stored instants
  and elapsed-time freshness limits. Persisted NBA game dates remain date-only
  basketball inputs, not verified tip-off or Yahoo matchup timestamps.
- Recent production uses regular-season logs in the league's NBA season from
  Pacific today minus 14 days through today inclusive. The oldest log import and
  latest game date must be within seven days. Season Evidence uses each player's latest
  eligible persisted regular-season per-game history, no later than the Yahoo
  league season (current Pacific year cutoff if absent), not a projection.
  Historical/schedule imports older than seven days cannot supply scored
  components; stale history cannot influence hold labels.
- The waiver model scores supported Yahoo points modifiers only; missing
  required stats are not zero-filled. Production/schedule use deterministic
  midrank percentiles over the loaded league pool; ties stay equal. Positional
  fit uses existing Yahoo eligibility/slot maximum matching. Opportunity uses
  the qualified unique role sub-evidence above; unsupported opportunity is
  omitted through the existing common component mask. Hold labels are descriptive heuristics.
- Weekly/Next 7 Days production uses descriptive shrinkage when supported
  fresh independent prior-season history exists: recent PPG weight `n/(n+10)`,
  prior-season PPG weight `10/(n+10)`. No prior-season substitute for missing
  or stale recent logs. Without supported history, raw recent evidence
  remains limited evidence. Season Evidence remains latest eligible historical
  fantasy PPG, never a projection. Neither historical sample size nor shrinkage
  can establish current-season recommendation eligibility.
- `WAIVER_WEIGHTS` configures all five components: roster_fit/player_value/
  opportunity/schedule/acquisition_value, default 35/25/15/15/10 percent.
  Values must be finite and nonnegative with a positive sum. Missing components
  are omitted with effective-weight renormalization; player value and roster
  fit evidence are mandatory for an overall score. Acquisition value remains
  unavailable; configuration does not create evidence.
- Best Overall is secondary context and ranks the selected mode's production
  percentile alone, not roster fit. Selected-player replacements rank the
  decision tier first (Phase-6 cleanup, deployed 2026-11-15, as above), then
  measured net improvement and stable ID, unavailable last; without a drop the board
  orders by backend `decision_priority` (action tier, need fit, net
  improvement, weighted overall, ID). A single best-team ID requires actionable supported
  impact and >=7 current-season games for add and drop (plus seven recent games
  for short windows), otherwise
  only a limited-evidence top measured result. Negative swaps are not improvements:
  holding the selected player is preferable under this model, not guaranteed
  future performance. Player quality and positional eligibility are distinct.
  All actionable recommendations, needs, drops, impact and explanations use the
  configured manager roster only. Other league teams contribute only existing
  league-wide availability/value context; they cannot become the analysis target.
  An actionable add requires positive supported impact; persisted open
  non-injury capacity or a legal IL move makes the add a no-drop action but
  does not bypass evidence gates. This is not Yahoo transaction eligibility.
- Generic drop options use only the configured roster; foreign drops are
  rejected. Explicit replacement responses contain only the selected drop.
  Fit is 0-100 percentage of required starting slots coverable by
  lineup-eligible players (not O/OFS/NA, not IL occupants), measured once
  per roster, not summed player marginal contributions. Fully covered before/
  after lineups have zero positional gain regardless of matching reassignment
  or UTIL/bench flexibility. Eligibility is not player quality.
  Non-fit roster components are means on the same 0-100 scale (no-drop
  comparisons divide lineup-member sums by the fixed non-injury spots), with deltas
  bounded -100 to +100. All compared replacements and both sides share one
  common measured-component mask, weights and fixed production percentiles.
  Missing optional evidence is omitted, not filled; missing mandatory roster
  values leave numeric impact unavailable. Expose component before/after,
  deltas, effective weights and matched-slot counts. Net improvement is a
  descriptive model-index change, not predicted fantasy points, wins or probability.
- No transaction/scoreboard/current-week/current-login-team contract follows
  from waiver analysis. FAAB is not applicable to this league. Ownership percentages, opponent bidding/demand,
  injury-return forecasts, matchup difficulty, calibrated confidence or
  probabilities, projections, unsupported category impact, What Changed/history
  and transaction execution remain unavailable without separately verified
  evidence and implementation. Preserve the independent Yahoo source-evidence
  and OAuth boundaries above.

## Canonical Draft Architecture

- Reuse normalization/reconciliation, session row locks, sequential pick
  handling, optimistic versions, conflicts, audit events, and recommendation
  snapshots. No parallel reconciler or "fastest source wins" behavior.
- v1 utility is stateless. v2 persists sessions/picks/targets and calculation
  snapshots; mutation/version contracts remain canonical. Corrections and
  latest-pick undo use the existing event/snapshot pipeline.
- Global picks determine availability/run context; only manager selections
  populate manager-roster inputs. Opponent selections are not manager demand.
- Ordinary session creation requires a complete explicit team-slot map.
  Live creation permits pending manager position and partial mapping;
  first-round authoritative picks discover order, later rounds validate known
  slots, and manager timing/recommendations require explicit slot confirmation.
  Unknown team identities are not invented. Order conflicts preserve evidence
  and stop automatic discovery until explicit resolution.
- Internal Mock Live Draft, synthetic Mock Sync Rehearsal, Yahoo Mock Practice,
  and Production Live are separate workflows. Internal mocks are seeded,
  rule-based practice; they do not mutate Yahoo state. Mock/practice evidence
  never validates Production Live.
- Production Live uses authenticated Yahoo `draftresults`, Sync Now,
  pause/resume, Quick Record/manual fallback, and conflict protection.
  Active-draft provider acceptance remains unverified; polling is not push
  streaming and the application interval is not a Yahoo-approved cadence.

## Read-Only Browser Observer

- One-time Windows install/pair; subsequent mocks use Yahoo draft URL + Connect.
  Dedicated Windows Chrome exposes CDP only on `127.0.0.1`, never the LAN.
  Do not assume Linux loopback reaches Windows.
- The observer reads authoritative Yahoo Picks player IDs and sends bounded
  observations over trusted HTTPS through the existing reconciler into
  disposable Yahoo Mock Practice. It never selects/submits Yahoo players.
  Browser-based Production Live writes are not enabled or verified.
- Missing/ambiguous evidence fails closed. Use a verified single-slot fallback
  when necessary; do not guess opponent mappings, rounds, or team count.
  The current practice bridge supports 12-team mocks and requires verified
  rounds and manager slot before initialization.
- Normal operation is windowless/background with bounded sanitized logs;
  diagnostics are not the normal operator workflow. After pairing, normal
  users do not hand off session IDs or re-enter credentials for every draft.

## Recommendation Invariants and Verified Limitations

- BEST PICK NOW ranks current adjusted roster value using historical
  Yahoo-weighted production, replacement value, scarcity/need, construction,
  durability, risk, upside, and recent run context. WAIT ANALYSIS is a separate
  ADP/survival/fallback decision; ADP does not directly determine BEST PICK NOW.
- Roster matching prioritizes starting positions before UTIL/bench and credits
  newly filled slots through incumbent reassignment. UTIL/bench credit is
  bounded; open UTIL/bench does not create positional need. Current board reads
  can recalculate legacy roster-fit results without rewriting old snapshots.
- Why this rank explains manager-roster score/rank contributions, not
  predictive accuracy. Historical production is not a future-season
  projection; small score differences do not prove real-world superiority.
- Yahoo O/Out and NA/Not Active are excluded from normal recommendations,
  best value at risk, and wait/fallback candidates. Q/P remain eligible with
  uncertainty. Blank/unrecognized status is unknown, never confirmed healthy.
  Historical metrics remain visible; no injury penalty or return forecast is
  inferred. Status refresh is player-pool-import-based, not continuous.
- Missing mappings/statistics leave players unscored; preseason samples remain
  explicitly distinguishable from regular-season inputs.
- Fantrax supplies partial ADP coverage, not draft rank, XRank, frequency,
  sample size, or an upstream source-updated timestamp. Retrieval age is the
  available freshness signal; the application stale threshold is 48 hours.
- Survival/wait estimates are uncalibrated heuristics. Opponent roster demand,
  category analysis beyond the factual roster baseline, Monte Carlo forecasts,
  historical outperformance, and post-draft championship/projection accuracy
  are not established.
- Later Windows mock acceptance does not resolve unverified Production Live
  source or full manual fallback/recovery browser acceptance.

## Migrations and Operational Safety

- Draft tables have versioned transactional migrations through
  `0006_observer_connections`, separate from legacy metadata bootstrap.
  Migration up/down/up is tested only on isolated PostgreSQL.
- Production downgrade is destructive: it removes draft sessions, picks,
  events, snapshots, and targets. Never validate with a production downgrade.
  Take a fresh private backup and obtain change approval before deployment or
  migration; preserve pre-existing draft and identity state.
- NBA imports precede metric recomputation; ordinary reads/calculations use
  persisted inputs. The 600-second proxy timeout is scoped to the exact
  NBA-import route, not all APIs; every other `/api/` request is cut off at
  60 seconds (504) by the frontend nginx proxy. After an idle period the API
  process is swapped out and its first heavy waiver reads can 504 until it
  pages back in (2026-11-14 Phase-6 baseline); retry once warm, never raise
  the timeout, and never treat it as a product defect.
- **2026-11-15 incident (proven):** the idle API sat ~93% in swap (the swap
  file is on the single rotational system disk). One normal desktop page load
  sends refresh status, board and best moves at once. Paging back in ran at
  about 230 major faults/s: refresh status hit its 30 s client limit, board
  and best moves got 504, and the deployed API kept computing the abandoned
  reads for up to 472 s. While paging, its single event loop froze, the
  5-connection pool filled and new asyncpg connects timed out (500).
  - Never stack heavy reads on a slow API: no retries, reloads, horizon
    switches, REFRESH clicks or parallel acceptance.
  - Before heavy validation, check the API's `VmSwap` (`/proc/<pid>/status`)
    and host pressure (Prometheus with node-exporter and cAdvisor on `:9090`).
    Start the browser before warming the API with one internal non-abandoned
    read: Chromium's start-up pushed the API back into swap and reproduced
    the incident.
  - A refresh POST whose client timed out can still start the job later.
  - Heavy-read admission (one at a time, cancel on disconnect) is **deployed**
    (2026-11-15 14:50 UTC; rollback tag
    `fantasy-basketball-gm-api:pre-waiver-reliability`). It bounds the damage
    from overlapping and abandoned reads but does not fix the host.
    Keeping the API resident (more RAM, swap off the rotational disk, or a
    no-swap limit for the `api` container) remains the infrastructure fix.
- **API-only deployments:**
  - Identify the running image by the container's `ImageManifestDescriptor`
    and `docker image inspect --platform linux/amd64 <tag>`, because recorded
    index IDs can stop resolving under the containerd store.
  - Prove a rollback tag by that manifest and by `/app` plus `pip freeze`
    content.
  - After `docker compose up -d --no-deps api`, compare the new container's
    compose-network IP with the old one; nginx resolves `api` only at start.
    If the IP changed, run `nginx -s reload` inside the frontend container;
    never recreate the frontend for DNS.
- Each provider import boundary is all-or-nothing: one bad request or
  statement discards everything that boundary fetched, and the previous
  snapshot stays. Batch every multi-row
  INSERT/UPSERT (NBA imports use `BULK_INSERT_BATCH_SIZE = 500`); PostgreSQL
  rejects a statement with more than 32,767 bind parameters, which the
  unbatched 30-day game-log upsert hit on 2026-11-14.
- The Yahoo player/roster import must only request real Yahoo leagues. Local
  Yahoo Mock Practice pseudo-leagues (`yahoo-mock-practice.*`, game key
  `yahoo_mock_practice` or a `practice_source` payload) copy a real league's
  pool and are never sent to Yahoo; naming one returns 422. REFRESH WAIVER
  DATA always passes the configured league; pass `league_key` when importing
  manually.
- Judge a refresh by persisted results (`imported_at`, roster
  `roster_position` counts), never by the request having been sent; the
  refresh's POST_REFRESH_VERIFICATION stage does exactly that. The API runs
  with `--no-access-log` and configures no logging: request status lives in
  the frontend nginx access log, and app warnings reach the API container log
  only as bare messages without their `extra` fields (path/status). Refresh
  stages (`waiver_refresh job=...`) and waiver read timings
  (`request_timing`) log through `uvicorn.error`, so they appear there; the
  `X-Request-ID` shown in the UI finds the matching `request_timing` line
  (the default nginx access-log format does not record it).
- Do not re-import providers or mutate production for documentation validation.
  Do not bypass TLS validation. The API has no general user authentication and
  must remain on a trusted network.
- Keep credentials, observer secrets, private backups, operational
  fingerprints, and sensitive runtime values out of source control and reports.

See [current state](status/current-state.md) for recorded validation evidence
and [next actions](status/next-actions.md) for the remaining roadmap.

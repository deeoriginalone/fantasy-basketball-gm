# Fantasy Basketball GM

Docker-first Yahoo Fantasy Basketball application with a React Draft Room,
a Championship HQ foundation view and read-only Waiver Center, FastAPI services, and PostgreSQL
persistence. Yahoo is authoritative for fantasy-league/player identity,
configuration, and state; persisted NBA and authorized external data provide
basketball inputs.

## Current Product Behavior

The final draft-era baseline preserves the draft module and its history.
**Championship HQ** is the post-draft product direction. Its initial Yahoo
foundation/category baseline and Waiver Center are implemented post-draft
capabilities, not a complete championship or predictive analytics system.
See the [gated follow-ups](docs/status/next-actions.md).

- **Championship HQ foundation:** the home page reads persisted Yahoo league
  settings and team rosters. **Refresh Yahoo baseline** imports league
  metadata/settings, then the player pool and team rosters, using existing
  authorized Yahoo import paths. League, settings, and roster import times are
  shown. A roster is `not imported` when no saved snapshot exists and `stale`
  only when a later league/team/settings import is known to postdate that
  snapshot; snapshot age alone has no stale cutoff. An imported empty roster
  differs from unknown data. Matchup and transaction context are not included,
  and the view does not calculate decisions or projections.
- **Waiver Center:** `/waivers` opens directly for Box Score Bully as a
  decision-first workflow. One **REFRESH WAIVER DATA** action in the page
  header (Phase 5; deployed 2026-11-14) runs the complete
  Yahoo + NBA refresh in the backend, shows stage
  progress, verifies what was saved and then reloads the board; opening the
  page and **Reload persisted evidence** stay database-only. Six sections
  follow: TEAM SITUATION (plain-language roster capacity from persisted Yahoo
  slot assignments, IL use, weekly adds and waiver priority, prioritized
  HIGH/MEDIUM/COVERED positional needs and evidence freshness), BEST MOVES
  RIGHT NOW (supported moves first; otherwise a non-actionable BEST MEASURED
  OPTION to check in Yahoo), OTHER GOOD OPTIONS (distinct position, schedule
  and longer-term picks, WATCHLIST and a separate POTENTIAL TARGETS TO CHECK
  IN YAHOO list), COMPARE A SPECIFIC DROP, FULL WAIVER LIST and ADVANCED
  EVIDENCE. Only players whose Yahoo availability class is actionable
  (confirmed free agent, confirmed waivers, or unrostered in a complete
  current roster snapshot) can be a move or a featured option, and every
  featured player must be in the board's eligible-candidate set; the backend
  enforces this and the UI checks it again. Every
  candidate carries one strict action type: ADD ONLY,
  MOVE TO IL THEN ADD, ADD + DROP, WATCH, HOLD or INSUFFICIENT EVIDENCE. An
  open roster spot never asks for a drop; ADD + DROP is used only when
  persisted evidence proves the roster is full with no legal IL move. Stale,
  missing or conflicting capacity evidence fails closed instead of defaulting
  to a drop. The app-configured analysis team is not authenticated "My Team"
  identity. Rest of Week, Next 7 Days and Season Evidence use persisted
  historical basketball inputs and schedule evidence, not verified Yahoo
  matchup weeks or projections (Phase 6 adds Next 14 Days and labels the
  season horizon Rest of Season Outlook). Unrecognized status or unresolved
  Yahoo-to-NBA identity blocks strong advice and cannot produce a supported
  PASS. When strict gates fail, measurable players are still shown as
  non-actionable options (BEST MEASURED OPTION, WATCH, AVAILABILITY
  UNVERIFIED potential targets) with the exact blockers; they are never
  labeled ADD, STREAM or MUST ADD. Incompatible model versions are not decision-ready; structured HTTP
  409 contract failures remain visible errors, never HOLD or empty-success
  fallbacks. A timeout shows WAIVER ANALYSIS TIMED OUT with RETRY ANALYSIS
  and REFRESH WAIVER DATA, never raw proxy HTML. The last verified
  deployment is model `waiver-season-blend-phase8` (Phase 8, 2026-11-24
  10:32 UTC; see Phase 8 below). Phase 9 (`waiver-permanent-drop-phase9`)
  is implemented and validated locally and ready to deploy. A build of it
  made outside the release procedure has served production since
  2026-11-24 21:24 UTC and is not yet accepted. Earlier: Phase 7.1 deployed 2026-11-21 21:46 UTC, after
  Phase 7 at 16:36 UTC the same day; Phase 6 deployed
  2026-11-14, the explicit-drop ordering cleanup 2026-11-15 02:36 UTC, and
  the API heavy-read admission 2026-11-15 14:50 UTC. Provider refresh stays
  user-initiated. The Waiver Center is PC-only: browser acceptance runs at
  desktop 1440 × 1000, with the mobile tests kept but not required. The
  shared 7.3 GB host, with swap on its rotational disk, remains a capacity
  limit.
- **Yahoo Mock Practice:** one-time Windows observer install/pair, then join a
  12-team Yahoo mock, paste its draft URL, and Connect. Verified rounds and
  manager slot are required. Observations pass through the
  canonical normalizer/reconciler into disposable practice sessions. The
  observer never selects players in Yahoo; browser-based Production Live writes
  are not enabled.
- **Internal practice:** seeded rule-based mocks and synthetic sync rehearsal
  reuse persisted draft calculations and events. Neither validates Yahoo Live.
- **Production Live:** official authenticated `draftresults` polling, Sync Now,
  pause/resume, Quick Record/manual fallback, and conflict protection are
  implemented. Active-draft provider behavior and full manual recovery browser
  acceptance remain unverified; mock acceptance does not establish them.
- **Recommendations:** BEST PICK NOW ranks current adjusted roster value;
  WAIT ANALYSIS separately evaluates ADP/survival/fallback. ADP does not directly
  determine BEST PICK NOW. Only manager selections populate manager-roster
  inputs; all picks affect availability. Why this rank explains roster-driven
  effects, not accuracy. Historical production is not a future-season projection,
  small score differences do not prove player superiority, and survival/wait
  remains uncalibrated.
- **Status/data:** Yahoo O, OFS (Out For Season, verified in the 2026-11-14
  player pool) and NA are excluded from normal recommendations, best
  value at risk, and wait fallbacks. Q/P remain eligible with uncertainty.
  Blank and unrecognized nonblank Yahoo statuses are UNKNOWN, never confirmed
  healthy; unrecognized status fails closed. The one exception (user-approved
  2026-11-14; deployed with Phase 6): a fresh, fully verified
  Yahoo record with no `status` field is NO CURRENT YAHOO DESIGNATION, which
  is not a medical-health guarantee. Unresolved, ambiguous or
  team-conflicting identity cannot support strong waiver advice. Refresh is
  import-based, not continuous injury monitoring. Historical metrics remain
  visible. Missing/stale inputs, unmapped/unscored players, partial ADP, and
  preseason samples remain explicit limitations; no values or recovery
  forecasts are invented.

The Windows observer runs windowless/background with loopback-only CDP on the
dedicated Chrome PC and bounded sanitized logs. Never expose CDP on the LAN.
See the [observer workflow](scripts/yahoo-observer/README.md),
[dated current-state evidence](docs/status/current-state.md), and
[draft-day checklist](docs/draft-day-checklist.md).

The backend owns calculations and decisions; the frontend prioritizes actions
and explanations; decision history supports audit and learning.
**Never surface a statistic as a primary result without explaining why it
matters to this roster/matchup and what decision it informs.**

## Championship HQ Foundation

After connecting Yahoo, use **Refresh Yahoo baseline** on the home page to
refresh persisted league/settings and player/roster inputs, including each
roster player's Yahoo slot assignment (`selected_position`) that the Waiver
Center uses for roster capacity. The panel shows
Yahoo scoring rules, roster eligibility, team roster snapshots, and their
import times. Page reads use saved data without importing. Unknown, stale, and
valid empty rosters are distinguished. Matchup and transaction context are not
yet available in this view. This home-page button is a Yahoo-only refresh; the
Waiver Center's **REFRESH WAIVER DATA** runs the same Yahoo imports plus the
NBA import and post-refresh verification as one backend job. Both share one
provider lock, so two provider imports never run at the same time.

### Local Yahoo source evidence capture

This working tree has a **local-only, ignored** capture command at
`backend/.local-yahoo-evidence/capture.py`; it is not distributed by a fresh
checkout. Its reports and synthetic safety tests stay in the same directory,
excluded through `.git/info/exclude`. No matchup/transaction importer is enabled.

Use the normal Yahoo connection workflow to restore expired authorization
first. Never paste tokens or private provider JSON into chat. From the repository
root, explicitly initiate one source read, replacing the placeholder with an
already persisted Yahoo league key:

```sh
docker compose run --rm --no-deps --user "$(id -u):$(id -g)" \
  --entrypoint python -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 \
  -v "$PWD/backend/.local-yahoo-evidence:/evidence" \
  api /evidence/capture.py --source identity \
  --league-key ALREADY_IMPORTED_YAHOO_LEAGUE_KEY
```

Evaluate `identity` first (the existing `league/{league_key}/teams` resource),
then explicitly run `scoreboard`, then `transactions` by changing only
`--source`. The latter two resource paths are candidates, not verified contracts.
**Stop after an authorization or rate-limit rejection; do not continue the
sequence.** The command never refreshes OAuth, writes to Yahoo, follows pages,
retries, or imports data. Database access uses a read-only transaction and
requires an existing, unexpired stored credential and an already imported league.

Reports contain actual HTTP status (or null when no request was sent), exact
requested path, redacted field/container structure, collection counts, observed
nullability, and explicit structural failure states. Unknown field names and
all scalar values except bounded collection/pagination counts are redacted.
Bodies over 1 MiB, excessive nesting/nodes, and summaries over 256 KiB fail
closed. Reports are owner-only files in the ignored directory, never raw payloads.
Exit **2** means the source contract remains unverified, even after a structurally
successful response; it is not an import-success signal. An authorized contract
review must still establish identity, stable IDs, week/date, pagination, and
correction semantics before any persistence implementation.

## Run

1. Copy `.env.example` to `.env`, configure Yahoo credentials, a PostgreSQL password, OAuth state secret, encryption key, and the registered HTTPS callback.
2. Build and start the stack with `docker compose up --build`.
3. Open `https://192.168.0.85:18002` for the Draft Room or append `/docs` for the API. Trust the local Caddy root certificate on the client before completing OAuth. Never commit `.env` or `caddy-root.crt`.

The API has no general user authentication and must stay on a trusted network.

To export and validate the public root certificate currently used by Caddy, run `scripts/export-caddy-root.sh`. It checks the root CA flag, validates the served TLS chain and configured host name/IP, prints certificate details, and writes only the public root to the ignored `caddy-root.crt`. It does not install trust or export private keys. See the [draft-day checklist](docs/draft-day-checklist.md) for safe client-trust guidance; never bypass TLS validation.

## Draft Workflow

1. Refresh NBA data and season stats: `POST /api/v1/nba/import?season=2026-27&recent_days=30`.
2. Build league-specific per-player draft metrics: `POST /api/v1/draft/metrics?league_key=478.l.50505&season=2026-27`.
3. Submit the manager team, players already drafted, and available Yahoo-pool player identity IDs to `POST /api/v1/draft/utility`.

Example request body:

```json
{
  "league_key": "478.l.50505",
  "team_key": "478.l.50505.t.9",
  "season": "2026-27",
  "draft_position": 9,
  "round_number": 2,
  "total_teams": 12,
  "drafted_player_ids": [10001, 10002],
  "available_player_ids": [10003, 10004],
  "recent_pick_player_ids": [10001, 10002],
  "adp_by_player_id": {"10003": 26.5, "10004": 40.0},
  "mode": "balanced"
}
```

The v1 endpoint returns the roster-best pick, best value at risk before the next turn, snake timing, positional runs, per-player availability assessments, component scores, explanations, and any IDs it could not score. It remains stateless and backward compatible. Recent pick IDs must be ordered oldest to newest; run detection examines the last ten.

For each player with ADP and draft timing, `market_value_delta = ADP - current_pick_number`: positive is a market reach, negative means the player has fallen past ADP. `reach_score` and `fall_score` range from 0 to 100 and scale each direction against one league round; they are descriptive heuristic indices, not probabilities or utility inputs. `expected_loss_if_gone` is the nonnegative `wait_utility_now` at stake. `expected_wait_cost` and its compatible alias `opportunity_cost_if_wait` use fallback expectation and can be positive, zero, negative, or unavailable. The best roster-fit player and the player with greatest positive expected wait cost are selected independently. Fantrax supplies no draft-rank field; the response says that comparison is unavailable. Opponent roster demand is not an input; only available pick history, market ADP, and the existing heuristic run signal inform survival.

### Persisted Draft Sessions (v2)

Use v2 when a draft should survive reloads. The regular `POST /api/v2/draft/sessions` route remains strict and requires a complete explicit team-slot map. Live Draft creation uses `POST /api/v2/draft/live-sessions` and permits a pending manager position and partial/empty opponent mapping. First-round picks from the existing Yahoo `draftresults` poll progressively establish authoritative team slots; later-round picks are validated against known slots but do not infer unknown order. Setting the manager slot is a deliberate action before manager timing and recommendations are enabled. Conflicts retain source evidence and stop automatic order discovery until manually resolved through `PUT /api/v2/draft/sessions/{session_id}/order`. `GET /api/v2/draft/sessions/{session_id}` reloads picks, targets, order state, session version, and the latest recommendation snapshot.

```json
{
  "league_key": "<imported-yahoo-league-key>",
  "season": "2026-27",
  "manager_team_key": "<manager-team-key>",
  "draft_position": 3,
  "total_teams": 4,
  "rounds": 13,
  "team_slots": {
    "<yahoo-team-key-for-slot-1>": 1,
    "<yahoo-team-key-for-slot-2>": 2,
    "<manager-team-key>": 3,
    "<yahoo-team-key-for-slot-4>": 4
  },
  "mode": "balanced"
}
```

Record the next overall pick with `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}` and `{ "selected_player_id": 10001, "expected_version": 0 }`. The service verifies that the player belongs to the imported Yahoo pool, derives the snake round/team slot from the overall pick, rejects out-of-order selections, and serializes updates with a session row lock. Repeating the same pick is idempotent. Stale versions return HTTP 409. Correct a pick with `PUT` on the same resource; undo only the latest pick with `POST .../{overall_pick}/undo`. The final configured pick marks the session completed; completed sessions reject new picks but still allow corrections and latest-pick undo. Undoing the final pick reopens the session. Each mutation appends an audit event and a recommendation snapshot in the same transaction.

Targets use `PUT` and `DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}` with statuses `target`, `priority`, `watch`, or `avoid`; writes require the expected session version. An unchanged target `PUT` is a no-op. A changed target advances the session version and records a snapshot so target annotations remain tied to the corresponding room revision; it retains the existing recommendation recalculation behavior. Snapshots preserve the input state, ordered pick/source evidence, target annotations, and calculation response. On reads, survival and dependent wait-cost fields are marked unavailable once the stored ADP retrieval time exceeds the freshness limit; the historical snapshot itself is not changed. Process assessment and realized player outcomes are not yet evaluated.

For player A, the wait model uses the top five other scored candidates by `wait_utility_now` (roster utility plus mode adjustment, excluding the direct positional-run bonus). It estimates the fallback as the expected highest-utility alternative available at the next turn, assuming independent survival estimates. If alternatives are utility-ordered, `E_fallback = Σ_i [p_i × Π_{j<i}(1-p_j)] × U_i`; the probability no listed fallback survives contributes zero. Then `E_wait = P(A survives) × U(A) + P(A gone) × E_fallback`, and `expected_wait_cost = U(A) - E_wait`. Positive cost yields `draft_now`, zero/negative yields `wait`, and missing player/fallback survival yields `insufficient_evidence`. Run pressure affects pick ranking and survival but is excluded from `wait_utility_now`, so it is not added twice to wait value. Utility is held constant through intervening picks. These estimates are low-confidence, uncalibrated heuristics; no frequency or correlation data is available. The wait action does not apply the old 50% survival threshold. See [ADR 0006](docs/adr/0006-draft-survival-and-wait-method.md).

### Yahoo Mock Practice

This browser-observed practice flow is separate from the internal Mock Live
Draft simulator below. Install and pair the Windows observer once. For each
practice draft, join the Yahoo mock yourself, copy its draft URL, paste it into
Court IQ, and choose **Connect**. The read-only observer uses a dedicated Chrome
profile and loopback-only CDP on Windows; it reads authoritative
`.ys-player[data-id]` entries from Yahoo Picks and sends observations over
trusted HTTPS. Court IQ runs them through the existing normalization and
reconciliation path into a disposable Yahoo Mock Practice session.

Normal operation is windowless/background after pairing: no per-draft
PowerShell, Python commands, session UUID handoff, full opponent mapping, or
observer-secret re-entry. Missing evidence fails closed and asks only for the
single slot value when needed. The observer never selects players in Yahoo.
Keep CDP bound to Windows `127.0.0.1`; never expose it on the LAN. See the
[Windows observer workflow](scripts/yahoo-observer/README.md).

### Internal Mock Live Draft

The setup page explicitly separates **Mock Live Draft** from **Live Draft**. A mock session uses the selected imported Yahoo league, manager team, explicit team-slot order, rounds, roster/scoring settings, internal Yahoo player IDs, and the existing persisted v2 board and utility engine. It is stored as `session_type: "mock"` using the existing `draft_source: "internal_mock"` discriminator; it is excluded from the live-session list and never writes to Yahoo roster/source-of-truth data.

In the mock room, **Auto Pick Next** simulates one opponent pick, **Auto Pick Until My Turn** stops before the manager's slot, and the manager selects their own player from the available board. Pause/resume, latest-pick undo, reset, start-new-mock, and removal are available. Reset starts a new attempt with the same league/slot/rules and retains the prior session; removal deletes only a standalone mock. Batch-managed runs cannot be individually removed.

Opponent selection uses fresh stored ADP when available, positional need/scarcity from the existing board and seeded randomness. If ADP is missing, no ADP is invented: the backend uses its scored board ranking when available and marks that fallback in pick evidence and the room. If there is no ADP or scored board row, the available-pool fallback is separately labeled. Picks use the same sequential v2 persistence, unique-player checks, version checks, roster construction, recommendations, run detection, and snapshots. Existing mock-batch APIs/workers remain available separately.

An opt-in single-run **Mock Sync Rehearsal** creates virtual opponent picks without first writing them as local picks. It serializes Yahoo-shaped snapshots through the production normalizer and sequential reconciler, and can hold/release delivery to exercise delayed source catch-up. The rehearsal does not contact Yahoo or modify Yahoo roster/source-of-truth data.

### Live Draft

Choose **Live Draft** explicitly to create a persisted v2 live room (`POST /api/v2/draft/live-sessions`). The shared room displays the current pick/round/team on clock, next manager turn, recommendations, available board, roster, targets, recent picks, and corrections/undo. Record actual picks manually as they happen; each write remains sequential and requires the current `expected_version`, with HTTP 409 conflicts preserved.

Authenticated Yahoo `draftresults` polling and sequential reconciliation are implemented for linked live sessions. Polling uses `LIVE_DRAFT_POLL_INTERVAL_MS` at frontend image build time, with a conservative 60-second default and bounded backoff after request/source failures. This interval is an application default, not a Yahoo-approved cadence. The room provides Sync Now and pause/resume controls; reconciliation confirms matching local picks, appends only contiguous source picks through the existing v2 event/version/snapshot pipeline, and stops on conflicts. This is polling, not push streaming. No active Yahoo draft or `draftresults` response has been exercised, so automatic production synchronization remains unverified. Production Live retains the official `draftresults` path, Sync Now, Quick Record/manual entry, and conflict protection. Yahoo Mock Practice does not verify production `draftresults`; Live browser observation is not a browser-write path.

Opponent names are not required to start a Live Draft. Unknown positions remain visibly pending; round-one source picks fill order slots progressively, while the manager confirms their position before turn timing is shown. A full manual order editor is available for explicit conflict resolution.

The Live Draft Quick Record field is focused when a live room opens. Search ignores case, punctuation, and accents; Up/Down select a match, Enter records it, and Escape clears or exits. It displays the next pick/team and keeps recommendations visible. Latest-pick undo and corrections remain in Recent Picks.

See the executable [draft-day checklist](docs/draft-day-checklist.md) before the live event. Changing `LIVE_DRAFT_POLL_INTERVAL_MS` in `.env` requires rebuilding/recreating the frontend image. No faster cadence should be described as provider-approved without direct supporting evidence.

### Waiver Center

Open `/waivers` from the existing navigation: it loads directly for
**Box Score Bully**, defaulting to **Rest of Week** (`mode=this_week`), with
**Next 7 Days** and **Season Evidence** (`mode=ros`) alternatives and no
league/team selectors. The subheader uses the persisted team name when available.
**Box Score Bully is the configured manager analysis team for the personal
application; this configuration is not Yahoo-authenticated ownership evidence.**

API environment `WAIVER_MANAGER_TEAM_KEY` is the single analysis-target setting,
default `478.l.50505.t.9`. Compose passes it to the API. The league
`478.l.50505` is resolved from that persisted team's league association, never
from browser selection, URL parameters or saved frontend state.

**PC/desktop only (2026-11-15).** The Waiver Center is used on a PC. Browser
validation and acceptance target desktop **1440 × 1000** only: one Playwright
project, one worker (`--project=desktop` with `playwright.waivers.config.ts`,
which still defines a mobile project). Mobile (390 × 844) acceptance is no
longer required; earlier mobile results in the records remain historical
evidence, and the mobile tests are kept.

**Phase 7: Decision integrity** (model `waiver-decision-integrity-phase7`;
**deployed** 2026-11-21 16:36 UTC and verified read-only; no migration;
rollback images are tagged `pre-phase7`; see the
[2026-11-21 session record](docs/sessions/2026-11-21.md))
makes every recommendation explain itself and refuses those whose
explanation does not hold:

- **Explanation-consistency gate:** an add that loses measured production is
  supported only if its compensating edge holds in the league's own scoring
  unit:
  - schedule: games × the same-basis FP/G over the window;
  - fit: requires a starting-slot gain;
  - role or opportunity: cannot offset a production loss.

  Otherwise it is **DO NOT ADD**, with the arithmetic shown. Weights,
  thresholds and gates are unchanged.
- **Every pair shows its math:**
  - each component's weighted contribution (they sum to the net);
  - both players' FP/G on the same basis, with blend weights;
  - games and window points;
  - "Why this drop?";
  - tradeoffs: FRAGILE window edge, PRIOR-SEASON DRIVEN, "Dropping is
    permanent".
- **Verdicts:** SUPPORTED ADD, WATCH ONLY, NEAR TIE — NO STRONG PREFERENCE
  (|net| < 0.005), DO NOT ADD, CANNOT EVALUATE. Each has its own style;
  "best" never implies a supported add.
- **OTHER GOOD OPTIONS:** on a full roster each card names the best
  compatible drop (or "No supported drop" with the reason), the exact net and
  the verdict. Group titles are qualified by the verdict.
- **Clearer labels:**
  - evidence by dimension (production sample, current role, schedule, source
    freshness, transaction verdict);
  - a reason instead of "n/a";
  - lineup gaps in dates;
  - "Watch only" vs "Keep" roster labels.

**Phase 9 (implemented and validated locally / ready to deploy):
short-horizon permanent-drop policy** (model `waiver-permanent-drop-phase9`;
2026-11-24 read-only audit and test-first implementation; deployment
closeout authorized 2026-11-24, acceptance pending; see
[the session notes](docs/sessions/2026-11-24.md)):

- A Rest of Week, Next 7 Days or Next 14 Days ADD + DROP whose positive net
  leans on a schedule edge is supported only when its window Yahoo FP cover
  the drop's production above the best available player over the drop's
  remaining games. Otherwise it is HOLD / DO NOT ADD (never WATCH), and the
  optimizer uses a cheaper drop for the same add when one is supported.
- Why: the weekly best moves dropped a 30 FP/G roster player for +2 to +28
  window FP, about 356–403 Yahoo FP given up over his remaining games, while
  drops at or below replacement level supported the same adds.
- The page shows only backend facts:
  - the short-term gain;
  - the permanent drop cost as `(drop FP/G − replacement FP/G) × games after
    the window = Yahoo FP`;
  - the drop against the best available player, and the remaining games;
  - PASS / FAIL, current-season values and any lower-cost drop.
- Rest of Season Outlook, no-drop additions and IL moves are unchanged.

**Phase 8: weekly production season blend** (model
`waiver-season-blend-phase8`; 2026-11-24 read-only audit and test-first
implementation; **deployed** 2026-11-24 10:32 UTC from commit `d16607f` and
verified read-only; no migration; rollback images are tagged `pre-phase8`;
see [the session notes](docs/sessions/2026-11-24.md) and the
[current-state report](docs/status/current-state.md)):

- Rest of Week, Next 7 Days and Next 14 Days value every persisted
  current-season game once, in exactly one bucket (last 14 days, earlier this
  season), beside the fresh prior season counted as **2 games**:
  `(sum of current-season game FP + 2 x prior FP/G) / (games + 2)`. The prior's
  share falls with every game; earlier current-season games now count.
- Why: the Phase 7.1 blend shrank only the last 14 days toward the prior season
  with 10 games of weight, so the prior kept at least 55% of every weekly value
  all season and earlier current-season games never counted. On the persisted
  2026-27 games, a 10-game prior was significantly worse than about 2 games on
  ordering accuracy, rank correlation and absolute error for the next 7 and 14
  days; a recency multiplier added nothing once the prior's share was fixed.
- Eligibility is unchanged (sample gates still read the Last 14 Days sample);
  Rest of Season Outlook is unchanged. The page shows each bucket's games and
  share and the exact arithmetic; PRIOR-SEASON DRIVEN stays disclosed.
- Production acceptance (GET only): the API and bundle serve Phase 8, and the
  live payloads equal a read-only Phase-8 shadow of the same data. The
  database is unchanged, with 0 refresh, provider or non-GET requests from
  the deployment. The saved Yahoo evidence (2026-11-21) is past 24 hours, so
  live decisions return after the next REFRESH WAIVER DATA.

**Phase 7.1: Compare a Specific Drop answers from the gate** (model
`waiver-decision-integrity-phase7.1`; **deployed** 2026-11-21 21:46 UTC from
commit `7a02a4f` and verified read-only; replaced in production by Phase 8 on
2026-11-24; no migration; rollback images are tagged `pre-phase71`; see the
[current-state report](docs/status/current-state.md)):

- The selected drop's answer comes from a backend `drop_summary` built from
  the same gated pair decisions as the cards and the roster label: BEST
  VALID REPLACEMENT, WATCH, HOLD <drop> or CANNOT EVALUATE.
- The raw-net leader appears only as a subordinate "HIGHEST RAW MODEL
  COMPARISON — not a recommendation", with its verdict, raw and reconciled
  net, the gate reason and an exact-pair Analyze. It is never called the top
  option.

**Phase 6: Waiver horizons & evidence** (model
`waiver-horizon-evidence-phase6`; **deployed** 2026-11-14 21:30 UTC and
verified read-only, application-only with no migration or refresh; rollback
images are tagged `pre-phase6`; see
[current state](docs/status/current-state.md)) carries the user-approved NO
CURRENT YAHOO DESIGNATION policy and adds:

- **Board = optimizer:** one shared pair judgment and ordering, so the
  board's best add and `best_drop_for_team_id` are the optimizer's best
  supported pair. BEST MOVES fails closed with a contract error if they ever
  differ, and a full roster never shows "Next open spot".
- **Horizons look forward; form windows look back.** Horizons: Rest of Week,
  Next 7 Days, **Next 14 Days** (`mode=next_14_days`, Pacific today through
  today + 13) and **Rest of Season Outlook** (`mode=ros`; Season Evidence
  remains the name of the historical evidence). Form windows: Last 7, 14 and
  30 Days, Current Season and Previous Season. Each shows games, Yahoo FP/G,
  minutes, sample tier and freshness; starts and usage appear only with
  explicit season provenance. The trend (Last 14 Days vs days 15-30) is
  descriptive.
- **Tiered recent sample:** 7+ games SUPPORTED. 5-6 LIMITED passes in the
  weekly horizons only with 7+ season games, fresh production, a qualified
  role and 2 of 4 corroborations: 10+ games in 30 days; a STABLE or RISING
  role; FP/G within 13%; no minutes drop of 3+. 0-4 games never pass, and
  Rest of Season Outlook never corroborates a 5-6-game season sample. The
  thresholds come from a read-only audit of the persisted pool.
- **Move intent** (descriptive): STREAM, TWO-WEEK STREAM or LONGER-TERM ADD.
- **Page:** VIEW DETAILS leads with the ROSTER DECISION, then RECENT FORM,
  SEASON EVIDENCE and UPCOMING SCHEDULE. The full list adds form columns and
  exploratory sorts that never change BEST MOVES or the backend rank.

**Phase-6 ordering and wording cleanup** (same model version; **deployed**
2026-11-15 02:36 UTC and verified read-only, application-only with no
migration or refresh; rollback images are tagged `pre-phase6-cleanup`; no
recommendation changes; see
[current state](docs/status/current-state.md)):

- **Compare a specific drop** lists supported moves first, then WATCH, then
  supported nonpositive HOLD, then insufficient evidence. Within each group it
  keeps the measured net and player-ID order, so a higher-net WATCH no longer
  outranks a supported move.
- **Next 14 Days moves** read "Two-week move supported by current production,
  role, roster impact, and persisted Next 14 Days schedule evidence." Role is
  named only for STREAM, and the schedule only when the add has persisted
  games in the window.

**Phase 5: One-click refresh & authoritative availability** (model
`waiver-availability-phase5`; **deployed** 2026-11-14 08:26 UTC; the first
REFRESH WAIVER DATA run, job `629bd689b6f0`, SUCCEEDED 08:31:29–08:33:05 UTC
with every stage verified; the four post-refresh acceptance fixes from the
same day were **deployed** 11:40 UTC and verified read-only — see
[current state](docs/status/current-state.md)) adds the REFRESH WAIVER DATA workflow, Yahoo availability
classes, the recommendation-to-candidate invariant, weekly-adds and
waiver-priority context, structured timeout handling and faster waiver reads,
all described below. It keeps every rule of **Phase 4: Roster Capacity & Team
Needs** (model `waiver-capacity-phase4`, deployed 2026-11-13 23:59 UTC; see
[current state](docs/status/current-state.md)), which answers "Do I need to
drop anyone?" before ranking players, and every strict gate. The page header
holds the configured **Box Score Bully** name and the refresh panel; then come
the analysis-window controls and:

1. **TEAM SITUATION**: one plain-language capacity headline ("2 OPEN ROSTER
   SPOTS — NO DROP REQUIRED", "MOVE [player] TO IL TO OPEN A ROSTER SPOT",
   "ROSTER FULL — AN ADD REQUIRES A DROP" or "ROSTER CAPACITY NEEDS A YAHOO
   REFRESH") with one short reason; roster spots used, open regular and IL
   spots, additions without a drop, IL spots used, injured players, possible
   IL moves, **Weekly adds used** and **Waiver priority**; prioritized
   positional needs (HIGH / MEDIUM / COVERED); and evidence freshness grouped
   by state and date. Capacity blockers, the acquisition source and the
   detailed needs analysis (schedule gaps by date, position coverage,
   production, hold guidance) are in collapsed **Why?** details.
2. **BEST MOVES RIGHT NOW** (focal point): supported moves first (ADD ONLY,
   MOVE [player] TO IL THEN ADD, ADD + DROP), up to one distinct card per
   fillable spot, each with its Yahoo availability label. When no supported
   move exists, the strict state (HOLD or INSUFFICIENT EVIDENCE) is stated in
   one line and the **BEST MEASURED OPTION** card names the strongest
   measurable confirmed-available target with why it fits, **NOT YET A
   SUPPORTED ADD**, what to confirm in Yahoo, the exact blockers (collapsed)
   and **CHECK IN YAHOO**. With no confirmed-available player it says **NO
   CONFIRMED AVAILABLE PLAYER**. A read error is never shown as HOLD, and a
   featured player missing from the eligible set shows **WAIVER MODEL
   CONTRACT ERROR** instead of a card.
3. **OTHER GOOD OPTIONS**: distinct picks for BEST GUARD, BEST WING /
   FORWARD, BEST CENTER, BEST MULTI-POSITION OPTION, BEST SHORT-TERM
   SCHEDULE and BEST LONGER-TERM OPTION (player, positions, measured Yahoo
   fantasy PPG, games in the window, need filled, evidence state and one
   reason; calculations behind View details), the WATCHLIST and, when league
   availability is not current, a visually separate (dashed) **POTENTIAL
   TARGETS TO CHECK IN YAHOO** list.
4. **COMPARE A SPECIFIC DROP**: collapsed and visually muted unless the
   roster is proven full (then promoted and open) or a drop is chosen; no
   drop is ever preselected.
5. **FULL WAIVER LIST**: collapsed initially; filters for position, roster
   need, action type (including POTENTIAL TARGET), evidence level, Yahoo
   status, schedule, production sample and confirmed versus unverified
   availability. The default order is the backend `decision_rank`; filters
   only narrow the list. Rostered players are never listed.
6. **ADVANCED EVIDENCE**: collapsed; model version, source timestamps,
   decision-support method and counts, supported-action blocker counts,
   acquisition context, Yahoo availability evidence (class counts and the
   FA/W source gap), weights, waiver rules, data quality, coverage, DATA GAPS,
   mapping worklist and limitations.

The primary question is "What should Box Score Bully do right now, and does it
require a drop?" The optional **Compare a specific drop** tool answers the
secondary question "If I drop this exact roster player, who is best?" No drop
is preselected, and a drop is never assumed when persisted capacity shows an
open spot, an IL move frees one, or capacity is undetermined. Analysis
buttons, VIEW ANALYSIS and watch analysis are read-only; no Yahoo transaction
is executed. A selected drop remains fixed in its comparison and detailed
analysis; a preferred alternative drop cannot silently replace it. Negative replacement values mean no measured
improvement: holding the selected player is preferable under this descriptive
model, not a guarantee of future performance. Best Overall Available is
secondary context and ranks player production, not replacement fit.
Model-index changes are not predicted fantasy points, wins or probabilities;
no predictive accuracy is claimed.

Read-only contracts:

- `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers?mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...&mode=this_week|next_7_days|ros` (`player_id` is the internal identity ID)
- `GET /api/v1/waivers/refresh` (refresh progress and persisted freshness; database-only, safe to poll)

The page's one deliberate mutation is `POST /api/v1/waivers/refresh`
(below); it never runs during the reads above. All four analysis reads default `mode` to `this_week`. The replacements endpoint requires
an integer `drop_player_id`; impact accepts it optionally. Without it, impact
returns the no-drop (ADD ONLY or MOVE TO IL THEN ADD) comparison when capacity
supports one and `comparison=null` otherwise; it never silently picks a drop.
Both player IDs refer to internal identities, not Yahoo IDs. Replacement
responses include the full roster, `selected_drop_player_id`, and each
candidate's exact comparison.

#### REFRESH WAIVER DATA (one-click refresh)

The normal workflow is one click. When a critical source is stale, the header
shows **WAIVER DATA NEEDS A REFRESH**, names the stale sources and offers a
prominent **REFRESH WAIVER DATA** button; when everything is current it shows
**WAIVER DATA IS CURRENT** with the last successful complete refresh time and
collapsed source details. Nobody needs endpoint paths, query parameters,
Docker, curl or Swagger to make the Waiver Center current.

The click sends one request, `POST /api/v1/waivers/refresh` with
`{"retry_failed": false}`, to one backend owner
(`app/features/waivers/refresh.py`), which answers 202 immediately with the job
and the persisted-evidence status. The page then polls the database-only
`GET /api/v1/waivers/refresh` every 2 seconds, shows each stage, disables the
button while the job runs, announces progress to screen readers and reloads
the board once the job saved and verified data. Stages run in order:

1. `LEAGUE_SETTINGS`: Yahoo league, settings and teams for the configured
   league `478.l.50505` (resolved from `WAIVER_MANAGER_TEAM_KEY`, never from
   the browser).
2. `PLAYER_POOL`: the Yahoo player pool with statuses.
3. `LEAGUE_ROSTERS`: every real team roster in that league.
4. `ROSTER_SLOTS`: each roster player's `selected_position`, IL included.
5. `YAHOO_AVAILABILITY_STATUS`: availability and status from that same
   snapshot.
6. `NBA_TEAMS_PLAYERS`, 7. `NBA_SCHEDULE`, 8. `NBA_GAME_LOGS` and
   9. `NBA_SEASON_STATS`: one NBA import for the league season
   (`recent_days=30`).
10. `POST_REFRESH_VERIFICATION`: re-reads every source from PostgreSQL.

Every stage reports its `state` (PENDING, RUNNING, SUCCEEDED, FAILED or
SKIPPED), `started_at`, `completed_at`, `rows_fetched`, `rows_persisted`,
`source_timestamp`, a `verification` result with named checks, a safe
`error_code` and a user-facing `message`. The job reports `SUCCEEDED`,
`PARTIAL_FAILURE` or `FAILED`, the number of read-only Yahoo requests, blocked
practice-league requests and `yahoo_transactions_executed` (always 0).

Success means verified persistence, not an HTTP 200 from a provider. Each
source boundary first fetches and validates its complete replacement
snapshot, then writes it in one transaction stamped with the database clock
and checks the stamped row counts before committing:

- **Yahoo:** the league exists with current settings; every expected real team
  has a current roster snapshot; Box Score Bully's roster is present;
  `selected_position` is populated for every roster player (a missing slot
  rejects the snapshot as `ROSTER_SLOTS_INCOMPLETE` before anything is
  written); the player-pool, roster and status timestamps are current; and no
  local practice league or transaction resource reached Yahoo (a guarded
  client refuses both).
- **NBA:** the expected season, a current import timestamp, persisted game
  logs, season statistics and schedule rows, a committed transaction, batched
  writes and the latest imported game date.

The source boundaries (Yahoo league, Yahoo players and rosters, NBA) are
independent. A failure inside one rolls back only that boundary and keeps the
previous good snapshot; nothing is deleted before its replacement passed
validation, and a successful Yahoo refresh stays committed when NBA fails.
The panel then says **REFRESH PARTIALLY COMPLETED**, lists what was saved
("Yahoo roster data updated successfully.") and names each failed stage with
its message (for example "NBA game logs failed. The NBA statistics source did
not return usable data. The previous NBA snapshot was kept."); verification
reports the stale sources and the page keeps labeling them stale.
**RETRY FAILED STAGE** sends `{"retry_failed": true}` and reruns only the
failed boundaries; the others are SKIPPED as "Not rerun". A refresh that saved
nothing is **REFRESH FAILED** and changes no data.

Only one provider import runs at a time. A second POST while a job runs
returns that job (`already_running: true`) instead of starting another, and a
PostgreSQL session advisory lock shared with the manual league, player and NBA
import routes makes them return 409 `PROVIDER_IMPORT_IN_PROGRESS` meanwhile.
Job progress lives in the single API worker's memory: after an API restart the
status endpoint still reports persisted freshness, but the job history starts
empty. No table or migration was added. There is no automatic or scheduled
provider refresh; opening the page, changing the mode and **Reload persisted
evidence** read PostgreSQL only.

Freshness in the panel uses the waiver model's own rules: Yahoo
league/settings, player pool and every league roster within 24 hours (rosters
must also be newer than the latest league/team/settings import); NBA
teams/players, schedule and season stats within 7 days; game logs imported
within 7 days with a game in the last 7 days. Season stats count only the
current season's **Regular Season** rows, the rows the waiver model reads;
preseason rows never satisfy the check.

#### Yahoo availability classes and the recommendation invariant

Every player gets exactly one backend `availability_classification` plus
`availability_evidence`: label, source, import time, roster-snapshot
completeness and counts, explicit Yahoo FA/W state and waiver-clear date when
Yahoo supplied them, why the player is eligible, and the exact blockers.

| Class | Meaning | Allowed use |
|---|---|---|
| `CONFIRMED_FA` | Yahoo explicitly reports a free agent and every roster is current | supported move or featured option |
| `CONFIRMED_WAIVER` | Yahoo explicitly reports waivers (claim-clear date when supplied) | supported move or featured option |
| `UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT` | absent from every current league roster; Yahoo FA/W state not supplied | supported move or featured option, labeled **UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO** |
| `ROSTERED_BY_OTHER_TEAM` | on another team's saved roster | never a target |
| `ROSTERED_BY_MANAGER` | on Box Score Bully | roster and drop side only |
| `AVAILABILITY_UNVERIFIED` | on no saved roster, but the snapshots are incomplete | **POTENTIAL TARGET TO CHECK IN YAHOO** only |
| `SOURCE_STALE` | explicit or absence evidence from a stale snapshot | **POTENTIAL TARGET TO CHECK IN YAHOO** only |
| `EXCLUDED_STATUS` | Yahoo O/OFS/NA | never a target |

A supported add requires every league roster snapshot to be current and
complete, the player to be absent from all of them, explicit FA/W evidence
when Yahoo supplied it, no O/OFS/NA status, and every existing identity, sample,
status and production gate. The supported Yahoo player resource used today
carries no FA/W ownership field, so a real unrostered player is labeled
UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO and is never called confirmed
available.

Invariant: every player the board or best-move analysis names as a supported
move or featured recommendation (best add, supported actions, best measured,
OTHER GOOD OPTIONS groups, WATCHLIST, option groups and need options) must be
in the board's `eligible_candidate_ids` with an actionable class. The backend
asserts this before responding and returns 500
`RECOMMENDATION_CONTRACT_VIOLATION` rather than a violating result. The UI
checks each featured ID against that eligible map and shows **WAIVER MODEL
CONTRACT ERROR** instead of the card; it never reconstructs availability.
Potential targets must have an unconfirmed, unrostered class and render only
in their separate section. No player name is hard-coded: a productive player
on another team's roster (the Jrue Holiday acceptance example) can be neither
a move nor a potential target, and an unconfirmed one can only be a potential
target.

The board returns full evidence for the top 12 eligible candidates
(`candidate_limit`), every eligible ID (`eligible_candidate_ids`,
`candidate_count`), an `availability_summary` (class counts, snapshot
completeness and the FA/W source gap) and `acquisition_context`; FULL WAIVER
LIST still lists every option from `decision_support`.

#### Weekly adds and waiver priority

The existing supported Yahoo `league/{key}/teams` resource already supplies
each team's `waiver_priority` and `roster_adds` (week and adds used), and the
league settings supply `max_weekly_adds`. They are normalized from the
persisted teams payload with its import time, refreshed by every league
refresh and shown in TEAM SITUATION as **Weekly adds used** (for example
"2 of 4 · 2 left") and **Waiver priority** (for example "4th"). They are
context only and never change ranking. Exact waiver claim-clear times are not
supplied by the import and remain unsupported. The teams payload's
`is_owned_by_current_login` flag is observed but not used as authentication
evidence.

#### Errors, timeouts and read performance

The client turns every API failure into a status, code, short message,
`retryable` flag and request ID. Non-JSON bodies such as the nginx 504 page are
never rendered, and HTML-looking or overlong text is dropped. A 504 or client
timeout shows **WAIVER ANALYSIS TIMED OUT** ("The saved data was not changed.
Retry the analysis, or refresh the evidence if its timestamps are stale.")
with **RETRY ANALYSIS** and **REFRESH WAIVER DATA**, says the error is not a
HOLD decision, shows the request ID and withholds every earlier
recommendation. The browser gives up on a waiver read after 75 seconds only
if the proxy never answers. nginx assigns `X-Request-ID` to every `/api`
request, the API reuses it in its logs, and nginx returns it even on its own
502/504 pages.

The 504s came from slow reads, not from the proxy limit: measured read-only
against the persisted production data with a post-refresh workload (309
eligible candidates, full roster), the weekly board and best-move reads each
took about 7 seconds and the board returned 6 MB, so overlapping page reads
exceeded nginx's 60-second limit on the shared host. The reads now load one context per request (only
schedule rows inside the window plus per-player aggregates), memoize
comparisons within the request instead of recomputing the same before-side
for every pair, cache position parsing, use bisect percentiles, skip pair
evaluation for adds that are not eligible, bound the board to 12 full
candidates and run the analysis off the event loop. Same host and data
(2026-11-14):

| Read (weekly modes) | Before | After |
|---|---|---|
| `GET /waivers` (board) | 6.4-7.1 s, 6.1 MB | 1.8-2.1 s, 1.1 MB |
| `GET /waivers/transactions` | 6.9-7.1 s | 1.8-1.9 s |
| `GET /waivers/replacements` | 4.9-5.3 s, 5.1 MB | 1.5-2.0 s, 0.4 MB |
| `GET /waivers/{id}/impact` | 3.4-3.7 s | 1.0-1.3 s |

Season Evidence reads take about 2-6 seconds (previously 4-10), most of it
loading the roughly 35,000 remaining-season schedule rows. Every read issues
17 read-only statements and no writes or provider calls. Waiver GETs return a
`Server-Timing` header and log one `request_timing` line (load/analyze phases
and candidate counts, no payloads). No proxy timeout was raised: the refresh
POST returns immediately and its progress is polled.

**Cold API and abandoned reads (2026-11-15 incident).** One page view sends
three reads at once: refresh status (30-second client limit), board and best
moves (each a full context load). After an idle period the shared host swaps
the API out to a swap file on the rotational system disk. The first page load
then pages it back in at roughly 0.5-1 MB/s: refresh status times out ("Saved-evidence
freshness could not be read"), board and best moves return 504. Before the
admission fix below, the API kept computing those abandoned reads for up to 8
minutes, holding database connections, so retries, reloads, horizon switches
and REFRESH clicks piled on. Wait for health, then retry once; never stack
retries. A refresh POST whose client timed out can still start the job once
the API catches up, so check the panel before clicking again.

**Heavy-read admission (deployed 2026-11-15 14:50 UTC, API only).**
`app/features/waivers/admission.py` lets one board, best-move, replacements
or impact read run at a time. A queued read waits before any database
dependency, so it holds no connection. A read whose client disconnects
(browser abort, nginx 499/504), queued or loading, is cancelled and logged as
`status=499`; `request_timing` and `Server-Timing` gain a `queue` phase.
Completed reads, scoring and contracts are unchanged; refresh status and the
refresh POST are not gated.

Verified on production:
- At most one heavy analysis ran at a time; a queued best-move read waited
  6.9 s while holding no transaction.
- A read whose client aborted after 2.5 s stopped 16 ms later, and the next
  read took the slot immediately.
- Responses were identical before and after the deploy.

A page's second heavy read now waits for the first. Cold reads after an idle
period can still exceed 60 s on this host, but their work stops instead of
piling up.

**Phase 2: Best Supported Transaction** analyzes hypothetical swaps, not
Yahoo transaction history or execution. It loads the existing context once
and, when the roster is full (ADD + DROP shape), evaluates the saved waiver
pool against every persisted manager roster drop in memory through the same
`enrich` / `compare` functions used by replacements and impact. With open
capacity it builds a no-drop fill plan instead (see Phase 4 below). No second formula, percentiles, component mask or
weight tuning is introduced. Positional coverage remains bounded whole-roster
coverage; REB/BLK/STL contribute only through Yahoo points, not category needs.

**Phase 3: Evidence Intelligence** extends the same four response models with
backend-owned CURRENT ROLE, independent minutes/usage/starts quality, normalized
Yahoo status evidence and schedule coverage/import time. It derives role once
per player during the bulk context load, never per transaction pair. The
existing optimizer, exact-pair comparison invariant, points formula, production
sample gates and component weights are unchanged. Current role is descriptive,
not future minutes, usage, a starting assignment or injury-return prediction.
WATCH details explain both measured role and the evidence blocking ADD.
Phase 3 shipped as model `waiver-evidence-phase3`; the current model version
is `waiver-horizon-evidence-phase6` (Phase 6, deployed 2026-11-14; Phase 5 was
`waiver-availability-phase5`).

CURRENT ROLE displays recent/comparison minutes and usage, measured deltas,
window counts/dates, supported season starts, role trend and independent quality.
Expandable source details expose medians, exact contributing/missing/stale game
IDs, source timestamps, reasons and limitations. Yahoo status remains visible
with freshness and uncertainty. SCHEDULE displays persisted games, opponents,
off-days, back-to-back pairs, calendar window, import time and coverage.
WATCH shows why a measured swap is interesting (positive descriptive index and
available evidence) separately from what prevents ADD; unsupported role is not
described as rising or projected opportunity.

Schedule resolution uses saved per-player `player_schedule` rows and the
persisted identity/team mapping; it does not infer a player's schedule from a
Yahoo team abbreviation and the general NBA daily-game table. No applicable
rows means UNKNOWN/null counts; in-window rows mean PARTIAL, never COMPLETE.
Mapping, status-source, schedule-coverage and freshness diagnostics are exposed
separately so unknown evidence is not presented as zero or healthy.
The frontend warns when the served model version differs from the one it
was built for (`waiver-horizon-evidence-phase6`); do not use a stale board for
a decision.

#### Roster capacity, action types and team needs

Capacity comes only from persisted Yahoo evidence: league-settings roster
positions (Driveway Dudes: 13 non-injury spots plus 3 IL) and each roster
player's persisted Yahoo slot assignment (`selected_position`). It is never
inferred from the number of rostered players. `app/features/waivers/capacity.py`
reports total, non-injury, active, bench and injury capacity, occupied and open
spots, open starting and injury slots, injured players with slot and IL
eligibility, possible IL moves, additions available without a drop, blockers,
warnings and the transaction-legality limitation.

Transaction shape precedence: an open non-injury spot gives **ADD ONLY**;
otherwise an injured player in a non-injury spot whose persisted Yahoo
eligible positions include an open injury slot (with status evidence that is
not stale or missing) gives **MOVE [player] TO IL THEN ADD**, conditional on
Yahoo accepting the move; otherwise **ADD + DROP**. Moving a player to IL
keeps the player on the roster and is never a drop; players already in IL
use no non-injury spot. Capacity is **UNDETERMINED** when settings or the
roster snapshot are not fresh (24-hour rule), a slot assignment is missing,
an assignment names an unknown slot, slot counts are exceeded, an IL occupant
no longer lists that IL slot in persisted eligibility, or a slot type has no
verified semantics. The board then returns **INSUFFICIENT EVIDENCE** with the
exact blockers; it never manufactures HOLD or assumes a drop. Roster locks,
game-time locks, claim timing and live IL eligibility remain unverified
(weekly adds and waiver priority are shown only as context), so every action
requires Yahoo confirmation.

Actions (`recommended_action_type`): ADD ONLY (`ADD_ONLY`), MOVE [player] TO
IL THEN ADD (`MOVE_TO_IL_THEN_ADD`), ADD + DROP (`ADD_DROP`), WATCH, HOLD and
INSUFFICIENT EVIDENCE (`INSUFFICIENT_EVIDENCE`). The capacity shape decides
which action an actionable result becomes; the existing ADD/STREAM gates
(sample, production, status, freshness and positive measured impact) are
unchanged. Positive low-sample results stay WATCH, supported nonpositive
results are HOLD, and an UNKNOWN Yahoo status (any blank that is not a
verified NO CURRENT YAHOO DESIGNATION) still blocks strong actions.

The no-drop comparison (`comparison_type` `ADD_ONLY` or
`MOVE_TO_IL_THEN_ADD`) uses the same weights, fixed percentiles and common
component mask. Non-fit components are summed over lineup members and divided
by the fixed non-injury roster spots, so open spots and spots held by O/OFS/NA
players contribute nothing; fit is whole-lineup starting-slot coverage
measured once, counting only lineup-eligible players (O/OFS/NA and IL occupants
cannot fill lineup slots). With several open spots, the fill plan picks
additions sequentially and re-measures uncovered slots after each pick; later
steps state that their comparison is standalone, not cumulative. For the same
add, mode and shape, the board, fill/watch item and no-drop impact
comparisons are identical; the ADD + DROP exact-pair invariant is unchanged.

Team needs (`team_needs_analysis`) lists open and injury-weakened starting
slots, per-date schedule gaps for Rest of Week and Next 7 Days from persisted
per-player schedule rows, position coverage and need scores, multi-position
players, lineup production context and short-term versus longer-term hold
guidance. Injury return timing is never forecast. When settings are stale the
starting-slot counts are null, not zero.

New response fields: board `recommended_action_type`, `roster_capacity`,
`team_needs_analysis` and `option_groups`; candidate `recommended_action_type`,
`action_label`, `requires_drop`, `requires_injury_slot_move`,
`suggested_injury_move`, `target_roster_position`, `fills_needs`,
`add_only_impact`, `evidence_blockers`, `decision_priority` and
`lineup_slot_days_gained`; drop options gain `comparison_type` and slot
context; transactions gain `recommended_action_type`, `action_label`,
`roster_capacity`, `team_needs_analysis`, `best_addition`,
`add_only_recommendations`, `watch_additions`, `unfilled_needs`, addition
counts and `excluded_addition_reasons`; impact gains `roster_capacity`.

Yahoo roster imports now persist each player's `selected_position`.
Previously, the sibling slot block in Yahoo's roster player payload was
dropped, so every saved slot was NULL. Existing rows are corrected by
**REFRESH WAIVER DATA** (or the home page's Refresh Yahoo baseline); until
then capacity stays UNDETERMINED. A refresh counts only when its persisted
result is verified (roster `imported_at` current and `roster_position`
populated for every roster player), which the refresh's verification stage
checks. The import fixes for local practice leagues and NBA batching are
described under the advanced operator section below.

#### Decision support when strict gates fail

`app/features/waivers/decision_support.py` adds a separate, non-actionable
layer (`decision_support` on the board, same model version). It never
changes `recommended_action_type`, and no gate or threshold is lowered.
Every listed player gets one classification and a backend `decision_rank`:

- **SUPPORTED ACTION**: the strict ADD ONLY / MOVE TO IL THEN ADD / ADD +
  DROP result, unchanged; always ranked first.
- **BEST MEASURED OPTION**: the strongest player persisted basketball
  evidence can compare when no supported action fills the opening. The
  number of cards follows the capacity shape: open spots not covered by
  supported moves (at most two, picked sequentially with HIGH needs
  re-measured), one when ADD + DROP has no supported pair and the player
  out-produces the lowest-producing roster player, and one when capacity is
  undetermined. The user action is CHECK IN YAHOO, never ADD, STREAM or
  MUST ADD.
- **WATCH**: strict WATCH players, the distinct OTHER GOOD OPTIONS picks and
  up to five WATCHLIST players who out-produce the lowest-producing roster
  player (or fill a need when that floor is unknown).
- **MEASURED**: other comparable players (full list only).
- **UNAVAILABLE**: players that cannot be compared, with counts by reason
  (Yahoo O/OFS/NA, unresolved Yahoo-to-NBA identity, no current-season games,
  fewer than 4 current-season games without prior-season history, missing
  scoring or stats). Players on another team's saved roster are counted, never
  targeted.

Model production value is Yahoo-rule FP/G from the persisted,
contract-verified scoring settings (used even when those settings are past
the 24-hour freshness rule). In Rest of Week, Next 7 Days and Next 14 Days
every current-season game counts once (last 14 days and earlier this season)
beside the previous season counted as 2 games (Phase 8; Phase 7.1 and earlier
shrank only the last 14 days toward the prior season with weight n/(n+10)).
In Rest of Season Outlook this season is shrunk toward the previous season
counted as 10 games. Without prior-season history at least 4 current-season
games are required. Import age is labeled stale, never hidden. Ranking:
confirmed availability, then a fit for a HIGH need, then model production value,
needs covered, current-season games and player ID.

Only actionable-availability candidates (see the availability classes above)
can be SUPPORTED ACTION, BEST MEASURED OPTION, WATCH or MEASURED.
**POTENTIAL TARGETS TO CHECK IN YAHOO** appear only when league-wide roster
availability is not current. They are comparable players with resolved
identity whose class is `AVAILABILITY_UNVERIFIED` or `SOURCE_STALE`: not on
Box Score Bully's saved roster, not O/OFS/NA and not on any saved league roster,
labeled **AVAILABILITY UNVERIFIED** or **SAVED ROSTERS STALE — CHECK IN
YAHOO** (top 10, classification POTENTIAL TARGET). They are never mixed into
confirmed-available candidates. With stale rosters no player is featured, and
decision support reports state `POTENTIAL_TARGETS` (shown as **NO CONFIRMED
AVAILABLE PLAYER**). Blank Yahoo status stays **UNKNOWN** ("Yahoo did not provide an
explicit current status. Confirm the player in Yahoo before acting."): it
still blocks supported ADD/STREAM/MUST ADD, but a measurable blank-status
player may appear as BEST MEASURED OPTION, WATCH or a potential target. A
fresh, fully verified record with no `status` field is instead labeled **NO
CURRENT YAHOO DESIGNATION** ("Yahoo's current player record contains no
explicit injury/status designation. This is not a medical-health guarantee.")
and passes the status gate (deployed with Phase 6).

Positional needs (`team_needs_analysis.summary`) translate the existing needs
into Head-to-Head Points guidance by family (Guard PG/SG/G, Wing/Forward
SF/PF/F, Center C): **HIGH** when a family slot is uncovered (injury or open
slot), **MEDIUM** when one absence or a schedule gap would uncover it,
otherwise **COVERED**. UTIL and bench are depth notes, not positional needs.
Needs use the persisted slot configuration even when settings are stale and
say so in `basis`; multi-position players get credit for every need they
fill. No category optimization is introduced.

Response additions: board `decision_support` and `evidence_freshness` (seven
sources with state and import time); candidate `measured`,
`decision_support_class` and `decision_rank`; `roster_capacity.headline` and
`short_reason`; team needs `summary`, `depth_note` and `basis`; schedule
`persisted_window_games`. Why/blocker/confirm text is returned only for
featured options to keep the board compact. Reads stay database-only; the
freshness summary adds one aggregate SELECT.

#### Source integrity, coverage and DATA GAPS

Source Integrity & Coverage is **deployed**: a 2026-11-13 audit found the
running API and frontend images match commit `93fd50f` (source file hashes
and built bundle content). It changes
evidence/view-model diagnostics and adds explicit fail-closed status/identity
eligibility. It preserves the `waiver-evidence-phase3` scoring mathematics,
sample thresholds, ranking weights and optimizer mechanics. Every
UNKNOWN/UNAVAILABLE result should expose its most specific supported reason.
Missing, explicit zero, explicit empty, stale, unsupported and unverified are
distinct evidence states.

Source authority is split: Yahoo is authoritative for fantasy identity, league
configuration, scoring rules, roster, Yahoo status and fantasy availability.
Yahoo matchup/acquisition/waiver facts require separate verification. Persisted
NBA sources supply basketball inputs such as PTS, REB, AST, STL, BLK, TOV, MIN,
game logs, schedules and supported aggregate usage/starts. A Yahoo player
payload without basketball stats is not evidence that NBA production or
fantasy PPG is missing.

The board response includes backend-owned `coverage` and `data_gaps` in
Advanced Evidence. Coverage reports the full persisted Yahoo-pool denominator,
eligible candidate and configured roster counts, plus supported/missing/stale
production, identity mapping, schedule, status, role and acquisition coverage.
Each percentage is paired with its count and denominator; acquisition coverage
is league-context scoped. `data_gaps` groups exact counts and an evidence-based
reason under **FIXABLE DATA ISSUE**, **WAITING FOR MORE GAMES**, **SOURCE DOES
NOT SUPPLY**, **NEW SOURCE REQUIRED** and **UNVERIFIED YAHOO CONTEXT**.
An empty group is shown explicitly rather than implying a verified source.

Candidate evidence preserves raw Yahoo status, Yahoo team and NBA team
separately. Identity mapping state/reason is independent of the legacy
downstream mapping diagnostic. Only normalized-name/team-consistent persisted
links are classified as resolved; no identity is automatically created or
rewritten. Unresolved records include exact normalized-name NBA candidates
when present and a review reason. A team conflict is not evidence of a trade.
NBA ID presence alone does not override unresolved identity quality.
Stable mapping evidence may include exact ID, exact name/team, normalized
name/team, a known alias plus team, or a supported team change. Fuzzy name
alone never establishes identity, and Yahoo identity is never overwritten by
another provider. Status reasons distinguish explicit Yahoo status,
Yahoo-supplied blank, a missing status field, stale player-pool import, missing
observation, identity mapping issue and normalization defect (the response uses
corresponding `STATUS_PRESENT`, `YAHOO_SUPPLIED_BLANK`, `STATUS_FIELD_MISSING`,
`STALE_PLAYER_POOL_IMPORT`, `MISSING_PLAYER_OBSERVATION`, `MAPPING_ISSUE` and
`NORMALIZATION_DEFECT` labels; ADVANCED EVIDENCE counts "Yahoo blank",
"status field missing" and "no current Yahoo designation" separately). In the
persisted 2026-11-14 player pool, 426 of 744 Yahoo records had no `status` key
at all (and no `status_full` or `injury_note`); none carried a supplied blank.
A supplied blank stays UNKNOWN. A missing field was also UNKNOWN until the
user approved reading it as NO CURRENT YAHOO DESIGNATION on 2026-11-14,
overriding the same-day REJECT review (deployed with Phase 6 on 2026-11-14;
see [current state](docs/status/current-state.md)).
`player_status.interpret_yahoo_status()` grants it only for a fresh (24-hour)
player-pool record of the configured league whose Yahoo ID matches a
resolved, team-consistent identity, with no `status_full`, `injury_note`,
`on_disabled_list` or stored identity status, while every league roster
snapshot is current. Otherwise the status stays UNKNOWN with the first failing
reason (`PLAYER_OBSERVATION_MISSING`, `STALE_PLAYER_POOL_IMPORT`,
`MAPPING_ISSUE`, `NORMALIZATION_DEFECT` or `ROSTER_SNAPSHOT_INCOMPLETE`).
Candidates expose `status_field_state`, `decision_status_state`,
`status_reason`, `status_gate_supported`, `status_label` and `status_detail`;
adds still need actionable availability.
Only stale/missing/mapping/normalization conditions may indicate a recoverable
data issue. Model-version mismatches make the affected surface non-decision-ready.
Structured HTTP 409 contract errors remain visible errors, never HOLD or
empty-success fallbacks.
Schedule records expose their persisted source-row count and timestamp; rows
outside the requested window produce `SCHEDULE_SOURCE_INCOMPLETE` and null
window counts when no completeness manifest exists. `NO_PLAYER_SCHEDULE_ROWS`
remains a separate root cause. Rows present mean PARTIAL; without player rows,
or with an empty requested window whose completeness is unverified, coverage
is UNKNOWN. Stale inputs remain STALE. COMPLETE is forbidden until a
completeness manifest/contract is verified. An empty window is not a verified
zero.

Persisted game logs do not currently establish supported game-level
`USG_PCT`, `GS` or `START_POSITION`. Season usage, season starter-filter
evidence and minutes are not substitutes for game-level usage or recent starts.
These are source gaps, not a reason to call the delivered descriptive Phase-3
role feature incomplete: qualified minutes can establish role while optional
usage/starts remain independently unavailable.

#### Read-only persisted-stats reconciliation

To compare saved Yahoo player-pool observations with saved NBA statistics
without contacting either provider, run:

```sh
docker compose exec -T api python -m app.features.waivers.reconciliation \
  --league-key 478.l.50505
```

The command runs a read-only database transaction and reports comparable and
non-comparable inputs, mapping/mismatch classifications, source timestamps and
the presence of named acceptance fixtures. It compares only fields present on
both sides; absent Yahoo player-pool stat fields are classified as
`NO_COMPARABLE_STAT_FIELDS` (**CROSS-SOURCE COMPARISON UNAVAILABLE**), not as
missing required Yahoo stats, missing NBA production, an absent fantasy PPG
formula or a Court IQ defect. Zero comparable Yahoo/NBA stat pairs means there
is no second persisted Yahoo statistical dataset with overlapping basketball
fields for independent cross-source value comparison. Partial overlap is
reported separately from a complete six-stat comparison. Treat the per-player
report as private. The command does not fetch from either provider or claim a
comparison succeeded when no comparable fields exist.

#### Reviewed source options (no provider calls)

No additional reviewed source met the current evidence, usefulness and
permission threshold for implementation. This does not establish that every
possible public API is unusable:

| Candidate | Documented evidence | Decision |
|---|---|---|
| [Yahoo Fantasy Sports API](https://developer.yahoo.com/fantasysports/guide/) | Official API access is application/OAuth based and subject to Yahoo policy requirements, including throttling and attribution/data-use conditions; current matchup, manager identity, transaction and acquisition semantics were not established in persisted evidence. | Existing authorized source only; no new call or scope requested. |
| [`nba_api` BoxScoreAdvancedV3 / BoxScoreTraditionalV2](https://github.com/swar/nba_api) | Community-maintained endpoint documentation describes game-level usage and starter-position fields, but the relevant docs are old and official NBA terms were not verified. | Research lead only; not cleared for implementation. |
| [BALLDONTLIE NBA API](https://docs.balldontlie.io/) | The documented free tier does not include player stats, advanced stats, injuries or lineups and is limited to 5 requests/minute; relevant coverage requires a paid tier. | Does not fill the identified free-tier gap. |
| [SportsDataIO NBA API](https://sportsdata.io/developers/api-documentation/nba) | The reviewed free trial did not include NBA access. | No eligible free NBA source established. |
| [API-Sports NBA](https://www.api-sports.io/documentation/nba/v2) | Official documentation was inaccessible during review; current terms, limits and free coverage remain unverified. | Not cleared. |
| [Sleeper API](https://docs.sleeper.com/) | Official docs describe NFL support, not NBA; the documented API is free for non-commercial use. | Not applicable. |
| Kaggle datasets | Dataset-level licenses and historical coverage vary; no current-state completeness/refresh contract was established. | Not a verified current source. |

These findings are a documentation review, not a provider probe or legal
opinion. No new provider was approved or implemented. Keep Yahoo for fantasy
identity/configuration/state and persisted NBA sources for basketball
production, schedules, logs and season stats; Fantrax remains a documented ADP
niche only. Source research is separate from implementation. Obtain explicit
authorization and verify the applicable terms before any future provider
request.

The evidence contract preserves availability, freshness, production sample
qualification, Yahoo points, current role and schedule evidence, exact ADD/DROP
comparison and supported eligibility before an actionable winner is selected.
Phase 3 enriches that existing engine, not a second recommendation path.
ADD/STREAM/WATCH/PASS retain their meanings; missing mandatory evidence yields
INSUFFICIENT EVIDENCE. No supported positive transaction means successful HOLD,
not an obligation to produce an ADD.

The transaction response contains:

- Overall `decision` (ADD/STREAM/MUST ADD, HOLD or INSUFFICIENT EVIDENCE),
  `recommended_action_type`, `action_label`, `roster_capacity` and
  `team_needs_analysis`. The capacity shape decides what is evaluated:
  - **ADD + DROP** (roster full): `best_transaction` or null plus the pair
    lists and counts below.
  - **ADD ONLY / MOVE TO IL THEN ADD**: no pairs are evaluated
    (`evaluated_pair_count=0`). `best_addition` is the first step of
    `add_only_recommendations`, a fill plan with one step per fillable spot.
    The response also returns `watch_additions`, `unfilled_needs`,
    `evaluated/supported/watch/excluded_addition_count` and
    `excluded_addition_reasons`.
  - **UNDETERMINED**: `decision` is INSUFFICIENT EVIDENCE with the capacity
    blockers as reasons; no pairs or additions are evaluated.
- Up to five `top_supported_transactions` and five `watch_transactions`,
  ordered by descending net roster-index improvement, then ascending add ID
  and drop ID. Each pair includes add/drop evidence, mode, decision, the exact
  comparison with before/after/deltas/coverage, reasons and limitations.
- `evaluated_pair_count`, `supported_pair_count`, `watch_pair_count`,
  `excluded_pair_count` and overlapping `excluded_pair_reasons`. Counts cover
  the full assessed Cartesian product, including pre-ineligible O/OFS/NA and
  unknown-availability adds; excluded means excluded from the supported pool,
  not omitted from the assessed count. WATCH is a separate excluded subset.
- Field-level `data_quality`, limitations and `acquisition_context`: current
  waiver priority, weekly adds used, remaining and limit and the Yahoo week
  from the persisted teams payload, with source and import time. Exact
  claim-clear time stays null. Acquisition context never changes ranking.

Evidence eligibility precedes supported optimization: both add and drop need
Phase-1 current-season sample, production, status and freshness support.
Positive low-sample pairs remain WATCH, never a supported winner; unsupported
negative pairs are not presented as supported PASS. Supported nonpositive
pairs are PASS. If no supported positive pair exists for a full roster,
**HOLD -- no supported waiver transaction currently improves Box Score
Bully**, with `best_transaction=null`. No least-negative or WATCH substitute.
MUST ADD remains unused without a validated stronger threshold.

HOLD is a successful evidence-based decision, not an error, optimizer failure
or missing ranking. WATCH means a positive measured comparison is blocked
from strong recommendation by evidence quality. ADD/STREAM require eligible
evidence and positive supported impact; a positive delta alone is not enough.
Missing/stale mandatory evidence fails closed. For identical add/drop/mode,
the optimizer comparison equals the selected-drop replacement comparison and
the impact comparison. No Yahoo/NBA provider calls or writes occur during
analysis; pair evaluation reuses the one loaded context in memory.

VIEW ANALYSIS displays the backend's exact returned addition, fill step or
pair comparison without silently choosing a drop or invoking another formula.
The optional Compare a specific drop tool remains independent of the
recommended move. A transaction-read failure is a visible error, not a
manufactured HOLD.

All routes always resolve the configured manager team. Optional legacy
`league_key`/`team_key` query parameters must match that target or return 422;
they cannot retarget analysis. The frontend sends only mode and optional drop
ID, never arbitrary team keys. Board responses expose resolved league/team keys
and the persisted team name. A missing configured team is a visible 404 error,
not a fallback to another roster. Generic calculation services remain reusable
internally; other teams supply only the existing league-wide model context.

All read PostgreSQL only, using the existing internal identity, Yahoo payloads,
rosters/settings, NBA season statistics, game logs and NBA games. No migration
is needed. A drop ID outside the selected manager roster returns 422; an
already-rostered add returns 409. Missing league/team/player returns 404.
Configuration does not establish the current Yahoo login's team.
No transaction/scoreboard/current-week source contract is established.

Availability follows the classes above. Absence from **every** current league
roster is `UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT`, not a verified free
agent, and waiver-claim timing remains unknown. Yahoo imports older than 24
hours or predating a newer league/team/settings snapshot cannot establish
absence; explicit ownership in such a snapshot is `SOURCE_STALE`. O/OFS/NA are
excluded, Q/P remain uncertain, and blank status is unknown, never healthy
(a verified missing field is NO CURRENT YAHOO DESIGNATION, which is not a
health claim either).

Model version `waiver-horizon-evidence-phase6` (Phase 6 keeps the Phase-5 contract below), preserving the Phase-1 scoring contract:

- **Driveway Dudes / 478.l.50505 is Head-to-Head Points, 12 teams, not a
  category league.** Persisted normalized settings and the saved Yahoo source
  must match the verified contract before analysis; disagreement returns 409
  with mismatches, never a hard-coded override. Roster:
  `PG SG G SF PF F C C UTIL UTIL BN BN BN IL IL IL`.
- Fantasy PPG is exactly `PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO`,
  using persisted modifiers and NBA `PTS/REB/AST/BLK/STL/TOV` (`TO` maps to
  `TOV`). Every required field must be present; never zero-fill. Responses
  expose per-game inputs, scoring weights and individual contributions; the
  UI shows the calculation, separately from the descriptive ranking blend.
- League rules: **continual rolling list, Standard, 2-day waiver period,
  4 adds/week, no season acquisition limit, Daily - Today, post-draft players
  follow waiver rules, injured available players may enter an injury slot**.
  **No FAAB: it is neither an acquisition assumption nor a planned feature for
  this league.** Current waiver priority and weekly adds come from the persisted
  Yahoo teams payload as context; exact claim-clear time is unsupported.
  Acquisition value remains unavailable and excluded from ranking.

- Recent: regular-season NBA per-game production from Pacific dates today minus
  14 days through today, inclusive, in the imported league's NBA season,
  scored only with supported persisted Yahoo points modifiers. Missing required
  stats are not zero-filled. The oldest selected log import must be within seven
  days and the latest selected game date within seven days.
- Weekly player value (Rest of Week, Next 7 and Next 14 Days; Phase 8):
  every current-season game once (last 14 days + earlier this season, no game
  in both) beside fresh prior-season regular-season FP/G counted as 2 games,
  `(sum of current-season game FP + 2 x prior FP/G) / (games + 2)`, so the
  prior's share `2/(games + 2)` falls with every game. Phase 7.1 and earlier
  used recent weight `n/(n+10)` and historical weight `10/(n+10)` and ignored
  earlier current-season games. This is descriptive shrinkage, not a
  projection or calibrated confidence. A weekly
  value still needs fresh Last 14 Days games; prior-season history never
  substitutes for missing or stale recent logs or for current-season games.
  Current-season evidence quality is backend-owned: **20+ EXCELLENT,
  10-19 GOOD, 7-9 LIMITED, 4-6 VERY LIMITED, 1-3 INSUFFICIENT FOR STRONG
  RECOMMENDATION, 0 NO CURRENT-SEASON EVIDENCE**. This is not probability.
  Prior-season history never bypasses the current-season sample gate.
- Season Evidence (`ros`): latest eligible persisted regular-season per-game history, **not a
  projection**. Each mapped player uses their latest season no later than the
  imported league season; missing league season uses the current Pacific year as
  cutoff. Imports older than seven days cannot supply scored value or hold-label
  evidence; historical values can remain visible with stale quality.
- Yahoo scoring settings and roster slots must be imported within 24 hours to
  supply scoring/fit. The selected roster must also be fresh within 24 hours
  and not predate later league/team/settings imports.
- Value scores use deterministic midrank percentiles of the imported league
  pool, with ties equal. Role compares the latest three and preceding three
  regular-season games inside the existing 14-day lookback. Both sides require
  three valid fresh inputs; windows are fixed by date/game ID, not backfilled
  after missing/invalid/stale observations. MIN must be finite and nonnegative;
  game-level `USG_PCT` must be finite and in [0,1]. Imports and latest game must
  be within seven days. Missing fields are unavailable, never zero.
  For each supported metric, both mean and median deltas **>= +3.0 minutes**
  (usage **>= +0.02**, two percentage points) establish rising direction;
  both **<= -3.0 minutes** (usage **<= -0.02**) establish falling direction.
  Boundaries are inclusive; deltas are rounded to six decimal places before
  classification. Both strictly between the negative and positive threshold
  establish stable direction; disagreement is insufficient, not STABLE.
  This prevents a single outlier establishing direction.
  Disagreeing mean/median directions, opposing supported minutes/usage
  directions or inadequate minutes windows yield INSUFFICIENT EVIDENCE.
  Qualified minutes can establish role without optional usage/starts; those
  inputs retain their independent unavailable/partial/stale states.
  With qualified minutes and no conflict, either supported metric rising
  gives RISING, either falling gives FALLING, otherwise STABLE.
  Import age exactly seven days and latest game exactly Pacific today minus
  seven days remain within the implemented boundary; older evidence is stale.
- Opportunity exposes its raw `score` and `score_parts`. Only qualified role
  can supply a score: recent minutes/36*100, optional measured usage change
  `50 + delta*100`, and optional fresh explicit season start rate*100, each
  bounded 0-100 and averaged once. Minutes level and minutes change are **not**
  separate scored parts. Unqualified role supplies no neutral/average score.
  Season starts require explicit current-season `starter_filter.GP` matching
  saved starts, positive games, valid bounds, >=3 season games and a fresh
  import to score. An absent starter row is not zero starts. Smaller supported
  season samples remain partial context. Season usage is context only, not a
  substitute for missing game-level usage or a usage delta. Recent starts
  remain unavailable without a supported game-level source.
- Schedule counts persisted non-final/non-cancelled/non-postponed games,
  off-days (at most five persisted NBA games), back-to-back pairs and opponents.
  Coverage is PARTIAL with rows and UNKNOWN without rows; COMPLETE is never
  asserted without a completeness manifest. No rows means unknown, not zero.
  Import timestamp and freshness are separate from coverage. The UI always
  calls `this_week` **Rest of Week**: Pacific
  today through Sunday inclusive. With fewer than two inclusive dates remaining,
  it additionally warns **limited days remaining**; Sunday is a one-day window.
  Next 7 Days includes Pacific today and the following six dates, using that
  separate schedule window for its ranking (Phase 6: Next 14 Days is
  today through today + 13). None is a verified Yahoo week.
  Season Evidence's schedule ends June 30
  after the imported season start year (or today if that date has passed).
  Imports older than seven days do not supply a schedule score. These are not
  verified Yahoo periods, lineup starts, or complete future coverage.
- Waiver timestamps and date-window boundaries use `America/Los_Angeles`
  (PST/PDT automatically), independent of browser/server local time.
  Stored timestamp instants remain UTC and freshness uses the same elapsed
  24-hour/seven-day limits; changing the display/calendar zone does not extend
  evidence freshness. NBA persisted game dates are date-only inputs, not
  newly verified tip-off times or Yahoo matchup boundaries.
- Positional fit is bounded 0-100: the percentage of required starting slots
  coverable from Yahoo eligibility. For a player it describes roster coverage
  with that player, not player quality. The swap measures coverage **once** per
  roster, not a sum of marginal matching contributions; two fully covered
  rosters have zero fit delta regardless of reassignment/UTIL flexibility.
  Only lineup-eligible players count toward fit: Yahoo O/OFS/NA players and IL
  occupants cannot fill starting slots; players without an explicit status
  can (neither UNKNOWN nor NO CURRENT YAHOO DESIGNATION is a health claim).
- Before/after impact is a 0-100 roster index. For ADD + DROP, non-fit
  components are means over players holding non-injury roster spots; the
  no-drop comparison divides summed lineup values by the fixed non-injury
  spots. Fit is whole-lineup coverage in both. Each component delta is bounded -100
  to +100. Both sides and all compared replacements use identical weights,
  fixed league production percentiles and a fixed common measured-component
  mask across the manager roster and eligible scored pool. Optional evidence
  missing anywhere in that comparison population is omitted, not zero-filled.
  Responses expose component before/after/deltas, effective weights and
  matched starting slots. Missing roster values prevent numeric impact.
  Without a drop ID, impact uses the no-drop comparison when persisted
  capacity has an open spot or an IL move frees one, and returns no
  comparison otherwise. An explicit drop ID always analyzes that exact ADD +
  DROP pair; dropping an IL occupant opens no non-injury spot and returns no
  numeric impact.
- Explicit-drop replacement lists rank by decision tier first (Phase-6
  cleanup, deployed 2026-11-15 02:36 UTC): supported ADD/STREAM/MUST ADD,
  then WATCH, then supported nonpositive PASS (HOLD), then INSUFFICIENT
  EVIDENCE and unavailable comparisons.
  - Within each tier they rank measured net improvement descending, then
    stable internal ID, with unavailable comparisons last, so a higher-net
    WATCH never outranks a supported move.
  - Every row keeps its own decision and the selected drop, and the list
    always includes the top measured option (the raw-net leader; since
    Phase 7.1 the page names it only as the subordinate HIGHEST RAW MODEL
    COMPARISON, never as the answer). Without a selected drop the
  board's `decision_priority` orders supported actions, then WATCH, HOLD and
  INSUFFICIENT EVIDENCE; within a tier, players filling a measured need come
  first, then net improvement, weighted overall score and ID. With open
  capacity the best-team ID is the first fill-plan step; with undetermined
  capacity it is null. On a full roster a single best-team ID
  requires positive impact, fresh critical evidence and at least seven
  current-season games for both add and drop; short windows also require
  seven recent games (Phase 6: 5-6 recent games pass only when
  corroborated, as described under Phase 6). Backend decisions are MUST ADD, ADD, STREAM, WATCH,
  PASS and INSUFFICIENT EVIDENCE. No MUST ADD is forced. Positive 1-6-game
  results are WATCH, never Best Add, even with strong prior history.
  Supported nonpositive swaps are PASS; if all measured replacements are
  nonpositive the primary answer is **HOLD [selected player]**, not a
  least-negative Best Add. Top alternatives remain available for comparison.
  Missing/stale settings, roster, availability, production or unverified
  Yahoo status blocks strong recommendations, not merely warnings.
  Gate explanations name the failing player and window: a WATCH or
  INSUFFICIENT EVIDENCE pair reads, for example, "Sample gate: Bones Hyland 6
  games in the last 14 days" (or "N games this season" in Season Evidence)
  and, when a compared player's status is UNKNOWN (blank but not a verified
  NO CURRENT YAHOO DESIGNATION), unrecognized or stale,
  "Yahoo status gate: [player] blank (UNKNOWN)". Featured decision-support
  players with seven or more current-season games but fewer than seven in the
  last 14 days show "Played N games in the last 14 days". The WATCH swap list
  shows these backend explanations rather than rebuilding a reason in the
  browser.
  Opportunity-led ADD (opportunity exceeds all other weighted positive gains
  combined) requires qualified fresh role for both players. Schedule/opportunity-led
  short-term swaps require fresh measured schedule, available opportunity and
  qualified fresh role for both players for STREAM; partial coverage is disclosed.
  Role never bypasses either player's seven-game production gate (the
  tiered sample gate in Phase 6).
  Role/minutes/usage/starts/status/schedule quality exposes available, partial,
  unavailable or stale states, counts and source time/reason. O/OFS/NA are excluded,
  Q/P remain uncertain and blank Yahoo status remains UNKNOWN, not healthy,
  unless it is a verified NO CURRENT YAHOO DESIGNATION (passes the status gate;
  not a health claim).
  The shared quality contract also retains `missing`, `unknown` and
  `unsupported` for other evidence fields; these are not new Phase-3 labels.
  Yahoo status age exactly 24 hours remains within the boundary; older status
  cannot support a strong action. No recovery/severity forecast, expected
  availability date or injured-teammate replacement permanence is established.
- Defaults: fit 35%, player value 25%, opportunity 15%, schedule 15%,
  acquisition value 10%. Set API environment `WAIVER_WEIGHTS` to a JSON object
  with keys `roster_fit`, `player_value`, `opportunity`, `schedule`,
  `acquisition_value` (for Compose, inject it through a deployment override).
  Nonnegative finite values with a positive sum are required. Missing
  components are omitted with explicit effective-weight renormalization;
  player value and roster fit are mandatory for an overall score.
- Hold labels are cautious heuristics: longer-term hold requires at least 20
  historical games, sufficient current-season evidence, a historical value percentile of at least 60 and at least
  24 recent minutes/game; streamer requires rising minutes, measured recent
  value and a weekly/Next 7 Days schedule percentile of at least 60. Otherwise undetermined.

Unavailable: category waiver scoring/impact (existing Championship HQ category
baselines remain unchanged), acquisition value, ownership percentages,
opponent bidding/demand, matchup difficulty, injury-return forecasts, validated
projections, calibrated confidence/probabilities, and What Changed/history.
Yahoo transactions are not executed. No predictive accuracy is claimed. Refresh Yahoo and NBA data
with **REFRESH WAIVER DATA**; **Reload persisted evidence** only rereads saved evidence.
Field-level quality, sample sizes, limitations and source timestamps are
included in the API and analysis modal.

Focused tests: `python -m pytest -q tests/test_waivers.py tests/test_waiver_refresh.py tests/test_yahoo_players.py tests/test_player_identity.py tests/test_nba_import.py`
in the backend (set both `DATABASE_URL` and `TEST_DATABASE_URL` to a
disposable PostgreSQL database), `npm test`, `npm run build`, and
`npm run test:waivers:browser` in the frontend. Refresh tests use fixture
Yahoo/NBA providers and cover ordered stages, practice-league exclusion,
structured Yahoo and NBA stage failures, Yahoo staying committed when NBA
fails, NBA write rollback, false-success verification, retry of only the
failed boundary, concurrent requests and the shared lock, safe status rereads
and zero provider calls/writes during waiver GETs. Availability tests cover
every class, explicit FA and W preserved separately, the
recommended-subset-of-eligible invariant in all three modes and a 13 + 2 IL
roster that needs a drop. Backend tests cover the
roster-capacity scenarios: open spots, IL moves and their blockers, a full
roster, injured players already in IL, multiple needs, multi-position
eligibility, stale/missing/conflicting slots, low-sample WATCH and the
nested Yahoo `selected_position` import, plus the decision-support layer:
measured-production shrinkage and comparability, HIGH/MEDIUM/COVERED needs,
supported moves ranked first, two distinct fills, the IL-move headline, the
full-roster production floor, BEST MEASURED OPTION with undetermined
capacity, stale-availability POTENTIAL TARGETS, blank/unrecognized status,
the NO CURRENT YAHOO DESIGNATION conditions (each failing condition stays
UNKNOWN), O/OFS/NA and unresolved-identity exclusion, and SELECT-only API reads. Browser tests require Playwright
Chromium (`npx playwright install --with-deps chromium` or the matching
Playwright 1.56.1 container) and exercise ADD ONLY, MOVE TO IL THEN ADD,
multiple open spots, full-roster ADD + DROP, HOLD/WATCH, undetermined
capacity with a BEST MEASURED OPTION and potential targets, and the
nothing-comparable explanation, plus the six-section order, collapsed
compare/full-list/advanced sections, no preselected drop, recommendations
above the fold at 1440px, desktop/mobile layouts, keyboard modal focus, API
errors, mode changes, zero transaction writes and axe accessibility checks
against synthetic API fixtures, not live Yahoo. They also run the one-click
refresh (progress, disabled button, focus moved to progress and back,
automatic reload), a partial failure with RETRY FAILED STAGE, an nginx HTML
504 and a network failure (no HTML rendered, RETRY ANALYSIS recovery, no
stale move left actionable), stale rosters with separate potential targets,
and the contract error for a featured player outside the eligible set; the
only allowed write is the refresh POST.

#### Advanced operator and debug: individual imports

Normal use never needs these routes: REFRESH WAIVER DATA runs the same
imports in order and verifies the result. They remain for operators and
debugging (for example from `/docs`) and share the refresh's provider lock,
returning 409 `PROVIDER_IMPORT_IN_PROGRESS` while any provider import runs:

- `POST /api/v1/leagues/import`: Yahoo leagues, settings and teams.
- `POST /api/v1/players/import?league_key=478.l.50505`: the player pool and
  every team roster with slot assignments, validated as a complete snapshot
  (every team roster and every `selected_position`) before one transaction
  replaces the previous one. Only real Yahoo leagues are imported: local Yahoo
  Mock Practice pseudo-leagues (league key `yahoo-mock-practice.*`, game key
  `yahoo_mock_practice` or a `practice_source` payload) are never sent to
  Yahoo, so they cannot roll back the real league's import, and naming one
  explicitly returns 422. Before this fix a call without `league_key` also
  requested those keys, Yahoo rejected them and the all-or-nothing import
  persisted nothing.
- `POST /api/v1/nba/import?season=2026-27&recent_days=30`: NBA teams,
  players, games, schedules, game logs and season stats in one transaction.
  Every multi-row upsert is written in batches of 500 rows; previously one
  statement over about 4,095 game logs (a 30-day window in season) exceeded
  PostgreSQL's 32,767 bind-parameter limit and rolled back the whole import.
  The response includes `imported_at` and `latest_game_date`; a persisted
  count mismatch returns 502 instead of a success-shaped result.
- `GET /api/v1/waivers/refresh` and `POST /api/v1/waivers/refresh` (body
  `{"retry_failed": false}`) are the same calls the page makes.

### PostgreSQL Migrations

The v2 draft tables are versioned separately from the legacy metadata bootstrap. Startup creates the established legacy tables, then applies pending migration revisions transactionally. Apply manually with:

```bash
docker compose run --build --rm --no-deps api python -m app.core.migrations upgrade
```

On a disposable database only, rollback the new draft tables with `docker compose run --rm --no-deps api python -m app.core.migrations downgrade base`; the next app startup reapplies pending migrations. This downgrade deletes draft sessions, picks, audit events, snapshots, and targets. Existing pre-v2 schema still uses the legacy bootstrap and is not covered by a baseline migration. See [ADR 0005](docs/adr/0005-draft-state-persistence.md).

The Yahoo player payloads currently do not contain market ADP, draft rank, XRank, or ownership fields. Supply ADP values for available internal player IDs in `adp_by_player_id`; players without ADP or draft timing have null next-pick survival estimates. Survival compares ADP with your next snake-draft pick and adjusts for league size, an available draft-frequency value, and active positional runs. Fantrax does not supply draft frequency, so that input remains null and does not alter its estimates. These are heuristic, uncalibrated estimates. Modes are `balanced`, `upside`, and `safe`.

### Draft-market sync and diagnostics

Fantrax's documented public REST API is the selected personal-use ADP source. Sync current NBA ADP without a manual file:

```bash
docker compose run --build --no-deps --rm api python -m app.services.draft.market_sync --season 2026-27
docker compose run --no-deps --rm api python -m app.services.draft.market_diagnostics --season 2026-27
```

The sync uses Fantrax's published `getAdp?sport=NBA` and `getPlayerIds?sport=NBA` JSON interfaces. It joins only on unique normalized name, current team, and position; no-team and ambiguous records are left unmatched. The player-ID endpoint supplies Fantrax ID, name, team, and position; the ADP endpoint supplies ADP, name, ID, and position. Neither endpoint supplies a source update timestamp, sample size, draft frequency, draft rank, or XRank. Data fetched more than 48 hours ago is treated as stale for survival. The provider's `ADP` field remains distinct from ranks and projections.

Fantrax's terms prohibit scraping and direct use through unpublished interfaces; this sync calls the two endpoints explicitly documented on Fantrax's developer page. The app is private and personal-use, not commercial, and the feed is not redistributed. The terms do not state a numeric API rate limit or an explicit data redistribution license; the implementation uses two sequential GETs, bounded retries, and no sharing. For any broader/commercial use, obtain written permission. The legacy manual CSV importer remains available but is not required for normal operation.

```csv
player_id,adp,draft_rank,draft_frequency
10001,24.5,20,82
10002,37.0,34,65
```

```bash
docker compose exec -T api python -m app.services.draft.market_import --season 2026-27 --source manual < draft-market.csv
```

Rows upsert by internal player, season, and source. Use a distinct `--source` label for each feed; imports never modify `player_identity`. This command requires a manually supplied file and is not the requested automatic solution.

Other candidates remain excluded: Yahoo's verified player pool has no ADP; ESPN publishes rankings/editorial draft material but its terms prohibit automated extraction absent express written permission; Sleeper's official docs did not establish an NBA ADP feed; Hashtag Basketball's public ADP is HTML and automated-use permission/stable feed were not verified; FantasyPros' free API tier is non-production; RotoWire prohibits automated extraction absent written consent; and the GitHub candidate has no declared license and predicts rather than reports ADP. No second free, documented, permitted machine-readable source has been verified. See [ADR 0004](docs/adr/0004-draft-market-source-selection.md).

Draft utility is a transparent heuristic based on Yahoo-weighted historical per-game production, replacement value, positional scarcity and need, durability, risk, upside, and roster-slot fit. It is not a projection or general player ranking.

Position need considers unfilled starting positions (including G/F), not open
UTIL or bench slots. Roster matching prioritizes starters before UTIL/bench and
credits newly filled slots even when an existing player moves through an
augmenting path. UTIL and bench retain bounded construction credit (30/100 and
10/100). Need does not force a center or any other position to rank first.
Current boards recalculate legacy roster-fit results read-only; historical
recommendation snapshots are not rewritten.

Survival uses request ADP overrides first on v1; persisted v2 sessions use fresh stored Fantrax ADP. Both use snake pick distance and recent positional runs. Fantrax supplies no draft frequency, and the survival curve has not been calibrated against an evaluation dataset. Survival confidence is `heuristic_unvalidated`; missing or stale ADP stays unknown. v1 remains stateless and exposes survival independently; v2 action semantics use expected fallback loss.

Historical engine-vs-ranking outperformance is not established. Evaluation
requires authorized historical draft state, contemporaneous ADP snapshots, and
season outcomes; local draft history does not establish Yahoo's current roster
or whether the real league has completed its draft.

## API

- `GET /api/v1/health`
- `GET /api/v1/yahoo/oauth/authorize`
- `GET /api/v1/league?league_key=...`
- `GET /api/v1/leagues`
- `POST /api/v1/leagues/import` (operator/debug; the Waiver Center uses REFRESH WAIVER DATA)
- `POST /api/v1/players/import?league_key=...` (operator/debug; local mock-practice leagues are never sent to Yahoo and naming one returns 422)
- `GET /api/v1/players`
- `GET /api/v1/player/{id}`
- `GET /api/v1/rosters`
- `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros` (capacity-aware: no-drop fill plan, IL move then add, or add/drop pairs; configured manager team)
- `GET /api/v1/waivers?mode=this_week|next_7_days|ros` (configured manager team)
- `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
- `GET /api/v1/waivers/{player_id}/impact?mode=this_week|next_7_days|ros&drop_player_id=...` (drop optional: omitted means the no-drop comparison when capacity supports it; configured manager team)
- `GET /api/v1/waivers/refresh` (refresh progress and persisted freshness; database-only)
- `POST /api/v1/waivers/refresh` (body `{"retry_failed": false|true}`; 202; starts or rejoins the one verified Yahoo + NBA refresh)
- `POST /api/v1/nba/import` (operator/debug; batched writes, 409 while another provider import runs)
- `POST /api/v1/draft/metrics`
- `POST /api/v1/draft/utility`
- `POST /api/v2/draft/sessions`
- `POST /api/v2/draft/live-sessions`
- `GET /api/v2/draft/sessions`
- `POST /api/v2/draft/mock-sessions`
- `GET /api/v2/draft/mock-sessions`
- `DELETE /api/v2/draft/mock-sessions/{session_id}` (standalone mock only)
- `POST|GET /api/v2/draft/mock-batches`
- `GET /api/v2/draft/mock-batches/{batch_id}`
- `POST /api/v2/draft/mock-batches/{batch_id}/run`
- `GET /api/v2/draft/sessions/{session_id}`
- `GET /api/v2/draft/sessions/{session_id}/board`
- `PUT /api/v2/draft/sessions/{session_id}/order`
- `POST /api/v2/draft/sessions/{session_id}/mock-action`
- `GET|POST /api/v2/draft/sessions/{session_id}/sync`
- `POST /api/v2/draft/sessions/{session_id}/sync/{pause,resume}`
- `POST /api/v2/draft/sessions/{session_id}/mock-rehearsal`
- `POST /api/v2/draft/sessions/{session_id}/mock/{pause,resume,reset}`
- `GET /api/v2/draft/sessions/{session_id}/replay?version=...`
- `POST|PUT /api/v2/draft/sessions/{session_id}/picks/{overall_pick}`
- `POST /api/v2/draft/sessions/{session_id}/picks/{overall_pick}/undo`
- `PUT|DELETE /api/v2/draft/sessions/{session_id}/targets/{player_id}`

NBA provider calls happen only during imports. Player and league reads use PostgreSQL.

## Draft Room UI

The React/TypeScript Draft Room is served at `/` through Caddy and the frontend Nginx container. Nginx proxies `/api/*` and `/docs` to FastAPI on the private Compose network; the browser uses same-origin API requests. Run it with the existing `docker compose up --build` command. The Vite development proxy targets `https://localhost:18002`.

### Routes and Components

- `/` presents the Championship HQ foundation/category baseline and Yahoo
  connection alongside the preserved observer/practice setup. The observer
  workflow uses Yahoo URL/Connect after pairing; missing Mock/Real or slot
  evidence prompts a follow-up. Saved rooms and advanced setup remain available.
  Internal mocks use an explicit or
  previewed seeded order; Live Draft permits pending manager position and
  incomplete team mapping.
- `/draft/:sessionId` is the shared mock/live room: `DraftRoomPage` composes the decision card, roster, timing window, server-ranked board, recent picks, explanations, fallback alternatives, and data-quality panel. Mock rooms add opponent auto-pick-next, auto-pick-until-manager-turn, pause/resume, manager-selected picks, latest-pick undo, reset/new-mock, and standalone removal controls. Live rooms support sequential manual picks, correction, undo, and targets.
- `/waivers` is the decision-first read-only Waiver Center described above:
  configured Box Score Bully, TEAM SITUATION (capacity headline, needs and
  freshness), BEST MOVES RIGHT NOW (supported ADD ONLY, MOVE TO IL THEN ADD
  or ADD + DROP cards, otherwise the strict HOLD/INSUFFICIENT EVIDENCE state
  plus a non-actionable BEST MEASURED OPTION), OTHER GOOD OPTIONS (groups,
  WATCHLIST, potential targets), the optional exact-drop comparison, Rest of
  Week, Next 7 Days, Season Evidence, the full list and advanced evidence.
  Detail views use the
  returned backend comparison. Reload rereads saved data; it does not refresh
  a provider or execute a transaction.
- Internal session setup is split into league/team selection, order/mode selection, and session creation. No team order or manager identity is guessed from Yahoo data.

### State and API Contracts

The client uses route-local React state as a cache of backend view models. The room refreshes the board every five seconds and after each successful mutation. Pick and target writes send the observed session version; HTTP 409 pauses writes and presents a reload action. Internal mock batch picks run in a serialized background worker; the room polls the same session board and displays the same backend decision view. Replay is read-only. The client never calculates utility, survival, scarcity, wait cost, roster fit, snake timing, opponent picks, or player rank.

Backend additions for the UI include explicit live-session creation, separate live/mock session lists, source-checked mock actions and standalone mock removal, server-owned timing on session state, and `GET /api/v2/draft/sessions/{session_id}/board` for the latest snapshot-backed recommendation, current server-sorted candidates, data-quality statuses, and the manager's matched roster slots. Board sort modes are `decision`, `value`, `survival`, and `name`; search and simple filters do not alter recommendations. Snapshots retain compact ranked display rows, not per-player full explanations or fallback models. Both pick flows retain session-version checks; stale writes return HTTP 409.

Loading, empty league/player-pool, API errors, draft conflicts, unavailable recommendation evidence, and unknown/stale survival have separate UI states. Yahoo OAuth is linked when no imported league is available. Recent picks, corrections, undo, and target changes are written through the existing v2 endpoints.

### Mobile and Accessibility

The desktop room uses a two-column decision/board layout; below tablet width it stacks the decision first and keeps the player table horizontally scrollable. Controls have labels, icon-only actions have accessible names, decision/status is not color-only, the correction dialog has dialog semantics, and keyboard focus/reduced-motion preferences are supported.

### Calculation Boundaries

Draft category fit remains unavailable; Championship HQ's separate factual
category baseline does not establish category-aware waiver impact. Survival
remains `heuristic_unvalidated`; market ADP coverage is partial. Rule-based
opponent selection and a mock sync rehearsal are implemented; no Monte Carlo or
calibrated simulation, opponent-demand model, alerts, or transaction automation
is established.

## Scope

The draft module remains supported and preserved. Championship HQ category/team
baselines and the read-only Waiver Center are implemented post-draft capabilities.
The baseline is descriptive, not authenticated team ownership. Persisted
descriptive role/status/schedule intelligence is implemented; richer authorized
game-level usage/starts and injury-source evidence, verified Yahoo source semantics, validated forward projections,
opponent demand, What Changed/history, outcome calibration and transaction execution
remain evidence-gated follow-ups in [next actions](docs/status/next-actions.md).
Category-weakness optimization is not a priority for this Head-to-Head Points
league; the Championship HQ category baseline remains descriptive only.
Start/Sit, broader trade/league intelligence, a Decision Journal, and
playoff/championship planning remain outside the implemented waiver contract.
Calibrated probabilities require historical validation first. Existing mock
simulation is not a calibrated forecast. Production Live source cadence/mapping
and full manual fallback/correction/recovery acceptance remain unverified; Yahoo
Mock Practice does not validate Production Live. No external provider is called
by v2 session reads or calculations.
See [current state](docs/status/current-state.md),
[project memory](docs/project-memory.md), and
[draft persistence ADR](docs/adr/0005-draft-state-persistence.md).

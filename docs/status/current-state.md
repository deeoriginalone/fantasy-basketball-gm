# CURRENT STATE — Phase 9 Running and Re-verified — 2026-11-28

**STATUS: PHASE 9 RUNNING AND RE-VERIFIED** (model
`waiver-permanent-drop-phase9`; read-only re-verification 2026-11-28
17:18–19:02 UTC). The running app already served the committed Phase 9, so
nothing was rebuilt, installed or recreated, and no migration ran. Evidence
(local, untracked): `qa-work/2026-11-28-phase9-reverify/`; details in
`docs/sessions/2026-11-28.md`.

- **Running app (2026-11-28):**
  - api `ae3a52bf1e8a`. A `docker compose up -d` outside this work recreated
    it at 16:45:38 UTC from the same Phase 9 image (built 2026-11-24 21:21
    UTC), which applied the edited Compose memory keys. Migrations are still
    0001–0006. Its 105 `/app` files equal HEAD.
  - frontend `684201829a5b` (`db8d307`, since 2026-11-25 01:52 UTC). A HEAD
    build with the Dockerfile's `VITE_LIVE_DRAFT_POLL_INTERVAL_MS=60000`
    equals it byte for byte (`index-L4pYP32D.js`, `index-D1ZZHy7H.css`).
  - db `32ee446dd34c` and caddy `08198174d855` unchanged.
- **Data:** the user's REFRESH WAIVER DATA at 16:46:04 UTC (job
  `6d4519f914cf`, every stage SUCCEEDED) is the current snapshot: 29 tables,
  79,558 rows. Yahoo evidence is fresh until about 16:46 UTC on 2026-11-29.
- **Host (2026-11-28 infrastructure work, before this re-verification):**
  swap is an 8 GiB file on a USB 3 SSD (`/mnt/ssd`, `nofail`) with
  `vm.swappiness` 10; `/swap.img` is off but kept. The `api` service runs
  without swap: `mem_limit`/`memswap_limit` 1536m and `mem_reservation`
  512m (with `system.slice` `MemoryLow=512M`). The Compose keys live in the
  working tree and are **not committed** (backup
  `docker-compose.yml.bak-20261128T124122Z`). The API held 0 kB of swap, and
  warm heavy reads took 4.6–9.6 s. Record:
  `qa-work/2026-11-28-swap-infra/CURRENT_STATE_AND_ROLLBACK.md`.
- **Validation (Test, disposable, serial):**
  - Inside the running API image: backend Phase 9 focused 15 and waiver
    files 342 passed, and the full backend 506 passed on a fresh database.
    Two earlier attempts are void harness errors (no `DATABASE_URL`, then a
    database left dirty by stopped runs).
  - 15 contract probes passed: a fit-led pair is unchecked, and 12
    ineligible kinds of stronger player never set replacement level.
  - Frontend unit 82, `tsc -b` and build passed; desktop Playwright (1440 ×
    1000, one project, one worker) 26 passed.
- **Read-only acceptance of the running app (GET only):**
  - 67 GETs through Caddy, all 200 and Phase 9, with 0 invariant violations.
    They equal a pinned-clock Phase 9 shadow of the same data on all 63 waiver
    payloads.
  - Phase 8 and Phase 9 shadows of that data are identical apart from the
    model stamp, including all 19 Rest of Season Outlook payloads.
  - Desktop browser: axe 0 in 18 states, keyboard focus returned in all four
    horizons, the page stayed 1440 wide, no stale-model warning and 22
    requests, all GET.
  - The database is identical at 17:55, 18:49 and 19:02 UTC. The API logged
    97 GETs (all 200, no 499) and no refresh, provider, OAuth or migration
    line; nginx shows only GETs.
- **Gate in operation (shadow of the 2026-11-24 backup, running image,
  clock 22:00 UTC):** the documented acceptance reproduces exactly.
  - Best moves: Jones Jr. / Huerter +0.076, DeRozan / Dunn +0.231, Jones Jr. /
    Huerter +0.076 and Larsson / Huerter +0.118 (Rest of Week, Next 7 Days,
    Next 14 Days and Rest of Season Outlook).
  - Pair level, Phase 8 against Phase 9 (3,874 pairs per horizon): nets are
    identical, and decisions changed exactly on the 45 / 62 / 1 / 0 pairs the
    gate blocks.
  - 0 violations in 82 payloads, and all 49 lower-cost drops are strictly
    cheaper.
- **Today's weekly boards cannot evaluate (fail-closed, pre-existing):**
  Norman Powell (Yahoo O, no game in 7+ days, last-14-days production stale)
  holds the SG slot because IL is 3/3 (Curry, Markkanen and Barrett, all O).
  With no weekly value for him, `player_value` leaves the common mask:
  - every Rest of Week, Next 7 Days and Next 14 Days pair is CANNOT
    EVALUATE (7,384 per horizon), so the permanent-drop gate cannot run live
    today;
  - Rest of Season Outlook answers (best measured move ADD Keegan Murray /
    DROP Kevin Huerter, +0.523; dated observation, not advice).

  An in-memory probe that treats Powell like an injury-slot player gives
  792 / 781 / 733 pairs that clear every gate (PASS included) and 0 / 11 / 55
  permanence-blocked positive pairs. That is a causality probe, not a
  method.
- **Schedule finding (not yet affecting data):** the NBA Cup Championship
  (`0062600001`, 2026-12-11) is persisted with TBD teams. It does not count
  for fantasy, but player schedules have no game-type filter, so once its
  teams are set and a refresh runs, both finalists gain a phantom game in
  windows covering 2026-12-11.
- **Backup (private, not committed):**
  `~/fantasy-gm-phase9-reverify-20261128T175605Z.dump` (`pg_dump -Fc`,
  138,346,291 bytes, mode 0600, SHA-256 `d0539e42940c…`). 29 TABLE and 29
  TABLE DATA; restored into a disposable database, it equals the live row
  counts.
- **Rollback (unchanged):** `pre-phase9-a11y` (the `8e51670` frontend) or
  both `pre-phase9` images (Phase 8). No database rollback is needed.

**PHASE 9 DEPLOYMENT RECORD (accepted 2026-11-25 02:31 UTC).** Source commit `8e51670` ("fix: protect
long-term roster value on short waiver streams") and the accessibility fix
`db8d307` ("fix: preserve heading order in permanent drop facts"), both
pushed to `origin/main`.

- **Running at that acceptance:** api `e8ec57d94aae` (since 2026-11-24 21:24 UTC; its image
  equals the `8e51670` build; replaced by `ae3a52bf1e8a`, same image, on
  2026-11-28) and frontend `684201829a5b` (`db8d307`, since
  2026-11-25 01:52 UTC). db and caddy were not recreated. No migration.
- **Acceptance (GET only):**
  - The live payloads equal a read-only Phase 9 shadow of the same data.
  - The desktop browser acceptance (1440 × 1000) passed with axe 0
    violations in 16 states. It checked every permanent-drop block against
    the backend: OTHER GOOD OPTIONS (h4), the best move, explicit drops and
    the Analyze dialog (h5).
  - The database is unchanged, with 0 refresh, provider, OAuth or non-GET
    requests from the closeout.
- **How it was deployed** (details in `docs/sessions/2026-11-24.md`):
  1. At 21:20–21:24 UTC on 2026-11-24 a build of the then-uncommitted Phase 9
     tree recreated `api` and `frontend`, outside the planned closeout. Its
     origin is unknown.
  2. REFRESH WAIVER DATA ran at 21:24:35 UTC from an open `/waivers` page
     (job `f56f60744a47`). It established the data baseline, and the
     closeout did not undo it.
  3. The closeout committed the source, rebuilt Phase 8 as the `pre-phase9`
     rollback and backed up the database. It proved live Phase 9 equal to
     the committed Phase 9 shadow; only the frontend needed recreating
     (23:59 UTC).
  4. The first formal browser acceptance (00:19 UTC) failed axe
     `heading-order`: inside an OTHER GOOD OPTIONS card (h3 title) the
     permanent-drop block used an h5.
  5. The fix was deployed frontend-only (01:52 UTC). The final desktop
     acceptance passed (02:22–02:31 UTC).
- **Rollback:** the fix alone with `pre-phase9-a11y` (the `8e51670`
  frontend, heading defect included), or all of Phase 9 with the two
  `pre-phase9` images (Phase 8). No database rollback is needed.

**PREVIOUS VERIFIED DEPLOYMENT: PHASE 8 (2026-11-24 10:32 UTC; 02:32 PST).**
Model `waiver-season-blend-phase8` was deployed from commit `d16607f` ("fix:
use current-season evidence in waiver production blend"), which is pushed to
`origin/main` together with its record. Phase 9 replaced it.

- Only `api` and `frontend` were recreated.
- No migration, refresh, provider call, OAuth, Yahoo transaction or data
  change came from that work. Phase 8 has no permanent-drop policy (Phase 9
  below adds one), no schedule change and no player-specific rule.
- Details: `docs/sessions/2026-11-24.md`. Evidence (local, untracked):
  `qa-work/2026-11-24-weekly-blend-audit/weekly-blend-report.md` (audit) and
  `qa-work/2026-11-24-phase8-deploy/deployment-acceptance.md` (deployment).

### Phase 9 (deployed and verified): short-horizon permanent-drop policy

- **Rule (E2, replacement break-even).** In Rest of Week, Next 7 Days and Next
  14 Days, an ADD + DROP whose consistent positive net leans on a schedule
  edge is supported only if its window gain (the Phase-7 window Yahoo FP)
  covers `max(0, drop FP/G − replacement FP/G) × the drop's games after the
  window`. Replacement level is the best available player: off the roster,
  confirmed available, fresh, status-verified and sample-supported, and never
  below the add. Break-even in Yahoo FP; no fitted threshold; no player names.
- **Where.** It runs after the Phase-7 gate and before the sample, status and
  STREAM role gates. A blocked pair is HOLD / DO NOT ADD, never WATCH, and the
  optimizer moves to the add's next supported drop. Rest of Season Outlook,
  ADD ONLY, MOVE TO IL THEN ADD and production- or fit-led pairs are never
  checked. The four Phase-7 consistency checks are unchanged.
- **Why.** On the persisted snapshots the best weekly moves dropped Jarrett
  Allen (30.0 FP/G, 5.9 above the best available player) for +5.8 / +14.0
  (Nov 24) and +28.5 / +3.9 (Nov 21) window FP. That gives up about 356–403
  Yahoo FP over his remaining games, while drops at or below replacement level
  supported the same adds.
- **Effect (read-only shadows).**

  | Snapshot / horizon | Phase 8 best move | Phase 9 best move |
  |---|---|---|
  | Nov 24 Rest of Week | Jones Jr. / Allen (+5.8 FP) | Jones Jr. / Huerter (+2.4 FP) |
  | Nov 24 Next 7 Days | DeRozan / Allen (+14.0 FP) | DeRozan / Dunn (+4.9 FP) |
  | Nov 24 Next 14 Days | Jones Jr. / Huerter | unchanged |
  | Nov 21 Next 7 Days | Jones Jr. / Allen (+28.5 FP) | Jones Jr. / Huerter (+23.7 FP) |
  | Nov 21 Next 14 Days | Jones Jr. / Allen (+3.9 FP) | Jones Jr. / Huerter (+24.9 FP) |

  Rest of Season Outlook payloads are identical apart from the model stamp.
- **Display.** Every checked weekly pair shows only backend facts:
  - the short-term gain (`+X.X Yahoo FP during` the horizon);
  - the permanent drop cost, `(drop FP/G − replacement FP/G) × games after
    the window = X.X Yahoo FP`, from 2-dp values that reproduce the cost;
  - the drop against the best available player, and the remaining games;
  - PASS / FAIL, current-season values and any lower-cost drop.

  The browser computes none of it. The block's title is an h4 directly under
  a card's h3 title (OTHER GOOD OPTIONS, WATCHLIST and best measured cards)
  and an h5 under an h4 (the best move, explicit-drop cards and every exact
  calculation).
- **Validation and acceptance:** see `docs/sessions/2026-11-24.md`. Deployed
  and verified 2026-11-25 02:31 UTC (GET-only acceptance; no migration). The
  API runs the `8e51670` build; the frontend runs `db8d307`. Rollback tags:
  `pre-phase9` (Phase 8, rebuilt from `2e6f379`) and `pre-phase9-a11y` (the
  `8e51670` frontend). `pre-phase8` holds Phase 7.1.
- **Known limitations.** Remaining games count to the end of the NBA regular
  season, not the fantasy league's end or playoffs, so late in the season the
  gate is slightly stricter than the fantasy schedule warrants. Replacement
  level assumes the best available player stays available; it is re-read on
  every request.

### Method (weekly horizons only)

- Rest of Week, Next 7 Days and Next 14 Days value each player at
  `(sum of current-season game Yahoo FP + 2 × prior-season FP/G) /
  (current-season games + 2)`.
- Every persisted current-season regular-season game counts once, in exactly
  one bucket: RECENT (last 14 days) or EARLIER (before them). The fresh prior
  season is a third bucket counted as 2 games, so its share `2/(games + 2)`
  falls with every game.
- `production.py` is the canonical production basis. Ranking, board,
  optimizer, replacements and impact use one value; decision support
  computes the same blend from the same buckets (as before Phase 8 it also
  scores with persisted settings past 24 hours and keeps a prior older than
  7 days). The backend returns each bucket's games, FP/G, share and dates
  plus the exact arithmetic; the page renders them and computes no weight.
- Unchanged: the sample eligibility gates (Last 14 Days sample only), the
  fresh-Last-14-Days requirement, the 7-day prior freshness rule, Rest of
  Season Outlook, the Phase 7/7.1 explanation gate and verdicts, schedule,
  fit, opportunity, drop policy and admission. No player-specific rule.

### Why (read-only audit of the 2026-11-21 snapshot)

- The Phase 7.1 weekly value, `n/(n+10) × last 14 days + 10/(n+10) × prior
  season`, kept at least 55.6% prior weight all season and ignored 53% of
  current-season games.
- It made 11 SUPPORTED ADDs of an add who trailed the drop on both Last 14
  Days and the current season, including the featured Rest of Week move
  DeRozan / Dunn (+0.589).
- On a backtest against the next 7 and 14 days, counting every game with a
  prior of about 2 games beat the 10-game blend on ordering, rank correlation
  and absolute error. K = 2 came from a rule fixed before the run.

### Decisions on the 2026-11-21 snapshot at its fresh instant (read-only, clock 2026-11-21T18:29:21Z)

The audit shadow and the deployed API image (`85efb1c1d659`, its own
`/app`) give the same decisions: 0 differences over 18,560 exact pairs.

| Horizon | Phase 7.1 | Phase 8 (deployed code) |
|---|---|---|
| Rest of Week | DeRozan / Dunn +0.589 (PRIOR-SEASON DRIVEN) | Tari Eason / Kevin Huerter +0.226 |
| Next 7 Days | Keldon Johnson / Jarrett Allen +0.566 | Derrick Jones Jr. / Jarrett Allen +0.656 |
| Next 14 Days | Keldon Johnson / Jarrett Allen +0.567 (FRAGILE) | Derrick Jones Jr. / Jarrett Allen +0.657 |
| Rest of Season Outlook | Isaiah Jackson / Kevin Huerter +0.412 | unchanged |

DeRozan / Dunn becomes DO NOT ADD (19.44 vs 23.21 FP/G, net −0.42), and all
11 SUPPORTED double reversals disappear. These are dated results; production
evaluates its own clock (see Acceptance).

### Pre-commit validation (2026-11-24 09:23–09:31 UTC)

| Suite | Result |
|---|---|
| Backend focused Phase-8 blend tests | 9 passed |
| Backend waiver files (3) | 332 passed |
| Full backend | 496 passed |
| Frontend unit | 78 passed |
| `tsc -b` / production build | pass / pass |
| Desktop Playwright (1440 × 1000, 1 worker) | 25 passed |

Backend on a disposable PostgreSQL on an internal-only network (source
read-only, removed afterwards); frontend in the Playwright image with no
network.

### Deployment

- **Commit** `d16607f` (09:32 UTC): 17 files (+1463/−304): 5 backend source,
  1 backend test, 3 frontend source, 2 frontend tests and 6 docs (including
  the previously uncommitted Phase 7.1 record). `git diff --check` clean;
  gitleaks v8.24.3: no leaks; no `.env` value in added lines; `qa-work/`
  untracked.
- **Backup:** `~/fantasy-gm-pre-phase8-20261124T100322Z.dump`.
  - `pg_dump -Fc`, 138,259,118 bytes, mode 0600, SHA-256 `3916bea5e00c…`.
  - `pg_restore --list`: 29 TABLE and 29 TABLE DATA. The archive's table
    inventory and COPY row counts equal production (29 tables, 79,433
    rows). Nothing restored.
- **Rollback tags:** tagged from the running containers' image IDs and
  proven by content.
  - `fantasy-basketball-gm-api:pre-phase8`: index `632ebb649d79`,
    linux/amd64 `d73d6ea9d814`. Its 104 `/app` files and `pip freeze`
    equal the running Phase 7.1 API (all 104 equal `7a02a4f`).
  - `fantasy-basketball-gm-frontend:pre-phase8`: index `38282253da1d`,
    linux/amd64 `6fcddd5f77a3`. Its 26 html files and both nginx configs
    equal the running frontend.
- **Build (serial):**
  - **API:** index `85efb1c1d659`, linux/amd64 `bf1ac64d5258`. All 105
    `/app` files equal `d16607f`, with model phase 8 and `PRIOR_GAMES = 2`.
  - **Dependency refresh:** the Phase 7.1 pip layer was no longer cached,
    so the build resolved `requirements.txt`'s ranges afresh on a refreshed
    `python:3.12-slim` (Python 3.12.16 unchanged). It picked up fastapi
    0.165.0 (was 0.162.6), pydantic 2.14.4, pydantic_core 2.50.5,
    SQLAlchemy 2.1.9 and patch releases of numpy, certifi, PyYAML,
    packaging, charset-normalizer and annotated-doc.
  - **Dependency validation:** before deploying, the exact image passed
    backend focused 9, waiver 332 and full 496 on its own `/app`. Its
    read-only Phase 8 shadow equals the validated environment's on all 100
    production payloads (0 differing paths).
  - **Frontend:** index `4ae81de3fb79`, linux/amd64 `aee2e001547c`. Its 25
    build files equal a production-env build of `d16607f` (`index-CTA7iDTo.js`,
    `index-DbIdjbVL.css`). `50x.html`, both nginx configs and nginx 1.27.5
    equal rollback. The bundle expects exactly `waiver-season-blend-phase8`.
- **Recreate:** `docker compose up -d --no-deps api frontend` ran
  10:31:53–10:32:31 UTC; health returned 200 at 10:32:37.
  - api `9bff7d62f56c` and frontend `f73cdcb3d4e9`, 0 restarts.
  - db `32ee446dd34c` and caddy `08198174d855` were not recreated. The db
    container dates from 2026-11-22 05:25, when the host's watchtower
    replaced it with a newer `postgres:16-alpine` image (data volume kept);
    that was not deployment work.
  - Clean startup with no migration. Five connection-refused lines fall in
    the boot window. nginx resolves `api` at the same IP (172.21.0.3), so
    no reload was needed.
- **Rollback, if ever needed:** retag both `pre-phase8` images as `latest`,
  then `docker compose up -d --no-deps api frontend`. No database rollback
  is needed.

### Acceptance (GET only, through Caddy with TLS validated)

- **Clock and freshness:** the saved Yahoo settings, player pool and rosters
  (2026-11-21 15:51–15:53) are past their 24-hour rule. Live boards
  therefore return INSUFFICIENT EVIDENCE with no candidates in every
  horizon, before and after the deploy. The weekly model production values
  and their buckets still show. Live decisions return after the user's next
  REFRESH WAIVER DATA; no refresh was run.
- **Captures:** live Phase 7.1 before (09:34–09:42) and Phase 8 after
  (10:33–10:41), 103 GETs each, all 200.
  - Each covers health, refresh status, 4 boards, 4 best-moves, all 16
    roster drops × 4 horizons and 28 exact pairs.
  - Every waiver response reported its model (phase 7.1, then phase 8).
- **Production = read-only shadow:**
  - The live Phase 7.1 baseline equals a Phase 7.1 shadow of the same data,
    and live Phase 8 equals the pre-deploy Phase 8 shadow, on all 100
    payloads.
  - The only differing path is the request stamp
    `data_quality.overall_score.as_of`, so there are 0 unexplained
    differences.

| Horizon | Live before → after | Weekly model production values |
|---|---|---|
| Rest of Week | INSUFFICIENT EVIDENCE → same; 16 drops CANNOT EVALUATE → same | 253 changed; DeRozan 25.91 → 19.44, Dunn 18.67 → 23.21 |
| Next 7 Days | same | same as Rest of Week |
| Next 14 Days | same | same as Rest of Week |
| Rest of Season Outlook | same | 270 unchanged |

- **DeRozan and Dunn in production:**
  - DeRozan 19.44 = (5 × 16.26 last 14 days + 8 × 18.61 earlier this season
    + 2 × 30.73 2025-26) / 15 (13% prior);
  - Dunn 23.21 = (5 × 14.70 + 9 × 28.51 + 2 × 20.66) / 16 (12% prior).

  No +0.589 PRIOR-SEASON DRIVEN move remains. On the same snapshot at its
  fresh instant, the deployed code makes the pair DO NOT ADD (−0.419815).
- **14 rookies without a prior** became comparable POTENTIAL TARGETs: the
  4-game minimum now counts every current-season game. Eligibility gates
  are unchanged.
- **Whole pool:** every weekly production value (270 players per horizon)
  was checked against an independent per-game extract of the snapshot.
  - Bucket game counts, FP/G and dates match; RECENT + EARLIER = every
    current-season game, with no overlap.
  - The prior counts as 2 games with share 2/(n + 2), monotone in games.
  - Each value is (sum FP + 2 × prior) / (n + 2).
  - 0 problems, 0 cross-surface inconsistencies and no Phase 7.1 basis
    code. Rest of Season Outlook keeps its 10-game shrinkage.
- **Exact pairs:** 28 pairs, 0 failures (live: impact only; deployed code at
  the fresh instant: impact = replacements = board = optimizer). All 88
  board cards and optimizer swaps equal the exact replacements-engine pair.
- **Desktop page** (1440 × 1000, one worker; Chromium pinned to the
  validated leaf key): 1 live test passed in 3.1 min.
  - Covered: all four horizons; BEST MOVES RIGHT NOW (the backend no-move
    state); OTHER GOOD OPTIONS with the 10 POTENTIAL TARGETS and their Phase
    8 values; COMPARE A SPECIFIC DROP (drop Kris Dunn ×4, drop Jarrett Allen
    in ROS).
  - VIEW DETAILS and Full Waiver List details (DeRozan), opened by keyboard,
    show the basis line, the exact arithmetic, three bucket lines and the
    prior counted as 2 games; focus returned.
  - axe 0 in 12 states; width 1440; 21 requests, all GET; no stale-model
    warning; REFRESH WAIVER DATA never clicked.
- **Database:** identical at 08:12, 09:09, 09:33, 10:10, 10:31, 10:32 and
  10:59 UTC (inventory, 79,433 rows, newest timestamps, 6 migrations, every
  write counter, the `yahoo_credentials` canary).
- **Logs after the deploy:**
  - the API logged 117 request timings, all GET 200, with 0 refresh,
    provider, OAuth, transaction or error lines;
  - nginx logged 795 requests, all GET, with 0 refresh POSTs.
  - The replaced containers' logs (09:08–10:32) were deleted with them. For
    that window the harness records every request this work sent (all GET),
    and the identical database snapshots exclude any refresh or write.
- **Remaining limitation:** `PRIOR_GAMES = 2` is observationally supported on
  the 2026-27 games so far; re-evaluate it with more season data.

# Phase 7.1 Compare-a-Drop Gate Fix — Deployed and Verified — 2026-11-21

**STATUS: DEPLOYED AND VERIFIED (2026-11-21 21:46 UTC; 13:46 PST); replaced
in production by Phase 8 at 2026-11-24 10:32 UTC.** Model
`waiver-decision-integrity-phase7.1` was deployed from commit `7a02a4f`
("fix: make waiver drop summaries gate-aware"; at the time not pushed, with
local `main` 2 ahead of `origin/main`).

- Only `api` and `frontend` were recreated.
- No migration, refresh, provider call, OAuth, Yahoo transaction or data
  change came from this work. No weight, threshold, blend, schedule, gate or
  drop policy changed, and no player-specific rule exists.
- Full evidence: `qa-work/2026-11-21-phase71-deploy/deployment-acceptance.md`
  (local, untracked).

### Deployment

- **Gate:**
  - HEAD `a9a0367`; the 8 code and test files matched the Phase-7.1 report
    and were last edited before its validation.
  - The snapshot was unchanged since the 7.1 shadow (29 tables, 79,433
    rows; identical counts, newest timestamps, write counters and
    migrations).
  - Backend: focused 18, waiver files 328, full 492 (disposable PostgreSQL
    on an internal network).
  - Frontend: unit 76/76, `tsc -b` and build pass (`index-uEroGjal.js`,
    `index-DmobFuB1.css`).
  - Desktop Playwright: focused 2/2, full 24/24 (1440 × 1000, one worker).
- **Commit** `7a02a4f`: 13 files (+912/−74): 3 backend, 5 frontend, 5 docs.
  - `git diff --check` clean; gitleaks v8.24.3: no leaks.
  - The only `.env` value in added lines is the league key, already
    committed in 13 files. `qa-work/` stays untracked.
- **Backup:** `~/fantasy-gm-pre-phase71-20261121T213725Z.dump`.
  - `pg_dump -Fc`, 138,259,118 bytes, mode 0600, SHA-256 `db6678cddd2c…`.
  - `pg_restore --list`: 176 TOC entries, 29 TABLE and 29 TABLE DATA. The
    archive's table inventory and COPY row counts equal production (29
    tables, 79,433 rows). Nothing restored.
- **Rollback tags:** matched to the running containers' platform manifests
  and proven byte-identical.
  - `fantasy-basketball-gm-api:pre-phase71`: index `01d2e3974298`,
    linux/amd64 `7c71acc08224`. Its 104 `/app` files and `pip freeze` equal
    the running Phase-7 API.
  - `fantasy-basketball-gm-frontend:pre-phase71`: index `5316049dbaf8`,
    linux/amd64 `bff62074095f`. Its 26 html files and both nginx configs
    equal the running frontend.
- **Build (serial):**
  - **API:** index `632ebb649d79`, linux/amd64 `d73d6ea9d814`. All 104
    `/app` files equal `7a02a4f`, and the model is phase 7.1. Versus
    rollback only `contracts.py`, `service.py` and `tests/test_waivers.py`
    differ; `pip freeze` is unchanged.
  - **Frontend:** index `38282253da1d`, linux/amd64 `6fcddd5f77a3`. Its 25
    build files equal the validated production-env build, `50x.html` is
    nginx's stock page, and both nginx configs equal rollback. The bundle
    expects exactly `waiver-decision-integrity-phase7.1`.
- **Recreate:** `docker compose up -d --no-deps api frontend` ran
  21:46:03–21:46:32 UTC; health returned 200 at 21:46:41.
  - api `687d0c98b3d0` and frontend `7906f01c3502`, 0 restarts.
  - db `c41db6714843` and caddy `08198174d855` were not recreated.
  - Clean startup with no migration. Five connection-refused lines fall in
    the boot window. nginx resolves `api` at the same IP (172.21.0.3), so no
    reload was needed.
- **Rollback, if ever needed:** retag both `pre-phase71` images as `latest`,
  then `docker compose up -d --no-deps api frontend`. No database rollback is
  needed.

### Acceptance (GET only, through Caddy with TLS validated)

- **Captures:** live Phase 7 before the deploy and Phase 7.1 after it, on the
  same snapshot, 97 GETs each, all 200. Each covers health, refresh status, 4
  boards, 4 best-moves, all 16 roster drops × 4 horizons and 22 exact pairs.
  Every waiver response reported its model (phase 7, then phase 7.1).
- **Global BEST MOVES unchanged:** the best-moves payloads are equal path for
  path apart from request-time stamps (`generated_at`, `model_version`,
  `data_quality.overall_score.as_of`). The no-drop boards differ only by the
  new `drop_summary: null`.

| Horizon | Best move | Net (raw = reconciled) | Verdict and intent | Supported moves |
|---|---|---|---|---|
| Rest of Week | DeMar DeRozan / Kris Dunn | +0.589356 | SUPPORTED ADD, STREAM | 28 |
| Next 7 Days | Keldon Johnson / Jarrett Allen | +0.565944 | SUPPORTED ADD, STREAM | 44 |
| Next 14 Days | Keldon Johnson / Jarrett Allen | +0.567050 | SUPPORTED ADD, TWO-WEEK STREAM | 14 |
| Rest of Season Outlook | Isaiah Jackson / Kevin Huerter | +0.412447 | SUPPORTED ADD, LONGER-TERM ADD | 6 |

- **64 drop × horizon views: 0 violations** (21 checks each):
  - 0 views where a DO NOT ADD pair is the answer, and 0 where WATCH
    outranks a supported replacement;
  - every best valid replacement is SUPPORTED ADD and equals
    `best_add_for_team_id`; the summary decision equals the roster label;
  - 0 INSUFFICIENT EVIDENCE results; the raw block appears exactly when the
    raw leader outranks the answer and equals its card;
  - every card, verdict and `top_measured_candidate_id` is unchanged.
- **Before → after:** Phase 7 INSUFFICIENT EVIDENCE 25, HOLD 20, ADD 7,
  STREAM 8, WATCH 4 → Phase 7.1 HOLD 33, CANNOT EVALUATE 12, ADD 7, STREAM 8,
  WATCH 4. Exactly 25 views changed:
  - the 13 refuted-leader views (Rest of Season 8, Next 14 Days 3, Next 7
    Days 2) now read HOLD <drop>;
  - the 3 injury-slot drops (Stephen Curry, Lauri Markkanen, RJ Barrett)
    read CANNOT EVALUATE in all 4 horizons.
- **Raw leader ≠ answer in 41 views:** 13 HOLD with a refuted positive DO
  NOT ADD raw leader, 20 HOLD where every comparison is nonpositive, and 8
  supported answers with a higher-raw WATCH.
- **Jarrett Allen (Rest of Season):** the answer is **HOLD Jarrett Allen**.
  Isaiah Jackson appears only as the HIGHEST RAW MODEL COMPARISON: DO NOT
  ADD, raw +1.025611, reconciled −0.387882, with the gate arithmetic (66 ×
  22.6 = 1490.9 vs 63 × 30.3 = 1908.3 Yahoo points).
- **Exact pairs (22, every answer category in every horizon):** card =
  impact, drop fixed, summary = impact; best move = board = replacements =
  impact.
- **Desktop page** (1440 × 1000, one worker, serial): 1 live test passed in
  6.0 min.
  - Covered: every section and horizon; HOLD, BEST VALID REPLACEMENT, WATCH
    and CANNOT EVALUATE answers; the subordinate raw block ("not a
    recommendation", dashed, below the answer) with raw and reconciled net
    and the reason.
  - Analyze opened the exact raw pair (Jackson/Allen) and the exact valid
    pair (DeRozan/Dunn).
  - Keyboard focus returned for 3 dialogs; axe: 0 violations in 15 states;
    page width 1440 everywhere; 23 requests, all GET.
  - The first attempt failed on host capacity, not the product. Chromium's
    start pushed the API back into swap, the page's board read took 44.5 s,
    and its queued best-moves read hit nginx's 60 s (504; the API cancelled
    it). The retry, after pressure settled, passed. No timeout changed.
- **Database:** identical at 20:58, 21:19, 21:45 and 22:21 UTC (inventory,
  rows, newest timestamps, 6 migrations, every write counter, the
  `yahoo_credentials` canary).
- **Logs since 20:40 UTC:** nginx 2,740 requests, 0 non-GET; the API logged
  211 request timings, all GET; 0 refresh jobs; 0 Yahoo, NBA, Fantrax,
  OAuth or transaction activity.
- **Admission** (unchanged; one slot): 116 deployed reads with 0
  overlapping executions; 8 queued reads each waited for the preceding read;
  the abandoned read was cancelled at disconnect (`status=499`).

# Phase 7.1 Compare-a-Drop Gate Fix — Implemented and Validated Locally — 2026-11-21 (deployed later that day; see above)

**Historical record.** At the time of this section production still ran
Phase 7 (below), and the Phase 7.1 fix (model
`waiver-decision-integrity-phase7.1`) was in the working tree on top of
`a9a0367`, neither committed nor deployed. Full evidence:
`qa-work/2026-11-21-phase71-fix/phase71-report.md` (local, untracked).

- **Root cause:** for an explicit drop, `build_board` named the raw-net leader
  "Top measured option" and derived the result from it. A pair refuted by the
  Phase-7 gate keeps its positive raw net, so the header could name a DO NOT
  ADD pair and read INSUFFICIENT EVIDENCE instead of HOLD.
- **Fix:** a backend `drop_summary` built from the cards' own gated decisions
  in their canonical order, with the roster label's categories:
  - BEST VALID REPLACEMENT (first supported pair);
  - else WATCH (never promoted);
  - else **HOLD <drop>**;
  - else CANNOT EVALUATE.

  The raw leader is shown only as a subordinate "HIGHEST RAW MODEL
  COMPARISON — not a recommendation", with verdict, raw and reconciled net,
  the gate reason and an exact-pair Analyze. The no-drop board, optimizer,
  scoring and gates are unchanged.
- **Validation:**
  - Backend: waiver files 328 and full suite 492 pass.
  - Frontend: unit 76/76, `tsc -b` and build pass.
  - Desktop Playwright: 24/24 (1440 × 1000, one worker).
  - The new tests failed before the fix for the stated reasons.
- **Read-only acceptance (current snapshot, unchanged; SELECT only):**
  - Scope: all 16 roster drops × 4 horizons = 64 views, run through Phase 7
    and 7.1 with the same pinned clock.
  - 0 invariant violations, 0 DO NOT ADD answers, 0 WATCH-over-supported
    answers.
  - The 13 refuted-leader views now read HOLD. The 3 injury-slot drops read
    CANNOT EVALUATE in all horizons (12 views).
  - Every supported or WATCH answer, every card, best moves and the
    no-drop boards are unchanged. The only no-drop difference is the new
    `drop_summary: null`.
  - Rest of Season DROP Jarrett Allen reads **HOLD Jarrett Allen**. Isaiah
    Jackson stays visible as raw +1.025611, reconciled −0.387882, DO NOT ADD,
    with the gate arithmetic.

# Phase 7 Waiver Decision Integrity — Deployed and Verified — 2026-11-21 (superseded by Phase 7.1 at 21:46 UTC; see above)

**STATUS: DEPLOYED AND VERIFIED (2026-11-21 16:36 UTC; 08:36 PST); replaced
by Phase 7.1 at 21:46 UTC.** Model `waiver-decision-integrity-phase7` was in
production from 16:36 to 21:46 UTC. It was deployed from
commit `a9a0367` ("feat: enforce waiver decision integrity"; not pushed).

- Only `api` and `frontend` were recreated.
- No migration, refresh, provider call, OAuth, Yahoo transaction or data
  change came from this work.
- Full evidence: `qa-work/2026-11-21-phase7-deploy/deployment-acceptance.md`
  (local, untracked).

### Snapshot

The user's own REFRESH WAIVER DATA (job `043e463ebb71`, 15:50:56–15:58:54
UTC, from Windows Chrome) replaced the audit's 09:37 snapshot before this
deployment session began.

- Imports are now 15:53:01 (Yahoo) and 15:56:41 (NBA). Games run through
  2026-11-20 in both.
- Acceptance therefore compared production against a read-only Phase-7
  shadow of this snapshot, not the audit's counts.

### Deployment

- **Gate:**
  - Source items A–G were verified.
  - Running Phase 6 equaled `2d48784`: 102 `.py` files.
  - 29 tables and 6 migrations, with no migration or model change.
  - The db container's 11-19 05:23 recreation was watchtower's
    `postgres:16-alpine` update (clean shutdown, same data directory).
  - Watchtower's next run is 2026-11-22 05:24 UTC; it cannot pull these
    local images.
- **Tests (disposable infrastructure):**
  - Backend: waiver files 320 and full 484 passed.
  - Frontend: `tsc -b`, unit 73/73 and `npm run build` pass.
  - Desktop Playwright: 23/23 (1440 × 1000, one worker).
- **Backup:** `~/fantasy-gm-pre-phase7-20261121T162834Z.dump`.
  - 138 MB, mode 0600, SHA-256 `10fc00d8c7ec…`.
  - `pg_restore --list`: 176 TOC entries and 29 TABLE DATA. The archive's
    COPY row counts equal the live database (29 tables, 79,433 rows).
- **Rollback tags:** matched to the running containers' platform manifests
  and proven byte-identical.
  - `fantasy-basketball-gm-api:pre-phase7`: index `e96e4be1b377`,
    linux/amd64 `cdbb6a1f36dc`. Its 103 `/app` files and `pip freeze` equal
    the running container.
  - `fantasy-basketball-gm-frontend:pre-phase7`: index `8e4328dc73c1`,
    linux/amd64 `2b268cbb7a53`. Its 26 html files and both nginx configs
    equal the running container. The running frontend's recorded index
    `a7f00cb72046` no longer resolved.
- **Build (serial):**
  - **API:** index `01d2e3974298`, linux/amd64 `7c71acc08224`. All 104
    `/app` files equal `a9a0367`, and the model is phase 7.
  - **Frontend:** index `5316049dbaf8`, linux/amd64 `bff62074095f`. Its 25
    html files equal the validated production-env build
    (`index-CDtRcvSk.js`, `index-DD2IEjtO.css`), and the nginx config is
    unchanged.
- **Recreate:** `docker compose up -d --no-deps api frontend` ran
  16:36:07–16:36:38 UTC; health returned 200 at 16:36:45.
  - api `8d5ef901e996` and frontend `ec3dfae7f540`, 0 restarts.
  - db `c41db6714843` and caddy `08198174d855` were not recreated.
  - Clean startup with no migration. nginx resolves the new API; 4
    connection-refused lines fall in the boot window.
- **Rollback, if ever needed:** retag both `pre-phase7` images as `latest`,
  then `docker compose up -d --no-deps api frontend`. No database rollback is
  needed.

### Acceptance (GET only, through Caddy with TLS validated)

**Live Phase-6 baseline (same snapshot):** 24 GETs, all 200. It featured
Rest of Season **Isaiah Jackson / Jarrett Allen +1.025611**. Supported
moves were 28, 48, 47 and 135 (Rest of Week, Next 7, Next 14, Rest of
Season).

**Deployed Phase 7:** 24 GETs, all 200, all phase 7.

- It equals the pre-deploy shadow path for path. The only differences are
  request-time stamps and the router's `team_name`.
- Board = optimizer = replacements = impact (with and without the drop),
  explanation and verdict included, in every horizon.

| Horizon | ADD / DROP | Net | Verdict and disclosures | Supported moves |
|---|---|---|---|---|
| Rest of Week | DeMar DeRozan / Kris Dunn | +0.589 | SUPPORTED ADD; PRIOR-SEASON DRIVEN (blend math shown); Dropping is permanent | 28 |
| Next 7 Days | Keldon Johnson / Jarrett Allen | +0.566 | SUPPORTED ADD (STREAM); window +28.6 FP; Dropping is permanent | 44 |
| Next 14 Days | Keldon Johnson / Jarrett Allen | +0.567 | SUPPORTED ADD (TWO-WEEK STREAM); **FRAGILE** +2.4 FP | 14 |
| Rest of Season Outlook | **Isaiah Jackson / Kevin Huerter** | **+0.412** | SUPPORTED ADD (LONGER-TERM ADD) | 6 |

- **Isaiah Jackson / Jarrett Allen** in Rest of Season is now **DO NOT ADD**
  on every surface.
  - 66 × 22.59 = 1490.9 vs 63 × 30.29 = 1908.3 Yahoo fantasy points.
  - Model net +1.026; reconciled −0.388.
  - Allen is "Keep: no supported replacement", and Luka Dončić is "Keep" in
    every horizon.
- **OTHER GOOD OPTIONS:** every card gives its verdict and exact drop (or
  "No supported drop").
- **Labels:** 0 "n/a" strings, and no lineup gap counts more dates than the
  window has.
- **Desktop page** (1440 × 1000, one worker, serial): 1 live test passed.
  - Covered: all four horizons, every section, VIEW DETAILS and Compare a
    Specific Drop.
  - Keyboard focus returned for 4 dialogs.
  - axe: 0 violations in 9 states.
  - Page width 1440 everywhere; 17 requests, all GET.
- **Database:** identical before the baseline, before the deploy and after
  acceptance.
  - All 29 tables' row counts and newest timestamps, `schema_migrations`.
  - Every insert/update/delete counter, including the `yahoo_credentials`
    canary.
- **Logs:**
  - nginx logged 0 non-GET requests since the session began.
  - The new API logged 35 timings, all GET, with 0 refresh jobs and 0
    provider or OAuth mentions.
- **Admission:** still serializes heavy reads (8 queued) and cancelled an
  abandoned read (`status=499`).
- **Payloads:** board +27–31% (about 1.9 MB), transactions +25–27%. No
  slowdown: 22 serial reads took 141 s, vs 166 s on Phase 6.

### Residual defect found in acceptance (fixed by Phase 7.1, deployed 21:46 UTC)

Compare a Specific Drop's "Top measured option" and result line use the raw
net, not the Phase-7 gate. In 13 of 64 drop × horizon views, the line names
a refuted pair and reads INSUFFICIENT EVIDENCE instead of "HOLD <drop>":

- Rest of Season: 8 views;
- Next 14 Days: 3 views;
- Next 7 Days: 2 views.

Example: drop Jarrett Allen in Rest of Season reads "Top measured option:
Isaiah Jackson · model-ranked, limited evidence", while its cards say DO NOT
ADD.

No recommendation surface was affected. Phase 7.1 (above) fixed it and was
deployed and verified at 21:46 UTC: these 13 views now read "HOLD <drop>",
with the refuted pair shown only as the subordinate highest raw model
comparison.

# Waiver Decision-Integrity Audit — Implemented and Validated Locally — 2026-11-21 (deployed later that day; see above)

**Historical record.** At the time of this section the deployed application
was still model `waiver-horizon-evidence-phase6`, featuring **ADD Isaiah
Jackson / DROP Jarrett Allen (+1.03)** in Rest of Season Outlook.
Model `waiver-decision-integrity-phase7` then existed only in the worktree, on top
of `2d48784`, uncommitted. No migration is needed. See the
[2026-11-21 session record](../sessions/2026-11-21.md) and
`qa-work/2026-11-21-waiver-audit/` (findings matrix, before/after traces,
acceptance and screenshots).

### What changed (worktree)

- **Explanation-consistency gate.** When an add loses measured production,
  the positive net must not rest on a claim that fails in the league's own
  scoring unit:
  - schedule: window Yahoo points = games × the same-basis FP/G;
  - fit: requires a starting-slot gain;
  - opportunity: never reconcilable.

  A refuted pair is DO NOT ADD on every surface. Weights, thresholds and
  gates are otherwise unchanged; there are no player-specific rules.
- **Per-pair explanation** with exact contributions, both players' production
  basis and blend math, window points, checks and tradeoffs (FRAGILE,
  PRIOR-SEASON DRIVEN, drop permanence).
- **Transaction verdicts:** SUPPORTED ADD, WATCH ONLY, NEAR TIE, DO NOT ADD,
  CANNOT EVALUATE.
- **OTHER GOOD OPTIONS:** an exact drop (or "No supported drop") and a
  verdict on every card.
- **Labels:** evidence by dimension, form reasons instead of "n/a", lineup
  gaps in dates, and distinct roster labels.

### Read-only acceptance on the 09:37 UTC snapshot (new code, not live)

| Horizon | Live (phase 6) | Worktree (phase 7) |
|---|---|---|
| Rest of Week | DeRozan / Dunn +0.589 | Same pair, SUPPORTED ADD; flagged PRIOR-SEASON DRIVEN and drop-permanent |
| Next 7 Days | Keldon Johnson / Jarrett Allen +0.566 STREAM | Same; window check +28.6 FP; drop permanence shown |
| Next 14 Days | Keldon Johnson / Jarrett Allen +0.567 STREAM | Same; **FRAGILE** (+2.4 FP, less than one game) |
| Rest of Season Outlook | Isaiah Jackson / Jarrett Allen +1.026 ADD | **Isaiah Jackson / Kevin Huerter +0.412 ADD**; Jackson/Allen is DO NOT ADD (−0.39 without the refuted schedule claim) |

- Supported positive moves: 24 → 24, 42 → 39, 40 → 12 and 124 → 4.
- Board = optimizer = replacements = impact (with and without the drop),
  including the explanation, in all four horizons.
- The read runs were SELECT only, with no provider call or write.

### Validation (disposable infrastructure)

- **Backend:** waiver files 307 → 320 passed; full suite 471 → 484.
- **Frontend unit:** 63 → 73 passed.
- **Desktop Playwright** (1440 × 1000, one worker): 22 → 23 passed.
- **Build:** `npm run build` passes.
- **Real payloads rendered offline:** 4/4.
- **New tests fail on `2d48784`** for the defect they encode.

# Waiver Heavy-Read Admission Fix — API-Only Deployment Verified — 2026-11-15

**STATUS: DEPLOYED AND VERIFIED (2026-11-15 14:50 UTC; 06:50 PST).** The
validated heavy-read admission fix (`admission.py` and its `router.py`
wiring) is live. This was an API-only deployment:
- No frontend rebuild or recreate, and no `db` or `caddy` change.
- No migration, refresh, provider call, OAuth, Yahoo transaction, commit or
  push.

The model is unchanged (`waiver-horizon-evidence-phase6`), and so are the
recommendations: all 24 captured responses are identical before and after.
The Waiver Center is PC-only; the browser target is 1440 × 1000.

### Release contract (from the worktree and its tests)

- One heavy waiver read (board, best moves, replacements, impact) runs at a
  time.
- The slot resolves before any database dependency, so a queued read holds
  no PostgreSQL session.
- A read whose client disconnects, queued or loading, is cancelled and logged
  `status=499`.
- `request_timing` and `Server-Timing` gain a `queue` phase. Refresh routes
  are not gated.

### Pre-deployment gate

- The running API differed from the worktree only in `admission.py` (new)
  and `router.py`. The other 69 app files were byte-identical.
- Every recommendation definition is AST-identical:
  - pairing and ordering: `evaluate_pair`, `pair_order`,
    `replacement_order`, `build_board`, `analyze_transactions`;
  - comparison: `compare`, `compare_no_drop`, `enrich`, `classify_action`;
  - gates: `transaction_blockers`, `sample_gap`, `status_gap`,
    `classify_availability`, the invariant asserts;
  - scoring: `aggregate`, `production`, `scoring_fields`;
  - constants and capacity: `MODEL_VERSION`, `ACTION_RANK`, roster capacity.
- `decision_priority` (set in `build_board`) and the sample evaluator
  (`sample.py`) live in byte-identical files.
- The fix files were last modified at 12:39-12:41 UTC, before the earlier
  validation (waiver suites 307, full backend 471, repository desktop 22/22).
- Re-run against the exact hashes: 10/10 focused tests. These are the 4
  admission regressions, including the real-PostgreSQL cancellation, and 6
  select-only, provider-free and timing tests.

### Deployment (14:42-14:51 UTC)

- **Baseline (read-only):**
  - Health 0.010 s; refresh status 0.055 s. All 9 sources were current from
    the user's own 14:29-14:30 REFRESH (job `4b89b6dd72c9`).
  - Rest of Week board 4.9 s, best moves 6.7 s.
  - 24 serial captures, all 200: four horizons × board, best moves, impact
    with and without the drop, and two drop lists.
  - Database at 14:42:21: 29 tables, 80,720 rows, 6 migrations, no active or
    blocked session.
- **Backup:** `~/fantasy-gm-pre-waiver-reliability-20261115T144551Z.dump`
  (`pg_dump -Fc`, 138 MB, mode 0600, no overwrite). `pg_restore --list`
  reads it (29 TABLE DATA entries); the inventory and all 29 COPY row counts
  equal the live database. Nothing was restored.
- **Rollback tag:** `fantasy-basketball-gm-api:pre-waiver-reliability`.
  - Index `fe0c214a1cb1`; linux/amd64 manifest `a3e52763ba8b`, which equals
    the old container's `ImageManifestDescriptor`.
  - Its `/app` (198 files) and `pip freeze` are identical to the old
    container. The old container's recorded index `2e0fb38b2e4b` no longer
    resolves under the containerd store.
- **Build:** `docker compose build api` (21 s) produced index
  `48035cedfb61` (linux/amd64 `da05adc29d45`).
  - Versus the old image, only `admission.py`, `router.py` and
    `tests/test_waivers.py` differ. `pip freeze`, `migrations.py` and every
    ORM `models.py` are identical.
  - App and test source equal the worktree (102 files).
- **Recreate:** `docker compose up -d --no-deps api` ran 14:50:04-14:50:22;
  health returned 200 at 14:50:31.
  - 502s appeared only in the ~25 s stop/boot window (4 health probes, 6
    observer polls).
  - The new container `bdf329394c93` kept its compose-network IP, so nginx needed no
    reload.
  - frontend `3b6a562ed6d4` (started 02:36:31), db `d6a02fc4fe35` and caddy
    `08198174d855` are unchanged.
- **Rollback, if ever needed:** retag `pre-waiver-reliability` as `latest`
  and recreate only `api`. No database rollback is needed.

### Acceptance (GET only)

- **Model and source:** the model is `waiver-horizon-evidence-phase6` on
  board, best moves, replacements and impact, and the running source equals
  the worktree (71 files).
- **No recommendation change:** the same 24 paths, re-fetched serially after
  the deploy (3.6-8.1 s each, queue 0), are identical apart from request
  stamps.
  - Board = optimizer and the exact pair (optimizer = board = replacements =
    impact) hold in all four horizons.
  - All 8 drop lists are ordered by tier, net, then ID. The drop stays fixed
    and WATCH stays WATCH.
  - Safety and NO CURRENT YAHOO DESIGNATION semantics are unchanged.
- **Decisions** on the 14:29 snapshot (roster 13/13, IL 3/3, adds 4 of 4,
  priority 4th):

  | Horizon | Add / drop | Decision | Net |
  |---|---|---|---|
  | Rest of Week | Bilal Coulibaly / Kris Dunn | ADD (STREAM) | +0.163 |
  | Next 7 Days | Coulibaly / Kevin Huerter | STREAM | +0.625 |
  | Next 14 Days | Brayden Burries / Huerter | STREAM (TWO-WEEK) | +0.944 |
  | Rest of Season Outlook | Ja'Kobe Walter / Huerter | ADD (LONGER-TERM) | +0.128 |

- **Admission (bounded load, through Caddy):**
  - **Running plus queued:** R1 (Rest of Season board) took 7.9 s with no
    queue; R2 (best moves) waited 6,867 ms, then loaded. Exactly one API
    transaction existed throughout, so the queued read held none. Threads
    stayed at 7.
  - **Client abort:** R3's client aborted at 2.5 s (the browser-abort path,
    not the nginx timeout). The API logged `status=499 total_ms=2516
    load_ms=2508`: it stopped 16 ms after the client left, before analysis,
    and its transaction disappeared.
  - **Release and recovery:** R4, queued behind R3, got the slot after
    1,941 ms. R5 returned 200 with no queue; nothing leaked.
  - **All 62 heavy reads since the deploy:** the largest overlap between two
    work intervals is 6.7 ms (the slot handoff), so at most **1** heavy
    analysis ran at a time. 16 reads queued, the longest for 7.66 s.
  - **Host:** the API had 0 swap and 0 new major faults, with RSS ≤ 278 MB.
    IO pressure stayed ≤ 12.6% and memory "full" ≤ 0.64%; observer polls
    stayed 200.
- **Desktop 1440 × 1000 (4/4):** one page load sends 3 API reads. Refresh
  status took 0.13 s and the board 4.8 s; best moves took 10.2 s after
  waiting 4.7 s for the server slot.
  - The browser had 2 heavy requests in flight, and the server analyzed them
    one at a time. There were no duplicates or aborts, and every read
    returned 200.
  - All panels, four horizons and the exact-pair dialogs pass.
  - Compare a Specific Drop ranks supported moves before a higher-net WATCH
    in two cases: DeMar DeRozan +0.419 under three ADDs for drop Dunn, and
    Julian Reese +0.668 under three STREAMs for drop Huerter.
  - axe 0, `scrollWidth` 1440, focus returns, GET only.
- **Database:** identical to the 14:42 baseline, including every write
  counter and `yahoo_credentials`.
  - 0 refresh POSTs, refresh-job lines, provider calls, OAuth actions or Yahoo
    transactions.
  - The 850 external observer GETs are recorded separately.

### Remaining limits

- **The host hardware is unchanged:** a 7.3 GB shared host, with swap on the
  single rotational system disk. The fix bounds abandoned and overlapping
  waiver work, but it does not stop the kernel from swapping an idle API, and
  it does not make a cold first read fast.
  - A cold read can still exceed nginx's 60 s. Its work now stops and nothing
    piles up.
  - Starting the Playwright browser still pushes host IO pressure to ~68%.
- **Serialization costs latency:** a page's second heavy read waits for the
  first (best moves ~10 s instead of ~7 s warm).
- **Known limits from the review:**
  - Analysis already in a worker thread finishes after a cancel, so it can
    overlap the next read by up to ~2 s.
  - A request-task cancellation that arrives during cleanup can be absorbed.

# Waiver Center Reliability Incident — Recovered; Heavy-Read Admission Fix Validated Locally (NOT Deployed) — 2026-11-15

> **Superseded (same day):** the admission fix described below as "not
> deployed" was deployed API-only at 14:50 UTC and verified; see the
> current-state section above. This section is kept as the incident record.

**STATUS: RECOVERED (2026-11-15 11:35-12:50 UTC; 03:35-04:50 PST).** The
deployed Waiver Center answers every read again, and its evidence is current.
The user's own REFRESH WAIVER DATA click succeeded at 11:20:50 UTC. The cause
was host capacity, amplified by two code-level reliability gaps. A fix for
those gaps is implemented and validated in the worktree but **not deployed**.
Production is unchanged:
- Same containers and images: api `cdd738a1899e` (image `2e0fb38b2e4b`),
  frontend `3b6a562ed6d4` (`a7f00cb72046`), `db` and `caddy`.
- Model `waiver-horizon-evidence-phase6`.
- No API restart, migration, OAuth, Yahoo transaction, commit or push.
- No refresh or provider call by this investigation.

The Waiver Center is now **PC-only**: validation and acceptance use desktop
1440 × 1000 only, and earlier mobile results remain historical evidence.

### What the user saw (11:09-11:21 UTC)

- **11:09:43:** Windows Chrome loaded `/waivers`. The page sent refresh
  status, board and best moves at once, then board and best moves twice more
  (reload/retry).
  - Refresh status hit its 30 s client limit: "Saved-evidence freshness could
    not be read".
  - Board and best moves got nginx 504 at 60 s: WAIVER ANALYSIS TIMED OUT,
    and BEST MOVES was withheld.
- **11:10:25-11:16:48:** REFRESH WAIVER DATA was clicked 5 times, and every
  POST timed out in the browser (499). The API processed them later:
  - Job `a8e4f09d6c16` failed at its first stage with a database-connection
    TimeoutError and persisted nothing. Its record was replaced by the next
    job, so its request count is unknown.
  - Job `68a294158101` (requested 11:16:18) **succeeded** at 11:20:50: all 10
    stages verified, 46 read-only Yahoo requests, 0 practice-league requests,
    `yahoo_transactions_executed = 0`. The job renewed the stored Yahoo access
    token as usual (`yahoo_credentials.updated_at` 11:16:19).
- The refresh was legitimately needed: Yahoo evidence had gone stale at
  08:31 UTC. The browser never saw the success because the POST had already
  timed out client-side.

### Root cause (proven)

| Class | Finding | Evidence |
|---|---|---|
| A. RAM exhaustion / swap | Swap **yes**, RAM exhaustion **no** | From 03:32 to 11:09 the API only served external observer polls. By 10:50 its working set was ~25 MB with **~329 MB in swap** (~93%). `MemAvailable` stayed 3.5-4.3 GB throughout, and memory PSI "full" stayed mostly under 10% in the stall. |
| B. Rotational-disk IO | **Yes** | `sdb` (HGST 2.5" laptop disk holding root and `/swap.img`) ran at 93-98% util and 150-260 reads/s. In 11:09-11:21 the API had **78,229 major faults / 957 MB read** and the DB 12,321; every other container was negligible (cAdvisor via Prometheus). API swap drained 330 → 3 MB over ~10 minutes (~0.5 MB/s), while API CPU stayed at 1-7%. |
| C. API worker wedged | **Yes** (consequence) | Single uvicorn worker. The event loop froze while threads page-faulted, so external observer polls returned 504 for ~7 minutes. Up to 8 waiver requests were in flight. |
| D. Abandoned reads keep running | **Yes** | Board and best-move reads aborted at 11:09:57 (499) finished 200 to nobody after **393 s and 472 s**, and another after 360 s. The API also started reads whose clients were already gone. |
| E. PostgreSQL blocking | **No** | No locks, blocked queries or idle-in-transaction sessions. A secondary symptom: slow and abandoned reads filled the 5-connection pool, so new asyncpg connects timed out (seven 500s). |
| F. nginx upstream/DNS | **No** | Upstream timeouts only; nginx resolved the API. |
| G. Refresh-status endpoint | Victim | The database-only read could not answer within the 30 s client limit while the process stalled. |
| H. Application regression | **No** | The running API source equals the validated worktree (70 files), and the slow phase is the unchanged context load. |
| I. Combination | **Yes** | A (swap) + B + C + D, with E and G as symptoms. |

The prior 2026-11-15 03:04-03:32 stall had the same mechanism. This session's
own VS Code server start-up (an extension host of ~650 MB, 11:35-11:39)
briefly pushed host memory PSI to 70% and the API back to 147 MB of swap.

### Reproduction with one normal desktop page load (12:10-12:18 UTC)

Starting the Playwright browser pushed the API back into swap (148 → 263 MB).
One page load at 1440 × 1000 then reproduced the incident exactly:
- Refresh status 499 at 30 s; board and best moves 504 at 60 s.
- Both abandoned reads completed 200 **441 s** later.
- A second test's page load got 500s (database connect TimeoutError, pool
  exhausted).
- Observer polls returned 504 from 12:12:37 to 12:17:55.

The browser was stopped, nothing more was sent, and the API recovered by
itself (health 0.12 s at 12:18:07; no restart).

Measured cost of one cold read: an internal board read (no proxy cutoff) took
**71.8 s** (load 69.5 s) with 16,446 major faults (~230/s). Warm, it takes
4-7 s.

### Recovery and verification (serial, GET only)

- **No restart:** health answered in 0.16 s at 11:38, so the API was slow,
  not wedged.
- **Freshness:** every source is current from job `68a294158101`:
  - Yahoo: league 11:17:53, players and rosters 11:18:11 UTC; current until
    2026-11-16 11:17 UTC.
  - NBA: 11:19:23 UTC; current until 2026-11-22.
  - No refresh was run here.
- **Serial reads through Caddy (warm):**
  - Health 0.02 s and refresh status 2.9 s.
  - Board / best moves: Rest of Week 7.1 / 5.1 s, Next 7 Days 5.6 / 4.2 s,
    Next 14 Days 4.9 / 4.4 s, Rest of Season Outlook 20.5 / 6.0 s.
  - All 200, with no stuck request.
- **API acceptance (68 + 4 serial GETs, no retries, 0 failures).** The fresh
  data changed the answers. Roster 13/13, IL 2/3, adds 2 of 4, priority 4th.
  Every horizon is MOVE Jarrett Allen TO IL, THEN ADD:

  | Horizon | Add | Decision | Intent | Net |
  |---|---|---|---|---|
  | Rest of Week | Kevin Huerter | ADD | STREAM | +2.223 |
  | Next 7 Days | Cam Spencer | STREAM | STREAM | +2.821 |
  | Next 14 Days | Brayden Burries | ADD | TWO-WEEK STREAM | +3.136 |
  | Rest of Season Outlook | Ja'Kobe Walter | ADD | LONGER-TERM ADD | +2.391 |

  - **Board = optimizer:** in every horizon. Optimizer = board = impact on
    candidate, comparison, weights, sample, role, schedule, status,
    availability and the IL step.
  - **Exact pair with a drop:** replacements = impact for an explicit drop
    in every horizon.
  - **All 60 Compare-a-Specific-Drop lists:** tier, then net, then ID; the
    drop stays fixed, the first supported row is the best add, the top
    measured option is listed, WATCH stays WATCH, and supported rows always
    have positive net.
  - **Safety:**
    - 294 eligible and 276 `EXCLUDED_STATUS`.
    - No manager, other-team (159) or O/OFS/NA player is an add or target,
      and unresolved identities never support a move.
    - Jrue Holiday's impact returns 409, and the 3 OFS players are excluded.
- **Desktop 1440 × 1000 (4/4, one project, one worker, through Caddy/TLS):**
  - One page load sends exactly 1 refresh-status, 1 board and 1 best-move
    read (max 3 concurrent, 2 heavy). There are no duplicates, so StrictMode
    adds none in production.
  - WAIVER DATA IS CURRENT, TEAM SITUATION and BEST MOVES (the optimizer's
    IL move) render; VIEW DETAILS opens the exact pair, and focus returns.
  - OTHER GOOD OPTIONS, FULL WAIVER LIST (294) and ADVANCED EVIDENCE render.
  - All four horizons and Compare a Specific Drop (three horizons) pass.
  - Simulated 504 and unanswered refresh-status messages are structured; no
    HTML is shown.
  - axe 0, `scrollWidth` 1440, and every request was a GET.
  - Even warm, a host memory event during the run made two horizon switches
    take 39.6 s and 47.9 s, close to nginx's 60 s.
- **Database:** identical to the 11:44 UTC baseline: all 29 row counts,
  newest timestamps, `schema_migrations` and every table's cumulative write
  counters, including `yahoo_credentials`. nginx logged 1,924 requests since
  11:35, all GET. Every non-200 is accounted for:
  - the designed Jrue 409;
  - the 12:10-12:18 reproduction.

### Permanent fix (implemented and validated locally; NOT deployed)

`backend/app/features/waivers/admission.py`, wired into the four heavy routes
in `router.py`:
- One heavy read (board, best moves, replacements, impact) runs at a time.
- The slot is a route-level dependency resolved before `configured_team`, so
  a queued read holds no database connection.
- A read whose client disconnects, queued or loading, is cancelled and logged
  `status=499`, and the pooled connection and running query are released.
- `request_timing` and `Server-Timing` gain a `queue` phase.
- Unchanged: results, scoring, weights, samples, status policy, availability,
  capacity, optimizer, exact-pair contract, horizons, invariant, model version,
  proxy, client and connect timeouts. Refresh routes are not gated.
- **Independent review:** no defects. It checked 195 forced interleavings and
  120 real uvicorn requests with random disconnects: peak 1, no slot leak.
  Two known limits remain:
  - Analysis already in a worker thread finishes after a cancel, so it can
    overlap the next read by up to ~2 s.
  - A request-task cancellation that arrives during cleanup can be absorbed.
    Nothing in this deployment cancels request tasks.

**Validation:**
- 4 new regression tests in `tests/test_waivers.py` failed on the deployed
  code for the proven causes, then passed: an abandoned read ran to
  completion; 3 heavy reads overlapped with 3 sessions; a queued read kept
  running; a real PostgreSQL `pg_sleep` kept running after the disconnect.
- Waiver suites 307 and full backend 471 passed.
- Frontend (unchanged): unit 63/63, `tsc -b`. The production build with the
  compose value `VITE_LIVE_DRAFT_POLL_INTERVAL_MS=60000` reproduces the
  deployed `index-0LZfF9Tl.js` byte for byte (25 files).
- Repository Playwright waiver suite: desktop 22/22 (mobile not run).

**Infrastructure (recommended, not applied):** keep the API resident. Options:
- Add RAM.
- Move swap off the rotational system disk.
- Give the `api` container a no-swap memory limit.
- Trim co-tenants (cAdvisor's cgroup was ~1 GB).

Never raise proxy, client or connect timeouts.

**Proposed follow-up:** let the page's board and best-move reads share one
context load.

### Observations (no change made)

- **No-drop excluded reasons are per player.** In the no-drop shape,
  `excluded_addition_reasons` keys stay per player for name-prefixed
  blockers: `gate_category` groups only sample and status gates, giving 368
  keys. O/OFS/NA players appear only as exclusions in ADVANCED EVIDENCE.
- **Deployed bundle needs the build value.** A frontend build without
  `VITE_LIVE_DRAFT_POLL_INTERVAL_MS=60000` yields a different bundle
  (`index-EEPIAMpQ.js`).
- **nginx buffers large responses to disk.** It writes the 1.4 MB board
  response to a temp file on the same disk.

# Phase-6 Ordering and Wording Cleanup — Deployed and Verified — 2026-11-14

**STATUS: DEPLOYED AND VERIFIED (2026-11-15 02:36 UTC; 2026-11-14 18:36
PST).** Production runs the Phase-6 release (deployed 21:30 UTC, record
below) plus this cleanup, on the unchanged model
`waiver-horizon-evidence-phase6`. The cleanup changes no recommendation:
scoring, weights, sample tiers, status policy, availability, roster capacity,
horizons, form windows, optimizer semantics and gates are untouched. This was
an application-only deployment: no migration, refresh, provider call, OAuth,
Yahoo transaction, database change, commit or push. The local validation
record comes first, then the deployment and its read-only acceptance.

### Changes

1. **Compare a Specific Drop ordering.** Root cause: with an explicit drop,
   `build_board` sorted candidates by measured net improvement alone. So
   WATCH DeMar DeRozan (+0.847) was listed above the supported Jerami Grant
   (+0.728) for drop Bones Hyland.
   - `replacement_order` (`service.py`) now sorts the explicit-drop list by
     decision tier, using the canonical `ACTION_RANK` map:
     1. Supported ADD / STREAM / MUST ADD (ADD + DROP).
     2. WATCH.
     3. Supported nonpositive PASS (shown as HOLD).
     4. INSUFFICIENT EVIDENCE and unavailable comparisons.
   - Within a tier it keeps the existing order: measured net (unavailable
     last), then stable player ID. In the supported tier this equals
     `pair_order` for the fixed drop, so the first card is that drop's best
     add.
   - Every candidate keeps its own decision and its exact comparison against
     the selected drop; nothing is promoted.
   - The list always includes the top measured option the page names,
     appended when it falls outside the 12-row window.
   - The page renders the backend order as received and states it in one
     sentence. There is no client-side sorting.
   - Unchanged: the optimizer (`evaluate_pair`, `pair_order`), the no-drop
     board (`decision_priority`, best add/drop) and `eligible_candidate_ids`.
2. **Next 14 Days wording.**
   - Old: "Supported over Next 14 Days by schedule and opportunity and the
     persisted two-week schedule."
   - New: "Two-week move supported by current production, role, roster
     impact, and persisted Next 14 Days schedule evidence."
   - Role is named only for STREAM, which is role-gated. The schedule is
     named only when the add has persisted games in the window; otherwise:
     "… current production and roster impact. Games for X in Next 14 Days
     are not established (REASON), so the schedule is not part of this
     support."
   - No projection, matchup-week, start or completeness claim.

### Validation (serial, host pressure checked before each heavy step)

- **Backend:** focused 16, then waiver suites 289, then full 467 passed.
  - New tests: supported before a higher-net WATCH, with net/ID ties, the
    HOLD and insufficient tiers, the fixed drop, unchanged comparisons and
    unchanged optimizer and board winners.
  - The top measured WATCH stays listed when supported moves fill the list.
  - Next 14 Days wording for ADD, STREAM and unscheduled moves.
  - All of these failed before the change. The persisted replacements test
    now asserts the tier contract instead of net-only order.
- **Frontend:** unit 63/63; the new order test fails if the page re-sorts
  by net. `tsc -b` passes; production build `index-0LZfF9Tl.js`.
- **Playwright:**
  - Focused explicit-drop set: 3/3 desktop and 3/3 mobile. Supported card
    before a higher-net WATCH, each card's decision, the fixed drop,
    "Analyze option" opening the exact pair (add 3 / drop 4), keyboard focus
    return, axe, overflow, GET only.
  - Full suite: 22/22 desktop and 22/22 mobile.

### Pre-deployment real-data acceptance (read-only, guarded, same persisted snapshot)

- **Freshness:** within limits. Yahoo evidence is current until 2026-11-15
  08:31 UTC, and the Pacific date had not changed.
- **No recommendation change:** board, transactions and impact equal the
  deployed engine path for path in Rest of Week, Next 7 Days and Rest of
  Season Outlook. Next 14 Days differs only in the intent sentence.
  Decisions:
  - Rest of Week: ADD Jerami Grant / DROP Bones Hyland +0.728 (STREAM).
  - Next 7 Days: STREAM Grant / DROP Kris Dunn +1.035.
  - Next 14 Days: STREAM Grant / DROP Zach LaVine +0.962 (TWO-WEEK STREAM).
  - Rest of Season Outlook: ADD Derrick Jones Jr. / DROP Hyland +0.455
    (LONGER-TERM ADD).
- **Contracts:**
  - Board = optimizer and the exact-pair contract hold in all four horizons.
  - The recommendation invariant passes.
  - Jrue Holiday and the O/OFS/NA players stay excluded (299 eligible, 272
    `EXCLUDED_STATUS`), and no manager player appears as an add.
- **Explicit drop for the optimizer's drop:**
  - Rest of Week (Hyland): DeRozan, Santi Aldama and Kelly Oubre Jr. (all
    WATCH) become Grant ADD +0.728, Cam Spencer ADD +0.673 and Bilal
    Coulibaly ADD +0.554.
  - Next 7 Days (Dunn): WATCH DeRozan +1.130 is no longer first; Grant
    STREAM +1.035 is.
  - Next 14 Days (LaVine): the third card, WATCH Isaiah Stewart, becomes
    STREAM GG Jackson.
  - Rest of Season Outlook: unchanged.
- **All 60 explicit-drop lists** (15 roster drops × 4 horizons):
  - Tiers and within-tier nets are ordered, the drop is fixed, the first
    supported row is the best add, and the top measured option is listed.
  - Previously 12 of the 18 drops with supported moves showed an
    unsupported row in a slot a supported move should fill; now none do.
- **Guard and database:** 340 statements, all reads, 0 provider calls. The
  database snapshot is identical before and after, and identical to the
  post-deployment snapshot.

### Deployment (2026-11-15 02:13-02:37 UTC)

- **Gate:**
  - The running API differed from the worktree only in `service.py`.
    `build_board` and `move_intent` changed, and `replacement_order` and
    `_series` were added.
  - Every scoring, gate, optimizer and invariant definition is identical at
    the AST level. This covers `evaluate_pair`, `pair_order`,
    `classify_action`, the invariant asserts and `ACTION_RANK`.
  - Since the Phase-6 build only `service.py`, `WaiverCenter.tsx` and three
    test files changed. Every code edit predates the validation runs, and
    `WaiverCenter.tsx` still has its validated hash.
  - `migrations.py` is unchanged: 6 migrations, newest
    `0006_observer_connections`.
- **Baseline (read-only):** production answered the four decisions above.
  - Its responses equal the post-Phase-6-deploy capture (21:32 UTC) path
    for path.
  - The explicit-drop defect was live: drop Hyland listed WATCH DeRozan,
    Aldama and Oubre Jr. before Grant ADD.
  - The database snapshot equaled the post-Phase-6-deploy snapshot.
  - The first cold board read returned 504 three times while the idle API
    paged in from swap. Warm, every read returned 200.
- **Backup:** `~/fantasy-gm-pre-phase6-cleanup-20261115T022755Z.dump`
  (138 MB, mode 0600).
  - `pg_restore --list` is readable and lists 29 TABLE DATA entries.
  - The object inventory equals the `pre-phase6` backup's.
  - All 29 tables' COPY row counts (80,850 rows) equal the live database.
- **Rollback tags:**
  - `fantasy-basketball-gm-api:pre-phase6-cleanup`: index `fb6a46820a23`,
    linux/amd64 `626f53d9872c`.
  - `fantasy-basketball-gm-frontend:pre-phase6-cleanup`: index
    `8d8cc82876f3`, linux/amd64 `d32d8baab1ab`.
  - Docker's containerd image store can give a cached rebuild a new image
    index while keeping the platform manifest. The previous containers'
    recorded index IDs (`24849b33dec4`, `eaf77184ba67`) no longer resolved.
    So the tags were matched to the running containers' recorded platform
    manifests and proven byte-identical in content (70 API files, 26 html
    files).
  - The earlier `pre-phase5`, `pre-acceptance-fixes` and `pre-phase6` tags
    are unchanged.
- **Build (serial):**
  - **API:** image index `2e0fb38b2e4b` (linux/amd64 `a3e52763ba8b`).
    - All 70 `.py` files equal the worktree; versus the previous image only
      `service.py` differs.
    - The new Next 14 Days wording is present, the old phrase is absent and
      the model constant is unchanged.
  - **Frontend:** image index `a7f00cb72046` (linux/amd64 `2b268cbb7a53`).
    - Its 25 html files equal the validated `frontend/dist`
      (`index-0LZfF9Tl.js`, `index-CVxqMg03.css`). The image also has
      nginx's stock `50x.html`.
    - Versus production only the JS bundle and `index.html` change. The
      nginx config is byte-identical.
- **Recreate:** `docker compose up -d --no-deps api frontend` ran
  02:36:04-02:36:32 UTC; health returned 200 at 02:36:40.
  - API container `cdd738a1899e` and frontend `3b6a562ed6d4`.
  - `db` (`d6a02fc4fe35`) and `caddy` (`08198174d855`) were not recreated.
  - The running API source equals the worktree, and the running html equals
    the validated build.
  - nginx resolves the new API, and Caddy serves `index-0LZfF9Tl.js`.
- **Rollback:** retag the `pre-phase6-cleanup` images as `latest` and
  recreate only `api` and `frontend`. The cleanup made no database change.

### Post-deployment acceptance (read-only, GET only)

- **Same engine, same snapshot:** all 20 deployed reads returned 200 with
  `waiver-horizon-evidence-phase6`. They cover board, transactions,
  replacements for the optimizer drop and impact with and without the drop,
  in four horizons. Every one equals the validated local harness output
  path for path.
- **No recommendation change versus pre-deploy production:**
  - Rest of Week, Next 7 Days and Rest of Season Outlook have 0 changed
    paths on board, transactions and impact.
  - Next 14 Days changes only `move_intent_detail`, to the new sentence.
  - Every replacement row present before and after has identical facts.
    Only the explicit-drop list's order and membership changed.
- **Deployed decisions** (persisted 2026-11-14 08:31–08:33 UTC snapshot):
  - Rest of Week: ADD Grant / DROP Hyland +0.728 (STREAM).
  - Next 7 Days: STREAM Grant / DROP Dunn +1.035.
  - Next 14 Days: STREAM Grant / DROP LaVine +0.962 (TWO-WEEK STREAM).
  - Rest of Season Outlook: ADD Jones Jr. / DROP Hyland +0.455
    (LONGER-TERM ADD).
  - Context: roster 13/13 regular, IL 2/3, ADD + DROP required, 2 of 4
    weekly adds used, waiver priority 4th.
- **Contracts:** board = optimizer and the exact pair hold in all four
  horizons (optimizer = board = replacements = impact, with and without the
  drop). The recommendation invariant passes.
- **Compare a Specific Drop, all 60 lists** (15 roster drops × 4 horizons,
  fetched from production):
  - Every list equals the validated audit.
  - Each list is ordered by decision tier, then net, then player ID.
  - The selected drop is fixed in every comparison.
  - The first supported row is that drop's best add, and the top measured
    option is listed.
  - WATCH rows stay WATCH. No unsupported row holds a supported slot;
    before, 12 of the 18 drops with supported moves had one.
  - Rest of Week (Hyland): Grant ADD +0.728, Cam Spencer ADD +0.673, Bilal
    Coulibaly ADD +0.554. The top measured option is still named: WATCH
    DeMar DeRozan +0.847.
  - Next 7 Days (Dunn): Grant, Spencer and Coulibaly, all STREAM. Top
    measured: WATCH DeRozan +1.130.
  - Next 14 Days (LaVine): Grant, Spencer and GG Jackson, all STREAM.
- **Wording:** across the 80 deployed waiver responses (20 surfaces and 60
  drop lists), the old phrase occurs 0 times and the new sentence 61 times.
- **Safety:**
  - 299 eligible and 272 `EXCLUDED_STATUS`.
  - Ariel Hukporti, Ben Simmons and Henri Veesaar are `EXCLUDED_STATUS`
    with "EXCLUDED (YAHOO O/OFS/NA)".
  - Jrue Holiday's impact returns 409 "already rostered", and he appears
    nowhere.
  - None of the 158 players rostered by other teams appears in any list,
    and no manager player is an add.
  - Status labels pass.
- **Deployed page:** desktop 4/4 (1440 × 1000) and mobile 4/4 (390 × 844).
  - Covered: the current-evidence panel (REFRESH never activated), TEAM
    SITUATION, BEST MOVES = the optimizer pair in all four horizons, the
    new Next 14 Days sentence, WATCH text, the full list (299), advanced
    evidence and structured 504/409 errors.
  - The explicit-drop flow ran in three horizons: supported cards first,
    the top measured line, the fixed drop, "Analyze option" opening the
    exact pair, and keyboard focus return.
  - axe found 0 violations. Page `scrollWidth` equals the viewport
    everywhere, including the 390 px roster-capacity expansion. GET only.
  - Three test runs failed for environment reasons, not product defects,
    and each passed when rerun alone:
    - On desktop, the first cold page load's refresh-status read hit its
      30 s client timeout while board and transactions spent ~40 s loading
      under IO pressure.
    - On mobile, two tests ran into the host stall below.
- **Host stall (incident, 03:04-03:32 UTC):** during the mobile run the API
  stopped answering.
  - The host saturated its single rotational disk: 85% utilization at about
    114 reads/s, with the swap file on the same disk (2.8-3.0 GB used) and
    IO pressure "full" averaging 74% over 5 minutes.
  - Health timed out, and nginx returned 504 to waiver reads and to the
    external observer polls.
  - The API kept working on abandoned read-only requests at page-fault
    speed.
  - Only the `api` container was restarted (same container and image) at
    03:31:57. Health returned 200 at 03:32:33, and a Rest of Week board
    read took 5.2 s.
  - No data was involved; every request was a GET. The deployed code was
    not implicated: the stall was in the unchanged data-load phase.
- **Database and logs:**
  - Identical before and after: the database snapshot (counts, newest
    import/update timestamps, `schema_migrations`, and write counters
    including the `yahoo_credentials` OAuth canary) and all 29 table row
    counts.
  - The API logged 162 request timings, all GET. nginx logged only GETs,
    including about 800 observer polls.
  - Every non-200 is accounted for: 502 only in the deploy and restart boot
    windows, 504 in the stall, 499 for aborted reads, and one designed 409
    (Jrue).
- **Freshness:** no refresh job exists, and every evidence stage is current
  with unchanged timestamps (Yahoo 2026-11-14 08:31:32–08:31:50 UTC, NBA
  08:32:14 UTC). Yahoo evidence goes stale at 2026-11-15 08:31 UTC.

# Phase 6 Deployed and Verified — 2026-11-14 (production)

Historical record. Production runs this release plus the ordering and wording
cleanup deployed at 2026-11-15 02:36 UTC (CURRENT STATE above, same model
version). That deployment resolved this record's explicit-drop ordering and
Next 14 Days wording limitations.


**STATUS: DEPLOYED AND VERIFIED (2026-11-14 21:30 UTC).** Model
`waiver-horizon-evidence-phase6` is in production. It ships the
board/optimizer reconciliation, Next 14 Days, Rest of Season Outlook, form
windows, the tiered recent sample, move intent and the user-approved NO
CURRENT YAHOO DESIGNATION status policy, unchanged from the validated
worktree. This was an application-only deployment: no migration, refresh,
provider call, OAuth, Yahoo transaction, database change, commit or push.
The decisions below are hypothetical analysis of the persisted 08:31–08:33
UTC snapshot; confirm in Yahoo before acting.

### Deployment

- **Pre-deployment gate:**
  - The worktree, API and frontend all use `waiver-horizon-evidence-phase6`.
  - The running API differed from the worktree in exactly 7 waiver/status
    files (6 changed plus the new `sample.py`).
  - `migrations.py` and every ORM model are unchanged: 6 migrations, newest
    `0006_observer_connections`.
  - Final serial validation: backend focused 286 and full 464 passed;
    frontend `tsc -b`, production build and unit 62/62; Playwright 21/21
    desktop and 21/21 mobile (axe, keyboard/focus, overflow and structured
    errors).
- **Baseline (read-only):**
  - Phase 5 (api `8801dc6f2a30`, frontend `319641cf6a70`) answered HOLD in
    all three of its windows.
  - The database snapshot was identical to the one taken at the start of
    the Phase-6 work.
  - The first three heavy baseline reads returned 504 at 60 s while the
    idle API paged back in from swap (health alone took 12 s). Retried
    warm, they answered in 2.6-4 s. This was host pressure, not an
    application defect.
- **Backup:** `~/fantasy-gm-pre-phase6-20261114T212327Z.dump` (138 MB, mode
  0600, custom format, 176 TOC entries, 29 TABLE DATA entries). `pg_restore`
  read the whole archive, the 29-table inventory matched, and every table's
  row count matched the live database.
- **Rollback tags:** `fantasy-basketball-gm-api:pre-phase6` =
  `8801dc6f2a30`; `fantasy-basketball-gm-frontend:pre-phase6` =
  `319641cf6a70`. No `pre-phase6` tag existed before.
- **Build (serial):**
  - API image `24849b33dec4`: its source equals the worktree (70 files,
    SHA-256).
  - Frontend image `eaf77184ba67`: its bundle equals the validated build
    (25 files, `index-DogvR0PR.js` / `index-CVxqMg03.css`), and its nginx
    config is byte-identical.
  - Both expect `waiver-horizon-evidence-phase6`.
- **Recreate:** `docker compose up -d --no-deps api frontend` ran
  21:29:57-21:30:32 UTC; health returned 200 at 21:30:43.
  - API container `f86c185c5b33` and frontend `5745e02cf00f`, 0 restarts.
  - `db` (`d6a02fc4fe35`) and `caddy` (`08198174d855`) were not recreated.
  - Startup ran no migration and logged no errors.
  - nginx resolves the new API; its 7 connection-refused lines fall inside
    the 10-second boot window.
- **Rollback:** retag the `pre-phase6` images as `latest` and recreate only
  `api` and `frontend`. Phase 6 made no database change, so no database
  rollback is needed.

### Deployed decisions (persisted 2026-11-14 08:31–08:33 UTC snapshot)

| Horizon | Decision | ADD | DROP | Net | Intent |
|---|---|---|---|---|---|
| Rest of Week | ADD (ADD + DROP) | Jerami Grant | Bones Hyland | +0.728 | STREAM |
| Next 7 Days | STREAM (ADD + DROP) | Jerami Grant | Kris Dunn | +1.035 | STREAM |
| Next 14 Days | STREAM (ADD + DROP) | Jerami Grant | Zach LaVine | +0.962 | TWO-WEEK STREAM |
| Rest of Season Outlook | ADD (ADD + DROP) | Derrick Jones Jr. | Bones Hyland | +0.455 | LONGER-TERM ADD |

- Supported moves: 40, 66, 40 and 36 respectively. The deployed Phase-5
  baseline was HOLD in all three of its windows.
- Every deployed response equals the pre-deploy read-only shadow of the same
  snapshot, path for path, apart from request-time stamps. This covers the
  board, transactions, replacements and impact (with and without the drop)
  in all four horizons, so no change is unexplained.
- Net gains are on the 0-100 roster index, not fantasy points. Confirm FA or
  waiver state and roster locks in Yahoo before acting; the app never
  executes a transaction.

### Acceptance (read-only)

- **Model:** all 20 deployed board, transactions, replacements and impact
  reads report `waiver-horizon-evidence-phase6`. The page shows no
  stale-model warning.
- **Board = optimizer** in every horizon:
  - Same add, drop, mode, decision, action type and comparison.
  - Decision support is SUPPORTED_ACTION ("1 supported move available.").
  - No "0 supported moves", "no supported add yet" or "Next open spot".
- **Exact pair:** the optimizer, the board row, the replacements for the
  selected drop and the impact with that drop all agree. So does the impact
  without a drop. The checked fields:
  - IDs, mode, decision and action type.
  - Before, after and net index; component before, after and deltas;
    effective weights.
  - Gates, status, sample, role, schedule and form.
  - The drop's evidence is also identical on the board and in the
    replacements.
- **Horizons vs form:**
  - Last 7/14/30 Days end on or before today, and every horizon's schedule
    starts today (Next 14 Days ends 2026-11-27).
  - Schedule coverage is only PARTIAL or UNKNOWN, and no value is
    zero-filled or invented.
  - Rest of Season Outlook says there are no projected fantasy totals.
- **Sample tiers:**
  - Every tier matches its game count. No VERY LOW or INSUFFICIENT sample
    passes, and every promoted LIMITED sample meets the full rule.
  - DeMar DeRozan: VERY LOW (4 games), never supported.
  - Kris Dunn: LIMITED, corroborated by 11 games in 30 days and FP/G −9.5%.
  - Bones Hyland: LIMITED, corroborated by 12 games in 30 days, a STABLE
    role and minutes +3.7.
  - All three are SUPPORTED in Rest of Season Outlook.
- **Status policy:**
  - 425 of 426 missing status fields read NO CURRENT YAHOO DESIGNATION with
    the exact non-health detail.
  - No label says healthy, active, cleared or injury-free; Q and P stay
    UNCERTAIN.
  - There are 0 supplied blanks and 0 stale records.
  - Blake Wesley (unresolved identity) stays UNKNOWN, gate-blocked and not
    comparable.
  - The other fail-closed states have no real occurrences; the backend
    tests cover them.
- **Safety:**
  - 299 eligible and 272 `EXCLUDED_STATUS`.
  - Ariel Hukporti, Ben Simmons and Henri Veesaar are `EXCLUDED_STATUS`.
  - Jrue Holiday is `ROSTERED_BY_OTHER_TEAM` (the impact read refuses him
    with 409 as rostered) and appears on no surface.
  - No manager player appears as an add, and no featured ID falls outside
    `eligible_candidate_ids`.
  - Roster 13/13 regular, IL 2/3; 2 of 4 weekly adds used (2 remaining);
    waiver priority 4th. These are context only.
- **Deployed page through Caddy (TLS validated):** desktop 1440×1000 passed
  4/4 and mobile 390×844 passed 4/4. Checked:
  - The four horizons, each showing the optimizer pair with its intent and
    form.
  - Details that lead with the ROSTER DECISION, then Last 7/14/30, Season
    and Previous Season, with keyboard focus returning to the opener.
  - The full list with the Last 14 sort, and ADVANCED EVIDENCE.
  - Recovery from a simulated 504 and 409 without HTML, HOLD or a stale
    move.
  - Compare-a-drop requests the exact drop.
  - axe found 0 violations, page width equals the viewport in every state,
    and only GET requests were sent.
- **Database and logs:**
  - The database is identical before and after: all 29 tables' row counts,
    newest import/update timestamps, migrations and write counters
    (`yahoo_credentials` updates unchanged).
  - Since the deploy: 70 API requests, all GET (one designed 409), and 713
    nginx requests, all GET.
  - No refresh job exists. The panel reads "All waiver evidence current as
    of: November 14, 2026 at 12:32 AM PST" from persisted evidence.

### Remaining limitations

- The decisions rest on the 08:31–08:33 UTC snapshot. Yahoo evidence goes
  stale 24 hours after import (2026-11-15 08:31 UTC), and the Pacific date
  changes at 08:00 UTC. After a user-initiated refresh the decisions can
  change.
- COMPARE A SPECIFIC DROP ranks a chosen drop's replacements by net index,
  so WATCH players (DeRozan +0.847) can precede the supported Grant
  (+0.728). Each card shows its backend decision; this ranking predates
  Phase 6. (Resolved: the cleanup deployed 2026-11-15 02:36 UTC ranks
  supported moves first.)
- The Next 14 Days intent reads "by schedule and opportunity and the
  persisted two-week schedule" (redundant wording, cosmetic). (Resolved by
  the same deployment.)
- Evidence limits are unchanged:
  - No game-level usage or per-game starts.
  - Schedule coverage is PARTIAL, never COMPLETE.
  - Yahoo does not state FA/waiver ownership (UNROSTERED — CONFIRM IN
    YAHOO), and claim-clear times are unsupported.
  - Evidence is historical, never a projection, and a status is never a
    health claim.
- Host capacity: an idle API is swapped out, so its first heavy reads can
  return 504 until it pages back in.

# Waiver Horizons & Evidence (Phase 6) — Implementation and Pre-Deployment Acceptance — 2026-11-14

Historical pre-deployment record; the release was deployed unchanged at 21:30
UTC (CURRENT STATE above).


**STATUS: IMPLEMENTED AND VALIDATED LOCALLY, NOT DEPLOYED.** Model
`waiver-horizon-evidence-phase6`. The local working tree also carries the
user-approved NO CURRENT YAHOO DESIGNATION policy (record below, unchanged).
The running system is unchanged: Phase 5 plus the four acceptance fixes (api
`8801dc6f2a30`, frontend `319641cf6a70`, model `waiver-availability-phase5`).
Everything in this record was local or read-only: no deployment, rebuild,
container change, refresh, provider call, OAuth, migration, database write,
Yahoo transaction, commit or push. A deployed Phase-5 response shown to the
Phase-6 page (or the reverse) fails closed on the model version.

### What changed (local)

1. **Board = optimizer.** Root cause of the Next 7 Days contradiction: the
   board judged each add only against its highest-net drop (Grant vs Kris
   Dunn, then sample-gated), while the optimizer searched every pair. Both
   now use one pair judgment (`evaluate_pair`) and one ordering
   (`pair_order`). On a full roster the board's `best_add_for_team_id` and
   new `best_drop_for_team_id` are the optimizer's best supported pair by
   construction, and the best add is always in the board's candidates. If a
   response ever disagrees, BEST MOVES shows a contract error instead of two
   answers. A full roster never shows "Next open spot" or a measured card
   beside a supported pair. No gate changed.
2. **Next 14 Days** (`mode=next_14_days`): Pacific today through today + 13,
   a forward schedule window, never Last 14 Days form. It is consistent
   across board, transactions, replacements, impact, decision support,
   schedule counts, team-needs date gaps, explanations and the page.
3. **Rest of Season Outlook** is the page label for `mode=ros` (API mode
   unchanged). Season Evidence remains the name of the historical evidence;
   the remaining persisted schedule is shown, never projected totals.
4. **Form windows are look-back evidence, not horizons:** Last 7, 14 and 30
   Days, Current Season and Previous Season. Each shows games, Yahoo FP/G
   (strict scoring fields, never zero-filled), minutes average and median,
   sample tier, dates and freshness. Starts and usage appear only for season
   windows with explicit provenance; log windows never invent them. The trend
   compares Last 14 Days with days 15-30 (non-overlapping, 3+ fresh games
   each side) and needs PPG (±30%) and minutes (±3.0) to agree: IMPROVING,
   DECLINING, MIXED or STABLE. It is descriptive and never a gate.
5. **Tiered recent sample** (`app/features/waivers/sample.py`) replaces the
   hard 7-game cliff without weakening other gates:
   - SUPPORTED (7+ relevant games) is the unchanged rule.
   - LIMITED (5-6 games in the last 14 days) passes in Rest of Week, Next 7
     Days and Next 14 Days only with 7+ current-season games, fresh
     production, a qualified current role (3 valid fresh games each side),
     and at least 2 of 4 independent corroborations: 10+ games in the last 30
     days; role STABLE or RISING; Last 14 vs Last 30 FP/G within 13% (3+
     earlier games, both windows fresh); and a minutes change above -3.0.
   - Current-season games are not a corroboration. The first version also
     counted "10+ games this season", but Last 30 Days games are a subset of
     the season's games, so the same games counted twice. Found during this
     acceptance and removed; on current data no promotion depended on it
     (the same 40 players and decisions before and after).
   - VERY LOW (3-4) and INSUFFICIENT (0-2) never pass; positive pairs stay
     WATCH.
   - Rest of Season Outlook never corroborates a LIMITED season sample with
     older seasons.
   - Status, identity, availability, positive impact, O/OFS/NA and Q/P are
     unchanged. A failing LIMITED sample is named exactly: for example "Kelly
     Oubre Jr. 5 games in the last 14 days (LIMITED SAMPLE: 2 of 4
     corroborations passed, 2 needed; missing requirement: qualified current
     role)". (The first wording, "not corroborated, 3 of 2 corroborations",
     was corrected during this acceptance.)
6. **Move intent** (descriptive; never changes a decision): supported moves
   are STREAM (Rest of Week, Next 7 Days), TWO-WEEK STREAM (Next 14 Days) or
   LONGER-TERM ADD (Rest of Season Outlook, or an ADD with longer-term
   Season Evidence). Everything else is WATCH, HOLD or INSUFFICIENT
   EVIDENCE. When the persisted schedule has no games for the add in the
   horizon, the detail says the support is production and roster fit, not
   the schedule (a zero is never asserted).
7. **Page:** four horizon radios; intent badge and form lines on move cards.
   VIEW DETAILS leads with ROSTER DECISION (ADD, DROP, NET, WHY,
   BLOCKERS), then RECENT FORM, SEASON EVIDENCE, UPCOMING SCHEDULE (Next 7,
   Next 14, rest of season) and the recent-sample gate. The FULL WAIVER LIST
   adds form and Next 7 / 14 columns and exploratory sorts (Last 7/14/30
   Days, Season, Next 7/14 Days) that never change BEST MOVES or the backend
   rank. ADVANCED EVIDENCE adds the supported-move count and the sample
   policy.

### Sample audit (read-only, persisted logs, Pacific 2026-11-14)

- The regular season began 2026-10-20, so Last 30 Days is the whole season.
  In the Last 14 Days window 10 of 30 teams played only 5-6 games (distinct
  logged game IDs); of 133 rotation players with 5-6 games, 62 played every
  team game. The hard cliff therefore blocked full-time players.
- 80th percentile of |FP/G 14 - FP/G 30| / FP/G 30 for well-sampled players
  (n = 114): 13.0% (bootstrap 90% CI 11.1-15.4%), the corroboration
  tolerance. The 90th percentile was unstable (14.9-24.9%).
- Non-overlapping change (Last 14 vs days 15-30), 75th percentile about 29%
  (CI 26-32%): the 30% trend threshold. Minutes change of -3.0 or less: 12-18%
  of players (the existing role threshold, reused).

### Real-data acceptance (read-only, local source, one snapshot per run)

CONTROL swaps only the recent-sample gate back to the hard seven-game rule on
an identically loaded context (same status policy and all other inputs).

| Horizon | CONTROL (hard seven) | Phase 6 (tiered) | Supported moves |
|---|---|---|---|
| Rest of Week | **HOLD** (0 supported, 83 WATCH) | **ADD Jerami Grant / DROP Bones Hyland +0.728** (STREAM) | 0 → 40 |
| Next 7 Days | STREAM Grant / Zach LaVine +0.649 | **STREAM Grant / DROP Kris Dunn +1.035** (STREAM) | 9 → 66 |
| Next 14 Days | STREAM Grant / LaVine +0.962 | **STREAM Grant / DROP LaVine +0.962** (TWO-WEEK STREAM) | 12 → 40 |
| Rest of Season Outlook | ADD Derrick Jones Jr. / Bones Hyland +0.455 | **identical** (LONGER-TERM ADD) | 36 → 36 |

- Index gains are on the 0-100 roster model, not fantasy points. Adds are
  unrostered in complete current snapshots; confirm FA/waiver state and
  roster locks in Yahoo before acting.
- Transitions: Rest of Week 40 WATCH → supported; Next 7 Days 57 WATCH →
  supported and 9 WATCH → INSUFFICIENT EVIDENCE (their sample now passes and
  the unchanged STREAM role/schedule gate blocks them); Next 14 Days 28 WATCH
  → supported. No pair lost support in any horizon.
- Why the drops differ by horizon: the drop with the most to give is the
  lowest-value roster player on that horizon's evidence (Hyland Rest of
  Week and Rest of Season Outlook, Dunn Next 7 Days, LaVine Next 14 Days).
- Named players:
  - Bones Hyland: 6 games in 14 days, 12 this season, role STABLE;
    corroborated by 12 games in 30 days, role and minutes (+3.7): 3 of 4.
    FP/G +25% fails the tolerance. Form IMPROVING.
  - Kris Dunn: 6 / 11, role FALLING (qualified); corroborated by 11 games
    in 30 days and FP/G (-9.5%, inside 13%): exactly 2 of 4. Minutes -4.7
    fails. Form DECLINING.
  - DeMar DeRozan: 4 games in 14 days, VERY LOW, never supported (WATCH).
  - Derrick Jones Jr.: weekly LIMITED, not promoted (3 of 4 corroborations
    but no qualified role); SUPPORTED in Rest of Season Outlook (10 games).
- 107 LIMITED players (adds and your roster) in the weekly horizons; 40
  corroborated (12 with 4 of 4 corroborations, 19 with 3, 9 with exactly 2),
  including your Hyland, Jarrett Allen, Julius Randle, Dunn, P.J. Washington
  and Pascal Siakam. Of the 67 not promoted, 49 lack only a qualified role,
  11 also lack 7+ season games and 7 have fewer than 2 corroborations. Rest
  of Season Outlook: 41 LIMITED, 0 corroborated.
- Equality: board, optimizer, replacements (fixed drop) and impact (with
  and without the drop) agree on the best pair's comparison and decision in
  every horizon. Repeat runs are identical except the request-time
  `generated_at` and `data_quality.overall_score.as_of`.
- Unchanged: roster 13/13 regular, IL 2/3, ADD + DROP required; 2 of 4
  weekly adds used (2 remaining); waiver priority 4th; 299 eligible and 272
  `EXCLUDED_STATUS`; Ariel Hukporti, Ben Simmons and Henri Veesaar excluded;
  Jrue Holiday `ROSTERED_BY_OTHER_TEAM` and on no surface.
- Guard: 339 statements, all reads, 0 blocked, 0 provider calls; 14
  statements per context load (no N+1). Load 3.7-7.0 s per horizon (Rest of
  Season Outlook slowest), optimizer 0.8-1.3 s, board 0.1-0.5 s on this host.
  The database snapshot is identical before and after every run.
- Payload: the board grew about 20-24% (Rest of Week 1.17 → 1.45 MB;
  transactions 424 → 590 KB) from per-candidate form and sample evidence.

### Validation

- Backend: 464 passed, including the board/optimizer regression (fails
  before the fix), the double-count regression (two cases pass only with
  the removed check) and the real-data wording and intent regressions.
- Frontend: unit 62/62 (the fail-closed pair check fails with the fix
  reverted), `tsc -b` and production build pass.
- Fixture Playwright: 42/42, desktop 1440×1000 and mobile 390×844, run
  serially.
- Real-data page render (local dev frontend, real read-only engine responses,
  nothing deployed): every horizon shows the agreeing pair with its intent
  and form, VIEW DETAILS keeps focus and returns it, no page or dialog
  overflow at 390 px, axe clean, the Last 14 Days sort orders the list
  without changing BEST MOVES, no Jrue Holiday or OFS player anywhere, zero
  non-GET requests.

### Observations for the next decision

- The 13% FP/G tolerance decides exactly one promotion: Kris Dunn (-9.5%).
  Dunn is the Next 7 Days drop, so that best move depends on the tolerance
  (CONTROL's Grant / LaVine +0.649 is the hard-seven alternative).
- A 5-game sample cannot qualify a 3 + 3 role inside 14 days, so in practice
  only 6-game samples are promoted.
- The FP/G tolerance is symmetric: a hot Last 14 Days drop is protected
  (conservative), a hot Last 14 Days add is not.
- 0-2-game positive pairs still show as WATCH when the player has
  current-season games (unchanged behavior).

### Deployment recommendation

Deploy the whole release together (status policy, board reconciliation,
horizons, form windows, tiered sample, intent, model version) only with
explicit approval. It is a material behavior change for your roster: Rest of
Week moves from HOLD to ADD Grant / DROP Hyland and Next 7 Days from dropping
LaVine to dropping Dunn. Every promotion is explained by backend evidence, no
invariant changed, and the evidence is reproducible. Before 2026-11-15 08:00
UTC the deployed result can be verified exactly against this record (same
persisted data and Pacific date); later, or after any refresh, rerun the
read-only shadow first and verify against it.

# Fresh Missing Yahoo Status: User-Approved Policy — 2026-11-14 (local; carried into Phase 6)

Deployed with Phase 6 at 21:30 UTC (CURRENT STATE above); the record below is
the pre-deployment history.

**STATUS: IMPLEMENTED AND VALIDATED LOCALLY, NOT DEPLOYED.** On 2026-11-14
the user explicitly approved overriding the REJECT decision recorded below: a
fresh Yahoo player record whose `status` key is absent now means **NO CURRENT
YAHOO DESIGNATION** and may pass the Yahoo status gate, but only when every
condition below holds. It is never a medical-health claim. The running system
is unchanged: Phase 5 plus the four acceptance fixes (api `8801dc6f2a30`,
frontend `319641cf6a70`, model `waiver-availability-phase5`), which still
treat every blank status as UNKNOWN. Everything in this record was local or
read-only: no refresh, deployment, rebuild, provider call, OAuth, migration,
database write, Yahoo transaction, commit or push.

### Policy (local working tree)

Label **NO CURRENT YAHOO DESIGNATION**; detail "Yahoo's current player record
contains no explicit injury/status designation. This is not a
medical-health guarantee." It is never called healthy, active, cleared or
injury-free. A missing field qualifies only when all of these hold; the first
failing condition is reported and the status stays UNKNOWN:

1. A player-pool record exists in the configured league's pool (`PLAYER_OBSERVATION_MISSING`).
2. It was imported within 24 hours (`STALE_PLAYER_POOL_IMPORT`).
3. The `status` key is genuinely absent from the record (and from the roster record for your players).
4. The Yahoo-to-NBA identity is resolved without a team conflict, and the record's Yahoo ID matches the identity (`MAPPING_ISSUE`).
5. Nothing else carries status evidence: no `status_full`, `injury_note` or truthy `on_disabled_list`, and the stored identity status is empty (`NORMALIZATION_DEFECT`).
6. Every league roster snapshot is current (`ROSTER_SNAPSHOT_INCOMPLETE`).

Adds must still be actionable (`CONFIRMED_FA`, `CONFIRMED_WAIVER` or
`UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT`) through the unchanged availability
gate; your own roster players qualify as drops. A Yahoo-supplied blank,
unrecognized token, stale record or any failed condition stays UNKNOWN and
keeps blocking. O/OFS/NA stay excluded and Q/P uncertain. The sample rule,
shrinkage, weights, availability classes, roster capacity, invariant, scoring
formula and acquisition logic are unchanged.

`interpret_yahoo_status()` in `app/services/draft/player_status.py` is the only
interpreter. Each candidate exposes `raw_yahoo_status`, `status_field_state`,
`decision_status_state` (`EXCLUDED`, `UNCERTAIN`,
`NO_CURRENT_YAHOO_DESIGNATION`, `UNKNOWN`), `status_reason`,
`status_gate_supported`, `status_label` and `status_detail`. Defaults fail
closed. The status gate (`status_gap`, now also used by
`transaction_blockers`) passes a blank only for a loader-verified designation
with fresh status evidence. The page shows the backend label and detail.
ADVANCED EVIDENCE keeps the explicit, Yahoo-blank, status-field-missing and
stale counts and adds "no current Yahoo designation".

### Real-data acceptance (read-only, local source, one snapshot)

Population (744 pool records): 318 explicit; 426 without a `status` field, of
which 425 qualify (287 eligible adds, your 12 players, 126 on other teams). The
remaining one is an eligible add with an unresolved identity and stays UNKNOWN
(`MAPPING_ISSUE`). There are 0 normalization defects, stale records, supplied
blanks or incomplete-roster cases. Totals are unchanged: 299 eligible, 272
`EXCLUDED_STATUS`.

| Window | Decision | Pairs (strong / PASS / WATCH) | Board decision support |
|---|---|---|---|
| Rest of Week | **HOLD** | 0 / 240 / 83 (every positive pair fails the sample gate) | BEST MEASURED OPTION DeMar DeRozan (4 games in the last 14 days) |
| Next 7 Days | **STREAM: ADD Jerami Grant / DROP Zach LaVine (+0.649)** | 9 STREAM (all dropping LaVine) / 227 / 152 | BEST MEASURED OPTION DeMar DeRozan (see finding) |
| Season Evidence | **ADD: Derrick Jones Jr. / DROP Bones Hyland (+0.455)** | 36 ADD / 2,200 / 4 | SUPPORTED_ACTION; best add Derrick Jones Jr. |

- Index gains are on the 0-100 roster model, not fantasy points. The adds
  are unrostered in complete current snapshots; confirm FA/waiver state in
  Yahoo.
- **Control (the previous gate on the same snapshot): HOLD in every window.**
  Every newly supported move is 9 in Next 7 Days and 36 in Season Evidence.
  Each was blocked only because the status field was absent (YES for all 45):
  the status gate was its sole blocker, and only on no-designation players.
- **Best-move field table.** Grant/LaVine and Jones/Hyland are identical on
  every condition, add and drop:
  - Raw status none; no `status` key in the pool record or your roster record.
  - Field `STATUS_FIELD_MISSING`; decision `NO_CURRENT_YAHOO_DESIGNATION`; gate passes.
  - Imported 08:31:50 UTC and fresh; `EXACT_NAME_TEAM`.
  - Yahoo IDs match (Grant 5350, LaVine 5324, Jones 5747, Hyland 6568).
  - Identity status empty; no companion status keys; rosters current.
  - Samples: Grant and LaVine 12 games this season and 7 in Next 7 Days with STABLE role; Jones 10, Hyland 12.
- **Cross-surface:** the optimizer, replacements (selected drop) and impact
  agree on decision and comparison for the top three moves in Next 7 Days and
  Season Evidence. Repeated runs are byte-identical. Service transactions equal
  the in-process analysis except the request-time `overall_score.as_of`. The
  recommendation invariant passed for every run.
- **Unchanged:**
  - Roster 13/13 regular, IL 2/3, ADD + DROP required.
  - 2 of 4 weekly adds used (2 remaining); waiver priority 4th.
  - Jrue Holiday is `ROSTERED_BY_OTHER_TEAM`. His record shows no
    designation, but he is never eligible and is absent from every list.
  - Ariel Hukporti, Ben Simmons and Henri Veesaar are `EXCLUDED_STATUS`
    ("EXCLUDED (YAHOO O/OFS/NA)").
  - Curry and Markkanen are O, in IL.
  - The sample gate still fails DeRozan (4), Hyland (6) and Dunn (6 games in
    the last 14 days).
  - TEAM SITUATION reads "3 of 15 roster players have an explicit Yahoo
    status; 12 have NO CURRENT YAHOO DESIGNATION …".
- **Guard:** 387 statements, all reads; 0 blocked; 0 provider calls. The
  database snapshot (counts, newest timestamps, write counters) is identical
  before and after.

### Finding: Next 7 Days board summary disagrees with the optimizer (pre-existing logic, now visible)

**Resolved locally in Phase 6 (see CURRENT STATE above); the original finding follows.**

The board ranks each add against its best-net drop. Jerami Grant's best-net
drop is Kris Dunn (+1.035), which fails the sample gate (6 games), so the
board marks Grant WATCH. It then reports BEST MEASURED OPTION DeMar DeRozan,
"0 supported moves", and board action WATCH. The optimizer searches every
pair and finds the fully supported Grant/LaVine STREAM.

Rendered with the real responses, BEST MOVES shows that STREAM card, then a
DeRozan card titled "Next open spot: no supported add yet" on a full roster.
ADVANCED EVIDENCE says "0 supported moves". Season Evidence is consistent
(board best add = optimizer best) and Rest of Week holds.

The board logic predates this change; a supported pair never existed before.
It was left unchanged because this task changes only the status variable.

### Validation

- Backend: 437 passed (31 new cases).
  - With the policy disabled in a throwaway copy, all 11 positive-path tests
    fail and the 21 fail-closed tests still pass.
- Frontend: unit 57/57, `tsc -b` and production build pass.
- Fixture Playwright: 42/42, desktop 1440×1000 and mobile 390×844. The
  full-roster pair renders a no-designation drop with its limitation and no
  page-level overflow.

### Deployment recommendation

**Superseded by the Phase-6 recommendation above.** Not yet. The status policy is ready, but deploying it alone would ship the
contradictory Next 7 Days page above. First reconcile the board's ADD + DROP
summary with the optimizer's best supported pair. That is a separate,
explicitly approved change. Then deploy both together with a model-version
change, so an older cached page fails closed instead of showing "Unknown"
beside a supported move.

# Blank Yahoo Status Policy Review — 2026-11-14 (superseded the same day by the user-approved policy above)

**STATUS: POLICY CHANGE REJECTED / STATUS-DIAGNOSTIC CORRECTION VALIDATED
LOCALLY, NOT DEPLOYED.** A blank Yahoo status stays UNKNOWN and keeps blocking
strong waiver actions, so decisions are unchanged: HOLD in Rest of Week, Next 7
Days and Season Evidence. The running system is still Phase 5 plus the four
acceptance fixes deployed at 11:40 UTC (next record). Everything here was
read-only: no refresh, deployment, provider call, Yahoo transaction or
database write.

### Source and persistence audit (read-only PostgreSQL)

- The normalizer stores each Yahoo player record as its merged JSON fragments
  and adds no keys; `_merge_player_payload` only fills a missing or blank key
  from another Yahoo observation of the same player. The persisted key set is
  therefore what Yahoo sent.
- All 744 pool observations were imported at 08:31:50 UTC (fresh until
  2026-11-15 08:31 UTC); every row joins its identity by Yahoo ID, and the
  normalized identity status equals the raw token in 744 of 744 rows. Every
  roster entry has a pool observation.

| Status-evidence class | Rows |
|---|---|
| `EXPLICIT_STATUS` (NA 218, O 77, Q 16, P 4, OFS 3; all with `status_full`) | 318 |
| `YAHOO_SUPPLIED_BLANK` (key present, blank or null) | 0 |
| `STATUS_FIELD_MISSING` (no `status` key) | 426 |
| `PLAYER_OBSERVATION_MISSING` | 0 |
| `STALE_PLAYER_POOL_IMPORT` | 0 |
| `MAPPING_ISSUE` (status attached to the wrong identity) | 0 |
| `NORMALIZATION_DEFECT` | 0 |
| `UNRECOGNIZED_NONBLANK` | 0 |

- The 426 are complete records: they carry the same 20 core keys as the
  designated ones and lack only `status`, `status_full` and `injury_note`
  (115 designated rows have a note), which never appear without `status`.
  Roster-endpoint records match (138 of 173 have no `status` key, including 12
  of Box Score Bully's 15).
- Yahoo omits other optional flags too (`has_player_notes` only ever appears
  as `1`) but sends some explicitly (`is_undroppable` is `"0"` on all 744), so
  omission is suggestive, not a documented contract. No raw Yahoo player
  capture exists locally.
- SQL NULL does not prove a supplied blank: `player_identity.status` and
  `source_payload->>'status'` are NULL because the key is absent.

### Decision: REJECT

The proposed policy needs a current record that contains the status field with
no designation. None exists: Yahoo never supplied a blank status. The persisted
evidence therefore cannot tell "Yahoo reported no designation" from "status not
observed", and a missing field stays UNKNOWN. Treating absence as "no
designation" would be a different policy that needs a documented Yahoo contract
and explicit approval. O/OFS/NA, Q/P, the sample rule, shrinkage, weights,
availability classes and roster capacity are unchanged.

### Shadow comparison (read-only, one frozen snapshot, deployed-identical engine)

Only the status-gate predicate differed between runs; a repeated CONTROL run
was byte-identical to the first, the replicated pair counts matched the engine
and the recommendation invariant passed for every policy.

| Window | CONTROL: blank = UNKNOWN | PROPOSED: verified supplied blank | Absent field counts, adds only | Absent field counts, adds and your drops |
|---|---|---|---|---|
| Rest of Week | HOLD; 0 supported, 83 WATCH | identical (0 players qualify) | HOLD | HOLD; all 83 positive pairs still fail the sample gate |
| Next 7 Days | HOLD; 0 supported, 152 WATCH | identical | HOLD | STREAM: ADD Jerami Grant / DROP Zach LaVine +0.649 (9 STREAM pairs, all dropping LaVine) |
| Season Evidence | HOLD; 8 PASS, 4 WATCH | identical | HOLD | ADD: Derrick Jones Jr. / DROP Bones Hyland +0.455 (36 ADD pairs) |

- CONTROL blockers among positive-impact pairs: Rest of Week 83 (sample 83,
  status 83); Next 7 Days 165 (sample 152, status 165, status alone 13);
  Season Evidence 43 (status 43, sample 7, production evidence 3, status
  alone 36). Nonpositive eligible pairs: 3,804 / 3,722 / 3,844; ineligible
  (O/OFS/NA) add pairs 3,536.
- Adds-only acceptance changes only nonpositive PASS pairs: 12 of the 13 drop
  candidates also have no status field, so every positive pair stays blocked.
- The hypothetical moves pass every non-status gate (both players at least 7
  games this season and, weekly, 7 in the last 14 days; qualified role for
  STREAM), but rest entirely on reading absence as no designation for both
  players. Net gains are +0.01 to +0.65 index points (0-100 roster index, not
  fantasy points), and the adds are unrostered players whose FA/waiver state
  must still be confirmed in Yahoo.

### Status-diagnostic correction (validated locally / not deployed)

The waiver diagnostic labeled every blank as `YAHOO_SUPPLIED_BLANK` ("Yahoo
supplied a blank status"), because `payload.get("status")` is `None` both for a
supplied null and for a missing key. All 426 production cases were missing
fields. `player_status.yahoo_status_field()` now classifies the field, the
waiver service reports `STATUS_FIELD_MISSING` ("The current Yahoo player record
has no status field, so no designation is recorded; status is UNKNOWN, not
healthy."), and status coverage counts "status field missing" separately. Both
remain UNKNOWN; no gate, decision, ranking or score changes.

### Validation

- Backend **406 passed** (two new regression tests, each failing before the
  correction); frontend unit **56/56**, `tsc -b` and build passed; fixture
  Playwright **42/42** (desktop 1440 and mobile 390: axe, keyboard focus,
  overflow, API-error recovery).
- Exact equality (read-only harness vs live GETs, all three windows: board,
  transactions, replacements, impact with and without a drop): the deployed
  code is identical to production in all 15 responses, and the local code
  differs only in the status-diagnostic fields (request-time stamps excluded).
  Read-only guard: 214 read statements per equality dump and 46 for the
  shadow run, 0 blocked, 0 provider attempts.
- Real-data safety: Jrue Holiday `ROSTERED_BY_OTHER_TEAM`; Hukporti, Simmons
  and Veesaar `EXCLUDED_STATUS`; Curry and Markkanen O in IL; 13 of 13 regular,
  IL 2 of 3, ADD + DROP required; 2 of 4 adds left; priority 4th; counts 299 /
  272 / 158 / 15 = 744; no featured player outside `eligible_candidate_ids`.

# Post-Refresh Acceptance and Patch Deployment — 2026-11-14

**STATUS: PHASE 5 DEPLOYED AND REFRESHED / FOUR ACCEPTANCE FIXES DEPLOYED AND
VERIFIED (11:40 UTC).** `waiver-availability-phase5` has been in production
since 2026-11-14 08:26 UTC. The user ran **REFRESH WAIVER DATA** once (job
`629bd689b6f0`, 08:31:29-08:33:05 UTC, SUCCEEDED); no refresh has run since.
The four post-refresh acceptance fixes were deployed at 11:40 UTC as an
application-only patch: same model version, no migration, no data change.
Every acceptance check was read-only: no second refresh, no provider call, no
Yahoo transaction, no database write.

### Patch deployment (2026-11-14 11:40 UTC)

- **Backup:** private `pg_dump` custom archive
  `~/fantasy-gm-pre-acceptance-fixes-20261114T113504Z.dump` (138 MB, mode
  0600, 176 TOC entries). `pg_restore` read every data block, and all 29
  tables' row counts matched the live database.
- **Rollback tags:** `fantasy-basketball-gm-api:pre-acceptance-fixes` and
  `fantasy-basketball-gm-frontend:pre-acceptance-fixes` point at the images
  that ran before the patch (`pre-phase5` tags kept). Rollback: tag them back
  to `:latest`, then `docker compose up -d --no-deps api frontend`.
- **Deploy:** built `api`, then `frontend`, and recreated only those two (API
  started 11:40:20, frontend 11:40:22 UTC). `db` and `caddy` kept their
  containers (started 05:20/05:21 UTC, 0 restarts). API startup ran the
  existing idempotent schema check; `schema_migrations` is unchanged (6
  revisions, newest from 2026-10-18).
- **Source identity:** before the deploy, the running API differed from the
  worktree in exactly the six fix files, and the worktree with the two
  frontend fixes reverted rebuilt the running bundle byte for byte (25 build
  files). After the deploy, the running API source equals the worktree (69
  files) and the running bundle equals the validated build
  (`index-fQW2Lt12.js`, `index-BZ8KPD4v.css`); nginx config unchanged.
- **No refresh, no write:** every table's row count, newest `imported_at` /
  `updated_at` and write counters were identical before the deploy, after it
  and after page acceptance. nginx logged only GET requests (764) after the
  deploy; the API holds no refresh job.

### Verified after the patch (deployed API and page, read-only)

- **OFS:** Ariel Hukporti, Ben Simmons and Henri Veesaar are
  `EXCLUDED_STATUS`, "EXCLUDED (YAHOO O/OFS/NA)", "Current Yahoo status: Out
  For Season", and are absent from `eligible_candidate_ids` and from every
  board and transactions response in all three windows. Eligible 299 (was
  302), `EXCLUDED_STATUS` 272 (was 269), other teams 158, manager 15;
  refresh evidence "318 explicit statuses".
- **Jrue Holiday:** `ROSTERED_BY_OTHER_TEAM` (Pick And Roll, BN); absent from
  every response and page section; his impact request returns 409 "Player
  is already rostered in the selected league".
- **Gate text:** WATCH pairs read, for example, "Sample gate: DeMar DeRozan 4
  games in the last 14 days; Bones Hyland 6 games in the last 14 days" and
  "Yahoo status gate: DeMar DeRozan blank (UNKNOWN); Bones Hyland blank
  (UNKNOWN)"; Season Evidence reads "Sample gate: Max Strus 5 games this
  season". The page shows the backend's exact strings (compared with the API
  response in the browser in every window).
- **Refresh verification:** `GET /api/v1/waivers/refresh` reports NBA season
  stats as "467 regular-season rows (2026-27)".
- **Mobile:** at 390 x 844 with "Why? Roster capacity details" (and the team
  needs details) open, `scrollWidth` = `innerWidth` = 390 (was 589).
- **Decisions unchanged:** HOLD in all three windows with the same best
  measured option, groups, watchlists and WATCH pairs (same net values) over
  7,423 pairs; capacity 13 of 13 regular, IL 2 of 3, ROSTER FULL, 2 of 4 adds
  left, waiver priority 4th. One Season Evidence reason count moved from
  7,143 to 7,140 pairs because OFS is now a recognized status.
- **Page acceptance (GET-only):** desktop 1440 x 1000 5/5 and mobile 5/5,
  axe 0 violations, keyboard focus return, no raw 504 HTML, no page-level
  overflow, 0 non-GET requests.
- **Refresh panel after the recreate:** the job record lived in API memory,
  so the panel now reads "All waiver evidence current as of: November 14,
  2026 at 12:32 AM PST" (source `persisted_evidence`, all 9 sources current)
  instead of "Last successful complete refresh". This is by design; no
  refresh was run.
- **Host capacity:** the host thrashed again during page acceptance (I/O
  full pressure up to about 60%). Some reads took 389 s and nginx returned
  504s at 60 s; one board read returned 500 when asyncpg's 60 s connect
  timeout expired while the new API container opened a database connection.
  Tests rerun on a quiet host passed. Not a code regression; no timeouts were
  raised.

### Phase 5 deployment (08:26 UTC)

- `api` and `frontend` were recreated 08:26 UTC (API started 08:26:53, 0
  restarts); `pre-phase5` rollback image tags exist. At the start of
  acceptance the running API source was byte-identical to the worktree (69
  files, SHA-256), nginx config identical, and the frontend bundle identical
  when built with the deploy argument (`index-BHrjSLrE.js`).
- The fixes below were local at acceptance time and were deployed at 11:40
  UTC (see Patch deployment above).

### What the refresh persisted (verified independently in PostgreSQL)

| Stage | Fetched → persisted | Verified evidence |
|---|---|---|
| LEAGUE_SETTINGS | 13 → 14 | league, settings and 12 teams at 08:31:32.116 UTC |
| PLAYER_POOL | 744 → 744 | pool and 12 roster snapshots at 08:31:50.093 UTC |
| LEAGUE_ROSTERS / ROSTER_SLOTS | 173 → 173 | 12 of 12 teams; every row has a slot; Box Score Bully 15 |
| YAHOO_AVAILABILITY_STATUS | 744 → 744 | 315 explicit statuses; Yahoo FA/W state not supplied |
| NBA_TEAMS_PLAYERS | 559 → 559 | 30 teams + 529 players at 08:32:14.536 UTC |
| NBA_SCHEDULE | 1,274 → 50,293 | 1,274 games + 49,019 player rows (to 2027-04-11) |
| NBA_GAME_LOGS | 4,467 → 4,467 | 4,126 regular-season logs 2026-10-20..2026-11-13 |
| NBA_SEASON_STATS | 1,626 → 1,626 | 2026-27: 467 regular season + 577 preseason; 2025-26: 582 |
| POST_REFRESH_VERIFICATION | 11 of 11 | 46 Yahoo requests, 0 practice-league requests, 0 transactions |

Mixed units are expected (league + settings + teams; games + player rows).
All nine November 13 games are Final with logs. Practice leagues untouched.

### Team and decision (persisted data, all three modes)

- Roster (matches the user's Yahoo page): PG Kris Dunn, SG Keyonte George,
  G Bones Hyland, SF Norman Powell, PF Cameron Johnson, F Zach LaVine, C
  Pascal Siakam, C P.J. Washington, UTIL Jarrett Allen, UTIL Julius Randle,
  BN Luka Dončić (P), BN Dillon Brooks, BN RJ Barrett, IL Stephen Curry (O),
  IL Lauri Markkanen (O). **ROSTER FULL — AN ADD REQUIRES A DROP**: 13 of 13
  regular spots, IL 2 of 3 (one open), no IL move available.
- Weekly adds 2 of 4 used (2 left, Yahoo week 4); waiver priority 4th.
- Availability: 302 `UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT` (eligible),
  158 other teams, 15 manager, 269 `EXCLUDED_STATUS` (299 / 272 with the
  local OFS fix). Invariant: 0 violations on the API (all modes, every
  featured surface) and on the page. Jrue Holiday is `ROSTERED_BY_OTHER_TEAM`
  (Pick And Roll) and appears nowhere.
- Decision: **HOLD** in Rest of Week, Next 7 Days and Season Evidence (7,423
  pairs each). Best measured: DeMar DeRozan (Rest of Week, Next 7 Days),
  Santi Aldama (Season Evidence). Top WATCH pairs: DeRozan / Hyland (+0.85,
  Rest of Week), DeRozan / Dunn (+1.13, Next 7 Days), Max Strus / Hyland
  (+0.22, Season Evidence).
- Main blocker: blank Yahoo status (UNKNOWN) fails every positive pair in
  every mode and is the only blocker for 13 Next 7 Days and 36 Season
  Evidence pairs; next is the sample gate (7 games this season and, in weekly
  windows, 7 in the last 14 days; Hyland and Dunn have 6). This is Yahoo's
  blank-for-no-designation convention meeting the deliberate fail-closed
  rule, not a defect; changing it is a product decision.
- Measured PPG is shrunk toward 2025-26 (n/(n+10)): DeRozan measures 26.5
  but averaged 15.8 over his last 4 games; Nikola Vučević measures 22.7 on
  8.6 actual. Labeled, by design.

### Defects found and fixed (deployed 2026-11-14 11:40 UTC)

1. **Yahoo status normalization:** `OFS` ("Out For Season" in persisted
   `status_full`) was unrecognized, so 3 OFS players were eligible and
   labeled "OFS · UNKNOWN", and an OFS roster player would count as
   lineup-eligible. OFS is now a verified excluded status (O/OFS/NA).
2. **Gate explanations:** WATCH pairs said "Below seven supported
   current-season games" for 12-game adds when the failing count was the
   drop's 6 games in the last 14 days, and never mentioned the status gate;
   the WATCH list rebuilt "Why not add" in the browser. Notes now name the
   player and window plus each unverified status; the UI shows them.
3. **Refresh verification:** season-stats checks counted preseason rows the
   model never reads (1,044 reported, 467 usable); a refresh without
   regular-season stats would have passed. Checks now count Regular Season.
4. **Mobile overflow:** opening "Why? Roster capacity details" widened a
   390 px page to 589 px (flex item `min-width: auto` around the slot
   table). Fixed with `min-width: 0`.

Real-data recheck with the fixed source (read-only, 235 SELECTs): eligible
299, `EXCLUDED_STATUS` 272, OFS players excluded in every mode, notes such as
"Sample gate: Bones Hyland 6 games in the last 14 days", season stats "467
regular-season rows (2026-27)", decisions unchanged.

### Validation

- Backend **404 passed** (6 new regression tests); frontend unit **55/55**,
  `tsc -b` and build passed; fixture Playwright **42/42** (desktop + mobile).
- Deployed page, GET-only (0 non-GET requests): desktop and mobile refresh
  panel, TEAM SITUATION, BEST MOVES, OTHER GOOD OPTIONS, COMPARE A SPECIFIC
  DROP (exact drop 10263), FULL WAIVER LIST (302 rows, no rostered player),
  ADVANCED EVIDENCE counts, keyboard focus return and simulated 504 passed;
  axe 0 violations. Mobile failed only the overflow check (defect 4) on the
  pre-patch build; it passes after the patch.
- Performance (deployed, normal load): board 2.6-3.6 s, transactions
  2.6-3.6 s, replacements 2.6-4.0 s, impact 1.7-3.0 s; board 1.16 MB. Fixed
  and deployed sources measure the same (2.3-2.5 s weekly board compute).

### Host capacity (environment, not an application change)

The 7.3 GB shared host repeatedly ran out of memory during acceptance (swap
2.4-3.1 GB, I/O full pressure up to 78%). The single API worker sat in
uninterruptible disk wait; reads took 13-48 s and at worst 218-340 s, so
nginx returned real 504s at 60 s. The page showed WAIVER ANALYSIS TIMED OUT
with the request ID and no HTML, as designed. Proxy timeouts were not changed.

# One-Click Waiver Refresh & Authoritative Availability — 2026-11-14

**STATUS AT THE TIME: IMPLEMENTED AND TESTED LOCALLY / NOT DEPLOYED / EVIDENCE
NOT REFRESHED.** Superseded the same day: deployed 08:26 UTC and refreshed
08:31-08:33 UTC (see CURRENT STATE above). Model `waiver-availability-phase5` adds one backend-owned
**REFRESH WAIVER DATA** workflow, Yahoo availability classes with a hard
recommended-subset-of-eligible invariant, weekly-adds and waiver-priority
context, structured timeout handling and faster waiver reads. Production
still runs `waiver-capacity-phase4` with 2026-10-25 rosters and NBA data.
Every production check in this record was read-only; deployment and the first
refresh wait for explicit authorization.

### Root causes

1. **No single refresh owner.** Making the Waiver Center current took three
   manual POSTs plus a reload. On 2026-11-14 at 03:39 UTC only
   `POST /api/v1/leagues/import` succeeded; the players import was never run
   and `POST /api/v1/nba/import?recent_days=30` failed with HTTP 500, so
   rosters, slots, statuses and NBA data stayed at 2026-10-25.
2. **Import defects** (first found 2026-11-13): an unscoped players import
   also sent 9 local Yahoo Mock Practice pseudo-leagues to Yahoo, and the
   all-or-nothing import saved nothing; the NBA game-log upsert exceeded
   PostgreSQL's 32,767 bind parameters and rolled back the whole NBA import.
3. **Availability inferred from stale absence.** With stale rosters the
   deployed model still featured players "not on any saved roster" as BEST
   MEASURED OPTION and OTHER GOOD OPTIONS (Jrue Holiday first). Yahoo's
   current available-player list does not include him.
4. **504 page rendered raw.** Under the post-refresh workload the weekly board
   and best-move reads each took about 7 seconds of single-worker analysis and
   the board returned 6 MB; overlapping reads on the shared host passed
   nginx's 60-second limit (proxy log: 499 and 504 at 60 s). The client used
   any non-JSON error body as the message, so the full nginx HTML appeared in
   TEAM SITUATION and BEST MOVES.
5. **Acquisition context ignored.** The persisted, already-supported Yahoo
   teams payload carries `waiver_priority` and `roster_adds`; they were never
   normalized.

### Implementation

- `POST /api/v1/waivers/refresh` (202) and `GET /api/v1/waivers/refresh`
  (database-only status): ten ordered stages, per-stage results and
  verification, overall SUCCEEDED / PARTIAL_FAILURE / FAILED, retry of failed
  boundaries only, one active job, and a PostgreSQL advisory lock shared with
  the manual import routes (409 `PROVIDER_IMPORT_IN_PROGRESS`). No table or
  migration was added.
- Yahoo import split into fetch, validate (every team roster and every
  `selected_position`) and one-transaction persist with stamped-count
  verification; practice leagues excluded by three discriminators; naming one
  returns 422. NBA import split into fetch and one-transaction persist, with
  every multi-row upsert batched at 500 rows and in-transaction count
  verification (502 on mismatch).
- Availability classes, the recommendation invariant (backend 500
  `RECOMMENDATION_CONTRACT_VIOLATION`; UI WAIVER MODEL CONTRACT ERROR),
  actionable-only featuring, separate potential targets and the
  `POTENTIAL_TARGETS` state (NO CONFIRMED AVAILABLE PLAYER).
- Acquisition context in TEAM SITUATION; structured client errors, WAIVER
  ANALYSIS TIMED OUT with RETRY ANALYSIS / REFRESH WAIVER DATA, `X-Request-ID`
  through nginx and the API, `Server-Timing` and one `request_timing` log line.
- Waiver read performance (same host and data, post-refresh workload):
  weekly board 6.4-7.1 s / 6.1 MB → 1.8-2.1 s / 1.1 MB; best-move
  transactions 6.9-7.1 s → 1.8-1.9 s; replacements 4.9-5.3 s → 1.5-2.0 s;
  impact 3.4-3.7 s → 1.0-1.3 s; Season Evidence 4-10 s → about 2-6 s. Each
  read issues 17 read-only statements, no writes and no provider calls.

### Current real-data result (read-only, new code, all three modes)

- Evidence: league/settings current (2026-11-14 03:39 UTC, Driveway Dudes, 12
  teams); player pool (744), all 12 roster snapshots, slots (0 of 13 saved)
  and NBA data (latest game 2026-10-24) stale since 2026-10-25.
- Saved Box Score Bully roster (2026-10-25): 13 players, no slot saved: DeMar
  DeRozan, Dillon Brooks, Jarrett Allen, Julius Randle, Keyonte George, Lauri
  Markkanen, Luka Dončić, Norman Powell, P.J. Washington, Pascal Siakam, RJ
  Barrett, Stephen Curry (P) and Zach LaVine. The user's current Yahoo roster
  has 15 (13 regular + Curry and Markkanen in IL): DeRozan is gone and Kris
  Dunn, Bones Hyland and Cameron Johnson are new. Persisted data cannot show
  this until a refresh.
- Capacity: ROSTER CAPACITY NEEDS A YAHOO REFRESH (stale snapshot; 0 of 13
  slots), INSUFFICIENT EVIDENCE, no drop assumed.
- Availability: 0 of 12 snapshots current; 309 `SOURCE_STALE`, 152
  `ROSTERED_BY_OTHER_TEAM`, 13 `ROSTERED_BY_MANAGER`, 270 `EXCLUDED_STATUS`;
  0 eligible candidates.
- Decision support: state POTENTIAL_TARGETS ("No player is confirmed available
  yet."); no supported move, best measured option, group pick or watch
  player. Potential targets (top 10 of 192, SAVED ROSTERS STALE — CHECK IN
  YAHOO): Jrue Holiday, Nikola Vučević, Keegan Murray, Jerami Grant, Isaiah
  Collier, Bilal Coulibaly, Bennedict Mathurin, Scotty Pippen Jr., Kelly Oubre
  Jr. and Deandre Ayton. The deployed build features eight of them as
  BEST MEASURED OPTION or group picks.
- Acquisition context: waiver priority 4th; 2 of 4 weekly adds used in Yahoo
  week 4 (2 left), from the 03:39 UTC league import. Matches the user's Yahoo
  page.
- Read-only harness: 109 read statements, 0 writes, 0 provider attempts.

### Validation

- Backend full suite **398 passed** (disposable PostgreSQL 16, internal
  network), including 8 refresh-orchestration tests, availability-class,
  invariant, 13 + 2 IL, acquisition and request-timing tests and a >4,095-log
  NBA import.
- Frontend: TypeScript and Vite build passed; unit **54/54**; waiver
  Playwright **40/40** (desktop 1440 and mobile 390, axe, keyboard focus
  return, GET-only except the refresh POST).
- `nginx -t` passed; a throwaway nginx + stub upstream confirmed one
  `X-Request-ID` per proxied response, the same ID upstream and the header on
  nginx's own error page.
- No deployment, rebuild, provider request, OAuth action, migration, database
  write, Yahoo transaction, commit or push occurred.

### Deployment and refresh acceptance (completed 2026-11-14; see CURRENT STATE)

Plan: take a private `pg_dump` archive backup; rebuild and recreate only `api`
and `frontend` (no migration); confirm `waiver-availability-phase5` and the
refresh status; click **REFRESH WAIVER DATA** once; then verify persisted
timestamps and counts, the 13 regular + 2 IL roster against Yahoo (Curry and
Markkanen in IL, one open IL slot), candidate availability against Yahoo's
available-player list (Jrue Holiday not recommended unless current Yahoo
evidence confirms him), current NBA logs/schedule/stats, all three modes, no
raw 504 HTML and zero Yahoo transactions. Exact commands are in
[next actions](next-actions.md).

## Post-Deployment Waiver Acceptance — 2026-11-13 (Pacific; 2026-11-14 UTC)

**STATUS: DEPLOYED / EVIDENCE NOT REFRESHED.** Phase 4 and the decision-support
redesign (`waiver-capacity-phase4`) are deployed and verified. The Yahoo
player/roster refresh and the NBA refresh that followed **failed and
persisted nothing**, so the page still reflects 2026-10-25 rosters, Yahoo
statuses and NBA data. Two import defects and one display defect were fixed
locally (**validated locally / not deployed**). All checks were read-only.
Superseded on 2026-11-14: these fixes shipped with Phase 5 (deployed 08:26
UTC) and the refresh then succeeded; see CURRENT STATE.

### Deployment verification

- API image built 2026-11-13 23:57:15 UTC and frontend image 23:59:21 UTC;
  containers recreated 23:59:33 / 23:59:54 UTC.
- The running API's waiver, players-import and Yahoo-roster sources are
  byte-identical to the worktree (SHA-256); the served bundle contains the
  final page text and none of the removed Phase-4 headings.
- `GET /api/v1/waivers` reports `waiver-capacity-phase4` in all three modes.

### What the refreshes persisted

| Request (UTC, proxy log) | Result | Persisted |
|---|---|---|
| `POST /api/v1/leagues/import` 00:00:22 | 502 (API still starting) | nothing |
| `POST /api/v1/leagues/import` 00:00:43 | 200 | league, settings and 12 teams at 00:00:42 |
| `POST /api/v1/players/import` (no `league_key`) 00:02:41 | 502 "Yahoo Fantasy API rejected the league request" | **nothing** |
| `POST /api/v1/nba/import?recent_days=30` 00:06:01 | 500 (bind-parameter limit) | **nothing** |

- Settings (current): `PG SG G SF PF F C×2 Util×2 BN×3 IL×3` — 13 regular
  spots plus 3 IL.
- Still 2026-10-25 18:20 UTC: all 165 league roster rows (**0 with a saved
  slot**), every `fantasy_teams` snapshot and the 744-row player pool.
- Still 2026-10-25 19:04 UTC: NBA game logs (latest game 2026-10-24; 812
  regular-season logs), season stats (388 rows for 2026-27, 1–3 games),
  schedule and games.

### Root causes

1. **Unscoped players import includes local practice leagues.** Without
   `league_key` the import selects every persisted league, including 9 local
   Yahoo Mock Practice pseudo-leagues (`yahoo-mock-practice.*`). Those keys
   cannot exist in Yahoo; the API log records "Yahoo Fantasy API rejected
   request" at 00:02:41.597 (a non-401 4xx). All fetching precedes the single
   write transaction, so the already-fetched `478.l.50505` rosters were
   discarded too. The **Refresh Yahoo baseline** button passes the league key
   and is unaffected.
2. **Oversized NBA upsert.** `import_game_logs` sent every log in one
   8-column multi-row INSERT; a 30-day window holds more than 4,095 logs, so
   asyncpg rejected it at 32,767 parameters. The NBA import is one
   transaction, so teams, players, schedule and stats rolled back as well.
3. **Display:** FULL WAIVER LIST counted only O/NA players with confirmed
   availability, so it read "0 Yahoo O/NA players excluded" while 270 were
   excluded.

None of these is a capacity, decision-support or evidence-gate defect: with
stale rosters the capacity engine correctly fails closed.

### Fixes (validated locally / not deployed)

- `features/players/service.py`: the import never selects
  `yahoo-mock-practice.*` leagues; naming one returns 404.
- `services/nba/game_logs.py`: game logs upsert in batches of 500 rows (the
  schedule importer's existing batch size).
- `WaiverCenter.tsx`: the O/NA count adds decision support's unverified O/NA
  count to `excluded_count`.
- Regression tests: both new backend tests fail on the pre-fix code with the
  exact production errors (502 rejection; 32,767-parameter `InterfaceError`)
  and pass after the fix; the unit test asserts the summed O/NA count.

### Current real-data result (all three modes)

- Capacity **ROSTER CAPACITY NEEDS A YAHOO REFRESH**: the roster snapshot
  predates the 00:00:42 settings import, and `selected_position` is missing
  for 13 of 13 players. Open spots, IL state, adds without a drop and
  `requires_drop` are unknown; no drop is assumed.
- Needs (stale basis): Guard, Wing/Forward and Center COVERED; no schedule
  gaps can be computed (stale schedule).
- Supported moves: none (INSUFFICIENT EVIDENCE).
- BEST MEASURED OPTION: Jrue Holiday (PG/SG), 30.5 measured PPG, AVAILABILITY
  UNVERIFIED, status UNKNOWN; groups Isaiah Collier, Keegan Murray (Q), Nikola
  Vučević, Jerami Grant, Bennedict Mathurin / Scotty Pippen Jr. (short-term),
  Bilal Coulibaly (longer-term); WATCHLIST empty; 10 of 192 potential targets.
- Availability: 0 confirmed, 192 comparable availability-unverified, 579
  pool players unknown, 152 on other saved rosters, 270 O/NA excluded; among
  comparable options 183 blank (UNKNOWN), 7 Q, 2 P; 0 unresolved among the 17
  featured players.
- Injury case: the persisted roster shows no injured player — only Stephen
  Curry has an explicit status (P) and no player lists IL eligibility. The two
  injuries reported by the user are not in persisted evidence yet.

### Validation

- Deployed API (GET only): every invariant passed in all three modes;
  per-table insert/update/delete counters for all 29 tables were unchanged
  across the API suite and both browser runs; the API container opened no
  new outbound :443 connection (one pre-existing CLOSE_WAIT socket from an
  earlier import).
- Deployed page: **6/6** (desktop 1440 / mobile 390 × three modes): section
  order, first recommendation above the fold, collapsed sections, muted
  compare tool with no drop preselected, keyboard focus return, no overflow,
  zero axe violations, GET-only, same-origin only. Two desktop cases first
  hit nginx 504s (60-second proxy timeout) while the shared host was under
  swap/IO pressure from the browser tooling and passed on rerun.
- Instrumented read-only replica of the same source: decision support,
  capacity, needs and transactions identical to the deployed API; 510
  SELECT, 0 commits, 0 blocked statements, 0 provider attempts. Local
  real-data UI with the fixes: 2/2 (Rest of Week, "270 Yahoo O/NA players
  excluded").
- Backend full suite **380 passed**; frontend unit **47/47**, waiver
  Playwright **28/28**, TypeScript and build passed.
- No deployment, rebuild, Yahoo/NBA refresh, OAuth action, migration,
  database write, Yahoo transaction, commit or push occurred during
  acceptance.

### PASS/FAIL (real data)

| | Check | Result |
|---|---|---|
| A | Current `selected_position` persisted | FAIL — players import failed; 0/165 slots |
| B | Capacity not UNDETERMINED solely for missing slots | FAIL — still undetermined (stale snapshot + missing slots) |
| C | Injured/IL players recognized | FAIL — not evaluable on 2026-10-25 data |
| D | Open capacity → ADD ONLY | PASS in tests; not exercised by real data |
| E | IL move → MOVE TO IL THEN ADD | PASS in tests; not exercised by real data |
| F | Full roster → ADD + DROP | PASS in tests; not exercised by real data |
| G | No drop preselected | PASS |
| H | Practical targets in BEST MOVES | PASS (best measured option, groups, targets) |
| I | Availability reflects refreshed rosters | FAIL — rosters not refreshed |
| J | Current NBA evidence used | FAIL — NBA import rolled back |
| K | Analysis read-only | PASS |
| L | No provider calls during waiver GETs | PASS |
| M | No Yahoo transaction | PASS |

## Decision Support & Decision-First Redesign — 2026-11-13

**STATUS AT THE TIME: VALIDATED LOCALLY / NOT DEPLOYED** (model version
unchanged: `waiver-capacity-phase4`). Deployed 2026-11-13 23:59 UTC; see the
post-deployment acceptance above. Its deploy step is complete; its refresh
steps are not.

When strict evidence gates fail, the Waiver Center now still names the best
measurable target to check in Yahoo instead of showing nothing useful. A
separate non-actionable layer classifies players as SUPPORTED ACTION, BEST
MEASURED OPTION, WATCH, MEASURED or UNAVAILABLE with a backend
`decision_rank`; the strict Phase-4 actions, evidence gates, exact ADD + DROP
and no-drop comparison equalities, database-only reads and structured 409
errors are unchanged. The page follows the six-section hierarchy TEAM
SITUATION → BEST MOVES RIGHT NOW → OTHER GOOD OPTIONS → COMPARE A SPECIFIC
DROP → FULL WAIVER LIST → ADVANCED EVIDENCE. Rules are in
[project memory](../project-memory.md) and the
[README](../../README.md#decision-support-when-strict-gates-fail); the dated
record is the [2026-11-13 session](../sessions/2026-11-13.md).

### Root causes found by the audit

- Strict actions were the only output channel. With no supported add, BEST
  MOVE showed only HOLD or INSUFFICIENT EVIDENCE, and nothing ranked
  measurable players that failed a gate.
- Unknown-availability players were never listed: with stale league rosters
  the board had 0 candidates while 579 pool players were unknown and 192
  of them were measurable.
- Stale league settings emptied the scoring fields, so no production could be
  measured even though the persisted formula had passed the contract check;
  team needs also lost all slot counts.
- Weekly modes had no recent production (no persisted games in the last 14
  days; the latest game is 2026-10-24) and 2026-27 rows have only 1–3 games,
  with no blended comparison to fall back on.
- Diagnostics led the page: capacity blockers, raw need scores including
  UTIL/bench, coverage tables and an expanded full list came before any
  decision.

### Implementation

- New `backend/app/features/waivers/decision_support.py`: measured
  production (14-day or current-season sample shrunk toward prior season
  with n/(n+10); at least 4 games without prior history), comparability
  reasons, sequential best-measured picks by capacity shape, distinct group
  picks, WATCHLIST, potential targets, ranks, why/blocker/confirm text.
- `capacity.py`: plain-language capacity headline and short reason;
  HIGH/MEDIUM/COVERED needs by Guard, Wing/Forward and Center with depth and
  basis notes. `service.py`: persisted-formula measurement and persisted slot
  needs when settings are stale, an evidence-freshness summary (one extra
  aggregate SELECT) and decision support on every board without an explicit
  drop. Contracts and frontend types add the new fields.
- `WaiverCenter.tsx`/`styles.css`: the six-section page; supported move
  cards first, BEST MEASURED OPTION cards with NOT YET A SUPPORTED ADD and
  CHECK IN YAHOO, grouped options, potential targets, muted/promoted compare
  tool, collapsed full list with eight filters, collapsed advanced evidence.

### Real-data result (read-only, all three modes)

Persisted evidence on 2026-11-13: league, settings and team rows were
refreshed at 21:05 UTC by a leagues-only import on the deployed (old) app;
rosters and the player pool are still from 2026-10-25 18:20 UTC and NBA
logs, stats and schedules from 19:04 UTC.

- Capacity: **ROSTER CAPACITY NEEDS A YAHOO REFRESH** — "Your saved roster
  is from 2026-10-25; Yahoo roster slots are not saved for 13 of 13
  players." Blockers: stale roster snapshot; `selected_position` missing for
  13/13. Needs (stale basis): Guard, Wing/Forward and Center all COVERED.
- Supported moves: none (INSUFFICIENT EVIDENCE; 0 pairs, 0 additions).
- BEST MEASURED OPTION: **Jrue Holiday** (PG/SG), 30.5 measured Yahoo
  fantasy PPG from 2 current-season games blended with 2025-26 (31.5),
  1/4/69 scheduled games (Rest of Week/Next 7 Days/Season, stale schedule),
  status UNKNOWN, AVAILABILITY UNVERIFIED, would rank 10 of 14 on the roster.
  Blockers: undetermined capacity, unverified availability, blank status
  from a stale import, 2-game sample (7 needed), stale production, no games
  in the last 14 days (weekly modes), stale roster.
- Groups: Isaiah Collier (guard), Keegan Murray (wing/forward), Nikola
  Vučević (center), Jerami Grant (multi-position), Bennedict Mathurin (Rest of
  Week) / Scotty Pippen Jr. (Next 7 Days) short-term, none in Season
  Evidence, Bilal Coulibaly (longer-term). WATCHLIST empty: nobody else
  out-produces the lowest roster player (27.2 PPG).
- POTENTIAL TARGETS: 192 comparable unverified players; the top 10 are led
  by Scotty Pippen Jr., Kelly Oubre Jr. and Deandre Ayton (Mathurin leads in
  Next 7 Days and Season Evidence). Not comparable: 270 O/NA, 82 without
  current-season games, 35 under 4 games without prior history, 152 on
  another team's saved roster.

### Validation

- Backend full suite **378 passed** (14 new decision-support tests; one
  existing assertion updated for stale-settings needs).
- Frontend: TypeScript and Vite build passed; unit tests **47/47**; waiver
  Playwright **28/28** (14 scenarios × desktop 1440/mobile 390), including
  the six-section order, collapsed sections, no preselected drop,
  recommendations above the fold at 1440px, keyboard focus return, 409
  errors, zero writes and axe.
- Real-data acceptance used the read-only local-source server (read-only
  sessions, read-only statement guard, provider entry points patched to
  fail). API check: all invariants passed in all three modes; 17 featured
  identities verified resolved and not O/NA; 510 SELECT, 0 commits,
  0 blocked statements, 0 provider attempts. Browser: **6/6** (desktop and
  mobile × three modes) with zero non-GET requests, zero foreign hosts, no
  overflow and zero axe violations. Desktop Rest of Week passed on a
  targeted rerun after its first attempt timed out in the final axe scan
  while the shared host was under heavy swap/IO pressure.
- No deployment, rebuild, provider refresh, OAuth action, migration,
  database write, Yahoo transaction, commit or push occurred.

### Remaining blockers

- Deploy, then run the **full** Refresh Yahoo baseline (the 21:05 UTC
  leagues-only import did not refresh rosters or the player pool, and the old
  app cannot persist `selected_position`), then the NBA import. Until then
  capacity stays undetermined, availability unverified and production stale.
- Blank Yahoo status (12 of 13 roster players) keeps blocking supported
  actions by design; transaction legality, game-level usage/starts, schedule
  completeness and acquisition context remain open evidence gaps.

## Phase 4: Waiver Roster Capacity & Team Needs — 2026-11-13 (earlier)

**STATUS AT THE TIME: VALIDATED LOCALLY / NOT DEPLOYED** (model
`waiver-capacity-phase4`); deployed 2026-11-13 23:59 UTC with the redesign.
Its page order below was superseded the same day by the decision-first
redesign above; the capacity and action behavior is unchanged.

The Waiver Center now decides whether an add needs a drop before ranking
players. Capacity comes only from persisted Yahoo roster positions and
persisted Yahoo slot assignments. Actions are **ADD ONLY**, **MOVE [player]
TO IL THEN ADD**, **ADD + DROP**, **WATCH**, **HOLD** and **INSUFFICIENT
EVIDENCE**; stale, missing or conflicting capacity evidence fails closed to
INSUFFICIENT EVIDENCE with exact blockers and no assumed drop. The Yahoo
points formula, sample/status/freshness gates, manager-team protection,
ADD + DROP exact-pair equality and the database-only read boundary are
unchanged. Durable rules are in [project memory](../project-memory.md); the
operator description is in the [README](../../README.md); the dated record is
the [2026-11-13 session](../sessions/2026-11-13.md).

### Root causes found by the audit

- **Slot assignments were never persisted.** Yahoo returns each roster player
  as `[[metadata fragments], {"selected_position": [...]}]`. The generic record
  extractor kept only the metadata, and `_roster_position` could not parse
  the fragment-list form, so `rosters.roster_position` was NULL for all 165
  persisted roster rows (13/13 for Box Score Bully). The previous test used a
  synthetic flat shape.
- **Capacity was assumed, not measured.** NULL slots were treated as
  non-injury spots, so the roster always looked full; the optimizer always
  evaluated ADD × DROP pairs (7,527 per mode); the UI preselected the first
  roster player as the drop; the direct injury-slot rule was display-only.
- Stale capacity evidence produced success-shaped HOLD instead of
  INSUFFICIENT EVIDENCE; lineup coverage counted O/NA players; impact without
  a drop silently used the best measured drop; team needs were one sentence.
- Documentation said Source Integrity was not deployed, but the running API
  and frontend images (built 2026-11-13 16:54Z/16:57Z) match commit `93fd50f`
  by source hashes and bundle content. Source Integrity is deployed; Phase 4
  is not.

### Implementation

- Yahoo roster import keeps the `selected_position`/`starting_status` sibling
  blocks (`extract_roster_player_records`); `_roster_position` parses the
  fragment-list form. Existing rows are corrected only by Refresh Yahoo
  baseline.
- New `backend/app/features/waivers/capacity.py` owns roster capacity
  (occupancy, open spots, IL moves and blockers, fail-closed blockers) and
  team needs (open/injury-weakened starting slots, per-date gaps, coverage,
  production context, hold guidance).
- `service.py` evaluates pairs only for ADD + DROP, builds a sequential
  no-drop fill plan for open capacity, adds the no-drop comparison, action
  types/labels, decision priority, option groups and lineup slot-days gained,
  and returns INSUFFICIENT EVIDENCE when capacity is UNDETERMINED.
- Contracts and frontend types add `roster_capacity`, `team_needs_analysis`,
  `option_groups`, action fields and addition counts. The UI is reordered to
  TEAM SITUATION → WHAT YOUR TEAM NEEDS → BEST MOVE RIGHT NOW → OTHER OPTIONS
  (optional Compare a specific drop, never preselected) → FULL WAIVER LIST →
  ADVANCED EVIDENCE.

### Current persisted evidence (read-only, 2026-11-13)

- Every Yahoo import (league, settings, teams, rosters, player pool) is from
  2026-10-25 18:20 UTC and NBA logs/schedules/stats from 19:04 UTC, so all are
  stale for waiver decisions.
- Driveway Dudes roster positions: `PG SG G SF PF F C C UTIL UTIL BN BN BN IL
  IL IL` (13 non-injury + 3 IL). Box Score Bully has 13 players, one explicit
  Yahoo status (P) and **no persisted slot assignments**.
- Result in all three modes: capacity **UNDETERMINED** (state stale),
  `requires_drop=null`, occupancy unknown, 13 unassigned players, three
  blockers (stale settings, stale roster snapshot, `selected_position` missing
  for 13/13), legality unavailable, team needs stale with null starting-slot
  counts. The board returns **INSUFFICIENT EVIDENCE** with 0 candidates
  (579 pool players have unknown availability because the league rosters are
  stale). Transactions: INSUFFICIENT EVIDENCE, 0 pairs, 0 additions. Impact
  without a drop returns no comparison; an explicit drop returns an ADD + DROP
  comparison with null net improvement. Other-team requests return 422 on all
  four endpoints.

### Validation

- Backend: focused waiver/Yahoo tests **200 passed**; full suite
  **364 passed**. Both report the one existing Starlette/httpx deprecation warning.
- Frontend: strict TypeScript and Vite build passed; unit tests **45/45**;
  waiver Playwright **26/26** (13 scenarios × desktop/mobile, including axe,
  zero writes, ADD ONLY, IL move, multiple open spots, full roster,
  HOLD/WATCH and undetermined capacity).
- Real-data acceptance ran the local source in a temporary server that loads
  only the waiver router. The database session defaulted to read-only, a
  statement guard allowed reads only, and Yahoo/NBA/HTTP entry points were
  patched to fail. A GET-only API check covered all modes and endpoints.
  Browser acceptance passed **6/6** (desktop/mobile × three modes) with zero
  non-GET API requests, zero foreign hosts, no horizontal overflow and zero
  axe violations; the compare tool stayed collapsed with no drop preselected.
  Server counters: 736 SELECT, 4 SHOW, 0 blocked statements, 0 commits,
  0 provider attempts.
- No deployment, image rebuild, service restart, migration, provider request,
  OAuth action, database write, Yahoo transaction, commit or push occurred.

### Remaining gaps

- Real roster capacity for Box Score Bully cannot be established until
  Refresh Yahoo baseline persists current slot assignments, which requires the
  new import code to be deployed first.
- Blank Yahoo status (439 pool observations; 12 of 13 roster players) remains
  UNKNOWN and blocks strong actions, so fresh data may still yield WATCH or
  INSUFFICIENT EVIDENCE for many candidates. This gate is intentionally
  unchanged.
- Transaction legality (roster/game-time locks, claim timing, weekly adds,
  live IL eligibility) is unverified; every action requires Yahoo
  confirmation.
- Game-level usage/starts, schedule completeness and acquisition context
  remain the open evidence gaps listed in [next actions](next-actions.md).

## Historical: Waiver Source Integrity & Coverage — 2026-10-26

**STATUS AT THE TIME: VALIDATED LOCALLY / NOT DEPLOYED.** Superseded on
2026-11-13: the running images match commit `93fd50f`, so Source Integrity is
deployed. The "NOT DEPLOYED" statements below are historical.

The local changes add backend-owned coverage, grouped DATA GAPS, root-cause
diagnostics, a non-mutating identity worklist, schedule/status source
diagnostics, source-aware reconciliation, Waiver Center evidence presentation
and explicit fail-closed status/identity eligibility. They change local API and
view-model behavior but do not change persisted data or the deployed production
behavior. The separate Phase-3 baseline below remains deployed as recorded in
its historical recheck.

### Closeout summary

- **Implemented:** local coverage and DATA GAP diagnostics, non-mutating
  identity review, explicit status/schedule source quality, and overlapping-
  field-only reconciliation. Recommendation mathematics and persisted rows
  were not changed.
- **Validated:** automated backend, frontend, build, browser and accessibility
  checks passed. Guarded persisted acceptance exercised current local
  status/identity/root-cause logic inside the existing API application boundary
  and matched source hashes and in-memory module provenance.
- **Read-only acceptance:** the existing configured database boundary retained
  its credentials; SELECTs ran in explicit READ ONLY transactions and rolled
  back. Provider calls, persisted writes and commits were zero. Invariants and
  exact optimizer/replacements/impact equality passed.
- **Authority and limits:** Yahoo remains authoritative for fantasy identity,
  configuration, roster and status; persisted NBA sources supply basketball
  inputs. Unknown status, unresolved identity, partial/unknown schedules,
  unsupported game-level usage/starts, and unverified Yahoo matchup/
  acquisition/transaction context remain explicit limitations. A lack of
  overlapping Yahoo/NBA statistics means CROSS-SOURCE COMPARISON UNAVAILABLE.
- **Deployment:** the Source Integrity changes remain local and NOT DEPLOYED;
  the separately recorded Phase-3 baseline remains the deployed application.
- **Next evidence slice:** Slice 1 in [next actions](next-actions.md) covers
  stable identity reconciliation, existing NBA source capability, and schedule
  completeness, with no new provider.

### Source authority and comparison meaning

Yahoo is authoritative for fantasy player identity, league configuration,
scoring rules, roster state, Yahoo player status and fantasy availability.
Yahoo matchup, acquisition and waiver facts require separate verification.
Persisted NBA sources are authoritative for basketball inputs: PTS, REB, AST,
STL, BLK, TOV, MIN, game logs, NBA schedule and supported aggregate usage and
starts. A Yahoo player payload without basketball stats does not imply missing
NBA production, a missing fantasy PPG formula or an incorrect Yahoo points
formula. **CROSS-SOURCE COMPARISON UNAVAILABLE** means there is no second
persisted Yahoo statistical dataset with overlapping basketball fields for
independent cross-source value comparison.

### Dated read-only audit observations

These are observations from the previously inspected persisted snapshot, not a
new query; counts may age and must not be treated as current after the snapshot:

- Yahoo pool: **744** observations; **45** lacked NBA IDs and **2 additional
  linked identities** had Yahoo/NBA team conflicts. No mapping or team change
  was justified.
- The broader earlier audit found that 14 of the 45 unmapped records had
  same-normalized-name NBA candidates with conflicting team evidence; 31 had
  no such record in the inspected NBA player table. These observations are not
  mapping fixes.
- Existing NBA imports include `nba_games`, `player_schedule` and
  player/game identity relationships; prior foundation imports contained tens
  of thousands of player schedule rows. In the inspected waiver snapshot,
  candidates had season schedule rows even when no row applied to the selected
  Rest-of-Week window.
- `NO_PLAYER_SCHEDULE_ROWS` is distinct from an empty requested window. A
  `NO_GAMES_IN_WINDOW` result is not a verified zero without proven source
  completeness. Rows present are PARTIAL; no player rows or an unverified
  empty window are UNKNOWN; stale data is STALE. COMPLETE remains forbidden
  until an explicit completeness manifest/contract is verified. Row counts,
  all 30 teams, date span and opponent presence do not prove completeness.
- A Yahoo-supplied blank status is legitimate UNKNOWN evidence, not healthy,
  an automatic import defect, stale or injured. O/NA remain excluded, Q/P
  uncertain and blank UNKNOWN. Status diagnostics distinguish
  YAHOO_EXPLICIT_STATUS (`STATUS_PRESENT`), YAHOO_SUPPLIED_BLANK,
  STALE_YAHOO_IMPORT (`STALE_PLAYER_POOL_IMPORT`),
  PLAYER_OBSERVATION_MISSING (`MISSING_PLAYER_OBSERVATION`),
  IDENTITY_MAPPING_PROBLEM (`MAPPING_ISSUE`) and NORMALIZATION_DEFECT. Blank
  itself is not a recoverable data issue; stale/missing/mapping/normalization
  causes may indicate one.
- Persisted game logs do not establish supported game-level `USG_PCT`, `GS`
  or `START_POSITION`. Season usage and season starter-filter evidence do not
  substitute for game-level usage or recent starts; minutes do not imply starts.
  Phase 3 remains delivered: qualified minutes can support descriptive role
  while optional usage and starts retain independent unavailable states.
- The historical “0 comparable Yahoo/NBA stat pairs” result means
  **CROSS-SOURCE COMPARISON UNAVAILABLE**, not missing required Yahoo stats or
  NBA production. The earlier `MISSING_REQUIRED_STAT` wording is superseded
  where it implied a production defect.

### Durable safety and implementation status

Mapping requires stable supported evidence, such as EXACT_ID,
EXACT_NAME_TEAM, NORMALIZED_NAME_TEAM, a known alias plus team, or a supported
team change. Never fuzzy-map on name alone, overwrite Yahoo identity fields,
or auto-correct a team. Unresolved states remain reviewable with reasons.

Every UNKNOWN/UNAVAILABLE should carry the most specific supported root cause:
RESOLVABLE_INTERNAL_DEFECT, STALE_EXISTING_SOURCE, MISSING_MAPPING,
MISSING_EXISTING_SOURCE_FIELD, SOURCE_DOES_NOT_SUPPLY,
SOURCE_CONTRACT_UNVERIFIED, REQUIRES_MORE_GAMES, REQUIRES_NEW_SOURCE or
INTENTIONALLY_UNSUPPORTED. Do not label legitimate source absence as an
application bug. Source Integrity preserves the `waiver-evidence-phase3`
scoring formula, Phase-1 sample gates, Phase-2 ADD × DROP optimizer, Phase-3
role method, weights, and optimizer/replacements/impact equality. Unknown
status and unresolved identity now block strong advice and supported PASS
without changing the existing HOLD/WATCH/PASS meaning for eligible pairs.

No additional reviewed source met the current evidence, usefulness and
permission threshold for implementation; this is not a claim that every
possible public API is unusable. Yahoo remains the fantasy source, persisted
NBA data the basketball source, and Fantrax a documented ADP niche only. No new
provider was approved or implemented.

### Validation and deployment status

- Source Integrity automated validation passed locally: focused waiver and
  reconciliation tests **176 passed**; full backend **336 passed**; focused
  frontend **15 passed**; full frontend **39 passed**; strict TypeScript/Vite
  build passed; desktop/mobile Playwright plus axe **18 passed**. Backend
  results include one existing Starlette/httpx deprecation warning. The
  additional root-cause regression passed in an offline container with both
  database URLs set to an unreachable placeholder.
- Final guarded read-only persisted acceptance ran **2026-10-26 09:40:56 UTC
  / 02:40:56 PDT** against the existing persisted database. Current local
  backend source was imported in memory inside a temporary Python child of the
  existing API container; its configured database environment stayed inside
  that boundary. No app lifespan/startup ran. Every SQL statement was guarded,
  the transaction used REPEATABLE READ + READ ONLY and rolled back, and
  provider entry points and HTTP clients were blocked.
- The snapshot contained **744** Yahoo pool observations, **309** eligible
  candidates and **13** configured-roster players. Identity was resolved for
  **697/744**, unresolved for **47/744** (16 AMBIGUOUS, 31 NO_MATCH), including
  **14** same-name candidate team disagreements and **2** linked Yahoo/NBA team
  conflicts. No identity or team row was changed.
- Among eligible candidates, recent production was available for **227/309**
  and missing for **82/309**; Season Evidence was available for **287/309** and
  missing for **22/309**. Neither window had stale records. All **309/309**
  candidates had PARTIAL schedule coverage; no completeness manifest exists.
  Status was explicit for **14/309** and Yahoo-blank for **295/309**. In the
  full pool, the status observations were O **60**, NA **222**, Q **15**, P
  **6**, blank **439**, and **2** unrecognized observations representing one
  distinct token. Blank/unrecognized status remained UNKNOWN.
- Returned DATA GAPS were validated field-by-field for category, cause,
  count, denominator, percentage and reason. They reported identity
  `MISSING_MAPPING` **47/744**; recent production `REQUIRES_MORE_GAMES`
  **82/309**; Season Evidence `REQUIRES_MORE_GAMES` **22/309**; unrecognized
  status `SOURCE_CONTRACT_UNVERIFIED` **2/744**; game-level usage and recent
  game-level starts each `SOURCE_CONTRACT_UNVERIFIED` **744/744**; acquisition/
  matchup context `SOURCE_CONTRACT_UNVERIFIED` **1/1**; and free-agent versus
  waiver-claim state `SOURCE_CONTRACT_UNVERIFIED` **309/309**. Blank status was
  not labeled a defect. Empty/unverified schedule windows were not treated as
  zero games.
- All modes assessed **7,527** pairs and supported **0**. Rest of Week and
  Next 7 Days each returned **186 WATCH** pairs; Season Evidence returned
  **117 WATCH** pairs. Each mode excluded 7,527 pairs, returned HOLD and had
  `best_transaction = null`. Exclusion-reason counts overlap. Across each mode,
  the 26 pairs touching unrecognized status had zero supported actions, zero
  ADD/STREAM actions; unresolved identity had zero supported ADD/STREAM/PASS.
  Unsupported positive comparisons were WATCH or insufficient evidence.
- Exact comparison equality passed for **15** returned top-WATCH pairs (five
  per mode): optimizer == selected-drop replacements == impact, including
  pair identity, decision, blockers, all comparison fields and evidence.
  Reconciliation scanned **744** rows: **0** comparable, **697**
  `NO_COMPARABLE_STAT_FIELDS`, **45** identity mismatches and **2** team
  mismatches; `MISSING_REQUIRED_STAT` was **0**. No Yahoo basketball stat field
  overlapped the persisted NBA fields, so the result is **CROSS-SOURCE
  COMPARISON UNAVAILABLE**, not missing NBA production or fantasy PPG.
- Final safety counters: **47 SELECT**, two `SET TRANSACTION READ ONLY`, one
  repeatable-read setting, zero blocked/non-read statements, zero provider
  calls (Yahoo/NBA/Fantrax/OAuth/HTTP), zero writes, zero commits and two
  rollbacks. Selected-drop/impact equality checks issued no per-pair SQL.
- No deployment, service rebuild/recreation, restart, migration, provider
  request, OAuth action, write, Yahoo transaction action, commit or push
  occurred. The changes remain local and **NOT DEPLOYED**.

## Historical: Waiver Evidence Reliability Recheck - 2026-10-26

The Phase-3 source implementation is now deployed. The API and frontend were
rebuilt and recreated with the existing no-lifespan override; PostgreSQL and
Caddy were not restarted or recreated. Public `/waivers`, the board GET and
`GET /api/v1/waivers/transactions` returned HTTP 200. The board and transaction
contract report `waiver-evidence-phase3`; the transaction result is HOLD with
7,527 assessed pairs, zero supported pairs and six WATCH pairs. The stale-model
warning is absent. Read-only browser acceptance confirmed the persisted roster
and selected-drop comparison flow; selecting a different roster player updated
the replacement context. No ADD was forced or submitted.

The read-only board snapshot contained 309 candidates: 139 had persisted
schedule rows (PARTIAL) and 170 had no schedule rows in the selected window
(UNKNOWN, not zero); 227 had complete player identity mappings and 82 were
missing game logs. Yahoo status was present for 14 candidates and blank in the
persisted pool for 295, which remains UNKNOWN rather than healthy. Live mobile
viewport acceptance at 390 CSS pixels showed no horizontal overflow.

The then-current read-only reconciliation report was run against persisted league
`478.l.50505` inside a transaction explicitly set READ ONLY. It scanned 744
persisted Yahoo pool observations: **0 comparable**, **697 missing required
Yahoo stats** (the old report classification), **45 identity-mapping
mismatches**, and **2 team-mapping mismatches**. The zero-comparable result
means **CROSS-SOURCE COMPARISON UNAVAILABLE**: persisted Yahoo player-pool
payloads did not provide a second statistical dataset with overlapping
basketball fields. It does not indicate missing NBA production, a missing
formula, or an incorrect formula. All four acceptance-name fixtures (Keegan Murray, Bilal
Coulibaly, Kris Dunn and Jrue Holiday) were absent from the persisted candidate
set. Yahoo player-pool observations were imported at 2026-10-25 18:20:50 UTC;
NBA player rows range from 2026-10-09 10:37:52 to 2026-10-25 19:04 UTC; the
persisted NBA stats import is 2026-10-25 19:04 UTC. This was not a completed
cross-source stat-value comparison. No Yahoo/NBA provider call, OAuth action,
database write, migration, or transaction execution occurred.

Validation on this recheck: **321 backend tests passed** (one existing
Starlette/httpx deprecation warning), **12 desktop/mobile Playwright + axe
tests passed**, **35 frontend unit tests passed**, and the strict
TypeScript/Vite build passed. The report and these current counts supersede any earlier deployment or
reconciliation status below; prior player-level snapshots remain historical.

## Waiver Source Integrity & Coverage Follow-up - 2026-10-26

This section records the local worktree implementation and the final guarded
read-only acceptance below the deployed Phase-3 reliability recheck above.
**The follow-up is not deployed.** Acceptance queried existing persisted
records only and did not alter the persisted snapshot.

### Final persisted baseline and unresolved causes

- Acceptance timestamp: **2026-10-26 09:40:56 UTC / 02:40:56 PDT**. The
  independently queried Yahoo pool denominator was **744**; the service
  returned **309** eligible candidates and **13** configured-roster players.
- Identity: **697/744 resolved**, **47/744 unresolved** (16 AMBIGUOUS, 31
  NO_MATCH). Fourteen unmapped same-name candidates have conflicting team
  evidence; two additional linked records have Yahoo/NBA team conflicts.
  Direct read-only SQL evidence reproduced the linked and unlinked conflict
  counts. No name-only mapping or team correction is supported; all remain
  review items. Team disagreement is not evidence of a trade.
- Production: **227/309** candidates have recent production inputs and
  **82/309** do not; **287/309** have Season Evidence and **22/309** do not.
  No production inputs were stale. These are NBA production inputs, not Yahoo
  payload requirements.
- Status: **14/309** candidates have explicit status and **295/309** have a
  Yahoo-supplied blank. Across all **744** observations, O=60, NA=222, Q=15,
  P=6, blank=439, and two unrecognized-status observations represented one
  distinct token. Blank and unrecognized values remain UNKNOWN; O/NA are
  excluded and Q/P uncertain.
- Schedule: **309/309** eligible candidates had in-window schedule rows for
  this snapshot; each is PARTIAL because no completeness manifest exists.
  Across the full pool, 699/744 had PARTIAL rows and 45/744 had UNKNOWN
  coverage. No schedule state was COMPLETE or STALE. An empty/unverified
  window remains UNKNOWN, not verified zero.
- Role: eligible candidates had role quality **227 partial / 82 unavailable**
  (zero available or stale); game-level usage and recent starts were
  unsupported. Season-start evidence existed for 27/309, but is not
  substituted for game-level role evidence. Acquisition context was missing
  (0/1 supported).

### Local implementation and source review

The local board contract now carries backend-owned coverage with explicit
counts/denominators and percentages, separate Yahoo/NBA teams and raw Yahoo
status, identity-only mapping state/reason, a non-mutating mapping worklist,
schedule source-row counts, and grouped DATA GAPS. The Advanced Evidence UI
renders the five required categories and keeps missing values distinct from
zero, blank status distinct from healthy, and incomplete schedules distinct
from confirmed no games. No recommendation gate, scoring formula, model
version, ranking weight, sample threshold, optimizer rule or Yahoo action was
changed.

The local reconciliation utility compares only persisted fields present on
both sides. The final report used **NO_COMPARABLE_STAT_FIELDS** for **697/744**
records and kept **PARTIAL_STAT_OVERLAP** separate; the remaining 45 records
were identity mismatches and two team mismatches. `MISSING_REQUIRED_STAT` was
zero. No Yahoo stat field overlapped the persisted NBA stats, so this is
**CROSS-SOURCE COMPARISON UNAVAILABLE**, not missing NBA production, fantasy
PPG, or the scoring formula.

Source scorecard (documentation review only; no provider probes):

- Yahoo Fantasy Sports: application/OAuth and policy requirements apply;
  persisted evidence does not verify matchup, manager identity or transaction
  semantics. No new authorization/request was made.
- `nba_api` game-level usage/start endpoints: useful fields are documented in
  community-maintained materials, but the endpoint notes are old and official
  NBA terms were not verified. Research lead only.
- BALLDONTLIE free tier: does not include the required player stats, advanced
  stats, injuries or lineups; relevant features are paid.
- SportsDataIO free trial: reviewed access did not include NBA.
- API-Sports current NBA terms/free limits could not be verified; Sleeper's
  official docs cover NFL, not NBA. Kaggle licenses and coverage are
  dataset-specific and do not establish a current source.

No new source is selected. The final acceptance executed current local source
inside an isolated Python child of the existing API container, with no app
lifespan. Provider entry points and HTTP clients were blocked; SQL allowed only
SELECT and read-only/safe transaction settings. It recorded 47 SELECTs, two
read-only transactions, zero blocked statements, provider calls, writes or
commits, and two rollbacks. The 15 returned top-WATCH pairs matched exactly
across optimizer, selected-drop replacements and impact. No per-pair SQL was
issued; each mode loaded one context (15/12/12 SELECTs for This Week/Next 7
Days/Season Evidence; independent validation and reconciliation reads account
for the remainder).

Automated validation passed: focused backend waiver/reconciliation tests
**176 passed**, full backend **336 passed**, focused/full frontend **15/39
passed**, strict TypeScript/Vite build passed, and desktop/mobile Playwright
plus axe **18 passed**. The additional root-cause regression passed offline.
No provider calls/OAuth, database write, migration, deployment, Yahoo
transaction, commit or push occurred. The changes remain local and **NOT
DEPLOYED**.

## Dated Historical Implementation and Acceptance Records

Sections below record the implementation and observations as they stood on
their dates. The current Source Integrity status and final acceptance are
above; earlier snapshots, contracts and validation counts must not be read as
current evidence where a later closeout supersedes them.

### Historical Waiver Accuracy Phase 3 - Evidence Intelligence - 2026-10-25

Implemented on existing persisted inputs, with no schema/provider change.
This section supersedes the older opportunity method and numerical snapshots
below; Phase-1 scoring/sample gates and the Phase-2 optimizer remain intact.
Phase 2 remains the delivered/current optimization foundation, not obsolete.
The acceptance and suite results below are the completed Phase-3 implementation
verification, rechecked against saved output during the docs-only closeout.
They are dated observations, not a new production query or application rerun.

- Model `waiver-evidence-phase3`: all four existing GETs expose CURRENT ROLE,
  independent minutes/usage/starts/status/schedule quality, supported/missing/
  stale game IDs, dates, counts, source time and schedule coverage.
  Role is derived once per player during bulk context loading, never per pair.
- Method: latest three vs preceding three regular-season games in the existing
  Pacific 14-day lookback; each side requires three valid fresh observations.
  Both mean and median deltas >=+3.0 minutes or >=+0.02 fractional usage
  (two percentage points) give rising direction; both <=-3.0 or <=-0.02
  give falling direction. Boundaries are inclusive, applied after six-decimal
  rounding. Both strictly inside the metric's thresholds give stable direction.
  Mean/median band disagreement or opposing supported metric directions is
  insufficient, preventing a single-game spike from establishing RISING.
  With qualified minutes and no conflict, either metric rising gives RISING,
  either falling gives FALLING, otherwise STABLE. Minutes establish support; optional
  unavailable usage/starts remain independent limitations. No future role.
- Invalid/missing/stale inputs are not zero-filled or backfilled. Seven-day
  log-import/latest-game freshness, 24-hour Yahoo status freshness and existing
  critical evidence gates remain. Explicit season starter-filter GP must match
  saved starts; missing starter rows are not zero starts. Recent starts are
  unavailable; season usage is context only, never recent-window usage.
  Exactly seven days of import age, latest game exactly Pacific today minus
  seven days and exactly 24 hours of Yahoo status age remain within their
  respective boundaries; older evidence is stale. Phase-3 field states are
  `available`/`partial`/`unavailable`/`stale`; the shared contract still retains
  `missing`/`unknown`/`unsupported` for other fields.
- Opportunity is unavailable without qualified role. Qualified score parts
  count minutes level once, optional supported usage change and optional
  explicit fresh season start rate. The old extra minutes-change score is
  removed; default component weights, Yahoo formula and fixed comparison mask
  are unchanged. Missing opportunity is omitted, not replaced with neutral
  value. Opportunity-led ADD and STREAM require qualified fresh role on both
  sides; STREAM also needs fresh schedule and available opportunity. Role
  cannot bypass either player's production sample gate.
- Yahoo O/NA remain excluded, Q/P uncertain and blank UNKNOWN, not healthy.
  Schedule coverage is PARTIAL with rows, UNKNOWN without; no completeness
  manifest supports COMPLETE. No rows is not zero games. Opponents remain
  identities, not matchup difficulty. Existing cards/dialogs expose compact
  role/schedule evidence, with source calculations in expandable details.
- Read-only audit: 812 regular-season game logs in the current lookback have
  MIN 0-44, median 23, and only 1-3 games/player. No game-level USG_PCT or
  starters are persisted. Aggregate usage and some explicit season starts
  exist but cannot manufacture recent comparisons.
- Real acceptance: **HOLD in all modes**, **7,527 assessed / 0 supported /
  7,527 excluded** per mode. Positive WATCH totals are **6 Rest of Week /
  176 Next 7 Days / 183 Season Evidence**. Changed short-window descriptive
  rankings follow removal of unsupported opportunity, not weight tuning.
  Every returned WATCH add has two games and insufficient role comparison.
  Top pairs: Jrue Holiday / Dillon Brooks **+0.218907** Rest of Week;
  Keegan Murray / Dillon Brooks **+1.143485** Next 7 Days;
  Kris Dunn / P.J. Washington **+0.935267** Season Evidence.
  Murray/Coulibaly/Dunn have 2/3/2 games and cannot be ADD/STREAM/MUST ADD.
  Leading WATCH details: Holiday/Murray/Dunn recent minutes are **23.5/27/30.5**;
  each has two recent observations and zero preceding observations, so
  comparison minutes/delta and recent usage/delta remain unavailable, with
  role **INSUFFICIENT EVIDENCE**. Holiday starts are unavailable; Murray/Dunn
  have partial explicit season starts **2/2**. Murray is Q, Holiday/Dunn
  UNKNOWN. Holiday's one-day schedule is UNKNOWN; Murray's Next-7-Days
  **4 games / 2 off-days / 0 back-to-back pairs** and Dunn's season
  **78 / 5 / 13** are PARTIAL, not completeness claims or forecasts.
- Selected persisted roster player Luka Doncic: **HOLD** in all modes.
  Yahoo fantasy PPG **41.9** = 25.5 + 1.2*7 + 1.5*7 + 3*0.5 +
  3*1.5 - 8.5; two current games, 33.5 recent minutes, no preceding
  comparison/usage trend, partial schedule. Highest descriptive replacement
  nets **-0.710415 / -0.726937 / -0.283732** across the three modes,
  never a least-negative Best Add.
- **All 15 returned WATCH pairs** had exact optimizer == replacements ==
  impact comparisons and role evidence. Guarded acceptance: **363 SELECTs,
  one read-only SET, zero provider calls/writes**.
- Final validation: **139 focused / 299 full backend**, **11 focused / 35 full
  frontend**, strict TypeScript/Vite production build and **12 desktop/mobile
  Playwright + axe** tests passed. One existing backend Starlette/httpx
  deprecation warning. Initial axe heading-order regression was corrected in
  the reusable role section; all final axe checks pass.
  Full real WATCH details and audit/validation provenance are in the
  [Phase-3 session record](../sessions/2026-10-25.md#waiver-accuracy-phase-3-evidence-intelligence).
- Remaining gaps: adequate current-season comparison/production samples,
  game-level usage/starts, unknown Yahoo status, schedule completeness, richer
  authorized injury inputs, Yahoo matchup periods/ownership, current priority,
  weekly usage/remaining and claim-clear times. No FAAB, projections, numeric
  confidence, injury-return forecasts, opponent demand, history/calibration or
  execution. No refresh, OAuth, Yahoo writes, migration, deployment, commit/push.

### Historical Waiver Accuracy Phase 2 - Best Supported Transaction - 2026-10-25

This section extends Phase 1 without changing its formula, weights or evidence
gates. Earlier selected-player-only primary-workflow descriptions are superseded
by the global summary; the exact selected-drop workflow remains supported.
Phase-2 acceptance/validation numbers below are historical snapshots; the
Phase-3 evidence method and current observations above supersede them.

- Implemented read-only `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`,
  configured only for **Box Score Bully**, team **478.l.50505.t.9**, league
  **478.l.50505**. This is application configuration, **not verified
  Yahoo-authenticated ownership**. This is hypothetical add/drop analysis,
  **not Yahoo transaction history or execution**.
- One context load, in-memory pairs using the same `enrich` / `compare` engine,
  fixed percentiles, common evidence mask and bounded coverage as replacements/
  impact. Supported eligibility precedes optimization. Positive 1-6-game pairs
  remain WATCH; prior history cannot bypass gates. Supported negative/zero pairs
  are PASS; no supported positive means HOLD and null best transaction.
  MUST ADD remains unused, with no validated stronger threshold.
- HOLD is a successful decision: **HOLD -- no supported waiver transaction
  currently improves Box Score Bully**; `best_transaction=null`. It is not an
  error or optimizer failure. Positive WATCH/unsupported pairs and least-negative
  pairs cannot become the supported winner. Missing/stale mandatory evidence
  fails closed; WATCH remains separate from actionable ADD/STREAM.
- All four waiver endpoints are database-only and default to `this_week`:
  - `GET /api/v1/waivers?mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/transactions?mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/replacements?drop_player_id=...&mode=this_week|next_7_days|ros`
  - `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...&mode=this_week|next_7_days|ros`
  No Yahoo/NBA provider calls or writes occur during analysis.
- UI modes: **Rest of Week** (`this_week`), **Next 7 Days** (`next_7_days`),
  **Season Evidence** (`ros`). Dates use `America/Los_Angeles`, PST/PDT
  automatically. Short windows are not Yahoo matchup periods; Season Evidence
  is historical/stat-based, not a projection. Points rules and unavailable
  acquisition inputs remain as documented in the Phase-1 foundation below.
- Response: exact best pair or null, top five supported pairs, top five WATCH
  pairs, full counts, overlapping exclusion reasons, quality and factual
  acquisition context. Each pair includes both players' production, sample,
  status, opportunity/schedule evidence and exact before/after/component/
  coverage comparison. Ordering is net descending, add ID then drop ID.
- Global summary above the preserved selected-player workflow: HOLD or exact
  ADD/DROP, reasons/risks, separate WATCHLIST and VIEW ANALYSIS. The dialog
  displays the exact returned optimizer comparison; it cannot change the
  selected workflow's drop. Errors are visible, not manufactured HOLD results.
  No category objectives, acquisition cost, FAAB, forecasts or numeric confidence.
- Real saved-data acceptance: **7,527 assessed / 7,527 excluded / 0 supported**
  pairs per mode (579 non-rostered pool observations x 13 roster players;
  includes pre-excluded O/NA adds). All three modes: **HOLD**, no best transaction
  and no top supported transactions. Positive WATCH counts:
  Rest of Week **10**, Next 7 Days **45**, Season Evidence **183**.
  WATCH is excluded from the supported pool, not a recommended transaction.
- Highest WATCH comparisons: Keegan Murray / DeMar DeRozan **+0.744339**
  Rest of Week; same pair **+1.219951** Next 7 Days; Kris Dunn /
  P.J. Washington **+0.935267** Season Evidence. All add/drop samples are two
  or three games; statuses and schedules have further gaps. They are not winners.
  Murray/Coulibaly/Dunn remain subject to Phase-1 gates without player-specific rules.
- Other verified WATCH examples: Rest of Week Bilal Coulibaly / DeMar DeRozan
  **+0.618263**, Kris Dunn / DeMar DeRozan **+0.468874**; Next 7 Days Keegan
  Murray / Dillon Brooks **+0.890583**. These are descriptive WATCH
  comparisons, **not supported transaction recommendations**.
- Each mode's checked optimizer comparison exactly equals selected-drop and
  impact output. Specifically, Next 7 Days Murray / DeRozan is
  **84.970762 -> 86.190713**, net **+1.219951**, in all three surfaces.
  Read-only acceptance rejects provider calls and non-read SQL:
  **94 SQL statements, zero provider calls, zero writes**.
  The analysis used 10-13 SELECTs per optimizer context, not per pair.
- Final validation: **93 focused / 253 full backend**, **10 focused / 34 full
  frontend**, strict TypeScript/Vite build, **12 desktop/mobile Playwright/axe**
  browser tests passed. See the [session record](../sessions/2026-10-25.md#waiver-accuracy-phase-2-best-supported-transaction).
  Implementation-run documentation links and `git diff --check` passed.
  These are completed Phase-2 validation results, not tests rerun for this
  documentation closeout.
  No production deploy, provider refresh, OAuth, Yahoo writes, migrations,
  formula/weight tuning, commit or push.
- Remaining limitations: current-season samples, role/status evidence,
  incomplete/stale production for some players, partial/missing schedules,
  unverified Yahoo matchup-week semantics, current priority, weekly acquisition
  usage/remaining and exact claim-clear time. No projections, numeric confidence,
  opponent bidding/demand, injury-return forecasts or execution are established.

### Historical Waiver Accuracy Phase 1 Foundation - 2026-10-25

The scoring, league and evidence foundation remains current under Phase 2;
this section's Phase-1 acceptance results are historical, not a new recheck.
All lower dated v1/v2 observations,
including old sample labels, action wording and rankings, are historical.
Older FAAB statements are obsolete/general exploration, not this league's roadmap.

- Persisted **Driveway Dudes / 478.l.50505** settings match: **Head-to-Head
  Points, 12 teams**, roster `PG SG G SF PF F C C UTIL UTIL BN BN BN IL IL IL`.
  Saved raw Yahoo settings and normalized settings are checked on every read;
  any disagreement returns explicit **409** mismatches, never a hard-coded fallback.
- Actual persisted Yahoo formula: **PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL
  - TO**. NBA TO input is `TOV`. Missing any required input makes value
  unavailable. API and UI expose per-game stats, modifiers and contributions.
- **No FAAB**, no bidding/cost substitute, no future FAAB feature for this
  league. Factual Command Center rules: continual rolling list, Standard,
  two-day waiver period, four adds/week, no season limit, Daily - Today,
  post-draft waiver rules, direct injury-slot additions. Current priority,
  remaining weekly adds and exact clear time are not verified or claimed.
  Acquisition value stays unavailable and excluded from scores.
- `mode=ros` remains API-compatible; its label is **Season Evidence**:
  historical/stat-based evidence, not a projection. Rest of Week and Next
  7 Days retain Pacific calendar windows, not inferred Yahoo matchup weeks.
- Backend evidence quality: **20+ EXCELLENT; 10-19 GOOD; 7-9 LIMITED;
  4-6 VERY LIMITED; 1-3 INSUFFICIENT FOR STRONG RECOMMENDATION;
  zero NO CURRENT-SEASON EVIDENCE**. This is not probability.
  Prior-season shrinkage remains descriptive and cannot bypass the current
  season gate, including in Season Evidence mode.
- Backend owns MUST ADD / ADD / STREAM / WATCH / PASS / INSUFFICIENT EVIDENCE.
  No forced MUST ADD, AVOID or confidence percentages. Positive 1-6-game
  candidates may be WATCH, never Best Add. ADD needs positive supported impact
  and sufficient current evidence for add/drop. Critical stale/missing evidence
  blocks strong decisions, not just warnings; unknown/stale Yahoo status also
  blocks them. O/NA exclusion and Q/P/blank eligibility behavior are preserved.
  STREAM requires fresh schedule and opportunity evidence. Partial schedule
  coverage is disclosed, never interpreted as guaranteed lineup starts.
- Selected-drop workflow and bounded/common-weight roster-index model are
  preserved. If every measured replacement is nonpositive: **HOLD [selected
  player]** is primary; the least-negative option is not Best Add.
- Real persisted-only acceptance: P.J. Washington selected, Next 7 Days,
  **WATCH** (not ADD): Keegan Murray **+0.393275**, 2 games, **13.85 fantasy
  PPG**; selected player 3 games, **26.4 fantasy PPG**. Keegan's four persisted
  games have partial coverage. Bilal Coulibaly (3 games, 23.3 fantasy PPG)
  and Kris Dunn (2 games, 30.0 fantasy PPG) cannot become strong recommendations.
  Selecting Luka Dončić produces HOLD in all three modes. See the
  [session record](../sessions/2026-10-25.md#waiver-accuracy-phase-1) for historical evidence
  and final validation.
- No provider refresh, Yahoo writes, OAuth, production migration, deployment,
  weight tuning, commit or push. Existing dirty unrelated work is preserved.

## Historical: Contract Reconciliation - 2026-10-25 3:06 PM PDT

Verified against current code/contracts/tests and trusted-TLS read-only runtime
checks. This section and the v2 correction immediately below were then current;
the explicitly marked historical snapshots further below are not current advice.

- `/waivers` is configured for **Box Score Bully**, team
  **478.l.50505.t.9**, league **478.l.50505**. This is application configuration,
  **not verified Yahoo-authenticated ownership**. Primary flow: configured
  roster -> select one player to replace -> ranked waiver alternatives.
  Selected drop controls every comparison and modal; Best Overall is secondary.
  Negative replacement values mean no measured improvement: hold is preferable
  under the model, not guaranteed future performance.
- Actual UI modes are **Rest of Week** (`this_week`, default), **Next 7 Days**
  (`next_7_days`) and **ROS** (`ros`). Rest of Week always has that label;
  fewer than two inclusive dates adds a **limited days remaining** warning.
  Pacific `America/Los_Angeles` today-through-Sunday remains the actual window;
  Next 7 Days includes today plus six dates. Neither is a verified Yahoo matchup
  period. ROS is historical/stat-based, not a projection.
- All three endpoints default `mode=this_week` and accept
  `this_week|next_7_days|ros`:
  - `GET /api/v1/waivers`
  - `GET /api/v1/waivers/replacements?drop_player_id=...` (required integer)
  - `GET /api/v1/waivers/{player_id}/impact?drop_player_id=...` (optional drop)
  Player/drop IDs are internal identities; non-manager drops are rejected.
  All reuse PostgreSQL-only calculations, with no provider calls or writes.
- The **3:06 PM PDT** runtime recheck reproduced every P.J. Rest of Week
  top-five value and the Next 7 Days Keegan **+0.393275** checkpoint below.
  P.J. selected ID **10184** remained fixed in every result and matched the
  impact endpoint. Curry selected ID **10022** produced Keegan **-0.443761**,
  rather than P.J.'s **-0.247672**. Thirteen roster players were returned.
  All five P.J. alternatives remain VERY LOW SAMPLE; missing schedule rows
  for Bilal/Christie are unknown, not zero. Keegan's Next 7 Days schedule is
  four games with **partial** coverage, from October 25 through October 31.
- Reproduced old v1 arithmetic in memory from persisted data, in a read-only
  transaction: marginal fit **0 -> 200**, slot coverage **10 -> 10**, obsolete
  net **+95.080661**. Current API instead returns fit **100 -> 100**, delta
  **0**, net **-0.523137** for Dunn/P.J. Old positive output is superseded.
- Yahoo fantasy identity/settings/roster/state and persisted NBA basketball
  inputs retain separate authority. Freshness/missing gates remain; O/NA
  excluded, Q/P uncertain, blank unknown, roster absence only `unrostered`
  without proven claim timing. No FAAB, ownership percentages, opponent demand,
  injury-return forecasts, matchup difficulty, calibrated confidence/probability,
  category-aware waiver impact, authenticated ownership, transaction execution
  or predictive accuracy is established.
- Validation numbers below belong only to the completed replacement
  implementation run: backend **31 focused / 191 full**, frontend
  **7 focused / 31 full / 8 browser**, production build passed, plus the
  **8 final targeted backend assertions**. No full suite or application build
  was rerun for this documentation reconciliation. Health GET returned **200**.
  No runtime changes, provider refresh, Yahoo writes, OAuth, migration,
  rebuild/deployment, commit or push in this docs-only pass.

## Historical: Replacement Quality Correction - 2026-10-25

This supersedes the old v1 recommendation results below; those dated results
remain historical evidence, not current advice.

- Audited the real old Dunn/P.J. calculation read-only. Removing P.J. made
  Jarrett Allen and Pascal Siakam individually indispensable to slot matching,
  changing each marginal fit from 0 to 100 even though both complete rosters
  cover **10/10** starting slots. Summing those marginal scores invented a
  **+200** fit gain. With common effective weights fit **0.466667**, value
  **0.333333**, opportunity **0.2**, old net was
  `200*.466667 + 7.603093*.333333 - 3.935185*.2 = 95.080661`.
  Dunn's displayed fit was zero because he was not individually indispensable;
  that mismatch was semantic, not an intended quality advantage.
- Version **waiver-evidence-v2** measures whole-roster starting-slot coverage
  once, 0-100, and uses roster means for all other components. Before/after
  use the same scale, common mask, effective weights and fixed league
  percentiles. Every component delta is bounded -100 to +100; covered-to-covered
  reassignment yields zero fit gain. Weights stayed **35/25/15/15/10**.
- Recent/Next 7 Days player value blends supported fresh prior-season PPG with
  recent PPG using recent weight `n/(n+10)`; no independent prior history means
  raw recent limited evidence. Missing/stale recent data still cannot score.
  Samples 1-3 are VERY LOW SAMPLE, 4-6 LOW SAMPLE, >=7 LARGER SAMPLE,
  zero is NO SAMPLE, never
  calibrated confidence. A single best-team result requires a supported impact
  and >=7 fresh production games for add and drop in that mode.
- Corrected real Dunn/P.J. comparison: coverage **100 -> 100**, production
  percentile roster mean **83.604282 -> 82.216495**, opportunity mean
  **89.440883 -> 89.138177**. Same effective weights give
  `0*.466667 - 1.387787*.333333 - .302707*.2 = -0.523137`.
  Overall roster index **92.422937 -> 91.899800**. Dunn's ranking PPG is
  `30*(2/12) + 20.66*(10/12) = 22.216667`, with two recent games and 82
  independent prior-season games. This is not a projection or drop recommendation.
- Explicit-drop endpoint
  `GET /api/v1/waivers/replacements?drop_player_id=...&mode=...` reuses the
  same loader/scorer as board and impact. It rejects non-manager drops and
  ranks only eligible unrostered/available players for that exact drop.
  Board responses include the full configured roster; detailed impact keeps
  the explicit drop even if capacity is open or another drop scores better.
- Read-only real **P.J. Washington / Rest of Week** top five:
  Keegan Murray **-0.247672**, Bilal Coulibaly **-0.373748**,
  Kris Dunn **-0.523137**, Derrick Jones Jr. **-0.529745**,
  Max Christie **-0.723925**. All are negative; no measured improvement.
  Each has only two or three recent games. For **Stephen Curry**, top three
  are Keegan **-0.443761**, Bilal **-0.569837**, Dunn **-0.719226**;
  same ordering happens to hold, but the exact drop and values differ.
- This Sunday Rest of Week remains **October 25 only**. **Next 7 Days**
  separately ranks schedule evidence for **October 25-31**, Pacific today
  plus six days. P.J.'s top next-seven result is Keegan **+0.393275**, with
  four persisted games and VERY LOW SAMPLE production, not confident advice.
  Neither date window claims Yahoo matchup-week semantics. ROS stays historical.
- Focused backend **31 passed**; full backend **191 passed** on disposable,
  internal-network-only PostgreSQL, with one existing Starlette/httpx warning.
  No provider calls during analysis/validation, Yahoo writes, NBA/Yahoo/Fantrax
  refresh, OAuth, migrations, fabricated production data, commits or pushes.
- Frontend **7 focused**, **31 full**, **8 desktop/mobile browser/accessibility**
  tests passed; strict TypeScript/Vite production build passed. Primary page
  order is configured-team header, full roster-player selector, selected-drop
  top three, date controls, secondary Best Overall, full table, data quality.
  Nonpositive results explicitly say no measured improvement. Modal keeps
  the selected drop; sample labels and risks are prominent.
- Rebuilt/recreated only local API/frontend with API lifespan disabled;
  database/Caddy unchanged. Reloaded frontend upstream DNS after recreation.
  Trusted-TLS health **200**. Real browser verified **13 selectable roster
  players**, P.J./Curry-specific responses, fixed P.J. modal comparison,
  Rest of Week default, Next7 October25-31, ROS, no visible API alerts,
  no blocking desktop/mobile overflow and **zero write requests**.

## Historical Snapshots - Superseded by the Phase-1/Phase-2 Contracts Above

The remaining sections preserve observations at earlier stages. Old endpoint
lists, UTC windows, selectors, best-fit results, v1 scores and test counts
describe those stages only. In particular the old positive Dunn/P.J. and
Jrue/P.J. outputs are not current recommendations. Earlier authorization and
missing-NBA blockers were resolved in later dated work.

## Historical: Weekly Evidence Restored - 2026-10-25 12:04 PM PDT

This supersedes the earlier missing-current-season-NBA blocker below. After
explicit user authorization, the existing NBA import endpoint ran for season
2026-27 with `recent_days=30`. It returned 30 teams, 521 players, 1,547 season
statistics rows across its existing periods, 1,274 games, 2,803 game logs,
56,332 player schedule entries, eight identity mappings and one unresolved
schedule-team reference. Independent read-only SQL verified **812 recent
current-season regular-season logs**, **388 current-season regular-season
statistics rows**, and **1,274 season games**, persisted **12:04:00.394622 PM
PDT**. Schedule coverage remains partial, not certified complete.

- Real This Week: **309 eligible rows**, **227 scored**, **184 analyze-add**,
  **43 watch**, **82 insufficient-evidence**. Both Best Overall and Best Fit
  selected **Kris Dunn** at that time; the v1 top drop was **P.J. Washington**.
  Before **570.432894**, after **665.513555**, net **+95.080661** descriptive
  model-index change. Component changes: roster fit **+200**, player value
  **+7.603093**, opportunity **-3.935185**; schedule is not a common measured
  component of this swap. This is not a predicted points/wins gain.
- Pacific Sunday October 25's today-through-Sunday window is **October 25
  only**, not the following week or verified Yahoo matchup semantics. Dunn's
  recent input has only **two games**, Yahoo status is unknown, and his one
  persisted remaining game is partial schedule evidence, not a guaranteed start.
- Read-only live browser verified This Week default, visible real drop/reasons,
  Analyze Add opening/closing, ROS switch and no blocking 1440px/390px overflow.
  No application code, scoring, freshness gates, Yahoo state, migrations or
  services changed. Only the explicitly authorized existing NBA import wrote
  basketball data; no Yahoo/provider refresh beyond that NBA workflow.

## Historical: Upfront Drop Explanation - 2026-10-25

The Best Fit card now surfaces the existing top positive modeled drop option,
its before/after roster indices, measured component changes and existing model
reasons. No new calculation or API was added. The suggestion is conditional on
needing a drop; open-slot additions are not presented as requiring one. Missing
or nonpositive swap evidence produces an explicit unavailable comparison.
The full Analyze Add dialog retains the other supported drop options.

- Validation: **7 focused frontend**, **31 full frontend**, **6 desktop/mobile
  browser/accessibility tests passed**; production TypeScript/Vite build passed.
  The first browser run had two 60-second axe/browser timeouts during the
  concurrent image build; the unchanged suite passed on rerun in **33.8s**.
- Rebuilt/recreated only local frontend. Read-only real browser verification
  shows ROS **add Jrue Holiday / top drop P.J. Washington**, with roster-fit
  **+200.0**, player-value **+3.2**, schedule **+50.0** component-index changes
  and net weighted roster-index change **+104.4**. These are aggregate model
  changes, not projected player points or a claim of uncovered roster slots.
  This Week remains the default; no selectors or 1440px/390px blocking overflow.
- Trusted-TLS health check returned **200**. No new provider import/refresh,
  Yahoo write, migration, scoring/gate change, commit or push for this UI change.

## Historical: Fresh OAuth Recovery and Yahoo Import - 2026-10-25 11:25 AM PDT

This runtime evidence supersedes the stale-Yahoo/authorization blockers recorded
earlier below, without changing those historical observations.

- Fresh callback credential metadata: row exists, both encrypted credential
  presence flags true, updated **11:14:23 AM PDT**, expires **12:14:23 PM PDT**.
  The credential commit precedes automatic league import; its later 502 did not
  roll back authorization. No secret values or provider payloads were displayed.
- Exactly one normal-auth/client canary, `league/478.l.50505/teams`, with
  `max_attempts=1`, returned **HTTP 200**. Authorization was restored as of
  this check; no additional OAuth flow or token refresh was performed.
- Callback failure was the league persistence transaction: deleting existing
  `teams` conflicted with preserved draft-pick references
  (`draft_picks_team_key_fkey`). It was not an OAuth exchange, league discovery,
  normalization, settings-source or schema defect.
  Changed only team persistence to upsert by stable team key, preserving
  referenced/historical rows rather than deleting them. Existing rows absent
  from a new response are retained without a new import timestamp.
  Persistence errors retain their sanitized 502 boundary and log only error
  class/event context, not SQL parameters/provider payloads.
- Existing supported league/settings import committed at
  **11:20:26.039906 AM PDT**, all **12 teams** in that snapshot. Existing
  player/all-roster import committed at **11:20:50.816210 AM PDT**:
  **744 player/status rows**, **12/12 fresh roster snapshots**, and
  **13 Box Score Bully roster players**. Separate read-only database queries
  verified timestamps/counts after each import; HTTP success alone was not used.
- Real `/waivers` now has **309 eligible candidate rows**, **270 O/NA
  exclusions**, **zero unknown-availability players** and available Yahoo
  league/settings/roster/availability quality. Q/P retain uncertainty; blank
  status remains unknown. All 12 rosters supply league-wide availability;
  all actionable calculations remain bound to Box Score Bully.
- This Week: **0 actionable/scored candidates**, Best Overall/Fit unavailable:
  there are **zero persisted 2026-27 recent regular-season NBA game logs**.
  No NBA import/call was performed under this task's explicit restriction.
  Calendar window is Pacific **October 25 through October 25** (Sunday).
- ROS: **252 scored**, **200 actionable** among 309 eligible candidates;
  Best Overall **Nikola Vučević**, Best Fit **Jrue Holiday**. Top supported
  drop **P.J. Washington**: descriptive roster index **535.823450 → 640.222502**,
  change **104.399052**, not predicted points/wins. All three drop options
  were independently verified inside Box Score Bully's roster. Historical ROS
  value is not a projection; missing recent opportunity/schedule evidence and
  all previously unsupported analytics remain explicitly unavailable.
- Real browser verified direct team opening/no selectors, This Week default,
  ROS switch, candidate table, Best Overall/Fit, roster needs, impact dialog
  open/close, Pacific timestamps and no blocking 1440px/390px overflow.
  Alternate-team requests still return 422.
- Focused persistence/Yahoo/player/waiver regressions: **43 passed**, one
  existing Starlette/httpx warning, on disposable PostgreSQL. This includes
  idempotent refresh, preserved draft history, and all-or-nothing rollback with
  sanitized errors. Preserved real history counts remained **18 sessions,
  2,022 picks, 2,022 events, 2,040 snapshots** before/after.
- Only the local API was rebuilt/recreated for this fix, retaining disabled
  lifespan startup; local frontend Nginx reloaded upstream DNS. No migration,
  scoring/freshness/target/timezone/UI change, Yahoo write, speculative endpoint,
  NBA/Fantrax call, commit or push occurred.

## Historical: Waiver Center Closeout - 2026-10-25

The read-only Waiver Center is an implemented post-draft capability alongside
the Championship HQ foundation/category baseline and preserved Draft module.
This section supersedes earlier future-scope wording about generic waivers;
older dated evidence below remains historical, not fresh runtime validation.

### Verified implementation and UX

- `/waivers` opens directly for **Box Score Bully**, without league/team
  selectors, default **This Week**, and retains **ROS**. The subheader uses the
  persisted team name. **Box Score Bully is the configured manager analysis team
  for the personal application; this configuration is not Yahoo-authenticated
  ownership evidence.**
- API setting `WAIVER_MANAGER_TEAM_KEY` defaults to `478.l.50505.t.9`;
  the persisted team association supplies league `478.l.50505`. Both existing
  routes enforce that target. Optional legacy `league_key`/`team_key` inputs
  must match or return 422. Missing configured team returns 404, never a
  different roster. Frontend URL/saved-state targets cannot select another team.
- `GET /api/v1/waivers` accepts
  `mode=this_week|ros` (default `this_week`). It returns candidates, separate
  best-overall/best-fit IDs, roster needs, configured weights, limitations,
  excluded/unknown-availability counts, persisted team name, resolved target
  keys and source quality/timestamps. The frontend sends no team-selection keys;
  the backend resolves the configured league/team for every board/impact read.
- `GET /api/v1/waivers/{player_id}/impact` uses the internal player ID and the
  same context, with optional `drop_player_id`. Drop IDs must belong to the
  selected roster (422); already-rostered adds return 409; missing
  league/team/player returns 404. Mode validation returns 422.
- Best Overall uses the mode's measured production percentile alone. Best Fit
  chooses scored actionable candidates by net add/drop model improvement,
  then weighted overall score and internal ID. The candidate table itself
  ranks weighted overall score. Up to three drop options come from the
  selected roster only; imported open non-injury capacity supports no-drop
  analysis. No transaction eligibility or roster-lock guarantee is implied.
- The analysis dialog exposes before/after scores, component deltas, drop
  options, historical values/sample sizes, schedule window, evidence and
  limitations. Loading, errors, empty/unscored results, keyboard modal focus,
  and responsive table overflow have synthetic test coverage. Reload only
  rereads persisted data.

### Data boundaries and scoring semantics

- Yahoo remains authoritative for league/player identity, settings, roster and
  state evidence. Persisted NBA season statistics, regular-season game logs,
  teams and games provide basketball inputs. Both waiver routes are
  database-only; guarded tests reject Yahoo/NBA provider calls.
- Availability needs fresh affirmative persisted Yahoo ownership or absence
  from every fresh league roster. Absence is `unrostered`, not verified
  free-agent/waiver-claim timing. Unknown availability is withheld.
  O/NA are excluded; Q/P stay eligible with uncertainty; blank status is unknown.
- Waiver roster/settings/availability freshness uses a 24-hour import cutoff.
  Roster snapshots predating later league/team/settings imports cannot establish
  current absence. Stale settings cannot supply scoring or positional fit.
  This age gate is waiver-specific; the foundation roster API retains its
  source-order-based stale semantics.
- Recent value uses persisted regular-season logs in the league's NBA season
  from Pacific today minus 14 days through today, inclusive, under supported
  Yahoo points modifiers. The oldest selected log import and latest selected
  game date must each be within seven days. ROS selects each player's latest
  eligible regular-season history, no later than the league season (current
  Pacific year cutoff if absent), **not a projection**. Seven-day-stale historical
  imports remain visible but cannot score or supply hold-label evidence.
- This Week counts persisted scheduled games from today through Sunday Pacific Time.
  ROS counts through June 30 after the league season start year, or today if
  that date has passed. Neither is a verified Yahoo matchup period.
  Final/cancelled/postponed games are omitted; no rows means unknown, not zero.
  Schedule coverage is partial, off-days mean at most five persisted games
  that date, and imports older than seven days cannot supply a schedule score.
- Displayed timestamps, recent-log calendar boundaries and schedule date windows
  use `America/Los_Angeles` (PST/PDT automatically), per the explicit follow-up
  request. Stored timestamp instants remain UTC and freshness uses unchanged
  elapsed-time limits. NBA dates remain persisted date-only inputs; neither
  tip-off times nor Yahoo matchup periods were newly established.
- `waiver-evidence-v1` uses deterministic midrank production/schedule
  percentiles, positional maximum-slot matching and measured minutes/trends.
  Hold labels are descriptive heuristics, not future roles or injury forecasts.
  API environment `WAIVER_WEIGHTS` configures fit/value/opportunity/schedule/
  acquisition components; defaults are 35/25/15/15/10 percent. Finite,
  nonnegative weights with a positive sum and all five keys are required.
  Missing components are omitted and measured weights renormalized; supported
  player value and roster fit remain mandatory for an overall score.
- Add/drop recomputes entire-roster positional fit on both sides using fixed
  value percentiles and the same common measured components/weights. Missing
  roster values leave numeric impact unavailable. Improvement is a descriptive
  model-index change, **not predicted fantasy points or wins**.

### Configured-team/Pacific follow-up validation

- Focused backend waiver suite: **17 passed**, one existing Starlette/httpx
  deprecation warning, no skips. It verifies server-bound target/default mode,
  rejection of other teams/leagues on board and impact routes, missing-target
  errors, stale-data gates, and Pacific Sunday boundaries in PST and PDT.
- Focused frontend: **6 passed**; full frontend: **30 passed**.
  Strict TypeScript/Vite production build passed. Desktop/mobile Playwright:
  **6 passed**, including axe, candidates, Best Fit, modal open/close/focus,
  drop comparison, mode toggle, error/stale empty states, URL/saved-target
  rejection and GET-only analysis. Timestamp tests verify PST/PDT independently
  of the browser zone.
- Test resources were disposable and network-isolated. Rebuilt/recreated only
  local API/frontend through existing Caddy, retaining the no-lifespan browser
  override so schema initialization/migrations and the draft worker do not run.
  Database/Caddy were not restarted or modified.
- Running-stack health returned 200. `/waivers` opens directly for persisted
  **Box Score Bully**, league `478.l.50505`, team `478.l.50505.t.9`, without
  selectors; This Week/ROS return the same configured target. Other-team board
  and impact requests return 422. Pacific timestamps and desktop/mobile layout
  were verified against real data.
- Real recommendations remain unavailable: league/settings are dated October 9,
  rosters October 18, and **744 players have unknown availability**. Both modes
  show the real empty state, not fabricated candidates or bypassed gates.
  No production migrations, provider refresh/import, OAuth or Yahoo write
  occurred. Existing unrelated dirty work was preserved.

### Earlier closeout validation and limitations

- Backend focused: **44 passed**, including **12 waiver tests**, category
  baseline, player-read/import, Yahoo-client and token-storage regressions.
  Full backend: **171 passed**. Each final run emitted one existing
  Starlette/httpx deprecation warning; no skips or failures.
- Frontend focused waiver rendering/contracts: **5 passed**; full frontend:
  **29 passed**. Strict TypeScript/Vite production build passed.
  Playwright 1.56.1: **4 passed**, desktop/mobile synthetic API fixtures,
  including axe, modal focus, mode changes, error/empty states and GET-only
  analysis.
- Validation used disposable PostgreSQL on a new internal Docker network,
  read-only source mounts, and temporary frontend storage in a network-disabled
  Playwright container. The full run exposed a category test's cross-event-loop
  pool reuse; a test-local NullPool engine/dependency override fixed isolation.
  Stale ROS/settings scoring and stale hold-label evidence were corrected;
  existing unrelated dirty work was preserved.
- Still unavailable: acquisition value/FAAB, ownership percentages, opponent
  bidding/demand, injury-return forecasts, validated projections, matchup
  difficulty, calibrated confidence/probabilities, category-aware waiver impact,
  What Changed/history, and transaction execution. Existing category baselines
  are not waiver impact. No Yahoo transaction, scoreboard, current-week, or
  authenticated ownership source contract was newly verified.
- No new migration was required. Existing schema/migration tests ran only on
  disposable databases. No production mutation, provider refresh/call, OAuth
  attempt, deployment, commit or push occurred.

See the [2026-10-25 session record](../sessions/2026-10-25.md) for exact commands
and initial validation/setup failures as well as final passing results.

## Final Draft-Era Baseline - 2026-10-19

The draft system is preserved as an implemented module and historical record.
The primary development direction is now post-draft **Championship HQ**.
This closeout does not implement post-draft features or establish that a Yahoo
league has completed its draft.

## Implemented and Tested

- Persisted v2 draft sessions, sequential picks, correction/latest-pick undo,
  targets, session locking, optimistic versions, audit events, recommendation
  snapshots, and read-only internal-mock replay. The stateless v1 utility API
  remains available.
- Separate internal mock, mock batch/practice, synthetic Mock Sync Rehearsal,
  Yahoo Mock Practice, and Production Live workflows. Internal opponent selection
  is rule-based and seeded, not a calibrated simulation.
- Official authenticated Yahoo `draftresults` retrieval, Yahoo-ID normalization,
  and the existing sequential reconciler. Matching local picks are confirmed;
  only contiguous source picks are appended; conflicts stop reconciliation.
  Production Live retains Sync Now, pause/resume, and Quick Record/manual entry.
- Progressive Live order discovery from first-round source picks, partial
  opponent mappings, explicit manager-slot confirmation, and manual conflict
  resolution. Unknown team slots are not invented.
- React Draft Room with backend-ranked board, manager roster, timing, targets,
  explanations, separate BEST PICK NOW / WAIT ANALYSIS, and version-conflict UX.
  The front door prioritizes Yahoo URL connection after one-time Windows
  observer pairing; internal practice and saved rooms remain available.
- Browser observation is read-only in Yahoo. Mock observations pass through
  the canonical normalization/reconciliation path into disposable practice
  sessions; browser-based Production Live writes are not enabled.
  The current Yahoo practice bridge supports 12-team mocks and requires verified
  rounds and manager slot before initialization.
- Migrations through `0006_observer_connections` are implemented; isolated
  PostgreSQL migration tests pass. The latest session records production
  application of 0006; production schema was not rechecked in this closeout.
- The exact NBA-import proxy route has a 600-second timeout; other API routes
  retain their existing timeout behavior.

## Recommendation Semantics and Limits

BEST PICK NOW is the highest current adjusted roster value under the historical
production heuristic. WAIT ANALYSIS is a separate ADP/survival/fallback
decision; ADP does not directly determine BEST PICK NOW. Only manager picks
populate manager-roster inputs; all league picks affect availability and run
context. Roster matching prioritizes starters before UTIL/bench and handles
incumbent reassignment. Why this rank explains roster-driven score/rank effects,
not predictive accuracy.

- Yahoo O/Out and NA/Not Active are excluded from normal recommendations,
  best value at risk, and wait/fallback candidates. Q/P remain eligible with
  uncertainty. Blank/unrecognized status is unknown, not evidence of health.
- Yahoo status is refreshed by player-pool import, not continuous monitoring.
  Historical values remain visible; no injury penalty or recovery forecast is
  inferred.
- Historical production is not a future-season projection. Small internal
  score differences do not prove objective real-world player superiority.
- Survival/wait estimates remain `heuristic_unvalidated`. No calibrated
  probability, Monte Carlo forecast, opponent roster-demand model, category
  engine, or historical outperformance is established.
- Missing/stale provider data stays unavailable; no fabricated ADP, source
  timestamps, injury forecasts, or player metrics.

## Last Recorded Runtime Evidence - 2026-10-18

These are dated observations from the latest session, not fresh production
checks or guarantees of current freshness. No provider import or production
mutation was performed for this closeout.

- Actual Yahoo Mock Practice smoke: 23 real picks and 24 recommendation
  snapshots, manager selections at picks 7 and 18, manager-only roster inputs,
  recalculation after manager picks, O-status exclusion, and no extra
  picks/events on duplicate reads. This is practice evidence only.
- Windows owner accepted background/windowless startup, tracking, and reconnect.
  Dedicated Chrome CDP stays on Windows `127.0.0.1`; observations use trusted
  HTTPS. One-time pairing avoids per-draft commands or credential handoff;
  missing slot evidence requires only the verified slot fallback.
- Yahoo pool: 744 identities, 691 NBA mappings. Persisted NBA inputs:
  738 players and 1,159 season-stat rows. Draft metrics: 682 scored
  (563 regular-season, 119 preseason samples); 62 unscored
  (53 unmapped, 9 mapped without eligible stats).
- Yahoo status population: 436 blank, 217 NA, 28 O, 62 Q, 1 P.
- Fantrax diagnostics: 396 fetched, 364 matched, 32 unresolved, 0 ambiguous.
  Stored ADP: 366 rows, then 364 fresh and 2 stale; then-fresh usable coverage
  48.92%, stored coverage 49.19%. These freshness labels age with retrieval.
  Draft rank, XRank, draft frequency, sample size, and upstream source-updated
  timestamp are not supplied.
- The session records persisted NBA/stat refresh and preservation of prior
  Live/session/pick/event/snapshot state and identity associations. This
  closeout does not independently repeat those runtime checks.

## Closeout Validation - 2026-10-19

- **146 backend tests passed**, with one existing Starlette/httpx deprecation
  warning, against a disposable PostgreSQL database isolated from production.
- **23 frontend tests passed**; strict TypeScript/Vite production build passed.
- Observer Results-reader tests and Picks DOM contract fixtures are separate
  synthetic checks: **4 Results-reader tests passed** and the Picks DOM fixtures
  passed. These are not new Yahoo or Windows acceptance.
- Canonical Markdown links/fences, Python syntax, observer export shell syntax,
  Compose configuration, and whitespace checks passed. Intended source was
  scanned for accidental credentials/private artifacts; generated dependencies
  and frontend build output are excluded from the commit.

See the [final session record](../sessions/2026-10-18.md) for closeout checks and
the distinction between recorded runtime acceptance and local test evidence.

## Remaining Draft Boundaries

Official Production Live active-draft `draftresults`, source mapping/cadence,
and full manual fallback/correction/recovery browser acceptance remain
unverified. The earlier integrated-browser certificate blocker is not proof
that these checks passed; later Windows mock acceptance does not replace them.
Retain official-source/manual fallback and conflict protection.

Partial mappings/ADP, preseason samples, snapshot-based status, and uncalibrated
heuristics remain material limitations. Post-draft roster/matchup/projection
and championship behavior is not validated by this draft baseline.

See [next actions](next-actions.md), [project memory](../project-memory.md),
the [recommendation audit](../recommendation-audit-2026-10-18.md), and the
[operator checklist](../draft-day-checklist.md).

## Championship Foundation Slice - 2026-10-19

- The home page has a Championship HQ foundation panel using persisted Yahoo
  league settings and team rosters. Its explicit refresh action uses the
  existing league import followed by the existing player/roster import.
- League and settings reads expose their persisted import timestamps.
  `GET /api/v1/rosters` now includes each persisted Yahoo team, including teams
  without a roster snapshot, with source, snapshot time, and
  `available` / `stale` / `not_imported` status.
- `stale` means a later league/team/settings import is known to postdate that
  roster snapshot; there is no age-based cutoff. A successfully imported empty
  roster remains distinct from a roster never imported. Reads use stored data
  and do not call Yahoo.
- Scoring settings remain Yahoo-authoritative. A database-only category
  baseline now returns one result per persisted team and configured category.
  It reports raw supported category output, category status, contributors,
  missing/unmapped players, selected source season/type, and source import
  timestamps. Unsupported categories return no value.
- The engine selects the latest eligible regular-season source season among
  persisted stats for mapped rostered players, no later than the Yahoo league
  season when known. This is not a season intersection across every player:
  players without a row in the selected season remain missing, with no
  fallback to an older season. The regular-season stat type is selected
  deterministically and reported with the season.
- Counting categories sum persisted per-game player rates. FG% and FT% are
  computed from season makes/attempts, derived from persisted per-game
  components × games played. A missing/zero denominator yields no percentage
  value. Category direction follows Yahoo negative modifiers and turnover
  semantics without changing raw category totals.
- Missing Yahoo-to-NBA mappings, source rows, stat fields, and required
  percentage components remain visible. Empty imported rosters and rosters
  not imported are distinct; stale roster snapshots remain identified.
  Matchup/transaction context and actual league draft completion are not
  established by this slice.
- Validation for this slice: 5 backend tests passed against a newly created
  disposable PostgreSQL container (2 category-baseline tests, player-read API,
  and 2 draft-readiness regressions); both Yahoo and NBA provider calls were
  guarded against use by the read route. All 24 frontend tests passed,
  including the focused rendering test. Strict TypeScript/Vite production
  build passed in a disposable Node container. The existing
  Starlette/httpx deprecation warning was emitted. No production database or
  live provider was used.

## Category + Team Identity Relative View - 2026-10-19

- Audited the prior baseline contract and corrected its source-season meaning:
  the selected season is the latest eligible regular season with mapped
  rostered-player statistics across the league, not a season shared by every
  roster player. Per-player older-season fallback remains disabled. Selected
  source-season and stat-type API names and UI wording now match this behavior.
- Category identifiers and names cover the Yahoo fixture-backed PTS, REB, AST,
  ST, BLK, and TO categories; FG% and FT% use their supported Yahoo IDs and
  season-weighted makes/attempts. Counting output is explicitly labelled as
  the sum of player per-game rates. Percentage denominators are preserved.
- The database-only category endpoint now includes versioned league-relative
  results. Comparisons are isolated by league, configured category, selected
  source season/stat type, calculation type/direction, and method version.
  Teams count as comparable only when both the roster snapshot and category
  data are available; partial, stale, unavailable, and unsupported values are
  excluded with reasons. At least three comparable teams are required.
- Ranks use competition ties; min, max, median, and 0–100 min-max position are
  returned. Higher/lower direction follows the category contract; equal values
  map to 50. Backend versioned thresholds classify sufficient results as
  strength (≥75), weakness (≤25), or neutral. Insufficient results are not
  ranked. No authenticated manager team is inferred.
- Championship HQ allows selection of any persisted Yahoo team, shows rank,
  comparable-team count, normalized position, descriptive label/meaning,
  coverage and exclusion reasons, and retains raw category evidence and
  missing contributors. The panel expressly disclaims projections,
  percentiles, matchup advantages, recommendations, and championship
  probabilities.
- Validation: 10 focused backend tests passed against isolated disposable
  PostgreSQL, including provider-call guards, source-season behavior,
  persisted Yahoo category recognition, counting and weighted percentage
  calculations, missing denominator and mapping handling, empty/unimported
  rosters, same-league comparison boundaries, directions, ties, thresholds,
  normalized positions, and exclusions. All 24 frontend tests passed and the
  strict TypeScript/Vite production build passed in a disposable Node
  container. The existing Starlette/httpx deprecation warning was emitted.
  `git diff --check` passed. No production database or provider was used.
- Validation: 15 Yahoo player/service unit tests passed (the PostgreSQL-only
  API test was skipped in that invocation); the player read API and player
  import persistence tests then passed (2 tests) against a disposable
  PostgreSQL container. A follow-up focused run of 25 Yahoo/roster/API tests
  passed against disposable PostgreSQL. All 24 frontend tests passed; strict
  TypeScript and Vite production build passed in a disposable Node container.
  No live Yahoo requests or production database mutations were performed.

See the [2026-10-19 session record](../sessions/2026-10-19.md) for the precise
implementation and validation scope.

## Yahoo Matchup/Transaction Source Review - 2026-10-19

- Existing authenticated Yahoo adapters request NBA games, user leagues, league
  settings/teams/players, team rosters, and draft results. Existing fixtures
  and contracts cover those shapes; there is no scoreboard/matchup or
  transaction adapter/fixture/contract, nor a verified current-login-team or
  current-week contract.
- The client can send a path, but no verified payload or semantics establish
  that a new source path is supported for this account. No matchup or
  transaction source model/import was added. Current-team identity and draft
  completion remain unknown unless explicit Yahoo evidence establishes them.
- Validation after source review: 25 focused backend tests passed against
  disposable PostgreSQL (including database-only reads, roster missing/stale/
  available states, empty roster import, malformed-import preservation, and
  existing Yahoo fixtures); 24 frontend tests and the production build passed.
  Existing Starlette/httpx deprecation warning only. No production mutation or
  live Yahoo request was made.

## Yahoo Source Evidence Gate Attempt - 2026-10-19

- **No new source passed the evidence gate.** A read-only database preflight
  found an existing credential whose access token is expired and an imported
  league selection that is not uniquely resolvable automatically. No keys,
  tokens, callback data, or raw private provider data were printed.
- Executed the ignored local capture command for `identity`. It exited 2 with
  `authorization_expired_no_refresh_attempted`, `requests: 0`,
  `http_status: null`, `resource_path: null`, and
  `contract_verified: false`. This is local preflight evidence, **not a Yahoo
  401/403 response**. No OAuth refresh, Yahoo request, or production database
  mutation was performed. Scoreboard and transaction requests were not
  attempted after the authorization blocker.
- Exact candidate path templates, in evaluation order:
  1. `league/{already_imported_league_key}/teams`: existing adapter path;
     authenticated ownership fields and their meaning remain unverified.
  2. `league/{already_imported_league_key}/scoreboard`: unverified candidate.
  3. `league/{already_imported_league_key}/transactions`: unverified candidate.
  No path was issued in this attempt. For all three, HTTP authorization,
  top-level source collection shape, missing/explicit-empty semantics,
  pagination, stable source identifiers, week/date meaning, update/correction
  behavior, and authenticated-team attribution remain unverified.
- Added `backend/.local-yahoo-evidence/capture.py` and synthetic safety tests,
  locally excluded using `.git/info/exclude`. The utility invokes only the
  existing Yahoo client for a single exact GET with `max_attempts=1`; its
  transport retains actual HTTP status without logging headers or bodies,
  rejects other routes/methods/repeated requests, and bounds response size.
  It emits only redacted structural evidence to owner-only ignored files.
  Counts, field/container types, observed nullability, and structural
  missing/empty/malformed/ambiguous states are preserved. No pagination is
  followed; 401/403/429 stop the attempt. Successful structural capture still
  exits 2 pending authorized semantic review.
- No source model, migration, fixture, import path, API, or frontend change
  was added by this attempt. Completed Category + Team Identity work and
  explicit team selection remain unchanged; no "My Team" attribution,
  current-week inference, strategy, or recommendations were added.
- Validation: **58 focused capture/Yahoo/player tests passed** against
  disposable PostgreSQL; **10 Category + Team Identity regression tests
  passed** in a separate disposable database/process. This includes existing
  database-only read/provider-call guards. Local capture tests use synthetic
  transport/schema data, not Yahoo representative fixtures, and cover
  redaction, nullability/counts, malformed/missing/empty distinctions, limits,
  exact single requests, actual error status, no retry on 401/403/429/503,
  expired-token refusal, read-only DB enforcement, and non-verification.
  Python compilation and `git diff --check` passed. No UI changed in this
  attempt, so frontend tests/build were not rerun. Existing Starlette/httpx
  deprecation warning only. Combined API/category execution exposed an
  existing cross-event-loop pool limitation; isolated runs passed without
  changing application code.

## OAuth Reconnection Attempt - 2026-10-19 07:17 UTC

- Rechecked only credential metadata in a PostgreSQL read-only transaction:
  a stored credential exists, but its access token is expired. No token value
  was read/decrypted or displayed. Automatic imported-league selection remains
  non-unique; an intended league has not been explicitly selected.
- The existing `/api/v1/yahoo/oauth/authorize` route returned HTTP 307 to
  Yahoo's `/oauth2/request_auth`. State and the callback cookie were present;
  the redirect URI matched the configured HTTPS callback origin and
  `/api/v1/yahoo/oauth/callback` path. No OAuth configuration was changed.
- Opened the existing authorization workflow in the integrated browser. It
  reached Yahoo's **Sign in** page, requiring the owner's interactive login
  and consent. No callback completion or usable access token was verified.
  Stopped at this interactive boundary; no source captures were run.
- The owner must finish Yahoo sign-in/consent in the opened browser, or start
  `/api/v1/yahoo/oauth/authorize` on the trusted application origin in their
  own browser and finish the redirect to the configured callback. Do not
  share credentials, callback query parameters, or provider JSON. After
  callback success, verify credential usability and explicitly select the
  intended already imported league before any source capture.
- No source contract passed. No capture infrastructure, source persistence,
  OAuth configuration, Category + Team Identity code, or UI was changed.
  Only status/session documentation changed. `git diff --check` passed;
  backend/frontend tests and Python compilation were not rerun because the
  task stopped at authorization and no executable code changed. Earlier
  disposable-PostgreSQL test results remain dated evidence, not a new run.

## Post-Sign-in Identity Capture - 2026-10-19 07:20 UTC

- After the owner completed sign-in, read-only credential metadata showed an
  existing stored credential with an unexpired access token. No token value
  was inspected. The callback page did not expose the expected success JSON;
  full callback/import completion was not independently established, and the
  one-time callback was not replayed.
- Explicitly selected the already persisted real Yahoo league, excluding local
  mock-practice keys. Initiated exactly one existing-client request:
  `league/478.l.50505/teams`. Actual HTTP status **401**; authorization outcome
  `rejected_stop`, request count 1, command exit 2. Unexpired local metadata
  therefore did not establish provider token usability.
- Stopped immediately. No scoreboard or transaction invocation followed.
  No response collection, count, identifier/ownership fields, week/date,
  pagination, or correction structure was available. All semantic gates
  remain closed; the HTTP rejection is not evidence of endpoint shape.
- Reviewed only a bounded summary from the redacted ignored report; the
  report was owner-only (0600). No tokens, headers, callback parameters, or
  private provider payloads were displayed or committed.
- No executable code, OAuth configuration, capture infrastructure, persistence,
  API, or UI changed. Category + Team Identity remains preserved. Only status
  and session documentation changed; whitespace validation passed. Tests were
  not rerun for this authorization-blocked, documentation-only follow-up.

## Normal-Path Authorization Diagnosis - 2026-10-19

- Traced callback -> existing auth service -> encrypted credential persistence
  -> expiry selection -> existing refresh service -> Yahoo client. Callback
  stores credentials before importing leagues, so stored unexpired metadata
  can coexist with a failed callback import. Normal acquisition and capture
  use the same stored access token/decryption when expiry is unexpired.
  Capture intentionally refuses refresh; normal acquisition refreshes only
  within 60 seconds of expiry. The HTTP client does not refresh on 401.
- Verified source and running-client header expression structurally: both
  reference the supplied access token with a bearer prefix. No header or
  token value was displayed. A redacted source rendering is not evidence
  that a literal redaction placeholder is sent.
- **Normal authorization gate failed:** exactly one existing-service/client
  GET `league/478.l.50505/teams` returned actual HTTP **401**. No capture
  command was involved; this is not an isolated capture failure.
- **Outcome C:** attempted the existing OAuth service's supported refresh
  exactly once. A stored encrypted refresh credential was present; Yahoo's
  `/oauth2/get_token` returned actual HTTP **400**, mapped by the existing
  service to application 401. No known-good GET retry followed a failed
  refresh, and no identity/scoreboard/transaction capture was initiated.
- To invoke the expiry-based service after a provider rejection, marked expiry
  eligible only in the loaded in-memory ORM object with autoflush disabled.
  On refresh rejection, rolled the session back. No expiry invalidation,
  replacement token, or credential change was persisted; no second refresh
  implementation or OAuth configuration change was introduced.
- Proven failure boundary: provider rejection of normal stored access and
  rejection of refresh. **Exact provider reason is not established**: no safe
  error category was retained from the failed refresh response. Do not infer
  revoked/invalid grant, client configuration error, or repair a presumed
  capture/header defect. No further provider calls or repeated sign-in.
- Added three synthetic regressions: unexpired normal acquisition returns the
  same decrypted stored credential without refresh; rejected refresh attempts
  once and preserves encrypted credentials/expiry; client 401 stops without
  retry or leaking provider detail. No runtime or capture code changed.
- Validation on disposable PostgreSQL: **59 capture/OAuth/token/client/Yahoo
  tests passed**, plus **2 player read/import regressions passed** in a
  separate process (database-only provider guard, idempotence and malformed
  refresh preservation). Python compilation and `git diff --check` passed.
  Existing Starlette/httpx deprecation warning only. No frontend changes;
  frontend tests/build not rerun. All post-draft semantic gates remain closed,
  Category + Team Identity preserved, no commit/push.

## Sanitized Refresh Classification - 2026-10-19

- After synthetic tests passed, performed exactly one separately authorized
  refresh diagnostic through the existing `YahooAuthService`/`YahooOAuth`
  path and existing configuration. **HTTP 400, OAuth category
  `invalid_grant`, error_description present (value never retained), content
  type category `json`, refresh requests 1, credential_changed false,
  fantasy_resource_requests 0.** Process exited 2 and stopped.
- The stored authorization grant was rejected. This does not distinguish
  revocation, expiry, or another underlying reason. One fresh normal OAuth
  authorization/consent flow is the permitted next action; no configuration,
  callback, endpoint, scopes, client credentials, or production code changed.
  No reauthorization or fantasy-resource request occurred in this task.
- Added only ignored local diagnostic code/tests under the existing private
  evidence directory. The diagnostic intercepts the existing service's one
  exact token POST, disables retries/redirects, bounds the body to 8 KiB,
  permits only strict allowlisted top-level error codes, rejects duplicate-key
  JSON, and discards descriptions, headers, tokens, and provider text before
  returning a synthetic failure to the existing service. Non-JSON, nested,
  malformed, unknown and oversized error values classify as `unknown`.
- Database access uses read-only transactions. Expiry eligibility was selected
  only in memory with autoflush disabled; rollback ran on every service exit.
  Even unexpected provider success cannot reach token persistence. An
  independent post-rollback comparison confirmed encrypted credentials,
  expiry, and update timestamp unchanged. Owner-only ignored reports contain
  only allowed status/category/presence/count/timestamp/configuration booleans.
- Validation: **55 diagnostic/OAuth/callback/token-storage/security/client/
  draft-results tests passed** on disposable PostgreSQL, including 35 local
  synthetic diagnostic tests. Covered every allowlisted error, unknown/
  malformed/ambiguous/oversized input, description redaction, one POST,
  no fantasy GET, credential preservation after 400 and unexpected 200,
  and absence of synthetic secrets/provider text from reports/logs.
  Python compilation and `git diff --check` passed. Initial run reached the
  database before readiness; rerun after `pg_isready` passed. Existing
  Starlette/httpx deprecation warning only. No frontend change/tests/build.
- Authorization is **not restored**. Identity, scoreboard, and transaction
  semantic gates remain closed. Category + Team Identity preserved; no commit
  or push.

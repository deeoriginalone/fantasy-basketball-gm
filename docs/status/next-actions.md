# Next Actions

The Waiver Center is implemented and closed out as a database-only, descriptive
post-draft capability; generic "waivers" is no longer future scope. Selected-
player replacement rankings, fixed-drop impact, bounded roster coverage,
small-sample labels, Next 7 Days, Phase-2 Best Supported Transaction,
Phase-3 descriptive role, Phase-4 roster capacity/team needs and the
non-actionable decision-support layer with the decision-first page (BEST
MEASURED OPTION, WATCH, POTENTIAL TARGETS TO CHECK IN YAHOO, HIGH/MEDIUM/
COVERED needs) are implemented. Hypothetical transaction analysis is not
Yahoo transaction history or execution.

Source Integrity & Coverage is **deployed** (2026-11-13 audit: running images
match commit `93fd50f`). Phase 4 Roster Capacity & Team Needs and the
2026-11-13 decision-support redesign (both `waiver-capacity-phase4`) are
**deployed** (2026-11-13 23:59 UTC, verified by post-deployment acceptance).
Phase 5 (`waiver-availability-phase5`: one-click REFRESH WAIVER DATA,
authoritative availability classes, the recommendation invariant, acquisition
context, timeout handling and faster reads) is **deployed** (2026-11-14 08:26
UTC), and the user's first REFRESH WAIVER DATA run (job `629bd689b6f0`,
08:31-08:33 UTC) **succeeded** with every stage verified, so persisted
rosters, slots, statuses and NBA data are current as of that run. The four
post-refresh acceptance fixes (OFS status, named gate explanations,
regular-season stats verification, mobile overflow) are **deployed**
(2026-11-14 11:40 UTC) and verified read-only. The blank Yahoo status policy
review (same day) first **rejected** treating blank as "no designation"; the
user then explicitly approved the override. The Phase-6 release
(`waiver-horizon-evidence-phase6`: the fresh-missing-field NO CURRENT YAHOO
DESIGNATION policy with the earlier status-diagnostic correction,
board/optimizer reconciliation, Next 14 Days, Rest of Season Outlook, form
windows, tiered recent sample, move intent) is **deployed** (2026-11-14
21:30 UTC, application-only: no migration, refresh or data change) and
verified read-only. A Phase-6 ordering and wording cleanup (Compare a
Specific Drop lists supported moves before WATCH; concise Next 14 Days
intent wording) is **deployed** (2026-11-15 02:36 UTC, application-only: no
migration, refresh or data change) and verified read-only, with no
recommendation change; see the [current-state report](current-state.md)
and the [2026-11-14 session record](../sessions/2026-11-14.md). Dated
acceptance counts are not current population claims.

On 2026-11-15 (11:09-11:21 UTC) the deployed Waiver Center stopped updating:
refresh status timed out, and board and best moves returned 504. Root cause:
the idle API had been swapped out to the rotational system disk, and the
deployed API kept computing reads its clients had abandoned. It is
**recovered** without a restart, and the user's own REFRESH WAIVER DATA
(job `68a294158101`) **succeeded** at 11:20:50 UTC. The heavy-read admission
fix was then validated and **deployed API-only at 14:50 UTC** (one heavy read
at a time, cancelled when its client leaves; responses unchanged). The host
limits remain. The Waiver Center is now
**PC-only**: validate at desktop 1440 × 1000 only. See the
[current-state report](current-state.md) and the
[2026-11-15 session record](../sessions/2026-11-15.md).

On 2026-11-21 a read-only decision-integrity audit reproduced the user's
09:37 UTC snapshot exactly and proved a general defect. A schedule advantage
(a game-count percentile) could outweigh a real production loss even when
the add trails in the window's Yahoo fantasy points. Rest of Season Outlook
therefore featured ADD Isaiah Jackson / DROP Jarrett Allen (+1.03): 66 × 22.6
= 1490.9 vs 63 × 30.3 = 1908.3 points.

The fix, model `waiver-decision-integrity-phase7`, adds:

- an explanation-consistency gate;
- per-pair explanations;
- transaction verdicts;
- exact drops on OTHER GOOD OPTIONS;
- labeled evidence.

It is **deployed and verified** (2026-11-21 16:36 UTC, commit `a9a0367`,
`api` and `frontend` only, no migration or data change). The live page now
features **Isaiah Jackson / Kevin Huerter (+0.412)** in Rest of Season
Outlook, and Jackson / Allen is DO NOT ADD everywhere. See the
[current-state report](current-state.md) and the
[2026-11-21 session record](../sessions/2026-11-21.md).

Driveway Dudes is Head-to-Head Points, not categories. Fantasy PPG uses
`PTS + 1.2*REB + 1.5*AST + 3*BLK + 3*STL - TO` from persisted Yahoo settings.
It uses a continual rolling waiver list, **not FAAB**. The `ros` horizon is
labeled **Rest of Season Outlook** (Phase 6); **Season Evidence** is the
historical, stat-based evidence behind it, never a projection.

## Immediate

The Phase-5 deployment, the first refresh, the 2026-11-14 acceptance-fix
patch, the Phase-6 deployment (2026-11-14 21:30 UTC), the Phase-6 ordering
and wording cleanup deployment (2026-11-15 02:36 UTC) and the heavy-read
admission deployment (2026-11-15 14:50 UTC) and the Phase-7
decision-integrity deployment (2026-11-21 16:36 UTC) are complete (see the
[current-state report](current-state.md)); do not repeat them.
Nothing below may run without explicit user authorization, and none of it
may run as a side effect of review or documentation work.

1. **Confirm in Yahoo before acting on a deployed recommendation.** The
   user's REFRESH WAIVER DATA at 15:50–15:58 UTC on 2026-11-21 (job
   `043e463ebb71`) saved the current snapshot. The live Phase-7 page shows:
   - Rest of Week: ADD DeMar DeRozan / DROP Kris Dunn (+0.589), flagged
     PRIOR-SEASON DRIVEN and drop-permanent.
   - Next 7 Days: STREAM Keldon Johnson / DROP Jarrett Allen (+0.566). The
     window holds (+28.6 FP), but it permanently drops a 30.3 FP/G player
     for a 7-day stream.
   - Next 14 Days: STREAM Keldon Johnson / DROP Jarrett Allen (+0.567),
     **FRAGILE** (+2.4 FP, less than one game).
   - Rest of Season Outlook: ADD Isaiah Jackson / DROP Kevin Huerter
     (+0.412). Jackson / Allen is DO NOT ADD.

   These are hypothetical analysis. Check FA/waiver state, locks, status and
   remaining weekly adds in Yahoo; the app never executes a move. Earlier
   answers (the Phase-6 Jackson / Allen pair and the 2026-11-14/15 pairs)
   are historical.
2. **Authorize (or not) committing and deploying Phase 7.1**, the Compare
   a Specific Drop gate fix. It is implemented and validated locally, NOT
   committed and NOT deployed.
   - **Problem (deployed Phase 7):** `build_board` picks `top_measured` by raw
     net and derives `selected_player_result` from it. In 13 of 64 drop ×
     horizon views (Rest of Season 8, Next 14 Days 3, Next 7 Days 2), the
     header names a refuted pair "Top measured option" and reads INSUFFICIENT
     EVIDENCE instead of "HOLD <drop>". For example, drop Jarrett Allen in
     Rest of Season names Isaiah Jackson while the cards say DO NOT ADD.
   - **Local fix (model `waiver-decision-integrity-phase7.1`):** a backend
     `drop_summary` from the cards' gated decisions, matching the roster
     label:
     - the answer is BEST VALID REPLACEMENT, WATCH, HOLD <drop> or CANNOT
       EVALUATE;
     - the raw leader appears only as a subordinate "HIGHEST RAW MODEL
       COMPARISON", with its gate reason and an exact-pair Analyze.
     - Nothing else changes.
   - **Validated:**
     - Backend 328 / 492; frontend unit 76/76, `tsc -b` and build; desktop
       Playwright 24/24.
     - Read-only shadow of all 64 views: 0 invariant violations; best moves
       and no-drop boards unchanged.
     - Evidence: `qa-work/2026-11-21-phase71-fix/phase71-report.md`.
   - **Deploy (only after authorization), same procedure as Phase 7:**
     1. Check memory and IO pressure.
     2. Make one commit of the 8 code files (qa-work stays untracked); run
        gitleaks and `git diff --check`.
     3. Back up the database and tag the running images `pre-phase71`.
     4. Build `api`, then `frontend`, serially.
     5. Run `docker compose up -d --no-deps api frontend`. Recreate both
        together: the version bump makes a mixed pair fail closed.
     6. Run GET-only acceptance of the 64 answers and confirm best moves
        are unchanged.

     **Rollback:** retag `pre-phase71` as latest and recreate `api` and
     `frontend`. No database rollback is needed.
3. **Watch the deployed heavy-read admission.** It has been live since
   2026-11-15 14:50 UTC (api `bdf329394c93`).
   - A cancelled read logs `status=499` with a `queue` phase in
     `request_timing`.
   - If it ever misbehaves, roll back by retagging
     `fantasy-basketball-gm-api:pre-waiver-reliability` as `latest` and
     recreating only `api`.
   - It bounds abandoned and overlapping reads; it does not fix the host
     (item 7).
4. **Validate the Waiver Center on desktop only.** It is PC-only: use
   1440 × 1000, one Playwright project (`--project=desktop`) and one worker.
   Do not run mobile/390 px projects for waiver validation. Start the browser,
   let host pressure settle and warm the API with one internal read before
   page tests. Never run heavy reads in parallel.
5. **Review the tiered-sample observations** (decision only; nothing
   changes without approval):
   - The 13% FP/G tolerance decides exactly one promotion, Kris Dunn
     (-9.5%), the Next 7 Days drop.
   - A 5-game sample can never qualify the 3 + 3 role, so only 6-game
     samples are promoted.
   - The tolerance is symmetric (it protects a hot drop and admits a hot
     add).
   - 0-2-game positive pairs still show as WATCH.
6. **Review history shrinkage and two related method questions** with the
   user (decisions only; phase 7 discloses them but changes no method):
   - **Weekly blend** (WC-04): measured PPG leans on 2025-26. On 2026-11-21:
     - DeRozan 24.89 = 0.412 × 16.54 (last 14 days) + 0.588 × 30.73
       (2025-26);
     - Dunn 19.26 = 0.375 × 16.92 + 0.625 × 20.66;
     - so DeRozan "beats" Dunn while trailing him this season (17.7 vs 23.6
       FP/G) and over the last 14 days.

     The weekly blend ignores earlier current-season games. Phase 7 labels
     the case PRIOR-SEASON DRIVEN.
   - **Short-horizon drop permanence** (WC-18): a Next 7 or Next 14 stream
     can permanently drop a much higher current-season producer (Jarrett
     Allen 30.3 vs Keldon Johnson 20.2 FP/G). Phase 7 shows "Dropping is
     permanent" on the card; whether such a stream should be supported is a
     policy decision.
   - **Schedule scale:** the schedule component is the percentile of an
     integer game count, so 1–3 games can swing it by 40–87 points. The
     phase-7 gate stops claims that fail in Yahoo points. Rescaling the
     component is a method decision.
7. **Host capacity.** The 7.3 GB shared host swaps under load; waiver reads
   then stall for minutes, nginx returns 504 at 60 s, and a new database
   connection can hit asyncpg's 60 s connect timeout (one 500 during the
   2026-11-14 patch acceptance). After an idle period the API itself is
   swapped out: at the Phase-6 baseline (21:19 UTC) health took 12 s and three
   reads returned 504 until it paged back in.
   - During the cleanup's mobile acceptance (2026-11-15 03:04-03:32 UTC) the
     API stopped answering for 28 minutes. The system disk is a single
     rotational laptop drive that also holds the 4 GB swap file; it ran at
     85% utilization on about 114 random reads/s.
   - The API kept computing heavy reads whose clients had already gone (nginx
     504, browser timeouts), so the backlog grew. Restarting only the `api`
     container (same image, no data involved) restored it.
   - **2026-11-15 11:09-11:21 UTC (user-visible incident):** the API had been
     ~93% swapped out (329 MB). The user's normal page load and retries
     caused 78,229 API major faults with the disk at 93-98%. Abandoned reads
     ran for up to 472 s, and the pool filled, so new connects timed out
     (500). One normal desktop page load reproduced it at 12:10 UTC.
   - Add memory, move services or put swap on faster storage, or give the
     `api` container a no-swap memory limit. Do not raise proxy or connect
     timeouts to hide it. Bounding concurrent heavy waiver reads and stopping
     work for disconnected clients are deployed (2026-11-15 14:50 UTC, item
     3); they bound the damage, but the host constraint itself remains.
8. **Later refreshes** are user-initiated from `/waivers` when the panel
   reports stale sources (Yahoo after 24 hours, NBA after 7 days). Never call
   the individual import routes or refresh as a side effect. An API restart or
   deploy drops the in-memory refresh job record; the panel then reads "All
   waiver evidence current as of …" from persisted evidence, which is not a
   reason to refresh. If the panel cannot read freshness, wait for the API
   instead of clicking again: a POST that timed out in the browser can still
   start the job once the API catches up (2026-11-15, job `68a294158101`).

## Remaining Evidence Roadmap

### SLICE 1 — EXISTING EVIDENCE / NO NEW PROVIDER

1. **High-confidence Yahoo-to-NBA identity reconciliation**
   - Resolve only from stable persisted evidence.
   - Never fuzzy-map on name alone or infer trades/team changes from conflict.
   - Preserve ambiguous, no-match and team-conflict cases for review.
2. **Existing NBA source capability audit**
   - Determine whether the existing source can provide game-level `USG_PCT`,
     `GS`, and `START_POSITION`.
   - Distinguish available-but-not-imported fields from unsupported or
     unverified source capability.
3. **NBA schedule completeness**
   - Determine whether the existing source contract can establish COMPLETE.
   - Row counts, all teams, date span and opponents alone do not prove
     completeness; preserve PARTIAL/UNKNOWN unless a contract proves it.

Do not prioritize another generic NBA provider before this slice establishes
whether the existing NBA source can close these gaps.

### SLICE 2 — YAHOO AUTHENTICATED IDENTITY

4. Verify authenticated Yahoo manager/team identity using explicit source
   ownership evidence. Configured Box Score Bully, a team name, roster contents
   or draft selections are not ownership proof.

### SLICE 3 — YAHOO SCOREBOARD / PERIOD

5. Verify the Yahoo scoreboard/matchup source contract.
6. Verify matchup-week/current-week/date semantics.
7. Verify stable participating team keys.
8. Verify correction/update and completeness semantics.

Rest of Week and Next 7 Days remain local Pacific calendar windows until this
slice is proved.

### SLICE 4 — YAHOO TRANSACTION / ACQUISITION CONTEXT

9. Weekly acquisitions used and remaining and the current rolling waiver
   priority are normalized from the existing supported Yahoo teams payload
   (`roster_adds`, `waiver_priority`) and `max_weekly_adds`; confirmed
   against the user's Yahoo page after the first Phase-5 refresh (2 of 4
   adds used in week 4, priority 4th on 2026-11-14).
10. Verify player waiver/free-agent state (FA/W) where supplied; the
    player-pool resource used today does not supply it, so unrostered players
    stay UNROSTERED — CONFIRM FA/WAIVER STATE IN YAHOO.
11. Verify exact claim-clear evidence where supplied (unsupported today).
12. Verify transaction stable IDs and type/status/date/team/player fields.
13. Verify pagination and correction/update semantics.

Do not infer these values from league rules: four adds per week is not
remaining adds; a continual rolling list is not current priority. Roster and
game-time locks and live IL eligibility also need verified semantics; until
then every Phase-4 capacity action (ADD ONLY, IL move, ADD + DROP) remains
conditional on Yahoo confirmation.

### SLICE 5 — REASSESS SOURCE GAPS

14. Evaluate richer injury/status evidence only if Yahoo status remains
    materially insufficient after preceding source work. Any new provider
    requires a documented contract, permitted use, stable identity, freshness
    and persistence semantics, failure preservation, tests, and a demonstrated
    material evidence gap.

### SLICE 6 — LATER MODEL / METHOD WORK

15. **Matchup quality:** require a verified source and validated method;
    opponent identity alone is not matchup difficulty.
16. **Validated forward projections:** Season Evidence remains historical;
    define inputs, method and error evaluation before prediction claims.
17. **Opponent demand:** do not infer intent or bidding from roster/draft
    behavior without validated evidence and method.
18. **What Changed / recommendation history:** define the persisted evidence
    snapshot, diff and version contract first; current waiver GETs remain
    non-writing.
19. **Outcome tracking/calibration:** define outcomes and sample coverage
    first. Evidence-quality labels are not probabilities; make no calibrated
    probability claims without validation.
20. **Yahoo transaction execution — LAST:** require a separately verified
    Yahoo write contract, authenticated ownership, state/rules/limits,
    idempotency/conflict behavior, explicit user confirmation and an audit
    trail. Hypothetical transaction analysis does not authorize execution.

## Early-Season Evidence Limit

Current-season samples may simply require more games. Legitimate early-season
small samples are not a source defect, and prior history never bypasses the
at-least-seven-current-season-game strong-action gate. Do not lower evidence
gates or tune weights to manufacture a winner.

## Secondary Draft-Era Leftovers

These remain secondary to Championship HQ/Waiver post-draft work and are not
the immediate development priority.

### Production Live

- Actual active-draft Yahoo `draftresults` behavior remains unverified.
- Source cadence and mapping remain unverified.
- Full manual fallback/correction/recovery browser acceptance remains
  unverified.
- Yahoo Mock Practice does not validate Production Live.

### Draft intelligence

- Fantrax ADP coverage remains partial; it does not establish draft rank,
  XRank, frequency, sample size or upstream update timestamp.
- Survival/wait remains heuristic and uncalibrated.
- Historical engine-versus-ranking outperformance remains unproven.

## Explicitly Unsupported / Non-Priority Work

- No FAAB for this configured league.
- Category-weakness waiver optimization is not a priority for this H2H Points
  league.
- No injury return-date forecasts or fabricated ownership percentages.
- No opponent bidding/demand claims or unsupported matchup difficulty.
- No inferred Yahoo matchup period.
- No calibrated confidence/probabilities or predictive-accuracy claim.
- No Yahoo transaction execution absent the final roadmap gate.
- No source gap may be converted to zero merely to score it.

## Historical Yahoo Source Authorization Notes

These notes preserve source-evidence chronology and safety boundaries; the
ordered roadmap above controls priority. They are not evidence that a new Yahoo
contract has passed, and they do not authorize a provider call.

- The 2026-10-19 source-evidence attempt found an expired stored access token;
  no Yahoo HTTP request was sent and no endpoint contract was established.
- On 2026-10-25, normal authorization recovery and a supported `teams` canary
  allowed existing imports. That did not establish manager ownership,
  scoreboard/matchup or transaction semantics.
- Candidate `league/{league_key}/teams`, `scoreboard` and `transactions`
  resources are not verified contracts merely because a path exists or a
  request succeeds. Explicit ownership, stable keys, week/date meaning,
  transaction fields, pagination and correction/update behavior require
  representative evidence.
- When separately authorized source work resumes, stop on authorization or
  rate-limit evidence. Never refresh OAuth or retry merely to reconcile these
  docs; do not alter credentials/scopes, probe unrelated leagues, replay
  callbacks, publish private payloads, scrape or use browser CDP as a source.
- Only after a source contract and permitted use are verified may a controlled,
  idempotent, failure-preserving persistence/import path be implemented.

All source work requires separate authorization. Do not refresh Yahoo or NBA,
start OAuth, call Fantrax, write database rows, migrate or execute Yahoo
transactions as a side effect of documentation or evidence review.

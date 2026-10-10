# ADR 0006: Heuristic Survival and Expected Wait Cost

- Status: Accepted
- Date: 2026-10-10

## Context

The existing survival estimate is not calibrated and Fantrax ADP coverage is partial. The prior wait cost, utility multiplied by probability gone, assumed no useful fallback and could not represent negative or zero wait cost.

## Decisions

- Keep survival labeled `heuristic_unvalidated`. Request ADP overrides fresh stored ADP where accepted; v2 persisted sessions use fresh stored market data. Missing/stale ADP produces null survival, not an estimate.
- Base survival remains a transparent logistic function of ADP relative to the next manager pick and team count. Optional draft frequency adjusts the estimate only when an actual value exists. Positional-run count adjusts the logistic result; Fantrax currently supplies no frequency, sample size, source timestamp, rank, or XRank.
- Calculate wait utility as roster utility plus mode adjustment, excluding the direct run bonus. The run signal is already used by the survival estimate; this keeps the same run evidence from being added a second time to expected wait value. Overall pick ranking may still expose/apply the existing run bonus.
- Choose up to five other scored candidates as fallback alternatives, ordered by wait utility. Estimate expected fallback utility as the expected highest-utility candidate available at the next pick. For fallback $i$ ordered by utility, `P(i selected) = p_i × Π(1 - p_j)` over higher-utility alternatives; sum each branch probability times its utility. If no fallback is scored or a top fallback lacks survival, fallback value is unknown.
- Hold team utility constant between now and the next pick. Do not add another scarcity, category, or survival multiplier to the expected wait equation.
- Calculate `E_wait = p_A × U_A + (1 - p_A) × E_fallback` and signed `expected_wait_cost = U_A - E_wait`. Positive means Draft now; zero/negative means Wait; missing candidate/fallback survival means Insufficient evidence.
- The fallback branch assumes independent player survival estimates and does not model opponent-specific demand or future roster/category changes. Decision confidence is low when estimates are present and unavailable otherwise; it cannot be high until calibration and input-quality criteria are established.
- `expected_loss_if_gone` remains a nonnegative conditional utility-at-stake field. `opportunity_cost_if_wait` mirrors the signed expected wait cost in the extended response.

## Consequences

- The model can show several fallback branches rather than treating the current second-ranked player as guaranteed available.
- The recommendation remains a heuristic, not a probability-calibrated forecast. No historical replay, empirical confidence interval, Monte Carlo simulation, opponent-need model, or category-league impact model is implemented.
- Low/stale ADP coverage naturally yields Insufficient evidence rather than an apparently precise answer.

## Validation

Tests verify fallback branch probabilities, the expected-wait equation, zero and negative costs, stale/missing ADP behavior, and PostgreSQL-backed utility responses. No outperformance claim is made.
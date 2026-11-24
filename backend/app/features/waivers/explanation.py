"""Explanation and consistency checks for one exact waiver comparison (model waiver-decision-integrity-phase7).

A positive roster-index change is only a supported recommendation when its explanation can be reconciled from the
returned evidence. Rules (contract consistency, no player-specific or basketball-tuned thresholds):

* ARITHMETIC: the weighted component contributions reproduce the returned net (within CALCULATION_TOLERANCE).
* CLAIMS_MEASURED: the explanation names a component as a reason only when it is in the common mask with a positive
  weighted contribution; components outside the mask are listed as omitted, with the reason.
* COMPENSATION: when the add's measured production is lower than the drop's (negative production contribution), the
  positive net depends on other components. Each such claim must hold in the league's own scoring unit:
  - schedule: the add's window Yahoo fantasy points (games in the window x model FP/G) must be at least the drop's,
    using the same games and FP/G the comparison used (an upper bound before daily lineup limits, applied to both);
  - roster fit: matched starting slots must increase;
  - opportunity: a role advantage cannot be converted into Yahoo fantasy points from the returned evidence.
  A refuted claim is removed (the net is re-measured without that component, weights renormalized as for any
  missing component). If the re-measured net is not above the near-tie threshold, the positive net is unsupported.
* NEAR_TIE: a net whose absolute value is below half of the displayed unit (two decimals) cannot show a preference.
  Calculation rounding (6-decimal before/after scores) is about 1e-6, far below that unit.

PERMANENT DROP (model waiver-permanent-drop-phase9; separate from the consistency checks above): in Rest of Week, Next 7
Days and Next 14 Days, an ADD + DROP whose consistent positive net leans on a schedule edge (the add produces less per
game) is only a short-term gain, while the drop is permanent. The window gain (Yahoo fantasy points above) must cover
the drop's production above replacement level - the best available player, never below the add - over the drop's
scheduled games after the window: max(0, drop FP/G - replacement FP/G) x games after the window. Break-even arithmetic,
no fitted threshold; Rest of Season Outlook, no-drop additions and production- or fit-led pairs are never checked.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from math import fsum

from app.features.waivers.contracts import (
    Candidate,
    ComponentContribution,
    DropAlternative,
    DropOption,
    ExplanationCheck,
    Mode,
    PairExplanation,
    PermanentDropCheck,
    ProductionBasis,
)
from app.features.waivers.production import blend_label, blend_math

NET_DISPLAY_DECIMALS = 2
CALCULATION_TOLERANCE = 1e-5
NEAR_TIE_NET = 0.5 * 10 ** -NET_DISPLAY_DECIMALS
HORIZON_LABELS = {"this_week": "Rest of Week", "next_7_days": "Next 7 Days", "next_14_days": "Next 14 Days",
    "ros": "Rest of Season Outlook"}
COMPONENT_NAMES = {"roster_fit": "roster fit", "player_value": "production", "opportunity": "opportunity (role)",
    "schedule": "schedule", "acquisition_value": "acquisition value"}
EXPLANATION_GATE = "Explanation-consistency gate"
NEAR_TIE_GATE = "Near tie"
PERMANENT_DROP_GATE = "Permanent-drop gate"
Replacement = tuple[int, str, float]


def signed(value: float | None, digits: int = NET_DISPLAY_DECIMALS) -> str:
    if value is None:
        return "unavailable"
    # A non-zero value that would print as +0.00 keeps enough precision to show its sign and size.
    if value != 0 and abs(value) < 0.5 * 10 ** -digits:
        digits = max(digits, 4)
    return f"{value:+.{digits}f}"


def _games(count: int | None) -> str:
    return "unknown games" if count is None else f"{count} game{'' if count == 1 else 's'}"


def _form_value(row: Candidate, key: str) -> tuple[float | None, int]:
    window = next((item for item in (row.form.windows if row.form else []) if item.key == key), None)
    if window is None or window.state not in {"available", "partial"}:
        return None, window.games if window is not None else 0
    return window.fantasy_ppg, window.games


def production_basis(row: Candidate, mode: Mode) -> ProductionBasis:
    """The value behind `components.player_value` for this horizon, with the exact blend when one was applied."""
    ranking = row.ranking_value
    value = ranking.value
    current_value, current_games = _form_value(row, "CURRENT_SEASON")
    if current_value is None and row.ros.season is not None and row.ros.season == row.recent.season:
        current_value, current_games = row.ros.value, row.ros.games
    common = dict(percentile=row.components.player_value, current_season_value=current_value,
        current_season_games=current_games)
    if value is None:
        return ProductionBasis(label="Production unavailable for this horizon (missing, stale or unsupported evidence).",
            **common)
    if mode == "ros":
        current = row.ros.season is not None and row.ros.season == row.recent.season
        basis = "SEASON_EVIDENCE" if current else "PREVIOUS_SEASON_FALLBACK"
        label = (f"Season Evidence {row.ros.season}: current-season Yahoo FP/G, {_games(row.ros.games)} (historical, not a projection)"
            if current else f"Previous-season fallback {row.ros.season}: no current-season row ({_games(row.ros.games)})")
        return ProductionBasis(value=round(value, 2), basis=basis, label=label, window_value=row.ros.value,
            window_games=row.ros.games, window_weight=1.0,
            math=f"{value:.2f} = {row.ros.season} Yahoo FP/G over {_games(row.ros.games)} (no blending).", **common)
    buckets = ranking.buckets
    if not buckets:
        return ProductionBasis(value=round(value, 2), basis="CURRENT_SEASON_ONLY",
            label="Current-season production (no bucket breakdown supplied)", window_value=row.recent.value,
            window_games=row.recent.games, window_weight=1.0, math=f"{value:.2f} Yahoo FP/G", **common)
    recent = next(bucket for bucket in buckets if bucket.key == "RECENT")
    prior = next((bucket for bucket in buckets if bucket.key == "PRIOR" and bucket.share > 0), None)
    return ProductionBasis(value=round(value, 2), basis="CURRENT_SEASON_BLENDED" if prior else "CURRENT_SEASON_ONLY",
        label=blend_label(buckets), window_value=row.recent.value, window_games=recent.games, window_weight=recent.share,
        prior_value=prior.value if prior else None, prior_games=prior.games if prior else 0,
        prior_season=prior.season if prior else None, prior_weight=prior.share if prior else None,
        buckets=buckets, math=blend_math(buckets, value), **common)


def _contributions(comparison: DropOption) -> list[ComponentContribution]:
    rows = []
    for key, weight in comparison.effective_weights.items():
        before, after = getattr(comparison.component_before, key), getattr(comparison.component_after, key)
        delta = getattr(comparison.component_deltas, key)
        if before is None or after is None or delta is None:
            continue
        rows.append(ComponentContribution(component=key, before=round(before, 6), after=round(after, 6),
            delta=round(delta, 6), effective_weight=round(weight, 6), weighted_contribution=round(weight * delta, 6)))
    return rows


def basis_short(basis: ProductionBasis | None) -> str:
    return {"CURRENT_SEASON_BLENDED": "this season's games blended with the previous season",
        "CURRENT_SEASON_ONLY": "this season's games", "SEASON_EVIDENCE": "current-season Season Evidence",
        "PREVIOUS_SEASON_FALLBACK": "previous-season fallback"}.get(basis.basis if basis is not None else "",
        "unavailable basis")


def _component_reason(key: str, contribution: float, explanation: PairExplanation, horizon: str) -> str:
    add, drop = explanation.add_production, explanation.drop_production
    if key == "player_value":
        if add.value is not None and drop is not None and drop.value is not None:
            versus = (f"{explanation.add_name} {add.value:.1f} vs {explanation.drop_name} {drop.value:.1f} Yahoo FP/G "
                f"({basis_short(add)})")
        elif add.value is not None:
            versus = f"{explanation.add_name} {add.value:.1f} Yahoo FP/G ({basis_short(add)})"
        else:
            versus = "measured production"
        return f"Production: {versus}, {signed(contribution)} index points"
    if key == "schedule":
        if explanation.drop_name is not None:
            return (f"Schedule: {_games(explanation.add_games)} vs {_games(explanation.drop_games)} in {horizon}, "
                f"{signed(contribution)} index points")
        return f"Schedule: {_games(explanation.add_games)} in {horizon}, {signed(contribution)} index points"
    if key == "roster_fit":
        return (f"Roster fit: matched starting slots {explanation.starting_slots_before} to "
            f"{explanation.starting_slots_after} of {explanation.starting_slots_required}, {signed(contribution)} index points")
    return f"{COMPONENT_NAMES.get(key, key).capitalize()}: {signed(contribution)} index points"


def explain_comparison(
    *,
    mode: Mode,
    add: Candidate,
    drop: Candidate | None,
    comparison: DropOption,
    window: tuple[date | None, date | None],
    omitted: dict[str, str],
    recompute: Callable[[list[str]], float | None],
    replacement: Callable[[], Replacement | None] | None = None,
) -> PairExplanation:
    """Explain `comparison` exactly as measured and run the consistency checks. `replacement` (weekly horizons only)
    returns the best available player for the permanent-drop check; it is read only when the check applies."""
    horizon = HORIZON_LABELS[mode]
    net = comparison.net_improvement
    add_basis = production_basis(add, mode)
    drop_basis = production_basis(drop, mode) if drop is not None else None
    explanation = PairExplanation(
        horizon=horizon, window_start=window[0], window_end=window[1], comparison_type=comparison.comparison_type,
        add_player_id=add.player_id, add_name=add.player_name,
        drop_player_id=drop.player_id if drop is not None else None,
        drop_name=drop.player_name if drop is not None else None,
        add_production=add_basis, drop_production=drop_basis, net=net, omitted=omitted,
        add_games=add.schedule.games_remaining, drop_games=drop.schedule.games_remaining if drop is not None else None,
        starting_slots_before=comparison.starting_slots_before, starting_slots_after=comparison.starting_slots_after,
        starting_slots_required=comparison.starting_slots_required,
    )
    if drop_basis is not None and add_basis.value is not None and drop_basis.value is not None:
        explanation.production_gap = round(add_basis.value - drop_basis.value, 2)
    if add_basis.value is not None and explanation.add_games is not None:
        explanation.add_window_points = round(add_basis.value * explanation.add_games, 1)
    if drop_basis is not None and drop_basis.value is not None and explanation.drop_games is not None:
        explanation.drop_window_points = round(drop_basis.value * explanation.drop_games, 1)
    if explanation.add_window_points is not None and explanation.drop_window_points is not None:
        explanation.window_points_gap = round(explanation.add_window_points - explanation.drop_window_points, 1)
    if net is None:
        explanation.checks = [ExplanationCheck(key="ARITHMETIC", passed=False,
            detail="Numeric impact is unavailable, so no explanation can be reconciled.")]
        explanation.statement = "No measured comparison: " + (comparison.reasons[0] if comparison.reasons else "numeric impact is unavailable.")
        explanation.blocker = explanation.checks[0].detail
        return explanation
    contributions = _contributions(comparison)
    by_key = {row.component: row.weighted_contribution for row in contributions}
    explanation.contributions = contributions
    explanation.contribution_sum = round(fsum(by_key.values()), 6)
    explanation.favorable = [key for key, value in by_key.items() if value > CALCULATION_TOLERANCE]
    explanation.unfavorable = [key for key, value in by_key.items() if value < -CALCULATION_TOLERANCE]
    keys = list(comparison.effective_weights)
    for key in ("schedule", "opportunity"):
        if key in keys:
            explanation.net_without[key] = recompute([item for item in keys if item != key])
    checks = [ExplanationCheck(key="ARITHMETIC", passed=abs(explanation.contribution_sum - net) <= CALCULATION_TOLERANCE,
        detail=(f"Weighted contributions sum to {explanation.contribution_sum:+.6f}; returned net {net:+.6f}."))]
    production_cost = by_key.get("player_value", 0.0) < -CALCULATION_TOLERANCE
    reconciled = net
    # Any comparison where the add loses production leans on other components; each such claim must hold in Yahoo
    # fantasy points, whatever the sign of the net (a near-zero net can also be an artifact of a refuted claim).
    if production_cost and drop is not None:
        explanation.compensating = [key for key in explanation.favorable if key != "player_value"]
        for key in explanation.compensating:
            if key == "schedule":
                add_points, drop_points = explanation.add_window_points, explanation.drop_window_points
                if add_points is None or drop_points is None:
                    explanation.refuted[key] = ("the schedule advantage cannot be converted into Yahoo fantasy points: "
                        "games or model FP/G are missing for a compared player")
                elif add_points < drop_points:
                    explanation.refuted[key] = (
                        f"{add.player_name} scores {abs(explanation.production_gap or 0):.1f} fewer Yahoo FP/G than "
                        f"{drop.player_name} ({add_basis.value:.1f} vs {drop_basis.value:.1f}); over {horizon} that is "
                        f"{explanation.add_games} x {add_basis.value:.1f} = {add_points:.1f} vs {explanation.drop_games} x "
                        f"{drop_basis.value:.1f} = {drop_points:.1f} Yahoo fantasy points ({explanation.window_points_gap:+.1f}), "
                        f"so {_games(explanation.add_games)} vs {_games(explanation.drop_games)} does not offset the production loss")
            elif key == "roster_fit":
                if not ((comparison.starting_slots_after or 0) > (comparison.starting_slots_before or 0)):
                    explanation.refuted[key] = "matched starting slots do not increase, so no positional need is filled"
            elif key == "opportunity":
                explanation.refuted[key] = ("a role/opportunity advantage cannot be converted into Yahoo fantasy points "
                    "from the returned evidence")
            else:
                explanation.refuted[key] = "this component cannot be reconciled with the production loss"
        if explanation.refuted:
            reconciled = recompute([key for key in keys if key not in explanation.refuted])
    explanation.reconciled_net = reconciled
    compensation_ok = net <= 0 or not explanation.refuted or (reconciled is not None and reconciled >= NEAR_TIE_NET)
    checks.append(ExplanationCheck(key="CLAIMS_MEASURED", passed=True, detail=(
        "Reasons name only components in the common mask with a positive weighted contribution: "
        + (", ".join(COMPONENT_NAMES.get(key, key) for key in explanation.favorable if key not in explanation.refuted) or "none") + ".")))
    if not explanation.compensating:
        compensation = "No compensating claim is needed: the add does not lose measured production."
    elif explanation.refuted:
        compensation = ("; ".join(f"{COMPONENT_NAMES.get(key, key)}: {reason}" for key, reason in explanation.refuted.items())
            + f". Without the unsupported claim the net is {signed(reconciled, 4)}.")
    else:
        compensation = "Every compensating claim holds in Yahoo fantasy points."
    checks.append(ExplanationCheck(key="COMPENSATION", passed=compensation_ok, detail=compensation))
    # The tie is judged on the reconciled net: a model net near zero only because a refuted claim offsets a real
    # production loss is not a tie (the evidence prefers keeping the drop).
    tie_net = reconciled if reconciled is not None else net
    explanation.near_tie = abs(tie_net) < NEAR_TIE_NET
    adjusted = " after removing the unsupported claim" if tie_net != net else ""
    checks.append(ExplanationCheck(key="NEAR_TIE", passed=not explanation.near_tie, detail=(
        f"Net {tie_net:+.6f}{adjusted} rounds to {tie_net:+.{NET_DISPLAY_DECIMALS}f} at the displayed precision: "
        "no strong preference." if explanation.near_tie
        else f"Net {tie_net:+.6f}{adjusted} is outside the {NEAR_TIE_NET:.3f} near-tie band.")))
    explanation.checks = checks
    explanation.consistent = all(check.passed for check in checks)
    failed = next((check for check in checks if not check.passed), None)
    if failed is not None:
        explanation.blocker = (f"{NEAR_TIE_GATE}: {failed.detail}" if failed.key == "NEAR_TIE"
            else f"{EXPLANATION_GATE}: {failed.detail}")
    if "schedule" in explanation.compensating and "schedule" not in explanation.refuted and add_basis.value:
        gap = explanation.window_points_gap
        if gap is not None and gap < add_basis.value:
            explanation.fragile = True
    # The production edge contradicts both current views and a prior season is in either value: the prior decided it.
    if (mode != "ros" and drop is not None and by_key.get("player_value", 0) > CALCULATION_TOLERANCE
            and drop_basis is not None and "CURRENT_SEASON_BLENDED" in {add_basis.basis, drop_basis.basis}):
        recent_trails = (add.recent.value is not None and drop.recent.value is not None
            and add.recent.value < drop.recent.value)
        season_trails = (add_basis.current_season_value is not None and drop_basis.current_season_value is not None
            and add_basis.current_season_value < drop_basis.current_season_value)
        explanation.prior_season_driven = recent_trails and season_trails
    explanation.permanent_drop = permanent_drop_check(explanation, drop, replacement)
    _write_text(explanation, by_key, horizon, add, drop)
    return explanation


def permanent_drop_check(explanation: PairExplanation, drop: Candidate | None,
        replacement: Callable[[], Replacement | None] | None) -> PermanentDropCheck | None:
    """The permanent-drop check of a weekly ADD + DROP whose consistent positive net leans on a schedule edge. None when
    it does not apply: Rest of Season Outlook, no drop, a nonpositive or unreconciled net, a production- or fit-led
    pair, or window points or remaining scheduled games that are not measured."""
    if (replacement is None or drop is None or explanation.horizon == HORIZON_LABELS["ros"] or explanation.net is None
            or explanation.net <= 0 or not explanation.consistent or "schedule" not in explanation.compensating
            or "schedule" in explanation.refuted):
        return None
    add_basis, drop_basis = explanation.add_production, explanation.drop_production
    gain, rest, window_games = explanation.window_points_gap, drop.schedule.rest_of_season_games, explanation.drop_games
    if (gain is None or rest is None or window_games is None or add_basis.value is None or drop_basis is None
            or drop_basis.value is None):
        return None
    best = replacement()
    if best is None or best[2] < add_basis.value:
        # The add is itself an available refill for the spot, so replacement level is never below the add.
        best = (explanation.add_player_id, explanation.add_name, add_basis.value)
    player_id, name, level = best
    excess = round(drop_basis.value - level, 2)
    after = max(0, rest - window_games)
    cost = round(max(0.0, excess) * after, 1)
    supported = gain >= cost
    drop_name = explanation.drop_name
    if excess <= 0:
        detail = (f"{drop_name} ({drop_basis.value:.1f} Yahoo FP/G) is not above the best available player ({name}, "
            f"{level:.1f}), so dropping {drop_name} gives up no production the waiver pool cannot replace.")
    elif after == 0:
        detail = (f"{drop_name} has no scheduled games after this window, so dropping {drop_name} gives up no later "
            "production.")
    else:
        detail = (f"{drop_name} is {excess:.1f} Yahoo FP/G above the best available player ({name}, "
            f"{drop_basis.value:.1f} vs {level:.1f}); over his {after} remaining scheduled games after this window that "
            f"is {cost:.1f} Yahoo fantasy points given up permanently, "
            f"{'covered by' if supported else 'more than'} the {gain:+.1f} window gain.")
    return PermanentDropCheck(horizon=explanation.horizon, window_gain=gain, add_value=add_basis.value,
        drop_value=drop_basis.value, add_current_season_value=add_basis.current_season_value,
        drop_current_season_value=drop_basis.current_season_value, replacement_player_id=player_id,
        replacement_name=name, replacement_value=level, drop_excess=excess, drop_rest_of_season_games=rest,
        drop_window_games=window_games, drop_games_after_window=after, permanent_cost=cost, supported=supported,
        detail=detail)


def permanent_drop_blocked(explanation: PairExplanation | None) -> PermanentDropCheck | None:
    """The failed permanent-drop check of a positive pair, or None."""
    check = explanation.permanent_drop if explanation is not None else None
    return check if check is not None and not check.supported else None


def permanent_drop_note(check: PermanentDropCheck) -> str:
    return f"{PERMANENT_DROP_GATE}: {check.detail}"


def permanent_drop_verdict(pair: str, explanation: PairExplanation, check: PermanentDropCheck) -> str:
    drop = explanation.drop_name
    alternative = check.lower_cost_drop
    if alternative is not None:
        window = ("unavailable" if alternative.window_points_gap is None else f"{alternative.window_points_gap:+.1f}")
        lower = (f" Lower-cost drop with a positive measured comparison: {alternative.player_name} (net "
            f"{signed(alternative.net)}, window {window} Yahoo FP).")
    else:
        lower = " No lower-cost drop has a positive measured comparison for this add."
    return (f"DO NOT ADD — {pair}: {check.window_gain:+.1f} Yahoo fantasy points in {check.horizon}, but dropping {drop} "
        f"permanently gives up {check.permanent_cost:.1f} ({check.drop_excess:.1f} FP/G above the best available player, "
        f"{check.replacement_name}, over his {check.drop_games_after_window} games after this window). Keep {drop}.{lower}")


def permanent_drop_label(explanation: PairExplanation, check: PermanentDropCheck) -> str:
    return (f"HOLD: Keep {explanation.drop_name}. A {check.window_gain:+.1f} Yahoo FP edge in {check.horizon} does not "
        f"cover the {check.permanent_cost:.1f} Yahoo FP permanent drop cost.")


def _write_text(explanation: PairExplanation, by_key: dict[str, float], horizon: str, add: Candidate,
        drop: Candidate | None) -> None:
    net = explanation.net or 0
    add_basis, drop_basis = explanation.add_production, explanation.drop_production
    ranked = sorted(((key, value) for key, value in by_key.items() if key in explanation.favorable
        and key not in explanation.refuted), key=lambda item: -item[1])
    explanation.primary_reason = (_component_reason(ranked[0][0], ranked[0][1], explanation, horizon) if ranked
        else "No component improves the roster index.")
    tradeoffs = []
    if explanation.fragile:
        tradeoffs.append(
            f"FRAGILE: the window edge is {explanation.window_points_gap:+.1f} Yahoo fantasy points, less than one "
            f"{add.player_name} game ({add_basis.value:.1f}); one missed game reverses it.")
    if explanation.prior_season_driven and drop_basis is not None and drop is not None:
        tradeoffs.append(
            f"PRIOR-SEASON DRIVEN: {_prior_part(add.player_name, add_basis)}; {_prior_part(drop.player_name, drop_basis)}. "
            f"On current-season evidence {add.player_name} trails: last 14 days {add.recent.value:.1f} vs "
            f"{drop.recent.value:.1f}, this season {add_basis.current_season_value:.1f} vs "
            f"{drop_basis.current_season_value:.1f} Yahoo FP/G.")
    permanent = None
    if (drop is not None and net > 0 and explanation.horizon != HORIZON_LABELS["ros"] and drop_basis is not None
            and add_basis.current_season_value is not None and drop_basis.current_season_value is not None
            and drop_basis.current_season_value > add_basis.current_season_value):
        permanent = (
            f"Dropping is permanent: {drop.player_name} has {drop_basis.current_season_value:.1f} current-season "
            f"Yahoo FP/G vs {add_basis.current_season_value:.1f} for {add.player_name}; this comparison covers only {horizon}.")
    check = explanation.permanent_drop
    if check is not None:
        permanent = f"{permanent} {check.detail}" if permanent else f"Dropping is permanent: {check.detail}"
    if permanent and check is not None and not check.supported:
        # A drop that costs more than the window gains is the pair's main tradeoff.
        tradeoffs.insert(0, permanent)
    elif permanent:
        tradeoffs.append(permanent)
    if drop is not None and "player_value" in explanation.unfavorable:
        tradeoffs.append("Production cost: " + _component_reason("player_value", by_key["player_value"], explanation,
            horizon).removeprefix("Production: ") + ".")
    if (drop is not None and net > 0 and not explanation.refuted and explanation.window_points_gap is not None
            and explanation.window_points_gap < 0):
        tradeoffs.append(f"Window points: {explanation.add_window_points:.1f} vs {explanation.drop_window_points:.1f} "
            f"Yahoo fantasy points over {horizon} ({explanation.window_points_gap:+.1f}), before daily lineup limits: "
            "a production-led move, not a gain in this window.")
    explanation.tradeoffs = tradeoffs
    explanation.primary_tradeoff = tradeoffs[0] if tradeoffs else None
    schedule_note = (f" Schedule is not part of this comparison: {explanation.omitted['schedule']}"
        if "schedule" in explanation.omitted else "")
    costs = [f"{COMPONENT_NAMES.get(key, key)} {signed(value)}" for key, value in by_key.items() if key in explanation.unfavorable]
    gains = [f"{COMPONENT_NAMES.get(key, key)} {signed(value)}" for key, value in ranked]
    refuted_text = "; ".join(explanation.refuted.values())
    if explanation.near_tie:
        explanation.statement = (f"NEAR TIE — NO STRONG PREFERENCE: net {net:+.4f} rounds to "
            f"{net:+.{NET_DISPLAY_DECIMALS}f} index points.{schedule_note}")
        return
    if net <= 0:
        target = f"keeping {drop.player_name}" if drop is not None else "keeping the open spot"
        unsupported = (f" The model's {', '.join(COMPONENT_NAMES.get(key, key) for key in explanation.refuted)} edge "
            f"does not hold: {refuted_text}; without it the net is {signed(explanation.reconciled_net)}."
            if explanation.refuted else "")
        explanation.statement = (f"No improvement: {target} is preferable under this model (net {signed(net)} index "
            f"points; {', '.join(gains + costs) or 'no component changes'}).{unsupported}{schedule_note}")
        return
    if explanation.refuted and not (explanation.reconciled_net is not None and explanation.reconciled_net >= NEAR_TIE_NET):
        explanation.statement = (f"Not supported: the {signed(net)} index change depends on a claim that does not "
            f"hold — {refuted_text}. Without it the net is {signed(explanation.reconciled_net)}.")
        return
    if drop is not None and "player_value" in explanation.unfavorable and add_basis.value is not None \
            and drop_basis is not None and drop_basis.value is not None:
        compensators = [key for key, _ in ranked]
        parts = []
        if "schedule" in compensators:
            extra = (explanation.add_games or 0) - (explanation.drop_games or 0)
            parts.append(f"{add.player_name} has {extra} more scheduled game{'s' if extra != 1 else ''} in {horizon} "
                f"({explanation.add_games} vs {explanation.drop_games}) worth {signed(by_key['schedule'])} weighted index points")
        if "roster_fit" in compensators:
            parts.append(f"matched starting slots rise from {explanation.starting_slots_before} to "
                f"{explanation.starting_slots_after} of {explanation.starting_slots_required}, worth "
                f"{signed(by_key['roster_fit'])} index points")
        window = (f" Window check: {explanation.add_games} x {add_basis.value:.1f} = {explanation.add_window_points:.1f} vs "
            f"{explanation.drop_games} x {drop_basis.value:.1f} = {explanation.drop_window_points:.1f} Yahoo fantasy points "
            f"({explanation.window_points_gap:+.1f}), before daily lineup limits." if "schedule" in compensators
            and explanation.window_points_gap is not None else "")
        dropped = (f" The {', '.join(explanation.refuted)} claim does not hold; without it the net is "
            f"{signed(explanation.reconciled_net)}." if explanation.refuted else "")
        explanation.statement = (
            f"Although {add.player_name} scores {abs(explanation.production_gap or 0):.1f} fewer Yahoo FP/G than "
            f"{drop.player_name} ({add_basis.value:.1f} vs {drop_basis.value:.1f}, {basis_short(add_basis)}), the model "
            f"prefers this swap because {' and '.join(parts)}, while production costs {signed(by_key['player_value'])} "
            f"weighted index points.{window}{dropped} Net modeled change: {signed(net)}.")
        return
    others = gains[1:]
    cost_text = f" Costs: {', '.join(costs)}." if costs else ""
    explanation.statement = (f"{explanation.primary_reason}" + (f"; also {', '.join(others)}" if others else "")
        + f".{cost_text} Net modeled change: {signed(net)}.{schedule_note}")


def _prior_part(name: str, basis: ProductionBasis) -> str:
    if basis.prior_weight and basis.prior_value is not None:
        return f"{name}'s {basis.value:.1f} is {round(basis.prior_weight * 100)}% {basis.prior_season} ({basis.prior_value:.1f})"
    return f"{name}'s {basis.value:.1f} has no prior-season component"


def short_note(explanation: PairExplanation | None) -> str:
    """A one-line reason an alternative drop's positive index is not usable: a failed consistency check or a failed
    permanent-drop check (empty when the pair is usable)."""
    if explanation is None:
        return ""
    if explanation.consistent:
        check = permanent_drop_blocked(explanation)
        return (f"permanent drop cost {check.permanent_cost:.1f} Yahoo FP exceeds the {check.window_gain:+.1f} window gain"
            if check is not None else "")
    if explanation.refuted:
        names = ", ".join(COMPONENT_NAMES.get(key, key) for key in explanation.refuted)
        window = (f" ({explanation.add_window_points:.1f} vs {explanation.drop_window_points:.1f} window Yahoo fantasy points)"
            if "schedule" in explanation.refuted and explanation.window_points_gap is not None else "")
        return f"{names} edge does not hold in Yahoo fantasy points{window}"
    if explanation.near_tie:
        return "near tie"
    return "explanation does not reconcile"


def alternatives(options: list[DropOption], chosen: DropOption | None, limit: int = 3) -> list[DropAlternative]:
    """The next measured drops for the same add (best net first) with their margin to the chosen drop."""
    rows = []
    chosen_net = chosen.net_improvement if chosen is not None else None
    for option in options:
        if option.player_id is None or (chosen is not None and option.player_id == chosen.player_id):
            continue
        explanation = option.explanation
        margin = (round(chosen_net - option.net_improvement, 6)
            if chosen_net is not None and option.net_improvement is not None else None)
        rows.append(DropAlternative(player_id=option.player_id, player_name=option.player_name,
            net=option.net_improvement, margin=margin,
            consistent=bool(explanation and explanation.consistent), near_tie=bool(explanation and explanation.near_tie),
            note=short_note(explanation) if option.net_improvement is not None and option.net_improvement > 0 else ""))
        if len(rows) >= limit:
            break
    return rows


def drop_choice_text(add: Candidate, chosen: DropOption | None, rows: list[DropAlternative]) -> str:
    """Why this drop: the chosen drop against the next measured drops for the same add."""
    if chosen is None or chosen.player_id is None or chosen.net_improvement is None:
        return ""
    if not rows:
        return f"{chosen.player_name} is the only measured drop for {add.player_name}."
    higher = [row for row in rows if row.margin is not None and row.margin < 0]
    if higher:
        skipped = "; ".join(f"{row.player_name} {signed(row.net)} ({row.note or 'not supported'})" for row in higher)
        return (f"{chosen.player_name} ({signed(chosen.net_improvement)}) is the best drop that clears every gate. "
            f"Higher-index drops were not used: {skipped}.")
    best = rows[0]
    if best.margin is not None and abs(best.margin) < NEAR_TIE_NET:
        return (f"FRAGILE DROP CHOICE: {chosen.player_name} ({signed(chosen.net_improvement)}) and {best.player_name} "
            f"({signed(best.net)}) are within {NEAR_TIE_NET:.3f} index points; the drop is decided by a near tie.")
    return (f"{chosen.player_name} gives the highest measured net ({signed(chosen.net_improvement)}); next best drop "
        f"{best.player_name} {signed(best.net)} ({signed(best.margin)} behind)"
        + (f", then {rows[1].player_name} {signed(rows[1].net)}" if len(rows) > 1 else "") + ".")

from types import SimpleNamespace

from app.services.draft.utility import (
    _availability_score,
    _expected_fallback_utility,
    _expected_wait_utility,
    _market_timing_scores,
    _mode_adjustment,
    _run_bonus,
    _survival_probability,
    _wait_decision_action,
    calculate_snake_draft_timing,
    detect_draft_runs,
    _survival_probability,
)


def test_snake_draft_picks_until_next_turn_on_both_round_sides() -> None:
    first_pick = calculate_snake_draft_timing(1, 1, 12)
    last_pick = calculate_snake_draft_timing(12, 1, 12)
    second_round = calculate_snake_draft_timing(9, 2, 12)

    assert (first_pick.current_pick_number, first_pick.next_pick_number, first_pick.picks_until_next_turn) == (1, 24, 22)
    assert (last_pick.current_pick_number, last_pick.next_pick_number, last_pick.picks_until_next_turn) == (12, 13, 0)
    assert (second_round.current_pick_number, second_round.next_pick_number, second_round.picks_until_next_turn) == (16, 33, 16)


def test_positional_run_detection_and_player_run_bonus() -> None:
    identities = {
        1: SimpleNamespace(position="C"),
        2: SimpleNamespace(position="C"),
        3: SimpleNamespace(position="C,PF"),
        4: SimpleNamespace(position="PG"),
        5: SimpleNamespace(position="SG"),
        6: SimpleNamespace(position="SF"),
    }
    runs, active = detect_draft_runs([1, 2, 3, 4, 5, 6], identities)

    assert active == {"center"}
    assert next(run for run in runs if run.position_group == "center").recent_pick_count == 3
    metric = SimpleNamespace(fantasy_value=40.0)
    assert _run_bonus(metric, {"C"}, runs) > 0
    assert _run_bonus(metric, {"PG"}, runs) == 0


def test_adp_survival_and_availability_respond_to_pick_pressure_and_scarcity() -> None:
    likely_gone = _survival_probability(20.0, 24, 12)
    likely_available = _survival_probability(40.0, 24, 12)
    assert likely_gone < likely_available
    high_frequency = _survival_probability(40.0, 24, 12, draft_frequency=100.0)
    active_run = _survival_probability(40.0, 24, 12, draft_frequency=100.0, recent_run_count=4)
    assert high_frequency < likely_available
    assert active_run < high_frequency
    less_scarce = _availability_score(likely_available, 10, 2, 12)
    more_scarce = _availability_score(likely_available, 90, 2, 12)
    more_picks_before_turn = _availability_score(likely_available, 10, 22, 12)
    assert less_scarce > more_scarce
    assert less_scarce > more_picks_before_turn


def test_market_timing_scores_distinguish_reach_from_fall() -> None:
    reach = _market_timing_scores(42.0, 25, 12)
    fall = _market_timing_scores(38.0, 40, 12)

    assert reach == (17.0, 100.0, 0.0)
    assert fall == (-2.0, 0.0, 16.7)
    assert _market_timing_scores(None, 25, 12) == (None, None, None)


def test_modes_adjust_player_profile_differently() -> None:
    safe_player = SimpleNamespace(fantasy_value=30.0, durability_score=95.0, risk_score=10.0, upside_score=40.0)
    upside_player = SimpleNamespace(fantasy_value=30.0, durability_score=60.0, risk_score=35.0, upside_score=95.0)

    assert _mode_adjustment(safe_player, "safe") > _mode_adjustment(upside_player, "safe")
    assert _mode_adjustment(upside_player, "upside") > _mode_adjustment(safe_player, "upside")
    assert _mode_adjustment(safe_player, "balanced") == 0


def test_expected_wait_cost_uses_expected_fallback_value_and_allows_nonpositive_cost() -> None:
    fallback_utility, branches = _expected_fallback_utility([
        (1, "Fallback A", 10.0, 0.5),
        (2, "Fallback B", 6.0, 0.5),
    ])
    assert fallback_utility == 6.5
    assert [branch.probability_selected_if_waiting for branch in branches] == [0.5, 0.25]

    expected_wait, wait_cost = _expected_wait_utility(10.0, 0.2, 4.0)
    assert expected_wait == 5.2
    assert wait_cost == 4.8
    assert _expected_wait_utility(10.0, 0.5, 10.0) == (10.0, 0.0)
    assert _expected_wait_utility(10.0, 0.5, 14.0) == (12.0, -2.0)
    assert _wait_decision_action(4.8) == "draft_now"
    assert _wait_decision_action(0.0) == "wait"
    assert _wait_decision_action(-2.0) == "wait"
    assert _wait_decision_action(None) == "insufficient_evidence"

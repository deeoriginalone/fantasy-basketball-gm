"""Non-actionable decision support layered on the strict waiver engine.

The strict engine (``enrich`` / ``classify_action``) alone decides ADD ONLY, MOVE TO IL THEN ADD,
ADD + DROP, WATCH, HOLD and INSUFFICIENT EVIDENCE, and this module never changes those results.
It ranks the players persisted basketball evidence can compare, so the page can still name a
BEST MEASURED OPTION, WATCH items and availability-unverified POTENTIAL TARGETS, each with the
exact reasons it is not a supported action.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from app.features.waivers.capacity import (
    CORE_POSITIONS,
    FLEX_SLOTS,
    pacific_day,
    player_positions,
    slot_accepts,
    uncovered_slots,
)
from app.features.waivers.contracts import (
    AVAILABILITY_CLASS_LABELS,
    CHECKABLE_AVAILABILITY,
    RESOLVED_IDENTITY_STATES,
    Candidate,
    DecisionOption,
    DecisionSupport,
    DecisionSupportClass,
    MeasuredProduction,
    Mode,
    NeedLevel,
    OptionGroupKey,
    OptionForm,
    OptionGroupPick,
    OptionPair,
    SampleLabel,
    availability_actionable,
    availability_class,
)
from app.features.waivers.sample import SAMPLE_TIER_LABELS, sample_assessment, sufficient_sample
from app.services.draft.player_status import recommendation_eligibility, status_is_supported, yahoo_status_label

if TYPE_CHECKING:
    from app.features.waivers.service import Context

# The model's existing descriptive shrinkage: n current games against ten prior-season games.
SHRINKAGE_GAMES = 10
# Without prior-season history, fewer games are too noisy to rank (the VERY LIMITED boundary).
MIN_UNSHRUNK_GAMES = 4
STRONG_SAMPLE_GAMES = 7
LONGER_TERM_MIN_GAMES = 20
MAX_MEASURED_CARDS = 2
WATCH_LIMIT = 5
POTENTIAL_TARGET_LIMIT = 10
SUPPORTED_TYPES = frozenset({"ADD_ONLY", "MOVE_TO_IL_THEN_ADD", "ADD_DROP"})
# Group nouns; the title is qualified by the pick's verdict, so "best" never implies a supported add.
GROUPS: tuple[tuple[OptionGroupKey, str], ...] = (
    ("BEST_GUARD", "GUARD"),
    ("BEST_WING_FORWARD", "WING / FORWARD"),
    ("BEST_CENTER", "CENTER"),
    ("BEST_MULTI_POSITION", "MULTI-POSITION OPTION"),
    ("BEST_SHORT_TERM", "SHORT-TERM SCHEDULE OPTION"),
    ("BEST_LONGER_TERM", "LONGER-TERM OPTION"),
)
VERDICT_ORDER = {"SUPPORTED_ADD": 0, "WATCH_ONLY": 1, "NEAR_TIE": 2, "DO_NOT_ADD": 3, "CANNOT_EVALUATE": 4}


def group_title(noun: str, verdict: str | None) -> str:
    if verdict == "SUPPORTED_ADD":
        return f"BEST SUPPORTED {noun} ADD"
    if verdict == "WATCH_ONLY":
        return f"BEST AVAILABLE {noun} TO MONITOR — not a supported add"
    if verdict == "NEAR_TIE":
        return f"BEST AVAILABLE {noun} — near tie, no strong preference"
    if verdict == "DO_NOT_ADD":
        return f"BEST AVAILABLE {noun} — do not add: no supported positive swap"
    return f"BEST AVAILABLE {noun} — cannot evaluate yet"
GROUP_POSITIONS = {"BEST_GUARD": {"PG", "SG"}, "BEST_WING_FORWARD": {"SF", "PF"}, "BEST_CENTER": {"C"}}
METHOD = (
    "Measured production is Yahoo-rule fantasy points per game (PTS + 1.2 REB + 1.5 AST + 3 BLK + 3 STL - TO) "
    "from persisted NBA games. The current sample (the last 14 days when present in Rest of Week, Next 7 Days and Next 14 Days, "
    "otherwise this season) is shrunk toward independent prior-season production with weight n/(n+10); without "
    f"prior-season history at least {MIN_UNSHRUNK_GAMES} current-season games are required. Import age never hides a "
    "value; it is labeled. Every featured option carries the backend verdict for its exact best comparison (SUPPORTED "
    "ADD, WATCH ONLY, NEAR TIE, DO NOT ADD or CANNOT EVALUATE) and, on a full roster, the exact drop. OTHER GOOD OPTIONS "
    "groups rank by that verdict first, then the group's own evidence, then the exact pair net. Only players absent "
    "from every current league roster (or with explicit Yahoo FA/W state) are featured; Yahoo FA/waiver state must "
    "still be confirmed in Yahoo. Players whose availability is unverified appear only as POTENTIAL TARGETS TO CHECK "
    "IN YAHOO. Decision support never creates a supported ADD, STREAM or MUST ADD."
)


def sample_label(games: int) -> SampleLabel:
    return ("EXCELLENT" if games >= 20 else "GOOD" if games >= 10 else "LIMITED" if games >= 7
        else "VERY LIMITED" if games >= 4 else "INSUFFICIENT FOR STRONG RECOMMENDATION" if games >= 1
        else "NO CURRENT-SEASON EVIDENCE")


def measured_production(
    *,
    mode: Mode,
    season: str,
    recent_value: float | None,
    recent_games: int,
    recent_as_of: datetime | None,
    recent_latest_game: date | None,
    current_value: float | None,
    current_games: int,
    current_as_of: datetime | None,
    prior_value: float | None,
    prior_games: int,
    prior_season: str | None,
    scoring_available: bool,
    now: datetime,
    today: date,
) -> MeasuredProduction:
    """Comparable non-actionable production; staleness is labeled, never used to hide the value."""
    prior = dict(prior_value=round(prior_value, 2) if prior_value is not None else None,
        prior_games=prior_games, prior_season=prior_season)
    if not scoring_available:
        return MeasuredProduction(state="unsupported", **prior,
            detail="Persisted Yahoo scoring modifiers are unavailable, so fantasy points cannot be measured.")
    if mode != "ros" and recent_games and recent_value is not None:
        basis, value, games, as_of = "RECENT", recent_value, recent_games, recent_as_of
        stale = (as_of is None or now - as_of > timedelta(days=7)
            or (recent_latest_game is not None and recent_latest_game < today - timedelta(days=7)))
        source = f"Last 14 days: {value:.1f} in {games} game{'s' if games != 1 else ''}"
    elif current_games and current_value is not None:
        basis, value, games, as_of = "CURRENT_SEASON", current_value, current_games, current_as_of
        stale = as_of is None or now - as_of > timedelta(days=7)
        source = f"{season}: {value:.1f} in {games} game{'s' if games != 1 else ''}"
    else:
        reason = ("Persisted current-season stats are incomplete for the Yahoo formula"
            if current_games or recent_games else "No current-season NBA games in persisted evidence")
        return MeasuredProduction(state="missing", **prior,
            detail=f"{reason}; a measured comparison needs this season's games.")
    if prior_value is not None:
        weight = games / (games + SHRINKAGE_GAMES)
        measured = weight * value + (1 - weight) * prior_value
        source += f", shrunk toward {prior_season} ({prior_value:.1f} in {prior_games} games) with weight {games}/{games + SHRINKAGE_GAMES}"
    else:
        weight, measured = 1.0, value
    comparable = prior_value is not None or games >= MIN_UNSHRUNK_GAMES
    detail = (f"{measured:.1f} measured Yahoo fantasy PPG. {source}. Imported {pacific_day(as_of)}"
        + (" (stale)" if stale else "") + ". Historical, not a projection.")
    if not comparable:
        detail += (f" Without prior-season history, at least {MIN_UNSHRUNK_GAMES} current-season games are needed "
            "to compare this player.")
    return MeasuredProduction(
        value=round(measured, 2), comparable=comparable, basis=basis, current_value=round(value, 2),
        current_games=games, current_season=season, current_weight=round(weight, 4), **prior,
        state="stale" if stale else "available", as_of=as_of, sample_label=sample_label(games), detail=detail,
    )


def identity_resolved(row: Candidate) -> bool:
    return row.identity_mapping_state in RESOLVED_IDENTITY_STATES


def not_comparable_reason(row: Candidate) -> str | None:
    if recommendation_eligibility(row.yahoo_status) == "excluded":
        return "Yahoo O/OFS/NA status"
    if not identity_resolved(row):
        return "Unresolved Yahoo-to-NBA identity"
    if row.measured.comparable:
        return None
    if row.measured.state == "unsupported":
        return "Yahoo scoring modifiers unavailable"
    if row.measured.value is not None:
        return f"Fewer than {MIN_UNSHRUNK_GAMES} current-season games and no prior-season history"
    if row.measured.detail.startswith("Persisted current-season stats are incomplete"):
        return "Incomplete current-season production stats"
    return "No current-season NBA games"


def _status_label(row: Candidate) -> tuple[str, str]:
    """The loader's status label and detail; candidates built without an interpretation use the token label."""
    if row.status_label is not None:
        return row.status_label, row.status_detail or ""
    return yahoo_status_label(row.yahoo_status)


def no_current_designation(row: Candidate) -> bool:
    return row.decision_status_state == "NO_CURRENT_YAHOO_DESIGNATION"


def option_form(row: Candidate) -> OptionForm | None:
    """Compact backend form and schedule numbers; the page may sort by them but never ranks decisions with them."""
    if row.form is None:
        return None
    windows = {window.key: window for window in row.form.windows}

    def pair(key: str) -> tuple[float | None, int]:
        window = windows.get(key)
        return (window.fantasy_ppg, window.games) if window is not None else (None, 0)

    def reason(key: str) -> str | None:
        window = windows.get(key)
        return (window.reason_label or None) if window is not None else "Not returned"
    (l7, g7), (l14, g14), (l30, g30) = pair("LAST_7_DAYS"), pair("LAST_14_DAYS"), pair("LAST_30_DAYS")
    (season, season_games), (previous, previous_games) = pair("CURRENT_SEASON"), pair("PREVIOUS_SEASON")
    return OptionForm(last_7_ppg=l7, last_7_games=g7, last_14_ppg=l14, last_14_games=g14, last_30_ppg=l30,
        last_30_games=g30, season_ppg=season, season_games=season_games, previous_season_ppg=previous,
        previous_season_games=previous_games, trend=row.form.trend.trend,
        next_7_games=row.schedule.next_7_days_games, next_14_games=row.schedule.next_14_days_games,
        last_7_reason=reason("LAST_7_DAYS"), last_14_reason=reason("LAST_14_DAYS"),
        last_30_reason=reason("LAST_30_DAYS"), season_reason=reason("CURRENT_SEASON"),
        previous_season_reason=reason("PREVIOUS_SEASON"))


def option_pair(row: Candidate) -> OptionPair | None:
    """The exact comparison behind an option: drop (or no drop), net and the backend explanation on one basis."""
    comparison = row.comparison
    if comparison is None:
        return None
    explanation = comparison.explanation
    add_basis = explanation.add_production if explanation is not None else None
    drop_basis = explanation.drop_production if explanation is not None else None
    return OptionPair(
        comparison_type=comparison.comparison_type, drop_player_id=comparison.player_id,
        drop_player_name=comparison.player_name if comparison.player_id is not None else None,
        net=comparison.net_improvement,
        add_ppg=add_basis.value if add_basis is not None else None,
        drop_ppg=drop_basis.value if drop_basis is not None else None,
        basis_label=add_basis.label if add_basis is not None else "",
        add_games=explanation.add_games if explanation is not None else None,
        drop_games=explanation.drop_games if explanation is not None else None,
        window_points_gap=explanation.window_points_gap if explanation is not None else None,
        starting_slots_before=comparison.starting_slots_before, starting_slots_after=comparison.starting_slots_after,
        starting_slots_required=comparison.starting_slots_required,
        statement=explanation.statement if explanation is not None else (comparison.reasons[0] if comparison.reasons else ""),
        primary_reason=explanation.primary_reason if explanation is not None else "",
        primary_tradeoff=explanation.primary_tradeoff if explanation is not None else None,
        blocker=explanation.blocker if explanation is not None else None,
        consistent=bool(explanation and explanation.consistent), near_tie=bool(explanation and explanation.near_tie),
        alternatives=list(row.drop_alternatives), drop_choice=row.drop_choice,
    )


def option_headline(row: Candidate) -> str:
    """The card's one-line answer: A ADD/DROP, B WATCH, C DO NOT ADD, D ADD ONLY / IL move (or cannot evaluate)."""
    return row.verdict_text or row.action_label


def _window_label(mode: Mode) -> str:
    return {"this_week": "Rest of Week", "next_7_days": "Next 7 Days", "next_14_days": "Next 14 Days"}.get(mode, "the rest of the season")


def _games(row: Candidate) -> tuple[int | None, str]:
    schedule = row.schedule
    if schedule.games_remaining is not None:
        return schedule.games_remaining, "partial"
    if schedule.persisted_window_games is not None:
        return schedule.persisted_window_games, "stale" if schedule.freshness == "stale" else "partial"
    return None, "unavailable"


class _Builder:
    def __init__(self, ctx: Context, candidates: list[Candidate], supported_picks: list[int]) -> None:
        self.ctx = ctx
        self.capacity = ctx.roster_capacity
        self.shape = self.capacity.transaction_shape if self.capacity is not None else "UNDETERMINED"
        self.needs = ctx.team_needs
        self.summary = [row for row in (self.needs.summary if self.needs else []) if row.level in {"HIGH", "MEDIUM"}]
        self.high_slots = {slot for row in self.summary if row.level == "HIGH" for slot in row.slots}
        self.supported_picks = list(supported_picks)
        self.candidates = {row.player_id: row for row in candidates}
        lineup_ids = {row.player_id for row in self.needs.players if row.lineup_eligible} if self.needs else set()
        self.lineup = [ctx.players[pid] for pid in ctx.roster_ids if pid in lineup_ids]
        injury_ids = ({row.player_id for row in self.capacity.assignments if row.slot_kind == "injury"}
            if self.capacity is not None else set())
        self.roster_values = sorted(
            (ctx.players[pid].measured.value, pid) for pid in ctx.roster_ids
            if pid not in injury_ids and identity_resolved(ctx.players[pid]) and ctx.players[pid].measured.comparable)
        self.floor = self.roster_values[0] if self.roster_values else None
        availability = ctx.quality.get("availability")
        self.availability_state = availability.state if availability is not None else "unknown"
        self.availability_as_of = availability.as_of if availability is not None else None

    def confirmed(self, row: Candidate) -> bool:
        return availability_actionable(row)

    def fills(self, row: Candidate) -> list:
        return [need for need in self.summary if any(slot_accepts(slot, row) for slot in need.slots)]

    def key(self, row: Candidate, high_slots: set[str] | None = None) -> tuple:
        high = self.high_slots if high_slots is None else high_slots
        return (0 if self.confirmed(row) else 1, 0 if any(slot_accepts(slot, row) for slot in high) else 1,
            -(row.measured.value or 0), -len(self.fills(row)), -row.measured.current_games, row.player_id)

    def blockers(self, row: Candidate, supported: bool) -> list[str]:
        if supported:
            return []
        ctx, items = self.ctx, []
        if self.shape == "UNDETERMINED" and self.capacity is not None:
            items.append(f"Roster capacity is undetermined: {self.capacity.short_reason}")
        if not self.confirmed(row):
            evidence = row.availability_evidence
            items.append(f"Yahoo availability is unverified: {evidence.detail}" if evidence is not None
                else "Yahoo availability is unverified: league rosters are from "
                f"{pacific_day(self.availability_as_of)} or incomplete, so this player may have been added since.")
        status = row.data_quality.get("status")
        if not row.yahoo_status:
            if not no_current_designation(row):
                items.append("Yahoo status is UNKNOWN (blank); blank is not treated as healthy.")
        elif not status_is_supported(row.yahoo_status):
            items.append(f"Yahoo status {row.yahoo_status} is not recognized.")
        if status is not None and status.state == "stale":
            items.append(f"Yahoo status comes from a stale player import ({pacific_day(status.as_of)}).")
        if row.current_season_games < STRONG_SAMPLE_GAMES:
            items.append(f"Current-season sample is {row.current_season_games} game"
                f"{'s' if row.current_season_games != 1 else ''}; supported adds need at least {STRONG_SAMPLE_GAMES}.")
        if row.measured.state == "stale":
            items.append(f"Production evidence is stale: NBA data imported {pacific_day(row.measured.as_of)}.")
        if ctx.mode != "ros" and row.measured.basis == "CURRENT_SEASON":
            items.append("No persisted games in the last 14 days; Rest of Week, Next 7 Days and Next 14 Days need recent games.")
        elif ctx.mode != "ros" and row.measured.basis == "RECENT" and not sufficient_sample(row, ctx.mode):
            assessment = sample_assessment(row, ctx.mode)
            items.append(f"Played {row.recent.games} game{'s' if row.recent.games != 1 else ''} in the last 14 days "
                f"({SAMPLE_TIER_LABELS[assessment.tier]}); weekly supported adds need at least {STRONG_SAMPLE_GAMES}, "
                f"or 5-6 with corroboration. {assessment.detail}.")
        for key, text in (("roster", "Your saved roster is stale, so roster impact cannot be measured."),
                ("settings", "League settings are older than 24 hours.")):
            quality = ctx.quality.get(key)
            if quality is None or quality.state != "available":
                items.append(text)
        if row.recommended_action_type == "HOLD":
            items.append("Measured roster impact is not positive.")
        if not items and row.evidence_blockers:
            items.append(row.evidence_blockers[0])
        return list(dict.fromkeys(items))

    def confirm(self, row: Candidate) -> list[str]:
        items = []
        if not self.confirmed(row):
            items.append("Yahoo availability (free agent or waivers)")
        elif availability_class(row) == "UNROSTERED_FROM_COMPLETE_ROSTER_SNAPSHOT":
            items.append("Free-agent or waiver state in Yahoo (the saved rosters show the player unrostered)")
        status = row.data_quality.get("status")
        if not no_current_designation(row) and (
                not status_is_supported(row.yahoo_status) or (status is not None and status.state == "stale")):
            items.append("Current Yahoo status")
        if self.shape == "UNDETERMINED":
            items.append("Whether you have an open roster spot")
        elif self.shape == "ADD_DROP" and (row.comparison is None or row.comparison.player_id is None):
            items.append("Which roster player you would drop (no measured drop comparison is available)")
        if row.current_season_games < STRONG_SAMPLE_GAMES:
            items.append("Current role and minutes (small current-season sample)")
        return items

    def roster_rank(self, row: Candidate) -> tuple[int | None, int]:
        if not row.measured.comparable or row.player_id in self.ctx.roster_ids:
            return None, len(self.roster_values)
        return 1 + sum(value > row.measured.value for value, _ in self.roster_values), len(self.roster_values) + 1

    def why(self, row: Candidate, fills: list) -> list[str]:
        items = []
        if fills:
            top = fills[0]
            comparison = row.comparison
            before = comparison.starting_slots_before if comparison is not None else None
            after = comparison.starting_slots_after if comparison is not None else None
            others = f" and also {', '.join(need.label for need in fills[1:])}" if len(fills) > 1 else ""
            # "Fills" only when the exact comparison covers more starting slots; otherwise eligibility is all it shows.
            if before is not None and after is not None and after > before:
                items.append(f"Fills the {top.label} need ({top.level.lower()} priority){others}: matched starting "
                    f"slots {before} to {after}.")
            else:
                items.append(f"Position-eligible for the {top.label} need ({top.level.lower()} priority){others}"
                    + (f"; matched starting slots stay {before} to {after}." if before is not None and after is not None
                        else "."))
        elif self.needs is not None and self.needs.summary:
            items.append("All starting positions are covered; this adds depth.")
        measured = row.measured
        if measured.value is not None:
            items.append(f"{measured.value:.1f} measured Yahoo fantasy PPG from {measured.current_games} current-season "
                f"game{'s' if measured.current_games != 1 else ''}"
                + (f", blended with {measured.prior_season}" if measured.prior_value is not None else "") + ".")
        games, state = _games(row)
        if games is not None:
            items.append(f"{games} scheduled game{'s' if games != 1 else ''} in {_window_label(self.ctx.mode)}"
                + (" (schedule import is stale)" if state == "stale" else "") + ".")
        positions = [position for position in CORE_POSITIONS if position in player_positions(row)]
        if len(positions) >= 2:
            items.append(f"Multi-position: {' / '.join(positions)}" + (
                f" covers {len(fills)} needs." if len(fills) >= 2 else "."))
        rank, count = self.roster_rank(row)
        if rank is not None:
            items.append(f"Would rank {rank} of {count} on your roster by measured fantasy PPG.")
        return items

    def option(self, row: Candidate, classification: DecisionSupportClass, rank: int, reason: str,
            detailed: bool = True) -> DecisionOption:
        supported = classification == "SUPPORTED_ACTION"
        comparable = classification not in {"UNAVAILABLE"}
        fills = self.fills(row) if comparable else []
        status_label, status_detail = _status_label(row)
        status = row.data_quality.get("status")
        if status is not None and status.state == "stale" and row.yahoo_status:
            status_detail += f" Status comes from a {pacific_day(status.as_of)} import."
        games, games_state = _games(row)
        rank_if_added, roster_count = self.roster_rank(row) if comparable else (None, len(self.roster_values))
        levels: list[NeedLevel] = [need.level for need in fills]
        measured = row.measured if identity_resolved(row) else MeasuredProduction(
            state="unavailable", detail="Yahoo-to-NBA identity is unresolved, so NBA production cannot be attributed.")
        return DecisionOption(
            player_id=row.player_id, yahoo_player_id=row.yahoo_player_id, player_name=row.player_name,
            positions=row.position, nba_team=row.nba_team,
            decision_rank=rank, classification=classification, action_type=row.recommended_action_type,
            availability=row.availability, availability_confirmed=self.confirmed(row),
            availability_label=AVAILABILITY_CLASS_LABELS[availability_class(row)],
            availability_classification=availability_class(row), availability_evidence=row.availability_evidence,
            yahoo_status=row.yahoo_status, status_label=status_label, status_detail=status_detail,
            decision_status_state=row.decision_status_state,
            measured=measured, games_in_window=games, games_in_window_state=games_state,
            fills=[need.label for need in fills], fills_level=("HIGH" if "HIGH" in levels else "MEDIUM" if levels else None),
            fills_slots=sorted({slot for need in fills for slot in need.slots}),
            multi_position=len(player_positions(row) & set(CORE_POSITIONS)) >= 2,
            evidence_level=row.evidence_quality, reason=reason,
            # Card text only for featured players; full-list rows link to the evidence dialog instead.
            why=self.why(row, fills) if comparable and detailed else [],
            blockers=self.blockers(row, supported) if detailed else [],
            confirm=[] if supported or not detailed else self.confirm(row),
            user_action=("CONFIRM IN YAHOO BEFORE ACTING" if supported
                else "CHECK IN YAHOO" if comparable else "VIEW DETAILS"),
            roster_rank_if_added=rank_if_added, roster_measured_count=roster_count,
            form=option_form(row), move_intent=row.move_intent if supported else None,
            verdict=row.verdict, verdict_text=row.verdict_text, headline=option_headline(row),
            # The exact pair and labeled evidence only for featured cards; full-list rows open details instead.
            pair=option_pair(row) if detailed and comparable else None,
            current_season_games=row.current_season_games,
            evidence_dimensions=list(row.evidence_dimensions) if detailed else [],
        )

    def build(self) -> DecisionSupport:
        ctx = self.ctx
        supported = [row for row in self.candidates.values() if row.recommended_action_type in SUPPORTED_TYPES]
        not_comparable: dict[str, int] = {}
        pool: list[Candidate] = []
        # Strict WATCH already has a positive measured comparison, so it stays WATCH even when the
        # sample is too small to rank against other players.
        strict_watch: list[Candidate] = []
        unavailable: list[tuple[Candidate, str]] = []
        for row in self.candidates.values():
            if row.recommended_action_type in SUPPORTED_TYPES:
                continue
            reason = not_comparable_reason(row)
            if reason is None:
                pool.append(row)
            elif row.recommended_action_type == "WATCH" and identity_resolved(row) and row.measured.value is not None:
                strict_watch.append(row)
            else:
                unavailable.append((row, reason))
                not_comparable[reason] = not_comparable.get(reason, 0) + 1
        rostered = 0
        # Unconfirmed availability (stale or incomplete saved rosters): never featured, only checkable.
        checkable: list[Candidate] = []
        for row in ctx.players.values():
            if availability_class(row) == "ROSTERED_BY_OTHER_TEAM" and row.player_id not in ctx.roster_ids:
                rostered += 1
            if row.availability != "unknown" or row.player_id in ctx.roster_ids or availability_actionable(row):
                continue
            reason = not_comparable_reason(row)
            if reason is not None:
                not_comparable[reason] = not_comparable.get(reason, 0) + 1
            elif availability_class(row) in CHECKABLE_AVAILABILITY:
                checkable.append(row)
        if rostered:
            not_comparable["On another team's saved roster (not a target)"] = rostered
        measured_pool = [row for row in pool if row.recommended_action_type != "HOLD"]

        if self.shape in {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD"}:
            cards = max(0, min(MAX_MEASURED_CARDS, self.capacity.additions_after_injury_moves or 0) - len(self.supported_picks))
        elif self.shape == "ADD_DROP":
            cards = 0 if self.supported_picks else 1
        else:
            cards = 1
        floor = self.floor[0] if self.floor else None
        eligible_best = [row for row in measured_pool
            if self.shape != "ADD_DROP" or floor is None or row.measured.value > floor]
        best: list[Candidate] = []
        lineup = [*self.lineup, *(ctx.players[pid] for pid in self.supported_picks)]
        for _ in range(cards):
            chosen = {row.player_id for row in best}
            remaining = [row for row in eligible_best if row.player_id not in chosen]
            if not remaining:
                break
            open_now = uncovered_slots(lineup, ctx.needs_slots) if ctx.needs_slots else []
            high = {slot for slot in open_now if slot not in FLEX_SLOTS}
            pick = min(remaining, key=lambda row: self.key(row, high))
            best.append(pick)
            lineup.append(pick)
        best_ids = [row.player_id for row in best]

        used = set(best_ids) | set(self.supported_picks)
        groups: list[OptionGroupPick] = []
        featured: dict[int, str] = {}
        ranked_pool = sorted(measured_pool, key=self.key)
        # Every comparable, confirmed-available player can answer a group's transaction question: other supported
        # adds, WATCH, and players whose best comparison says DO NOT ADD. Leaving supported and HOLD players out made
        # groups feature only insufficient-evidence leftovers (2026-11-21 audit, WC-08).
        group_pool = [*(row for row in supported if row.player_id not in used), *pool, *strict_watch]
        for key, noun in GROUPS:
            members, group_key, empty = self.group(key, group_pool)
            ranked = sorted(members, key=group_key) if group_key else []
            pick = next((row for row in ranked if row.player_id not in used), None)
            if pick is not None:
                used.add(pick.player_id)
                featured[pick.player_id] = self.group_reason(key, pick)
                groups.append(OptionGroupPick(key=key, title=group_title(noun, pick.verdict), player_id=pick.player_id,
                    verdict=pick.verdict))
            else:
                groups.append(OptionGroupPick(key=key, title=f"BEST AVAILABLE {noun}", empty_reason=(
                    f"The best option here is already shown above: {ranked[0].player_name}." if ranked else empty)))
        watch = [row for row in sorted([*ranked_pool, *strict_watch], key=self.key) if row.player_id not in used and (
            row.recommended_action_type == "WATCH"
            or (floor is not None and row.measured.value > floor)
            or (floor is None and bool(self.fills(row))))][:WATCH_LIMIT]
        watch_ids = [row.player_id for row in watch]
        used |= set(watch_ids)
        ranked_checkable = sorted(checkable, key=self.key)
        potential = ranked_checkable[:POTENTIAL_TARGET_LIMIT] if self.availability_state != "available" else []

        classes: dict[int, DecisionSupportClass] = {pid: "BEST_MEASURED_OPTION" for pid in best_ids}
        ranked_all = sorted([*pool, *strict_watch], key=self.key)
        for row in ranked_all:
            # A group pick keeps its own class; its card shows the backend verdict (WATCH ONLY, DO NOT ADD, ...).
            classes.setdefault(row.player_id, "WATCH" if (
                row.recommended_action_type == "WATCH" or row.player_id in watch_ids) else "MEASURED")
        order: list[tuple[Candidate, DecisionSupportClass, str]] = [
            (row, "SUPPORTED_ACTION", featured.get(row.player_id) or row.action_label)
            for row in sorted(supported, key=lambda row: (row.decision_priority or 10**6, row.player_id))]
        for row in best:
            fills = self.fills(row)
            order.append((row, "BEST_MEASURED_OPTION", "Strongest measured option" + (
                f" for the {fills[0].label} need" if fills else "") + f": {row.measured.value:.1f} Yahoo fantasy PPG."))
        for tier in ("WATCH", "MEASURED"):
            order.extend((row, tier, featured.get(row.player_id) or self.reason(row, tier, floor))
                for row in ranked_all if classes[row.player_id] == tier)
        order.extend((row, "POTENTIAL_TARGET", f"Measured {row.measured.value:.1f} Yahoo fantasy PPG; "
            f"{AVAILABILITY_CLASS_LABELS[availability_class(row)].lower()} — check in Yahoo before acting.")
            for row in ranked_checkable)
        order.extend((row, "UNAVAILABLE", reason + "; this player cannot be compared.")
            for row, reason in sorted(unavailable, key=lambda item: (not self.confirmed(item[0]), item[0].player_id)))
        detailed = (set(self.supported_picks) | set(best_ids) | set(featured) | set(watch_ids)
            | {row.player_id for row in potential} | {row.player_id for row in supported})
        options = [self.option(row, classification, index + 1, reason, row.player_id in detailed)
            for index, (row, classification, reason) in enumerate(order)]

        comparable_count = len(measured_pool)
        if self.supported_picks:
            state, headline = "SUPPORTED_ACTION", (f"{len(self.supported_picks)} supported move"
                f"{'s' if len(self.supported_picks) != 1 else ''} available.")
            detail = "Supported moves clear every evidence gate; measured options below are alternatives to check."
        elif best:
            state = "BEST_MEASURED_OPTION"
            headline = f"Best measured option: {best[0].player_name} — not yet a supported add."
            detail = ("The strict evidence gates block a supported move, but persisted basketball evidence can still "
                "compare players. Check these options in Yahoo before acting.")
        elif watch or any(row.recommended_action_type == "WATCH" for row in [*measured_pool, *strict_watch]):
            state = "WATCH"
            headline = ("No measured option out-produces your lowest-producing roster player."
                if self.shape == "ADD_DROP" else "No measured option is strong enough to feature; watch the players below.")
            detail = "Nothing is recommended now. WATCH players are measurable but not ready."
        elif potential:
            state = "POTENTIAL_TARGETS"
            headline = "No player is confirmed available yet."
            detail = (f"Saved Yahoo rosters are not all current, so no player can be confirmed available. "
                f"{len(checkable)} measurable player{'s' if len(checkable) != 1 else ''} were not on any saved roster: "
                "refresh waiver data, or check the POTENTIAL TARGETS in Yahoo before acting.")
        else:
            state = "UNAVAILABLE"
            headline = "No player can be compared yet."
            reasons = sorted(not_comparable.items(), key=lambda item: (-item[1], item[0]))
            detail = ("Persisted evidence cannot support a measured comparison: "
                + "; ".join(f"{reason}: {count}" for reason, count in reasons[:4]) + "." if reasons
                else "No available or availability-unverified players exist in the persisted pool.")
        availability_note = ("League rosters are current: featured players were absent from every current league roster. "
            "Yahoo does not state free-agent vs waiver status in this import, so confirm it in Yahoo."
            if self.availability_state == "available" else
            f"League rosters are from {pacific_day(self.availability_as_of)} or incomplete, so availability is "
            "unverified. Players who were not on any saved league roster appear only as POTENTIAL TARGETS TO CHECK IN "
            "YAHOO; they may have been added since.")
        return DecisionSupport(
            state=state, headline=headline, detail=detail, availability_state=self.availability_state,
            availability_note=availability_note, best_measured_ids=[row.player_id for row in best], groups=groups,
            watch_ids=[row.player_id for row in watch], potential_target_ids=[row.player_id for row in potential],
            potential_target_count=len(checkable), options=options, supported_count=len(self.supported_picks),
            comparable_count=comparable_count, not_comparable_reasons=dict(sorted(not_comparable.items())),
            roster_floor_ppg=self.floor[0] if self.floor else None,
            roster_floor_player_id=self.floor[1] if self.floor else None,
            method=METHOD,
            limitations=[
                "Decision support never upgrades a player to ADD, STREAM or MUST ADD; supported actions use the strict evidence gates.",
                "Only players with confirmed Yahoo availability are featured. POTENTIAL TARGETS were absent from every saved league roster when it was imported; they may have been added since.",
                "Players on another team's saved roster are never targets. A fresh, verified Yahoo record without a status field is NO CURRENT YAHOO DESIGNATION, not a medical-health guarantee; any other blank Yahoo status remains UNKNOWN, not healthy. Yahoo O/OFS/NA players and unresolved identities are never targets.",
                "Measured production is historical Yahoo-rule fantasy PPG, not a projection. Stale imports are labeled, not hidden.",
            ],
        )

    def group(self, key: OptionGroupKey, pool: list[Candidate]):
        """Members and order of one group: the verdict first (supported add, WATCH ONLY, near tie, DO NOT ADD,
        cannot evaluate), then confirmed availability, then the group's own evidence, then the exact pair net."""
        def tier(row: Candidate) -> tuple[int, int]:
            return VERDICT_ORDER.get(row.verdict, len(VERDICT_ORDER)), 0 if self.confirmed(row) else 1

        def net(row: Candidate) -> float:
            return -(row.net_improvement if row.net_improvement is not None else float("-inf"))
        if key in GROUP_POSITIONS:
            wanted = GROUP_POSITIONS[key]
            noun = {"BEST_GUARD": "guard", "BEST_WING_FORWARD": "wing or forward", "BEST_CENTER": "center"}[key]
            return ([row for row in pool if player_positions(row) & wanted],
                lambda row: (*tier(row), net(row), -(row.measured.value or 0), row.player_id),
                f"No measurable {noun} option.")
        if key == "BEST_MULTI_POSITION":
            return ([row for row in pool if len(player_positions(row) & set(CORE_POSITIONS)) >= 2],
                lambda row: (*tier(row), -len(self.fills(row)), net(row), -(row.measured.value or 0), row.player_id),
                "No measurable multi-position option.")
        if key == "BEST_SHORT_TERM":
            if self.ctx.mode == "ros":
                return [], None, ("Rest of Season Outlook is a longer-term view; choose Rest of Week, Next 7 Days or Next 14 Days for "
                    "schedule-driven options.")
            return ([row for row in pool if _games(row)[0] is not None],
                lambda row: (*tier(row), -(_games(row)[0] or 0), net(row), -(row.measured.value or 0), row.player_id),
                "No measurable option has persisted schedule rows in this window.")
        return ([row for row in pool if row.measured.current_games + row.measured.prior_games >= LONGER_TERM_MIN_GAMES],
            lambda row: (*tier(row), -(row.ros.value or 0), net(row), row.player_id),
            f"No measurable option has at least {LONGER_TERM_MIN_GAMES} games across this season and last season.")

    def group_reason(self, key: OptionGroupKey, row: Candidate) -> str:
        rank, count = self.roster_rank(row)
        context = f" Would rank {rank} of {count} on your roster by measured fantasy PPG." if rank is not None else ""
        return self._group_reason(key, row) + context

    def _group_reason(self, key: OptionGroupKey, row: Candidate) -> str:
        value = _ppg(row.measured.value)
        if key == "BEST_MULTI_POSITION":
            fills = self.fills(row)
            return (f"Covers {len(fills)} needs; measured {value} Yahoo fantasy PPG." if len(fills) >= 2
                else f"Most flexible option in its verdict tier; measured {value} Yahoo fantasy PPG.")
        if key == "BEST_SHORT_TERM":
            games, state = _games(row)
            return (f"Most scheduled games in {_window_label(self.ctx.mode)} within its verdict tier ({games}"
                + (", stale schedule" if state == "stale" else "") + f"); measured {value} Yahoo fantasy PPG.")
        if key == "BEST_LONGER_TERM":
            return (f"Strongest Season Evidence in its verdict tier ({_ppg(row.ros.value)} Yahoo FP/G, "
                f"{LONGER_TERM_MIN_GAMES}+ games across this season and last); historical, not a projection.")
        noun = {"BEST_GUARD": "guard", "BEST_WING_FORWARD": "wing / forward", "BEST_CENTER": "center"}[key]
        return f"Top available {noun} by verdict, then exact pair net; measured {value} Yahoo fantasy PPG."

    def reason(self, row: Candidate, tier: str, floor: float | None) -> str:
        value = row.measured.value
        if row.recommended_action_type == "WATCH":
            return "Positive measured impact, but the sample is too small for a supported add."
        if tier == "WATCH":
            return (f"{value:.1f} Yahoo fantasy PPG" + (", above your lowest-producing roster player"
                if floor is not None and value > floor else "") + "; ranks behind the featured options.")
        return f"Measured {value:.1f} Yahoo fantasy PPG."


def _ppg(value: float | None) -> str:
    return "unavailable" if value is None else f"{value:.1f}"


def build_decision_support(ctx: Context, candidates: list[Candidate], supported_picks: list[int]) -> DecisionSupport:
    """`candidates`: enriched confirmed-available, recommendation-eligible players (strict actions set).
    `supported_picks`: the strict supported moves featured as BEST MOVES, in order."""
    return _Builder(ctx, candidates, supported_picks).build()


__all__ = [
    "build_decision_support", "identity_resolved", "measured_production", "not_comparable_reason", "sample_label",
]

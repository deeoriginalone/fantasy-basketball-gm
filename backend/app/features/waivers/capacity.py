"""Backend-owned roster-capacity and team-needs analysis.

Capacity is derived only from persisted Yahoo roster positions plus persisted Yahoo slot
assignments (``selected_position``). It is never inferred from the number of rostered players,
and missing, stale or conflicting evidence fails closed instead of defaulting to ADD + DROP.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from statistics import median
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from app.features.waivers.contracts import (
    Candidate,
    Evidence,
    InjuryMoveBlocker,
    InjuryMoveOption,
    LineupDay,
    Mode,
    NeedPlayer,
    NeedSummary,
    PositionFamily,
    ProductionNeed,
    RosterAssignment,
    RosterCapacity,
    RosterSlot,
    SlotCoverage,
    SlotKind,
    TeamNeed,
    TeamNeeds,
)
from app.services.draft.metrics import _selected_position_positions
from app.services.draft.player_status import recommendation_eligibility
from app.services.draft.utility import _maximum_slot_matching, _slot_accepts, _slot_positions

INJURY_SLOTS = frozenset({"IL", "IL+", "IR", "IR+"})
FLEX_SLOTS = frozenset({"UTIL", "UT"})
CORE_POSITIONS = ("PG", "SG", "SF", "PF", "C")
PACIFIC = ZoneInfo("America/Los_Angeles")
# Positional needs are reported per family; UTIL and bench are depth, never positional needs.
POSITION_FAMILIES: tuple[tuple[PositionFamily, tuple[str, ...]], ...] = (
    ("GUARD", ("PG", "SG", "G")),
    ("WING_FORWARD", ("SF", "PF", "F")),
    ("CENTER", ("C",)),
)
NEED_LEVEL_ORDER = {"HIGH": 0, "MEDIUM": 1, "COVERED": 2}
# Specific positions are reported before combo and flex slots.
NEED_SLOT_ORDER = ("PG", "SG", "SF", "PF", "C", "G", "F", "UTIL", "UT")
CAPACITY_LIMITATIONS = [
    "Capacity uses persisted Yahoo roster positions and persisted Yahoo slot assignments only; it is never inferred from the number of rostered players.",
    "Roster-capacity recommendation requiring Yahoo confirmation: roster locks, game-time locks, waiver-claim timing, weekly add usage and live injury eligibility are not verified.",
    "Moving a player to IL keeps that player on the roster; it is never treated as a drop.",
    "Direct injury-slot additions apply only to injured (IL-eligible) available players. Yahoo O/OFS/NA players remain excluded from recommendations, so that league rule never creates a recommended add.",
    "Injury return timing is not forecast.",
]
NEEDS_LIMITATIONS = [
    "Positional need uses Yahoo eligibility and maximum slot matching measured once for the whole lineup; eligibility is not player quality.",
    "Out (O) and Not Active (NA) players and players in injury slots cannot fill lineup slots. Players without an explicit Yahoo status count as lineup-eligible: NO CURRENT YAHOO DESIGNATION is not a medical-health guarantee, and any other blank status is UNKNOWN, not healthy.",
    "Daily lineup coverage is descriptive persisted-schedule evidence, not a lineup optimizer, start guarantee or projection.",
    "Driveway Dudes is Head-to-Head Points: needs use roster construction and the Yahoo points formula, not category weaknesses.",
]


@dataclass(frozen=True)
class RosterEntryEvidence:
    player_id: int
    player_name: str
    positions: str | None
    roster_slot: str | None
    eligible_positions: tuple[str, ...] | None
    yahoo_status: str | None
    status_state: str
    injury_note: str | None = None
    coverage_date: date | None = None
    status_label: str | None = None
    decision_status_state: str = "UNKNOWN"


def normalized_slot(value: object) -> str | None:
    text = str(value or "").strip().upper()
    return text or None


def slot_kind(position: str, is_starting: object = 1) -> SlotKind:
    if position in INJURY_SLOTS:
        return "injury"
    if position == "BN":
        return "bench"
    if (position in FLEX_SLOTS or _slot_positions(position)) and str(is_starting) != "0":
        return "starting"
    return "unsupported"


def _count(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number < 0 or not number.is_integer():
        return None
    return int(number)


def slot_configuration(roster_positions: Iterable[Any] | None) -> tuple[list[RosterSlot], list[str]]:
    counts: dict[str, int] = {}
    kinds: dict[str, SlotKind] = {}
    problems: list[str] = []
    for row in roster_positions or []:
        if not isinstance(row, dict):
            problems.append("A persisted roster-position entry is not an object.")
            continue
        position = normalized_slot(row.get("position"))
        count = _count(row.get("count"))
        if position is None or count is None:
            problems.append(
                f"Persisted roster position {row.get('position')!r} has invalid count {row.get('count')!r}."
            )
            continue
        counts[position] = counts.get(position, 0) + count
        kinds[position] = slot_kind(position, row.get("is_starting_position", 1))
    return [RosterSlot(position=position, count=count, kind=kinds[position])
        for position, count in counts.items()], problems


def starting_slot_list(slots: list[RosterSlot]) -> list[str]:
    return [slot.position for slot in slots if slot.kind == "starting" for _ in range(slot.count)]


@lru_cache(maxsize=1024)
def position_set(position: str) -> frozenset[str]:
    """Canonical core positions for a Yahoo position string; pair comparisons call this hundreds of
    thousands of times per request, so the parse is cached on the (small) set of distinct strings."""
    return frozenset(_selected_position_positions(position))


def player_positions(row: Candidate) -> frozenset[str]:
    return position_set(row.position or "")


def lineup_eligible(row: Candidate) -> bool:
    return recommendation_eligibility(row.yahoo_status) != "excluded"


def slot_accepts(slot: str, row: Candidate) -> bool:
    return _slot_accepts(slot, player_positions(row))


def slot_core_positions(slot: str) -> list[str]:
    if slot in FLEX_SLOTS:
        return list(CORE_POSITIONS)
    return [position for position in CORE_POSITIONS if position in _slot_positions(slot)]


def need_order(slot: str) -> tuple[int, str]:
    return (NEED_SLOT_ORDER.index(slot) if slot in NEED_SLOT_ORDER else len(NEED_SLOT_ORDER), slot)


@lru_cache(maxsize=16384)
def _matched_slot_indexes(positions: tuple[str, ...], slots: tuple[str, ...]) -> frozenset[int]:
    return frozenset(_maximum_slot_matching(
        [_selected_position_positions(position) for position in positions], list(slots),
    ))


def uncovered_slots(players: Iterable[Candidate], slots: list[str]) -> list[str]:
    """Starting slots the players cannot fill under one maximum matching of the whole lineup."""
    positions = tuple(sorted(row.position or "" for row in players))
    matched = _matched_slot_indexes(positions, tuple(slots))
    return [slot for index, slot in enumerate(slots) if index not in matched]


def newly_covered_slot(before: list[str], after: list[str], player: Candidate) -> str | None:
    gained = list((Counter(before) - Counter(after)).elements())
    if len(after) < len(before):
        if gained:
            return min(gained, key=need_order)
        accepted = [slot for slot in before if slot_accepts(slot, player)]
        return min(accepted, key=need_order) if accepted else None
    return None


def eligible_positions_from_payload(payload: dict[str, Any]) -> tuple[str, ...] | None:
    value = payload.get("eligible_positions")
    items = value.values() if isinstance(value, dict) else value if isinstance(value, list) else None
    if items is None:
        return None
    result: list[str] = []
    for item in items:
        text = normalized_slot(item.get("position") if isinstance(item, dict) else item)
        if text and text not in result:
            result.append(text)
    return tuple(result)


def coverage_date_from_payload(payload: dict[str, Any]) -> date | None:
    selected = payload.get("selected_position")
    if isinstance(selected, list):
        selected = {key: value for fragment in selected if isinstance(fragment, dict)
            for key, value in fragment.items()}
    if not isinstance(selected, dict) or not selected.get("date"):
        return None
    try:
        return date.fromisoformat(str(selected["date"]))
    except ValueError:
        return None


def _status_label(status: str | None) -> str:
    return status or "blank (UNKNOWN)"


def pacific_day(value: datetime | None) -> str:
    return value.astimezone(PACIFIC).date().isoformat() if value is not None else "an unknown date"


def _capacity_headline(
    *,
    shape: str,
    open_roster: int | None,
    occupied_roster: int | None,
    non_injury: int,
    moves: list[InjuryMoveOption],
    settings_state: str,
    roster_state: str,
    roster_as_of: datetime | None,
    unassigned: int,
    roster_count: int,
    conflicting: bool,
) -> tuple[str, str]:
    """One plain-language headline and one short reason; full blockers stay in `blockers`."""
    if shape == "ADD_ONLY":
        return (f"{open_roster} OPEN ROSTER SPOT{'S' if open_roster != 1 else ''} — NO DROP REQUIRED",
            f"{occupied_roster} of {non_injury} regular roster spots are used; players in IL do not use them.")
    if shape == "MOVE_TO_IL_THEN_ADD":
        names = " AND ".join(move.player_name.upper() for move in moves)
        spots = "A ROSTER SPOT" if len(moves) == 1 else f"{len(moves)} ROSTER SPOTS"
        return (f"MOVE {names} TO IL TO OPEN {spots}",
            f"All {non_injury} regular roster spots are used. An IL move keeps the player on your roster; it is not a drop.")
    if shape == "ADD_DROP":
        return ("ROSTER FULL — AN ADD REQUIRES A DROP",
            f"All {non_injury} regular roster spots are used and no injured player can move to an open IL slot.")
    parts = []
    if roster_state in {"missing", "not_imported"}:
        parts.append("no saved Yahoo roster exists for your team")
    elif roster_state != "available":
        parts.append(f"your saved roster is from {pacific_day(roster_as_of)}")
    if unassigned:
        parts.append(f"Yahoo roster slots are not saved for {unassigned} of {roster_count} players")
    if settings_state != "available":
        parts.append("league settings are " + ("older than 24 hours" if settings_state == "stale" else "missing"))
    if conflicting:
        parts.append("saved roster slots conflict with the league settings")
    reason = "; ".join(parts) or "required roster evidence is missing"
    return "ROSTER CAPACITY NEEDS A YAHOO REFRESH", reason[0].upper() + reason[1:] + "."


def analyze_roster_capacity(
    *,
    roster_positions: Iterable[Any] | None,
    settings_state: str,
    roster_state: str,
    roster_as_of: datetime | None,
    status_as_of: datetime | None,
    entries: list[RosterEntryEvidence],
    today: date,
) -> RosterCapacity:
    slots, problems = slot_configuration(roster_positions)
    by_slot = {slot.position: slot for slot in slots}
    blockers: list[str] = []
    warnings: list[str] = []
    stale = missing = conflicting = False
    if settings_state != "available":
        stale = stale or settings_state == "stale"
        missing = missing or settings_state != "stale"
        blockers.append(
            f"Yahoo league settings evidence is {settings_state}; use REFRESH WAIVER DATA so persisted roster positions are current."
        )
    if problems:
        conflicting = True
        blockers.extend(problems)
    if not slots:
        missing = True
        blockers.append("No persisted Yahoo roster positions are available for capacity analysis.")
    unsupported = sorted(slot.position for slot in slots if slot.kind == "unsupported")
    if unsupported:
        conflicting = True
        blockers.append(f"Roster slot types {', '.join(unsupported)} have no verified capacity semantics.")
    if roster_state in {"missing", "not_imported"}:
        missing = True
        blockers.append(
            "No persisted Yahoo roster snapshot exists for the configured team; use REFRESH WAIVER DATA."
        )
    elif roster_state != "available":
        stale = True
        blockers.append(
            f"The configured roster snapshot is {roster_state}: it is older than 24 hours or predates the latest "
            "league/team/settings import. Use REFRESH WAIVER DATA before relying on roster capacity."
        )

    counts: Counter[str] = Counter()
    unassigned: list[RosterEntryEvidence] = []
    unknown_slots: list[tuple[RosterEntryEvidence, str]] = []
    assignments: list[RosterAssignment] = []
    for entry in sorted(entries, key=lambda row: row.player_id):
        slot = normalized_slot(entry.roster_slot)
        kind = by_slot[slot].kind if slot in by_slot else None
        if slot is None:
            unassigned.append(entry)
        elif slot not in by_slot:
            unknown_slots.append((entry, slot))
        else:
            counts[slot] += 1
        known = entry.eligible_positions is not None
        eligible_injury = [
            candidate.position for candidate in slots
            if candidate.kind == "injury" and known and candidate.position in (entry.eligible_positions or ())
        ]
        excluded = recommendation_eligibility(entry.yahoo_status) == "excluded"
        in_injury_slot = kind == "injury"
        injured = excluded or bool(eligible_injury) or in_injury_slot
        if in_injury_slot:
            detail = f"In {slot}: on the roster without using a non-injury roster spot or lineup slot."
        elif excluded:
            detail = f"Yahoo status {entry.yahoo_status} excludes lineup use while occupying {slot or 'an unknown slot'}."
        elif slot is None:
            detail = "Yahoo slot assignment is not persisted."
        else:
            detail = f"Occupies {slot} ({kind or 'unknown'} slot)."
        assignments.append(RosterAssignment(
            player_id=entry.player_id, player_name=entry.player_name, positions=entry.positions,
            roster_slot=slot, slot_kind=kind, yahoo_status=entry.yahoo_status,
            status_state=entry.status_state if entry.status_state in {
                "available", "partial", "missing", "stale", "unknown", "unsupported", "unavailable",
            } else "unknown",
            status_label=entry.status_label,
            decision_status_state=entry.decision_status_state if entry.decision_status_state in {
                "EXCLUDED", "UNCERTAIN", "NO_CURRENT_YAHOO_DESIGNATION",
            } else "UNKNOWN",
            eligible_positions_known=known, eligible_injury_slots=eligible_injury,
            injured=injured, lineup_eligible=not in_injury_slot and not excluded,
            injury_note=entry.injury_note, detail=detail,
        ))
    if unassigned:
        missing = True
        blockers.append(
            f"Yahoo slot assignments (selected_position) are not persisted for {len(unassigned)} of {len(entries)} "
            "roster players; capacity is never inferred from player counts. Use REFRESH WAIVER DATA "
            "to save current slots."
        )
    if unknown_slots:
        conflicting = True
        blockers.append("Persisted slot assignments reference slots absent from the persisted roster positions: "
            + ", ".join(f"{entry.player_name} ({slot})" for entry, slot in unknown_slots) + ".")
    overfilled = sorted(slot for slot, count in counts.items() if count > by_slot[slot].count)
    if overfilled:
        conflicting = True
        blockers.append("Persisted slot assignments exceed configured slot counts for "
            + ", ".join(f"{slot} ({counts[slot]}/{by_slot[slot].count})" for slot in overfilled)
            + "; the roster evidence conflicts.")
    ineligible_injury = [row for row in assignments if row.slot_kind == "injury"
        and row.eligible_positions_known and row.roster_slot not in row.eligible_injury_slots]
    if ineligible_injury:
        conflicting = True
        blockers.append(", ".join(row.player_name for row in ineligible_injury)
            + " occupy an injury slot, but persisted Yahoo eligibility no longer lists that slot. "
            "Resolve the roster in Yahoo (activate or move the player) before relying on capacity.")
    mismatched = [row for row in assignments if row.slot_kind == "starting" and row.roster_slot
        and not _slot_accepts(row.roster_slot, _selected_position_positions(row.positions or ""))]
    if mismatched:
        warnings.append("Persisted assignments place " + ", ".join(
            f"{row.player_name} in {row.roster_slot}" for row in mismatched
        ) + " without matching display-position eligibility; capacity counts are unaffected.")
    coverage_dates = sorted({entry.coverage_date for entry in entries if entry.coverage_date})
    assignment_as_of = coverage_dates[0] if coverage_dates else None
    if len(coverage_dates) > 1:
        warnings.append("Persisted slot assignments cover different Yahoo dates: "
            + ", ".join(day.isoformat() for day in coverage_dates) + ".")
    if assignment_as_of is not None and assignment_as_of < today:
        warnings.append(
            f"Persisted slot assignments describe {assignment_as_of.isoformat()}; lineup or IL changes made in Yahoo after that date are not reflected."
        )

    def capacity_of(kind: str) -> int:
        return sum(slot.count for slot in slots if slot.kind == kind)

    active, bench, injury = capacity_of("starting"), capacity_of("bench"), capacity_of("injury")
    non_injury = active + bench
    complete = bool(slots) and not unassigned and not unknown_slots
    for slot in slots:
        slot.occupied = counts[slot.position] if complete else None
        slot.open = max(0, slot.count - counts[slot.position]) if complete else None

    def occupied_of(kind: str) -> int | None:
        return sum(counts[slot.position] for slot in slots if slot.kind == kind) if complete else None

    occupied_active, occupied_bench, occupied_injury = (occupied_of(kind) for kind in ("starting", "bench", "injury"))
    occupied_roster = occupied_active + occupied_bench if complete else None
    open_roster = max(0, non_injury - occupied_roster) if occupied_roster is not None else None
    open_active = [slot.position for slot in slots if slot.kind == "starting"
        for _ in range(max(0, slot.count - counts[slot.position]))] if complete else []
    open_bench = max(0, bench - occupied_bench) if occupied_bench is not None else None
    open_injury = max(0, injury - occupied_injury) if occupied_injury is not None else None

    injured_rows = [row for row in assignments if row.injured]
    outside = [row for row in injured_rows if row.slot_kind in {"starting", "bench"}]
    inside = [row for row in injured_rows if row.slot_kind == "injury"]
    moves: list[InjuryMoveOption] = []
    move_blockers: list[InjuryMoveBlocker] = []
    if complete:
        open_by_injury_slot = {slot.position: slot.open or 0 for slot in slots if slot.kind == "injury"}
        injury_summary = ", ".join(f"{slot.position} {slot.occupied}/{slot.count} occupied"
            for slot in slots if slot.kind == "injury") or "no injury slots configured"
        for row in outside:
            reason = None
            if row.status_state in {"stale", "missing"}:
                reason = f"{row.player_name}: Yahoo status evidence is {row.status_state}; IL eligibility cannot be confirmed."
            elif not row.eligible_positions_known:
                reason = f"{row.player_name}: persisted Yahoo eligible positions are missing; IL eligibility cannot be confirmed."
            elif not row.eligible_injury_slots:
                reason = (f"{row.player_name}: persisted Yahoo eligibility does not include an injury slot "
                    f"(status {_status_label(row.yahoo_status)}); Yahoo would not accept the IL move.")
            else:
                target = next((slot for slot in row.eligible_injury_slots if open_by_injury_slot.get(slot, 0) > 0), None)
                if target is None:
                    reason = f"{row.player_name}: no eligible injury slot is open ({injury_summary})."
                else:
                    open_by_injury_slot[target] -= 1
                    moves.append(InjuryMoveOption(
                        player_id=row.player_id, player_name=row.player_name,
                        from_slot=row.roster_slot or "unknown", to_slot=target,
                        released_slot=row.roster_slot or "unknown",
                        released_slot_kind=row.slot_kind or "unsupported",
                        detail=(f"Move {row.player_name} from {row.roster_slot} to {target}. {row.player_name} stays on the "
                            f"roster and the {row.roster_slot} spot is released. Conditional: Yahoo must currently allow "
                            "the IL placement; live status, roster locks and game-time locks are not verified."),
                    ))
            if reason:
                move_blockers.append(InjuryMoveBlocker(
                    player_id=row.player_id, player_name=row.player_name, roster_slot=row.roster_slot, reason=reason,
                ))

    if blockers:
        shape = "UNDETERMINED"
        state = "conflicting" if conflicting else "stale" if stale else "missing" if missing else "missing"
    else:
        state = "available"
        shape = "ADD_ONLY" if open_roster else "MOVE_TO_IL_THEN_ADD" if moves else "ADD_DROP"
    if shape == "UNDETERMINED":
        requires_drop = requires_move = None
        reason = ("Roster capacity is undetermined, so no drop requirement is asserted and ADD + DROP is not used as a default. "
            f"Resolve the {len(blockers)} listed blocking issue(s) first.")
    elif shape == "ADD_ONLY":
        requires_drop, requires_move = False, False
        reason = (f"{open_roster} of {non_injury} non-injury roster spots are open ({occupied_roster} occupied; "
            "players in injury slots do not use these spots). An add needs no drop.")
    elif shape == "MOVE_TO_IL_THEN_ADD":
        requires_drop, requires_move = False, True
        reason = (f"All {non_injury} non-injury roster spots are occupied, but moving "
            + ", ".join(move.player_name for move in moves)
            + f" to an open injury slot releases {len(moves)} spot(s). Moving a player to IL keeps that player on the roster; it is not a drop.")
    else:
        requires_drop, requires_move = True, False
        reason = (f"All {non_injury} non-injury roster spots are occupied and no injured player can move to an open injury slot"
            + (": " + " ".join(blocker.reason for blocker in move_blockers) if move_blockers else ".")
            + " An add requires a drop.")

    status_states = [row.status_state for row in assignments]
    status_state = ("missing" if not status_states else "stale" if "stale" in status_states
        else "missing" if "missing" in status_states
        else "available" if all(value == "available" for value in status_states) else "partial")
    explicit = sum(bool(row.yahoo_status) for row in assignments)
    no_designation = sum(row.decision_status_state == "NO_CURRENT_YAHOO_DESIGNATION" for row in assignments)
    detail = {
        "available": "Persisted Yahoo slot assignments, roster positions and roster import are fresh and consistent.",
        "stale": "Roster or settings evidence is stale; refresh before relying on capacity.",
        "missing": "Required roster, slot-assignment or roster-position evidence is missing.",
        "conflicting": "Persisted roster evidence conflicts; resolve before relying on capacity.",
    }[state]
    headline, short_reason = _capacity_headline(
        shape=shape, open_roster=open_roster, occupied_roster=occupied_roster, non_injury=non_injury,
        moves=moves, settings_state=settings_state, roster_state=roster_state, roster_as_of=roster_as_of,
        unassigned=len(unassigned), roster_count=len(entries), conflicting=conflicting,
    )
    return RosterCapacity(
        state=state, transaction_shape=shape, slots=slots, assignments=assignments,
        headline=headline, short_reason=short_reason,
        total_capacity=active + bench + injury if slots else None,
        non_injury_capacity=non_injury if slots else None,
        active_slot_capacity=active if slots else None,
        bench_capacity=bench if slots else None,
        injury_slot_capacity=injury if slots else None,
        roster_count=len(entries),
        occupied_roster_spots=occupied_roster, occupied_active_slots=occupied_active,
        occupied_bench_slots=occupied_bench, occupied_injury_slots=occupied_injury,
        open_roster_spots=open_roster, open_active_slots=open_active,
        open_bench_slots=open_bench, open_injury_slots=open_injury,
        unassigned_player_ids=[entry.player_id for entry in unassigned],
        injured_players=injured_rows,
        injured_players_outside_injury_slots=[row.player_id for row in outside],
        injured_players_in_injury_slots=[row.player_id for row in inside],
        no_drop_additions_available=open_roster if shape != "UNDETERMINED" else None,
        move_to_injury_slot_options=moves if shape != "UNDETERMINED" else [],
        injury_move_blockers=move_blockers,
        additions_after_injury_moves=(open_roster + len(moves)) if shape != "UNDETERMINED" and open_roster is not None else None,
        requires_drop=requires_drop, requires_roster_move=requires_move,
        drop_requirement_reason=reason, blockers=blockers, warnings=warnings,
        assignment_as_of=assignment_as_of,
        evidence=Evidence(state="available" if state == "available" else "stale" if state == "stale"
            else "missing" if state == "missing" else "partial",
            source="Yahoo roster slot assignments (selected_position) and roster positions",
            as_of=roster_as_of, sample_count=len(entries), detail=detail),
        status_evidence=Evidence(state=status_state, source="Yahoo player import (status and eligible positions)",
            as_of=status_as_of, sample_count=len(assignments),
            detail=(f"{explicit} of {len(assignments)} roster players have an explicit Yahoo status; {no_designation} "
                "have NO CURRENT YAHOO DESIGNATION (not a medical-health guarantee); any other blank status is UNKNOWN, "
                "not healthy. IL eligibility comes only from persisted Yahoo eligible positions.")),
        transaction_legality_quality=Evidence(
            state="unavailable" if shape == "UNDETERMINED" else "partial",
            source="Persisted Yahoo roster capacity", as_of=roster_as_of,
            detail=("Roster-capacity recommendation requiring Yahoo confirmation: roster locks, game-time locks, "
                "waiver/free-agent claim state, weekly add usage and live injury eligibility are not verified."),
        ),
        limitations=list(CAPACITY_LIMITATIONS),
    )


def analyze_team_needs(
    *,
    capacity: RosterCapacity,
    players: dict[int, Candidate],
    roster_ids: list[int],
    starting_slots: list[str],
    mode: Mode,
    window_start: date,
    window_end: date,
    roster_state: str,
    settings_state: str,
) -> TeamNeeds:
    assignment_by_id = {row.player_id: row for row in capacity.assignments}
    roster = [players[player_id] for player_id in roster_ids if player_id in players]

    def can_play(row: Candidate) -> bool:
        assignment = assignment_by_id.get(row.player_id)
        return assignment.lineup_eligible if assignment is not None else lineup_eligible(row)

    lineup = [row for row in roster if can_play(row)]
    unavailable = [row for row in roster if not can_play(row)]
    uncovered = uncovered_slots(lineup, starting_slots) if starting_slots else []
    with_injured = uncovered_slots(lineup + unavailable, starting_slots) if starting_slots else []
    weakened = Counter(uncovered) - Counter(with_injured)
    open_counts = Counter(uncovered)

    days: list[LineupDay] = []
    # Dates with at least one open instance of a slot (never above the date count) and the open instances summed
    # over dates (two C slots open on one date count 2). Text that says "dates" uses only the first.
    day_gaps: Counter[str] = Counter()
    day_slot_games: Counter[str] = Counter()
    if mode == "ros":
        day_state, day_detail = "unsupported", (
            "Rest of Season Outlook covers the whole season; daily lineup coverage is calculated only for Rest of Week, Next 7 Days and Next 14 Days.")
    elif not starting_slots:
        day_state, day_detail = "unavailable", "Starting slots are unavailable until fresh Yahoo settings are imported."
    else:
        unscheduled = [row.player_name for row in lineup
            if row.schedule.games_remaining is None or row.schedule.coverage != "PARTIAL"]
        if unscheduled:
            day_state = "unavailable"
            day_detail = ("Daily lineup coverage needs supported persisted schedules for every lineup-eligible player; "
                f"unavailable for {', '.join(unscheduled)}. Missing schedule rows are not zero games.")
        else:
            day = window_start
            while day <= window_end:
                playing = [row for row in lineup if day in row.schedule.game_dates]
                open_today = uncovered_slots(playing, starting_slots)
                days.append(LineupDay(date=day, players_with_games=len(playing),
                    fillable_starting_slots=len(starting_slots) - len(open_today),
                    starting_slots_required=len(starting_slots), open_starting_slots=open_today))
                day_gaps.update(set(open_today))
                day_slot_games.update(open_today)
                day += timedelta(days=1)
            day_state = "partial"
            day_detail = ("Uses persisted per-player schedule rows (coverage PARTIAL; no completeness manifest). A day's open "
                "slots are starting slots that no lineup-eligible player with a persisted game can fill; this is not a "
                "lineup optimizer or start guarantee.")

    coverage_rows: list[SlotCoverage] = []
    for slot in dict.fromkeys(starting_slots):
        required = starting_slots.count(slot)
        injured_ids = [row.player_id for row in unavailable if slot_accepts(slot, row)] if weakened[slot] else []
        coverage_rows.append(SlotCoverage(
            slot=slot, kind="starting", required=required,
            covered=required - open_counts[slot], uncovered=open_counts[slot],
            eligible_player_ids=[row.player_id for row in lineup if slot_accepts(slot, row)],
            weakened_by_injury=bool(weakened[slot]), injured_player_ids=injured_ids,
            need_score=round(100 * open_counts[slot] / required, 2),
            open_slot_days=day_gaps[slot] if day_state == "partial" else None,
            open_slot_games=day_slot_games[slot] if day_state == "partial" else None,
            detail=(f"{required - open_counts[slot]} of {required} {slot} starting slot(s) coverable by lineup-eligible players."
                + (" Weakened by injury." if weakened[slot] else "")),
        ))
    for slot in capacity.slots:
        if slot.kind in {"bench", "injury"}:
            coverage_rows.append(SlotCoverage(
                slot=slot.position, kind=slot.kind, required=slot.count,
                covered=slot.occupied, uncovered=slot.open,
                eligible_player_ids=([row.player_id for row in lineup] if slot.kind == "bench"
                    else [row.player_id for row in capacity.assignments if slot.position in row.eligible_injury_slots]),
                detail=(f"{slot.occupied if slot.occupied is not None else 'Unknown'} of {slot.count} {slot.position} "
                    "spots occupied per persisted Yahoo assignments."),
            ))

    needs: list[TeamNeed] = []
    for slot in sorted(open_counts, key=need_order):
        names = ", ".join(f"{row.player_name} ({_status_label(row.yahoo_status)})"
            for row in unavailable if slot_accepts(slot, row))
        needs.append(TeamNeed(
            priority=len(needs) + 1, slot=slot,
            kind="INJURY_WEAKENED" if weakened[slot] else "OPEN_STARTING_SLOT",
            count=open_counts[slot], positions=slot_core_positions(slot),
            reason=(f"{open_counts[slot]} of {starting_slots.count(slot)} {slot} starting slot(s) cannot be filled by "
                "lineup-eligible roster players" + (f"; weakened by {names}" if weakened[slot] and names else "") + "."),
        ))
    if day_state == "partial":
        for slot, gap_days in sorted(day_gaps.items(), key=lambda item: (-item[1], need_order(item[0]))):
            if slot in open_counts:
                continue
            slot_games = day_slot_games[slot]
            needs.append(TeamNeed(
                priority=len(needs) + 1, slot=slot, kind="LINEUP_DAY_GAP", count=gap_days, slot_games=slot_games,
                positions=slot_core_positions(slot),
                reason=(f"{slot} has no lineup-eligible player with a persisted game on {gap_days} of {len(days)} "
                    "dates in this window"
                    + (f" ({slot_games} open {slot} slot-games across its {starting_slots.count(slot)} slots)"
                        if slot_games != gap_days else "") + "."),
            ))
    fill_capacity = capacity.additions_after_injury_moves or 0
    structural = sum(open_counts.values())
    if capacity.transaction_shape in {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD"} and fill_capacity > structural:
        needs.append(TeamNeed(
            priority=len(needs) + 1, slot="BN", kind="BENCH_DEPTH", count=fill_capacity - structural,
            positions=list(CORE_POSITIONS),
            reason=("Open roster spot(s) beyond uncovered starting slots. Depth adds options on dates when starters "
                "have no persisted game; bench players score only when moved into the lineup."),
        ))

    production_key = "ros" if mode == "ros" else "recent"
    supported = []
    for row in lineup:
        evidence = row.data_quality.get(production_key)
        value = (row.ros if mode == "ros" else row.recent).value
        if evidence is not None and evidence.state == "available" and value is not None:
            supported.append((value, row.player_id))
    lowest = min(supported, default=None)
    label = "Season Evidence" if mode == "ros" else "Recent"
    production = ProductionNeed(
        state=("unavailable" if not supported else "available" if len(supported) == len(lineup) else "partial"),
        lineup_players=len(lineup), supported_players=len(supported),
        lowest_supported_ppg=lowest[0] if lowest else None,
        lowest_supported_player_id=lowest[1] if lowest else None,
        median_supported_ppg=median(value for value, _ in supported) if supported else None,
        detail=(f"{len(supported)} of {len(lineup)} lineup-eligible players have supported {label} Yahoo-rule fantasy PPG "
            "(PTS + 1.2 REB + 1.5 AST + 3 BLK + 3 STL - TO). An empty starting slot scores zero; values are historical, "
            "not projections."),
    )
    notes = [f"{row.player_name}: {row.injury_note}" for row in capacity.injured_players if row.injury_note]
    hold_guidance = ("Injury return timing is not forecast. For a short absence, a schedule-driven short-term option "
        "(Rest of Week / Next 7 Days / Next 14 Days) fits the open spot; for a longer absence, a longer-term hold supported by Season "
        "Evidence fits." + (" Yahoo injury notes: " + "; ".join(notes) + "." if notes else ""))
    players_out = []
    for row in roster:
        assignment = assignment_by_id.get(row.player_id)
        value = row.ros if mode == "ros" else row.recent
        evidence = row.data_quality.get(production_key)
        role = row.opportunity.current_role
        players_out.append(NeedPlayer(
            player_id=row.player_id, player_name=row.player_name, positions=row.position,
            roster_slot=assignment.roster_slot if assignment else None, yahoo_status=row.yahoo_status,
            lineup_eligible=can_play(row), injured=bool(assignment and assignment.injured),
            multi_position=len(player_positions(row) & set(CORE_POSITIONS)) >= 2,
            games_in_window=row.schedule.games_remaining,
            schedule_state=row.data_quality["schedule"].state if "schedule" in row.data_quality else "unavailable",
            fantasy_ppg=value.value, production_state=evidence.state if evidence else "unavailable",
            role_trend=role.trend if role else "INSUFFICIENT EVIDENCE", minutes=row.opportunity.minutes,
        ))
    if roster_state in {"missing", "not_imported"}:
        state = "missing"
    elif roster_state != "available" or settings_state != "available":
        state = "stale"
    elif capacity.state != "available" or (mode != "ros" and day_state == "unavailable") or production.state != "available":
        state = "partial"
    else:
        state = "available"
    summary, depth_note = need_summary(
        lineup=lineup, unavailable=unavailable, starting_slots=starting_slots, uncovered=uncovered,
        weakened=weakened, day_gaps=day_gaps if day_state == "partial" else Counter(), day_count=len(days),
        extra_open_spots=max(0, fill_capacity - structural)
        if capacity.transaction_shape in {"ADD_ONLY", "MOVE_TO_IL_THEN_ADD"} else 0,
    )
    if not starting_slots:
        basis = "Positional needs are unavailable: no valid persisted Yahoo roster positions."
    elif state in {"available", "partial"}:
        basis = "Based on the current saved Yahoo roster and league settings."
    else:
        basis = (f"Based on the saved Yahoo roster from {pacific_day(capacity.evidence.as_of)} ({state}); "
            "refresh Yahoo before relying on these needs.")
    return TeamNeeds(
        state=state, mode=mode, window_start=window_start, window_end=window_end,
        lineup_player_count=len(lineup), starting_slots_required=len(starting_slots) or None,
        starting_slots_covered=len(starting_slots) - len(uncovered) if starting_slots else None,
        open_starting_slots=uncovered, weakened_positions=sorted(weakened, key=need_order),
        slot_coverage=coverage_rows,
        position_need_scores={row.slot: row.need_score for row in coverage_rows if row.need_score is not None},
        needs=needs,
        multi_position_player_ids=[row.player_id for row in lineup
            if len(player_positions(row) & set(CORE_POSITIONS)) >= 2],
        redundancy={position: sum(position in player_positions(row) for row in lineup) for position in CORE_POSITIONS},
        players=players_out, lineup_days=days, lineup_day_state=day_state, lineup_day_detail=day_detail,
        production=production,
        injured_player_ids=[row.player_id for row in capacity.injured_players],
        uncertain_status_player_ids=[row.player_id for row in lineup if row.yahoo_status in {"Q", "P"}],
        unknown_status_player_ids=[row.player_id for row in lineup
            if recommendation_eligibility(row.yahoo_status) == "unknown"
            and row.decision_status_state != "NO_CURRENT_YAHOO_DESIGNATION"],
        hold_guidance=hold_guidance,
        summary=summary, depth_note=depth_note, basis=basis,
        limitations=list(NEEDS_LIMITATIONS),
    )


def _slot_label(slots: Iterable[str]) -> str:
    return " / ".join(sorted(dict.fromkeys(slots), key=need_order))


def need_summary(
    *,
    lineup: list[Candidate],
    unavailable: list[Candidate],
    starting_slots: list[str],
    uncovered: list[str],
    weakened: Counter,
    day_gaps: Counter,
    day_count: int,
    extra_open_spots: int,
) -> tuple[list[NeedSummary], str | None]:
    """HIGH: a family starting slot cannot be filled. MEDIUM: covered, but one absence or a
    scheduled-game gap leaves it open. COVERED otherwise. UTIL/bench gaps are reported as depth."""
    rows: list[NeedSummary] = []
    baseline = Counter(uncovered)
    lost_by_player = {
        row.player_id: Counter(uncovered_slots([other for other in lineup if other is not row], starting_slots)) - baseline
        for row in lineup
    } if starting_slots else {}
    for family, family_slots in POSITION_FAMILIES:
        required = [slot for slot in starting_slots if slot in family_slots]
        if not required:
            continue
        eligible = [row for row in lineup if any(slot_accepts(slot, row) for slot in set(required))]
        positions = sorted({position for slot in required for position in slot_core_positions(slot)}, key=CORE_POSITIONS.index)
        open_slots = [slot for slot in uncovered if slot in family_slots]
        if open_slots:
            label = _slot_label(open_slots)
            injured = [row.player_name for row in unavailable if any(slot_accepts(slot, row) for slot in open_slots)]
            if any(weakened[slot] for slot in open_slots) and injured:
                reason = f"Injury coverage needed: {', '.join(injured[:2])} cannot play, leaving {label} open."
            else:
                reason = f"Open-slot coverage needed: no lineup-eligible player can fill {label}."
            level, focus = "HIGH", open_slots
        else:
            critical = [row for row in lineup if any(slot in family_slots for slot in lost_by_player.get(row.player_id, {}))]
            thin = [slot for row in critical for slot in lost_by_player[row.player_id].elements() if slot in family_slots]
            gaps = {slot: days for slot, days in day_gaps.items() if slot in family_slots and days}
            if thin or gaps:
                parts = []
                if thin:
                    who = (" and ".join(row.player_name for row in critical) if len(critical) <= 2
                        else f"{len(eligible)} lineup-eligible players")
                    parts.append(f"Limited active coverage: only {who} can fill {_slot_label(thin)}; one absence leaves it open")
                if gaps:
                    slot, days = max(gaps.items(), key=lambda item: (item[1], -need_order(item[0])[0]))
                    parts.append(f"no lineup-eligible player with a scheduled game can fill {slot} on {days} of {day_count} dates")
                reason = "; ".join(parts)
                reason = reason[0].upper() + reason[1:] + "."
                level, focus = "MEDIUM", [*thin, *gaps]
            else:
                reason = f"Covered: {len(eligible)} lineup-eligible players can fill these slots."
                level, focus = "COVERED", required
        rows.append(NeedSummary(
            priority=0, family=family, label=_slot_label(focus), level=level,
            slots=sorted(set(focus), key=need_order), positions=positions, reason=reason,
            eligible_player_ids=[row.player_id for row in eligible],
        ))
    family_order = {family: index for index, (family, _) in enumerate(POSITION_FAMILIES)}
    rows.sort(key=lambda row: (NEED_LEVEL_ORDER[row.level], family_order[row.family]))
    for index, row in enumerate(rows):
        row.priority = index + 1
    depth = []
    flex_open = [slot for slot in uncovered if slot in FLEX_SLOTS]
    if flex_open:
        depth.append(f"{len(flex_open)} UTIL starting slot(s) cannot be filled by lineup-eligible players; "
            "a player at any position adds lineup depth.")
    if extra_open_spots:
        depth.append(f"{extra_open_spots} open roster spot(s) beyond starting needs add bench depth.")
    return rows, " ".join(depth) or None

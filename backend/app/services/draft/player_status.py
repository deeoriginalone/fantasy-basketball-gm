from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.features.players.normalization import _player_id

# Labels verified in the imported Yahoo player payload's status_full field
# (OFS = "Out For Season", verified in the 2026-11-14 player pool).
YAHOO_STATUS_LABELS = {
    "O": "Out (short-term injury)",
    "OFS": "Out For Season",
    "NA": "Not Active",
    "P": "Probable",
    "Q": "Questionable",
}
UNAVAILABLE_YAHOO_STATUSES = frozenset({"O", "OFS", "NA"})
SUPPORTED_YAHOO_STATUSES = frozenset({"O", "OFS", "NA", "P", "Q"})
# How one Yahoo player observation carries its status field. A missing field and a supplied blank are different
# evidence and stay distinct; neither is a health claim.
YahooStatusField = Literal["EXPLICIT_STATUS", "UNRECOGNIZED_NONBLANK", "YAHOO_SUPPLIED_BLANK", "STATUS_FIELD_MISSING"]
# How decisions treat a player's Yahoo status. NO_CURRENT_YAHOO_DESIGNATION (user-approved 2026-11-14) is a fresh,
# fully verified record whose `status` key is absent: Yahoo lists no designation. It is not a medical-health claim.
YahooStatusDecisionState = Literal["EXCLUDED", "UNCERTAIN", "NO_CURRENT_YAHOO_DESIGNATION", "UNKNOWN"]
YahooStatusReason = Literal[
    "EXPLICIT_DESIGNATION",
    "NO_CURRENT_YAHOO_DESIGNATION",
    "YAHOO_SUPPLIED_BLANK",
    "UNRECOGNIZED_NONBLANK",
    "PLAYER_OBSERVATION_MISSING",
    "STALE_PLAYER_POOL_IMPORT",
    "MAPPING_ISSUE",
    "NORMALIZATION_DEFECT",
    "ROSTER_SNAPSHOT_INCOMPLETE",
]
NO_CURRENT_DESIGNATION_LABEL = "NO CURRENT YAHOO DESIGNATION"
NO_CURRENT_DESIGNATION_DETAIL = (
    "Yahoo's current player record contains no explicit injury/status designation. "
    "This is not a medical-health guarantee."
)
BLANK_STATUS_DETAIL = "Yahoo did not provide an explicit current status. Confirm the player in Yahoo before acting."
_CONFIRM = " Status is UNKNOWN, not healthy. Confirm the player in Yahoo before acting."
_MISSING_FIELD_UNKNOWN_DETAILS: dict[YahooStatusReason, str] = {
    "PLAYER_OBSERVATION_MISSING": "Yahoo's record has no status field, but no current player-pool record exists for "
        "this player in the league, so the absence is not current evidence.",
    "STALE_PLAYER_POOL_IMPORT": "Yahoo's record has no status field, but the player-pool import is older than "
        "24 hours, so the absence is not current evidence.",
    "MAPPING_ISSUE": "Yahoo's record has no status field, but the player's Yahoo/NBA identity is unresolved or "
        "inconsistent, so the absence cannot be attributed to this player.",
    "NORMALIZATION_DEFECT": "Yahoo's record has no status field but carries other status evidence, so the absence "
        "is treated as a data defect.",
    "ROSTER_SNAPSHOT_INCOMPLETE": "Yahoo's record has no status field, but the league roster snapshots are not all "
        "current, so the absence is not accepted as no current designation.",
}
# Yahoo sends these only together with `status` (2026-11-14 audit); one of them without `status` is a defect.
_STATUS_COMPANION_KEYS = ("status_full", "injury_note")


@dataclass(frozen=True)
class YahooStatusInterpretation:
    status: str | None
    raw_status: str | None
    field_state: YahooStatusField
    decision_state: YahooStatusDecisionState
    reason: YahooStatusReason
    label: str
    detail: str


def normalize_yahoo_status(value: Any) -> str | None:
    text = str(value).strip().upper() if value is not None else ""
    return text or None


def yahoo_status_field(payload: Mapping[str, Any]) -> YahooStatusField:
    """Classify the status field of one persisted Yahoo player observation without interpreting its absence."""
    if "status" not in payload:
        return "STATUS_FIELD_MISSING"
    status = normalize_yahoo_status(payload["status"])
    if status is None:
        return "YAHOO_SUPPLIED_BLANK"
    return "EXPLICIT_STATUS" if status_is_supported(status) else "UNRECOGNIZED_NONBLANK"


def recommendation_eligibility(status: str | None) -> Literal["excluded", "uncertain", "unknown"]:
    if status in UNAVAILABLE_YAHOO_STATUSES:
        return "excluded"
    if status in {"P", "Q"}:
        return "uncertain"
    return "unknown"


def status_is_supported(status: str | None) -> bool:
    return status in SUPPORTED_YAHOO_STATUSES


def yahoo_status_reason(status: str | None) -> str:
    label = YAHOO_STATUS_LABELS.get(status, status or "Unknown")
    if recommendation_eligibility(status) == "excluded":
        return f"Current Yahoo status: {label}. Not eligible for normal recommendation. Historical value is shown for reference."
    if status in {"P", "Q"}:
        return f"Current Yahoo status: {label}. Recommendation permitted with status uncertainty; no injury forecast is implemented."
    return f"Current Yahoo status: {label}. Availability is unknown, not confirmed healthy."


def yahoo_status_label(status: str | None) -> tuple[str, str]:
    """Display label and detail for a status token; a missing token is UNKNOWN."""
    if not status:
        return "UNKNOWN", BLANK_STATUS_DETAIL
    if not status_is_supported(status):
        return (f"{status} · UNKNOWN", f"Yahoo status {status} is not a recognized status, so it is treated as UNKNOWN. "
            "Confirm the player in Yahoo before acting.")
    label = YAHOO_STATUS_LABELS.get(status, status)
    return f"{status} · {label}", f"Yahoo lists the player as {label}; status remains uncertain."


def _missing_field_reason(
    payload: Mapping[str, Any], *, identity_yahoo_player_id: str | None, identity_status: str | None,
    player_pool_observation: bool, observation_fresh: bool, identity_resolved: bool, mapping_conflict: bool,
    rosters_complete: bool,
) -> YahooStatusReason:
    if not player_pool_observation:
        return "PLAYER_OBSERVATION_MISSING"
    if not observation_fresh:
        return "STALE_PLAYER_POOL_IMPORT"
    record_id = _player_id(dict(payload))
    if not identity_resolved or mapping_conflict or not record_id or record_id != identity_yahoo_player_id:
        return "MAPPING_ISSUE"
    if (normalize_yahoo_status(identity_status) is not None or any(key in payload for key in _STATUS_COMPANION_KEYS)
            or str(payload.get("on_disabled_list") or "").strip() not in {"", "0"}):
        return "NORMALIZATION_DEFECT"
    if not rosters_complete:
        return "ROSTER_SNAPSHOT_INCOMPLETE"
    return "NO_CURRENT_YAHOO_DESIGNATION"


def interpret_yahoo_status(
    payload: Mapping[str, Any], *, identity_yahoo_player_id: str | None, identity_status: str | None,
    player_pool_observation: bool, observation_fresh: bool, identity_resolved: bool, mapping_conflict: bool,
    rosters_complete: bool,
) -> YahooStatusInterpretation:
    """Interpret one Yahoo player observation's status for decisions.

    Explicit and supplied-blank statuses keep their established meaning. Only a genuinely absent `status` key on a
    current player-pool record of the configured league (`player_pool_observation`), imported within 24 hours, linked
    to a resolved, conflict-free identity, with no normalization defect and complete current league rosters, is
    NO_CURRENT_YAHOO_DESIGNATION; every other absence stays UNKNOWN with the first failing condition as the reason.
    """
    value = payload.get("status")
    raw_status = str(value) if value is not None else None
    status = normalize_yahoo_status(value)
    field_state = yahoo_status_field(payload)
    label, detail = yahoo_status_label(status)
    decision_state: YahooStatusDecisionState
    reason: YahooStatusReason
    if field_state == "EXPLICIT_STATUS":
        excluded = recommendation_eligibility(status) == "excluded"
        reason = "EXPLICIT_DESIGNATION" if observation_fresh else "STALE_PLAYER_POOL_IMPORT"
        decision_state = "EXCLUDED" if excluded else "UNCERTAIN" if observation_fresh else "UNKNOWN"
    elif field_state == "STATUS_FIELD_MISSING":
        reason = _missing_field_reason(
            payload, identity_yahoo_player_id=identity_yahoo_player_id, identity_status=identity_status,
            player_pool_observation=player_pool_observation, observation_fresh=observation_fresh,
            identity_resolved=identity_resolved, mapping_conflict=mapping_conflict, rosters_complete=rosters_complete,
        )
        if reason == "NO_CURRENT_YAHOO_DESIGNATION":
            decision_state, label, detail = reason, NO_CURRENT_DESIGNATION_LABEL, NO_CURRENT_DESIGNATION_DETAIL
        else:
            decision_state, detail = "UNKNOWN", _MISSING_FIELD_UNKNOWN_DETAILS[reason] + _CONFIRM
    else:
        decision_state = "UNKNOWN"
        reason = ("STALE_PLAYER_POOL_IMPORT" if not observation_fresh
            else "YAHOO_SUPPLIED_BLANK" if field_state == "YAHOO_SUPPLIED_BLANK" else "UNRECOGNIZED_NONBLANK")
    return YahooStatusInterpretation(status=status, raw_status=raw_status, field_state=field_state,
        decision_state=decision_state, reason=reason, label=label, detail=detail)

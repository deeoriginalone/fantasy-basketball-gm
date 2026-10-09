from typing import Any
from decimal import Decimal, InvalidOperation

from pydantic import BaseModel


class NormalizedYahooTeam(BaseModel):
    team_key: str
    team_name: str | None
    source_payload: dict[str, Any]


class NormalizedYahooLeague(BaseModel):
    league_key: str
    game_key: str
    league_name: str
    season: int | None
    scoring_settings: dict[str, Any]
    roster_positions: list[dict[str, Any]]
    source_league: dict[str, Any]
    source_settings: dict[str, Any]
    teams: list[NormalizedYahooTeam]


def _merge_values(left: Any, right: Any) -> Any:
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            merged[key] = _merge_values(merged[key], value) if key in merged else value
        return merged
    if isinstance(left, list) and isinstance(right, list):
        return [*left, *right]
    return right


def _collect_entities(value: Any, identity_field: str) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if identity_field in value:
            return [value]
        results: list[dict[str, Any]] = []
        for nested in value.values():
            results.extend(_collect_entities(nested, identity_field))
        return results

    if not isinstance(value, list):
        return []

    fragments = [item for item in value if isinstance(item, dict)]
    anchors = [index for index, item in enumerate(fragments) if identity_field in item]
    if anchors:
        results = []
        for anchor_index, start in enumerate(anchors):
            end = anchors[anchor_index + 1] if anchor_index + 1 < len(anchors) else len(fragments)
            merged: dict[str, Any] = {}
            for fragment in fragments[start:end]:
                merged = _merge_values(merged, fragment)
            results.append(merged)
        return results

    results = []
    for item in value:
        results.extend(_collect_entities(item, identity_field))
    return results


def extract_yahoo_records(payload: dict[str, Any], resource_name: str, identity_field: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                if key == resource_name:
                    records.extend(_collect_entities(nested, identity_field))
                else:
                    visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)

    visit(payload)
    unique: dict[str, dict[str, Any]] = {}
    for record in records:
        identity = record.get(identity_field)
        if identity is not None:
            unique[str(identity)] = record
    return list(unique.values())


def _merge_settings(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        if value and all(str(key).isdigit() for key in value):
            merged: dict[str, Any] = {}
            for nested in value.values():
                if isinstance(nested, (dict, list)):
                    merged = _merge_values(merged, _merge_settings(nested))
            return merged or value
        return value
    if isinstance(value, list):
        merged: dict[str, Any] = {}
        for nested in value:
            if isinstance(nested, (dict, list)):
                merged = _merge_values(merged, _merge_settings(nested))
        return merged
    return {}


def _roster_positions(value: Any) -> list[dict[str, Any]]:
    positions: list[dict[str, Any]] = []

    def visit(nested: Any) -> None:
        if isinstance(nested, dict):
            if "roster_position" in nested:
                visit(nested["roster_position"])
            elif "position" in nested:
                positions.append(nested)
            else:
                for child in nested.values():
                    visit(child)
        elif isinstance(nested, list):
            for child in nested:
                visit(child)

    visit(value)
    return positions


def _season(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _stat_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        if "stat" in value:
            return _stat_records(value["stat"])
        if "stat_id" in value:
            return [value]
        results: list[dict[str, Any]] = []
        for nested in value.values():
            results.extend(_stat_records(nested))
        return results
    if isinstance(value, list):
        results = []
        for nested in value:
            results.extend(_stat_records(nested))
        return results
    return []


def _numeric_value(value: Any) -> Any:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return value
    if number == number.to_integral_value():
        return int(number)
    return float(number)


def _normalized_scoring_settings(raw_settings: dict[str, Any]) -> dict[str, Any]:
    categories_by_id: dict[str, str] = {}
    for stat in _stat_records(raw_settings.get("stat_categories")):
        stat_id = stat.get("stat_id")
        name = stat.get("display_name") or stat.get("name")
        if stat_id is not None and name:
            categories_by_id[str(stat_id)] = str(name)

    categories = []
    for stat in _stat_records(raw_settings.get("stat_modifiers")):
        stat_id = stat.get("stat_id")
        if stat_id is None or "value" not in stat:
            continue
        stat_id = str(stat_id)
        categories.append(
            {
                "stat_id": stat_id,
                "name": categories_by_id.get(stat_id),
                "value": _numeric_value(stat["value"]),
            }
        )

    normalized: dict[str, Any] = {}
    if raw_settings.get("scoring_type") is not None:
        normalized["scoring_type"] = raw_settings["scoring_type"]
    if categories:
        normalized["categories"] = categories
    return normalized


def normalize_yahoo_settings(
    league_key: str,
    settings_response: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    settings_records = extract_yahoo_records(settings_response, "league", "league_key")
    settings_record = next(
        (item for item in settings_records if str(item.get("league_key")) == league_key),
        settings_records[0] if settings_records else {},
    )
    raw_settings = _merge_settings(settings_record.get("settings"))
    return (
        _normalized_scoring_settings(raw_settings),
        _roster_positions(raw_settings.get("roster_positions", [])),
    )


def normalize_yahoo_league(
    game_key: str,
    league: dict[str, Any],
    settings_response: dict[str, Any],
    teams_response: dict[str, Any],
) -> NormalizedYahooLeague:
    league_key = str(league["league_key"])
    scoring_settings, roster_positions = normalize_yahoo_settings(league_key, settings_response)

    team_records = extract_yahoo_records(teams_response, "team", "team_key")
    teams = [
        NormalizedYahooTeam(
            team_key=str(team["team_key"]),
            team_name=str(team["name"]) if team.get("name") is not None else None,
            source_payload=team,
        )
        for team in team_records
    ]

    return NormalizedYahooLeague(
        league_key=league_key,
        game_key=game_key,
        league_name=str(league.get("name") or league_key),
        season=_season(league.get("season")),
        scoring_settings=scoring_settings,
        roster_positions=roster_positions,
        source_league=league,
        source_settings=settings_response,
        teams=teams,
    )
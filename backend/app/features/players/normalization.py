import re
from typing import Any

from pydantic import BaseModel


class NormalizedPlayer(BaseModel):
    yahoo_player_id: str
    player_name: str
    team: str | None
    position: str | None
    status: str | None
    source_payload: dict[str, Any]


def _source_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _player_id(player: dict[str, Any]) -> str | None:
    player_id = _source_text(player.get("player_id"))
    if player_id:
        return player_id
    player_key = _source_text(player.get("player_key"))
    if player_key:
        match = re.search(r"(?:^|\.)p\.([^.]*)$", player_key)
        if match:
            return match.group(1)
    return None


def _player_name(player: dict[str, Any]) -> str | None:
    name = player.get("name")
    if isinstance(name, dict):
        full_name = _source_text(name.get("full"))
        if full_name:
            return full_name
        pieces = [_source_text(name.get("first")), _source_text(name.get("last"))]
        return " ".join(piece for piece in pieces if piece) or None
    return _source_text(name or player.get("full_name"))


def _positions(player: dict[str, Any]) -> str | None:
    display_position = _source_text(player.get("display_position"))
    if display_position:
        return display_position
    eligible = player.get("eligible_positions")
    values: list[str] = []
    if isinstance(eligible, list):
        for item in eligible:
            value = item.get("position") if isinstance(item, dict) else item
            text = _source_text(value)
            if text and text not in values:
                values.append(text)
    elif isinstance(eligible, dict):
        for item in eligible.values():
            value = item.get("position") if isinstance(item, dict) else item
            text = _source_text(value)
            if text and text not in values:
                values.append(text)
    return ",".join(values) or None


def normalize_yahoo_player(player: dict[str, Any]) -> NormalizedPlayer:
    yahoo_player_id = _player_id(player)
    player_name = _player_name(player)
    if not yahoo_player_id or not player_name:
        raise ValueError("Yahoo player response omitted a required player ID or name")
    return NormalizedPlayer(
        yahoo_player_id=yahoo_player_id,
        player_name=player_name,
        team=_source_text(player.get("editorial_team_abbr")),
        position=_positions(player),
        status=_source_text(player.get("status")),
        source_payload=player,
    )
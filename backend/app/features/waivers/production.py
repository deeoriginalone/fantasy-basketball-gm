"""Weekly production value (model waiver-season-blend-phase8).

Rest of Week, Next 7 Days and Next 14 Days rank players by one Yahoo-rule production value built from three
non-overlapping evidence buckets. Every persisted current-season regular-season game belongs to exactly one:

    RECENT   current-season games in the last 14 days (the model's Last 14 Days evidence)
    EARLIER  current-season games before the last 14 days
    PRIOR    the previous regular season's per-game production, counted as PRIOR_GAMES games

    value = (sum of current-season game Yahoo FP + PRIOR_GAMES x prior-season FP/G) / (current-season games + PRIOR_GAMES)

Every real game weighs one, so the prior's share PRIOR_GAMES / (games + PRIOR_GAMES) falls with every game played.
PRIOR_GAMES comes from the 2026-11-24 read-only backtest of the persisted 2026-27 games (next-7 and next-14-day Yahoo
FP/G as the observed target): ordering accuracy, rank correlation and absolute error all worsened steadily as the prior
grew beyond about two games; ten games (the former blend) was significantly worse on each, and a recency multiplier on
the last 14 days added nothing once the prior's share was held fixed. Rule fixed before the run: the largest prior
weight not significantly worse than the best in both horizons, for all players and for fantasy-relevant players.

A bucket without games weighs nothing (never zero production); a bucket with games but no computable Yahoo FP/G makes
the value unavailable; without current-season games there is no value (the prior never stands in for this season).
Historical evidence, not a projection. Eligibility is separate: the recent-sample gates never read this value.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from app.features.waivers.contracts import ProductionBucket

PRIOR_GAMES = 2
TERMS = {"RECENT": "last 14 days", "EARLIER": "earlier this season", "CURRENT_SEASON": "this season"}
LABELS = {"RECENT": "Recent current season (last 14 days)", "EARLIER": "Earlier current season",
    "CURRENT_SEASON": "Current season", "PRIOR": "Prior season"}


@dataclass(frozen=True)
class SeasonBlend:
    value: float | None
    buckets: list[ProductionBucket] = field(default_factory=list)
    current_games: int = 0
    current_value: float | None = None
    prior_share: float = 0.0
    reason: str = ""


def _bucket(key: str, games: int, value: float | None, weight: float, total: float, season: str | None,
        first: date | None = None, last: date | None = None) -> ProductionBucket:
    used = weight > 0 and value is not None
    return ProductionBucket(key=key, label=LABELS[key], games=games, weight_games=weight if used else 0,
        value=round(value, 4) if value is not None else None, share=round(weight / total, 4) if used and total else 0,
        season=season, first_game=first, last_game=last)


def weighted_blend(parts: list[tuple[str, int, float | None, float, date | None, date | None]], season: str | None,
        prior: tuple[int, float | None, float, str | None] | None) -> SeasonBlend:
    """Mean of current-season buckets (`key, games, FP/G, weight in games, first, last`) beside an optional prior
    season (`games, FP/G, weight in games, season`) counted as a fixed number of games."""
    if any(games and value is None for _, games, value, _, _, _ in parts):
        return SeasonBlend(None, reason="a current-season game has no computable Yahoo FP/G")
    current_games = sum(games for _, games, _, _, _, _ in parts)
    if not current_games:
        return SeasonBlend(None, reason="no current-season games")
    prior_games, prior_value, prior_weight, prior_season = prior or (0, None, 0.0, None)
    prior_weight = prior_weight if prior_value is not None and prior_games > 0 else 0.0
    total = sum(weight for _, games, _, weight, _, _ in parts if games) + prior_weight
    points = sum(weight * value for _, games, value, weight, _, _ in parts if games) + prior_weight * (prior_value or 0)
    current_value = sum(games * value for _, games, value, _, _, _ in parts if games) / current_games
    buckets = [_bucket(key, games, value, weight if games else 0, total, season, first, last)
        for key, games, value, weight, first, last in parts]
    buckets.append(_bucket("PRIOR", prior_games, prior_value, prior_weight, total, prior_season))
    return SeasonBlend(points / total, buckets, current_games, current_value, prior_weight / total)


def season_blend(*, recent_games: int, recent_value: float | None, earlier_games: int, earlier_value: float | None,
        prior_games: int = 0, prior_value: float | None = None, prior_season: str | None = None,
        season: str | None = None, recent_first: date | None = None, recent_last: date | None = None,
        earlier_first: date | None = None, earlier_last: date | None = None) -> SeasonBlend:
    """The weekly production value: every current-season game once, the prior season as PRIOR_GAMES games."""
    return weighted_blend([
        ("RECENT", recent_games, recent_value, float(recent_games), recent_first, recent_last),
        ("EARLIER", earlier_games, earlier_value, float(earlier_games), earlier_first, earlier_last),
    ], season, (prior_games, prior_value, float(PRIOR_GAMES), prior_season))


def _number(value: float) -> str:
    return f"{value:g}" if float(value).is_integer() else f"{value:.2f}"


def blend_math(buckets: list[ProductionBucket], value: float | None) -> str:
    """The exact arithmetic, every bucket with its games-equivalent weight: no hidden coefficient."""
    used = [bucket for bucket in buckets if bucket.weight_games > 0 and bucket.value is not None]
    if value is None or not used:
        return ""
    terms = [f"{_number(bucket.weight_games)} x {bucket.value:.2f} "
        f"{TERMS.get(bucket.key) or bucket.season or 'prior season'}" for bucket in used]
    return f"({' + '.join(terms)}) / {_number(sum(bucket.weight_games for bucket in used))} = {value:.2f}"


def blend_label(buckets: list[ProductionBucket]) -> str:
    """One line naming the basis and the prior's share."""
    prior = next((bucket for bucket in buckets if bucket.key == "PRIOR"), None)
    games = sum(bucket.games for bucket in buckets if bucket.key != "PRIOR")
    current = f"{games} game{'' if games == 1 else 's'}"
    if prior is None or prior.share <= 0:
        return f"This season only ({current}; no supported prior-season history)"
    share = round(prior.share * 100)
    return (f"This season ({current}) blended with {prior.season} counted as {_number(prior.weight_games)} games "
        f"({share}% prior season)" + (": mostly previous-season evidence" if prior.share > .5 else ""))

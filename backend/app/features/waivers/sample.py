"""Recent-sample evidence tiers and corroboration (model waiver-horizon-evidence-phase6).

Relevant games are the last 14 days in Rest of Week, Next 7 Days and Next 14 Days, and the current season in Rest of
Season Outlook. Tiers are evidence labels, never probabilities:

    0-2  INSUFFICIENT     never supports a move
    3-4  VERY_LOW         never supports a move (WATCH at most)
    5-6  LIMITED          supports a move only when corroborated (below)
    7+   SUPPORTED        supports a move (with at least 7 current-season games and fresh production evidence)

A LIMITED weekly sample is corroborated only with at least 7 current-season games, fresh production evidence and a
qualified current role, plus at least two of four independent corroborations: 10+ games in the last 30 days; a
qualified STABLE or RISING role; Last-30-Days fantasy PPG within FORM_PPG_TOLERANCE of Last-14-Days PPG (with 3+
earlier games); no material minutes drop against the earlier 30-day games. Current-season games are deliberately not a
corroboration: Last-30-Days games are a subset of them, so 10+ in 30 days would always count twice.
Status, identity, availability and a positive supported
roster impact stay separate mandatory gates for every supported move. Prior-season evidence never rescues a
current sample: a LIMITED Rest of Season Outlook sample (5-6 games this season) cannot be corroborated.
"""

from app.features.waivers.contracts import Candidate, Mode, SampleAssessment, SampleCheck, SampleTier

SUPPORTED_SAMPLE_GAMES = 7
LIMITED_SAMPLE_GAMES = 5
VERY_LOW_SAMPLE_GAMES = 3
CORROBORATION_GAMES = 10
# Evidence-based (read-only audit of the 2026-11-14 persisted pool): the 80th percentile of
# |Last-14 PPG - Last-30 PPG| / Last-30 PPG among well-sampled players (7+ games in 14 days, 10+ in 30 days, Last-30
# PPG 10+; n=114) is 13.0%, bootstrap 90% CI 11.1-15.4%. A 5-6 game sample must sit inside that typical range.
FORM_PPG_TOLERANCE = 0.13
# The existing role minutes threshold; about 12% of well-sampled players fell at least this far (same audit).
MINUTES_DROP = 3.0
CORROBORATIONS_REQUIRED = 2
SAMPLE_TIER_LABELS: dict[str, str] = {
    "INSUFFICIENT": "INSUFFICIENT SAMPLE",
    "VERY_LOW": "VERY LOW SAMPLE",
    "LIMITED": "LIMITED SAMPLE",
    "SUPPORTED": "SUPPORTED SAMPLE",
}
SAMPLE_POLICY = (
    "Recent-sample tiers: 0-2 games INSUFFICIENT and 3-4 VERY LOW never support a move; 5-6 LIMITED supports one only "
    "with 7+ current-season games, fresh production, a qualified current role and two of four corroborations (10+ "
    "games in the last 30 days; a STABLE or RISING role; Last-30 PPG within 13% of Last-14 PPG; no minutes drop of 3+ "
    "against earlier 30-day games); 7+ SUPPORTED. Rest of Season Outlook counts this season's "
    "games, so 5-6 cannot be corroborated there. Prior-season history never replaces current games."
)


def sample_tier(games: int) -> SampleTier:
    return ("SUPPORTED" if games >= SUPPORTED_SAMPLE_GAMES else "LIMITED" if games >= LIMITED_SAMPLE_GAMES
        else "VERY_LOW" if games >= VERY_LOW_SAMPLE_GAMES else "INSUFFICIENT")


def _games(count: int) -> str:
    return f"{count} game{'' if count == 1 else 's'}"


def limited_shortfall(required: list[SampleCheck], corroborations: list[SampleCheck]) -> str:
    """Why a LIMITED sample is not promoted: the corroboration count and any missing mandatory requirement."""
    missing = [check.label for check in required if not check.passed]
    passed = sum(check.passed for check in corroborations)
    text = f"{passed} of {len(corroborations)} corroborations passed, {CORROBORATIONS_REQUIRED} needed"
    if missing:
        text += f"; missing requirement{'s' if len(missing) > 1 else ''}: {', '.join(missing)}"
    return text


def _window(player: Candidate, key: str):
    return next((row for row in (player.form.windows if player.form else []) if row.key == key), None)


def _corroborations(player: Candidate) -> list[SampleCheck]:
    last_30, last_14 = _window(player, "LAST_30_DAYS"), _window(player, "LAST_14_DAYS")
    role = player.opportunity.current_role
    trend = player.form.trend if player.form else None
    checks = []
    games_30 = last_30.games if last_30 is not None else 0
    checks.append(SampleCheck(key="last_30_games", label=f"{CORROBORATION_GAMES}+ games in the last 30 days",
        passed=last_30 is not None and games_30 >= CORROBORATION_GAMES,
        detail=f"{_games(games_30)} in the last 30 days" if last_30 is not None else "Last 30 Days evidence unavailable"))
    qualified = role is not None and role.quality.state == "available"
    checks.append(SampleCheck(key="role_direction", label="qualified STABLE or RISING role",
        passed=qualified and role.trend in {"STABLE", "RISING"},
        detail=f"role {role.trend} ({role.quality.state})" if role is not None else "role evidence unavailable"))
    ppg_14 = last_14.fantasy_ppg if last_14 is not None else None
    ppg_30 = last_30.fantasy_ppg if last_30 is not None else None
    earlier = games_30 - (last_14.games if last_14 is not None else 0)
    if (ppg_14 is None or ppg_30 is None or ppg_30 <= 0 or earlier < 3 or last_30.state != "available"
            or last_14.state != "available"):
        checks.append(SampleCheck(key="ppg_corroboration", label="Last-30 PPG corroborates Last-14 PPG", passed=False,
            detail=("needs fresh Last 14 and Last 30 Days fantasy PPG with 3+ games before the last 14 days "
                f"({_games(max(earlier, 0))} earlier)")))
    else:
        deviation = (ppg_14 - ppg_30) / ppg_30
        checks.append(SampleCheck(key="ppg_corroboration", label="Last-30 PPG corroborates Last-14 PPG",
            passed=abs(deviation) <= FORM_PPG_TOLERANCE,
            detail=(f"Last 14 {ppg_14:.1f} vs Last 30 {ppg_30:.1f} fantasy PPG ({deviation * 100:+.1f}%; "
                f"tolerance {FORM_PPG_TOLERANCE * 100:.0f}%)")))
    change = trend.minutes_change if trend is not None else None
    checks.append(SampleCheck(key="minutes_stable", label="no material minutes drop",
        passed=change is not None and change > -MINUTES_DROP,
        detail=(f"Last 14 {trend.recent_minutes:.1f} vs earlier 30-day {trend.baseline_minutes:.1f} minutes "
            f"({change:+.1f}; a drop of {MINUTES_DROP:.1f}+ is material)" if change is not None
            else "needs 3+ games with minutes in both the last 14 days and the earlier 30-day games")))
    return checks


def assess_sample(player: Candidate, mode: Mode) -> SampleAssessment:
    season_games = player.current_season_games
    if mode == "ros":
        window, relevant, quality = "CURRENT_SEASON", min(season_games, player.ros.games), player.data_quality.get("ros")
        noun = "this season"
    else:
        window, relevant, quality = "LAST_14_DAYS", player.recent.games, player.data_quality.get("recent")
        noun = "in the last 14 days"
    tier = sample_tier(relevant)
    fresh = quality is not None and quality.state == "available"
    label = SAMPLE_TIER_LABELS[tier]
    base = dict(mode=mode, window=window, relevant_games=relevant, current_season_games=season_games, tier=tier)
    if tier == "SUPPORTED":
        passes = season_games >= SUPPORTED_SAMPLE_GAMES and fresh
        problems = ([f"{_games(season_games)} this season"] if season_games < SUPPORTED_SAMPLE_GAMES else []) + (
            [f"production evidence {quality.state if quality is not None else 'missing'}"] if not fresh else [])
        return SampleAssessment(**base, passes=passes,
            detail=f"{_games(relevant)} {noun} ({label})" + (f"; {' and '.join(problems)}" if problems else ""))
    if tier != "LIMITED" or mode == "ros":
        reason = ("a limited current-season sample cannot be corroborated by older seasons" if tier == "LIMITED"
            else "never supports a move")
        return SampleAssessment(**base, passes=False, detail=f"{_games(relevant)} {noun} ({label}: {reason})")
    role = player.opportunity.current_role
    required = [
        SampleCheck(key="season_games", label=f"{SUPPORTED_SAMPLE_GAMES}+ current-season games",
            passed=season_games >= SUPPORTED_SAMPLE_GAMES, detail=f"{_games(season_games)} this season"),
        SampleCheck(key="fresh_production", label="fresh production evidence", passed=fresh,
            detail=f"Last 14 Days production {quality.state if quality is not None else 'missing'}"),
        SampleCheck(key="qualified_role", label="qualified current role",
            passed=role is not None and role.quality.state == "available",
            detail=(f"role {role.trend} ({role.quality.state}; needs 3 valid fresh games on each side)"
                if role is not None else "role evidence unavailable")),
    ]
    corroborations = _corroborations(player)
    count = sum(check.passed for check in corroborations)
    corroborated = all(check.passed for check in required) and count >= CORROBORATIONS_REQUIRED
    if corroborated:
        detail = (f"{_games(relevant)} {noun} ({label}), corroborated: "
            + "; ".join(check.detail for check in corroborations if check.passed))
    else:
        detail = f"{_games(relevant)} {noun} ({label}: gate not met; {limited_shortfall(required, corroborations)})"
    return SampleAssessment(**base, passes=corroborated, corroborated=corroborated, required=required,
        corroborations=corroborations, corroborations_passed=count, detail=detail)


def sufficient_sample(player: Candidate, mode: Mode) -> bool:
    """The recent-sample gate. Loaded candidates carry their assessment; hand-built ones are assessed on demand."""
    assessment = player.sample if player.sample is not None and player.sample.mode == mode else assess_sample(player, mode)
    return assessment.passes


def sample_assessment(player: Candidate, mode: Mode) -> SampleAssessment:
    return player.sample if player.sample is not None and player.sample.mode == mode else assess_sample(player, mode)

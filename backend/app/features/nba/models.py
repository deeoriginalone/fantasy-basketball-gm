from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class NbaTeam(Base):
    __tablename__ = "nba_teams"

    nba_team_id: Mapped[str] = mapped_column(String(20), primary_key=True)
    abbreviation: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state: Mapped[str | None] = mapped_column(String(100), nullable=True)
    year_founded: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NbaPlayer(Base):
    __tablename__ = "players_nba"
    __table_args__ = (Index("ix_players_nba_team_id", "team_id"),)

    nba_player_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="SET NULL"), nullable=True
    )
    team_abbreviation: Mapped[str | None] = mapped_column(String(10), nullable=True)
    roster_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    from_year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    to_year: Mapped[str | None] = mapped_column(String(10), nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NbaPlayerSeasonStats(Base):
    __tablename__ = "nba_player_season_stats"
    __table_args__ = (
        Index("ix_nba_player_season_stats_season_type", "season", "season_type"),
    )

    nba_player_id: Mapped[str] = mapped_column(
        ForeignKey("players_nba.nba_player_id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    season_type: Mapped[str] = mapped_column(String(40), primary_key=True)
    games_played: Mapped[int] = mapped_column(Integer, nullable=False)
    games_started: Mapped[int] = mapped_column(Integer, nullable=False)
    minutes_per_game: Mapped[float | None] = mapped_column(Float, nullable=True)
    usage_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    advanced_stats: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NbaGame(Base):
    __tablename__ = "nba_games"
    __table_args__ = (
        Index("ix_nba_games_season_date", "season", "game_date"),
    )

    game_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    game_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    home_team_id: Mapped[str | None] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="RESTRICT"), nullable=True
    )
    away_team_id: Mapped[str | None] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="RESTRICT"), nullable=True
    )
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlayerGameLog(Base):
    __tablename__ = "player_game_logs"
    __table_args__ = (
        Index("ix_player_game_logs_game_date", "game_date"),
    )

    nba_player_id: Mapped[str] = mapped_column(
        ForeignKey("players_nba.nba_player_id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("nba_games.game_id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    season_type: Mapped[str] = mapped_column(String(40), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_id: Mapped[str | None] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="SET NULL"), nullable=True
    )
    stats_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlayerSchedule(Base):
    __tablename__ = "player_schedule"
    __table_args__ = (
        Index("ix_player_schedule_season_date", "season", "game_date"),
    )

    nba_player_id: Mapped[str] = mapped_column(
        ForeignKey("players_nba.nba_player_id", ondelete="CASCADE"), primary_key=True
    )
    game_id: Mapped[str] = mapped_column(
        ForeignKey("nba_games.game_id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    game_date: Mapped[date] = mapped_column(Date, nullable=False)
    team_id: Mapped[str] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="RESTRICT"), nullable=False
    )
    opponent_team_id: Mapped[str] = mapped_column(
        ForeignKey("nba_teams.nba_team_id", ondelete="RESTRICT"), nullable=False
    )
    is_home: Mapped[bool] = mapped_column(Boolean, nullable=False)
    game_status: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

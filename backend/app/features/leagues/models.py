from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class League(Base):
    __tablename__ = "leagues"

    league_key: Mapped[str] = mapped_column(String(80), primary_key=True)
    game_key: Mapped[str] = mapped_column(String(80), nullable=False)
    league_name: Mapped[str] = mapped_column(String(255), nullable=False)
    season: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    settings: Mapped["LeagueSettings | None"] = relationship(
        back_populates="league",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="selectin",
    )
    teams: Mapped[list["Team"]] = relationship(
        back_populates="league",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LeagueSettings(Base):
    __tablename__ = "league_settings"

    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), primary_key=True
    )
    scoring_settings: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    roster_positions: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    league: Mapped[League] = relationship(back_populates="settings")


class Team(Base):
    __tablename__ = "teams"

    team_key: Mapped[str] = mapped_column(String(100), primary_key=True)
    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), nullable=False, index=True
    )
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    league: Mapped[League] = relationship(back_populates="teams")
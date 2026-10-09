from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Identity, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class PlayerIdentity(Base):
    __tablename__ = "player_identity"

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=10001), primary_key=True)
    yahoo_player_id: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    nba_player_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    espn_player_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    observations: Mapped[list["LeaguePlayer"]] = relationship(back_populates="identity")
    roster_entries: Mapped[list["RosterEntry"]] = relationship(back_populates="identity")


class LeaguePlayer(Base):
    __tablename__ = "players"
    __table_args__ = (
        UniqueConstraint("league_key", "yahoo_player_id", name="uq_players_league_yahoo_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=10001), primary_key=True)
    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), nullable=False, index=True
    )
    yahoo_player_id: Mapped[str] = mapped_column(String(40), nullable=False)
    player_identity_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    identity: Mapped[PlayerIdentity] = relationship(back_populates="observations")


class FantasyTeam(Base):
    __tablename__ = "fantasy_teams"

    team_key: Mapped[str] = mapped_column(
        ForeignKey("teams.team_key", ondelete="CASCADE"), primary_key=True
    )
    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), nullable=False, index=True
    )
    team_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    roster_entries: Mapped[list["RosterEntry"]] = relationship(
        back_populates="fantasy_team",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RosterEntry(Base):
    __tablename__ = "rosters"
    __table_args__ = (
        UniqueConstraint("team_key", "yahoo_player_id", name="uq_rosters_team_yahoo_player"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(start=10001), primary_key=True)
    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), nullable=False, index=True
    )
    team_key: Mapped[str] = mapped_column(
        ForeignKey("fantasy_teams.team_key", ondelete="CASCADE"), nullable=False, index=True
    )
    yahoo_player_id: Mapped[str] = mapped_column(String(40), nullable=False)
    player_identity_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    roster_position: Mapped[str | None] = mapped_column(String(80), nullable=True)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fantasy_team: Mapped[FantasyTeam] = relationship(back_populates="roster_entries")
    identity: Mapped[PlayerIdentity] = relationship(back_populates="roster_entries")
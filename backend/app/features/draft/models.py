from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Identity, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DraftPlayerMetric(Base):
    __tablename__ = "draft_player_metrics"
    __table_args__ = (
        Index("ix_draft_player_metrics_league_season", "league_key", "season"),
    )

    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), primary_key=True
    )
    player_identity_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    fantasy_value: Mapped[float] = mapped_column(Float, nullable=False)
    replacement_value: Mapped[float] = mapped_column(Float, nullable=False)
    positional_scarcity: Mapped[float] = mapped_column(Float, nullable=False)
    durability_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    upside_score: Mapped[float] = mapped_column(Float, nullable=False)
    sample_games: Mapped[int] = mapped_column(Integer, nullable=False)
    source_season: Mapped[str] = mapped_column(String(9), nullable=False)
    source_season_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DraftMarketData(Base):
    __tablename__ = "draft_market_data"
    __table_args__ = (
        Index("ix_draft_market_data_season_source", "season", "source"),
    )

    player_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), primary_key=True)
    adp: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    draft_frequency: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_updated: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DraftMarketProviderSnapshot(Base):
    __tablename__ = "draft_market_provider_snapshots"

    player_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="CASCADE"), primary_key=True
    )
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), primary_key=True)
    source_player_id: Mapped[str] = mapped_column(String(80), nullable=False)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team: Mapped[str | None] = mapped_column(String(20), nullable=True)
    positions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    xrank: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DraftMarketUnmatchedRecord(Base):
    __tablename__ = "draft_market_unmatched_records"
    __table_args__ = (
        Index("ix_draft_market_unmatched_records_season_source", "season", "source"),
    )

    source_player_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    season: Mapped[str] = mapped_column(String(9), primary_key=True)
    source: Mapped[str] = mapped_column(String(80), primary_key=True)
    player_name: Mapped[str] = mapped_column(String(255), nullable=False)
    team: Mapped[str | None] = mapped_column(String(20), nullable=True)
    positions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    adp: Mapped[float] = mapped_column(Float, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DraftMarketSyncRun(Base):
    __tablename__ = "draft_market_sync_runs"
    __table_args__ = (
        Index("ix_draft_market_sync_runs_season_source", "season", "source", "completed_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_records_fetched: Mapped[int | None] = mapped_column(Integer, nullable=True)
    matched_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ambiguous_matches: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_players: Mapped[int | None] = mapped_column(Integer, nullable=True)
    adp_coverage_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    rank_coverage_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    draft_frequency_coverage_percentage: Mapped[float | None] = mapped_column(Float, nullable=True)
    stale_records: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_type: Mapped[str | None] = mapped_column(String(80), nullable=True)


class DraftSession(Base):
    __tablename__ = "draft_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    league_key: Mapped[str] = mapped_column(
        ForeignKey("leagues.league_key", ondelete="CASCADE"), nullable=False, index=True
    )
    season: Mapped[str] = mapped_column(String(9), nullable=False)
    manager_team_key: Mapped[str] = mapped_column(
        ForeignKey("teams.team_key", ondelete="CASCADE"), nullable=False
    )
    draft_position: Mapped[int] = mapped_column(Integer, nullable=False)
    total_teams: Mapped[int] = mapped_column(Integer, nullable=False)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    team_slots: Mapped[dict[str, int]] = mapped_column(JSONB, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class DraftPick(Base):
    __tablename__ = "draft_picks"
    __table_args__ = (
        Index(
            "uq_draft_picks_session_player",
            "session_id",
            "selected_player_id",
            unique=True,
            postgresql_where="selected_player_id IS NOT NULL",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("draft_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    overall_pick: Mapped[int] = mapped_column(Integer, primary_key=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    team_slot: Mapped[int] = mapped_column(Integer, nullable=False)
    team_key: Mapped[str] = mapped_column(ForeignKey("teams.team_key"), nullable=False)
    selected_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_identity.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    picked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source_evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DraftPickEvent(Base):
    __tablename__ = "draft_pick_events"

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("draft_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    overall_pick: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_identity.id", ondelete="SET NULL"), nullable=True
    )
    selected_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_identity.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    version_after: Mapped[int] = mapped_column(Integer, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DraftRecommendationSnapshot(Base):
    __tablename__ = "draft_recommendation_snapshots"
    __table_args__ = (
        UniqueConstraint("session_id", "session_version", name="uq_draft_snapshot_version"),
        Index("ix_draft_snapshot_session_created", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        ForeignKey("draft_sessions.id", ondelete="CASCADE"), nullable=False
    )
    session_version: Mapped[int] = mapped_column(Integer, nullable=False)
    recommendation_player_id: Mapped[int | None] = mapped_column(
        ForeignKey("player_identity.id", ondelete="SET NULL"), nullable=True
    )
    input_state: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DraftTarget(Base):
    __tablename__ = "draft_targets"
    __table_args__ = (
        Index("ix_draft_targets_session_status", "session_id", "status"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("draft_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("player_identity.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

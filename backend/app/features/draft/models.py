from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Identity, Index, Integer, String, func
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

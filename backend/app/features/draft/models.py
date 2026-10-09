from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
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

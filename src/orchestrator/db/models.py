"""SQLAlchemy models for the orchestrator database."""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from orchestrator.db.base import Base


class Model(Base):
    """AI model information from various providers."""

    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    context_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    metrics: Mapped[list["Metric"]] = relationship("Metric", back_populates="model", cascade="all, delete-orphan")
    routing_indices: Mapped[list["RoutingIndex"]] = relationship(
        "RoutingIndex", back_populates="model", cascade="all, delete-orphan"
    )
    aliases: Mapped[list["ModelAlias"]] = relationship(
        "ModelAlias", back_populates="canonical_model", cascade="all, delete-orphan"
    )


class Metric(Base):
    """Metrics collected from benchmark sources."""

    __tablename__ = "metrics"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_type: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(nullable=False, index=True)

    # Relationship
    model: Mapped["Model"] = relationship("Model", back_populates="metrics")

    # Indexes for common queries
    __table_args__ = (
        Index("ix_metrics_model_source", "model_id", "source"),
        Index("ix_metrics_source_type", "source", "metric_type"),
    )


class BenchmarkSourceRecord(Base):
    """Tracking information for benchmark data sources."""

    __tablename__ = "benchmark_sources"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    last_sync: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    last_success: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sync_interval_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)


class ModelAlias(Base):
    """Mapping of model name variations to canonical models."""

    __tablename__ = "model_aliases"

    alias: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    canonical_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationship
    canonical_model: Mapped["Model"] = relationship("Model", back_populates="aliases")

    # Index for finding unreviewed aliases
    __table_args__ = (Index("ix_model_aliases_reviewed", "reviewed"),)


class RoutingIndex(Base):
    """Pre-computed routing scores for models by profile."""

    __tablename__ = "routing_index"

    model_id: Mapped[int] = mapped_column(ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    profile: Mapped[str] = mapped_column(String(100), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    latency_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cost_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    components_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationship
    model: Mapped["Model"] = relationship("Model", back_populates="routing_indices")

    # Composite index for profile lookups
    __table_args__ = (
        Index("ix_routing_index_profile_score", "profile", "score"),
        Index("ix_routing_index_model_profile", "model_id", "profile", unique=True),
    )

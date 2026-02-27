"""SQLAlchemy models for the analysis schema (profiles, QA findings, imputation)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from load_gear.core.database import Base


class AnalysisProfile(Base):
    """Central intelligence artifact. One profile per analysis run."""

    __tablename__ = "analysis_profiles"
    __table_args__ = {"schema": "analysis"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id"), nullable=False
    )
    meter_id: Mapped[str] = mapped_column(Text, nullable=False)
    day_fingerprints: Mapped[dict | None] = mapped_column(JSONB)
    seasonality: Mapped[dict | None] = mapped_column(JSONB)
    holiday_rules: Mapped[dict | None] = mapped_column(JSONB)
    weather_correlations: Mapped[dict | None] = mapped_column(JSONB)
    asset_hints: Mapped[dict | None] = mapped_column(JSONB)  # NULL in v0.1 (ADR-005)
    impute_policy: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class QualityFinding(Base):
    """QA check results from P3. Read-only record of what QA found."""

    __tablename__ = "quality_findings"
    __table_args__ = (
        Index("ix_quality_findings_job_check", "job_id", "check_id"),
        {"schema": "analysis"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id"), nullable=False
    )
    check_id: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    check_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Enum("ok", "warn", "error", name="check_status", schema="analysis",
             create_constraint=True),
        nullable=False,
    )
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    metric_value: Mapped[float] = mapped_column(Double, nullable=False)
    threshold: Mapped[float | None] = mapped_column(Double)
    affected_slots: Mapped[dict | None] = mapped_column(JSONB)
    recommendation: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ImputationRun(Base):
    """Tracks each imputation execution for lineage."""

    __tablename__ = "imputation_runs"
    __table_args__ = {"schema": "analysis"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    analysis_profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analysis.analysis_profiles.id"), nullable=False
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id"), nullable=False
    )
    slots_replaced: Mapped[int] = mapped_column(Integer, nullable=False)
    method_summary: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

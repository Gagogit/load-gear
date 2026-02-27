"""SQLAlchemy models for the data schema (time series hypertables, HPFC)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Double,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from load_gear.core.database import Base


class MeterRead(Base):
    """Normalized energy time series. v1=raw (P2), v2=imputed (P4). Hypertable on ts_utc."""

    __tablename__ = "meter_reads"
    __table_args__ = (
        UniqueConstraint("ts_utc", "meter_id", "version", name="uq_meter_reads_ts_meter_version"),
        Index("ix_meter_reads_meter_ts_ver", "meter_id", "ts_utc", "version"),
        Index("ix_meter_reads_job_id", "job_id"),
        {"schema": "data"},
    )

    ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    meter_id: Mapped[str] = mapped_column(String(100), primary_key=True, nullable=False)
    version: Mapped[int] = mapped_column(SmallInteger, primary_key=True, nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id"), nullable=False
    )
    value: Mapped[float] = mapped_column(Double, nullable=False)
    unit: Mapped[str] = mapped_column(
        Enum("kW", "kWh", name="energy_unit", schema="data", create_constraint=True),
        nullable=False,
    )
    quality_flag: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    source_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.files.id")
    )
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class WeatherObservation(Base):
    """DWD weather station data. Hypertable on ts_utc. PostGIS GEOGRAPHY for location."""

    __tablename__ = "weather_observations"
    __table_args__ = (
        Index("ix_weather_obs_station_ts", "station_id", "ts_utc"),
        {"schema": "data"},
    )

    ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    station_id: Mapped[str] = mapped_column(String(20), primary_key=True, nullable=False)
    # source_location is GEOGRAPHY(POINT) — created via raw SQL in migration
    temp_c: Mapped[float | None] = mapped_column(Double)
    ghi_wm2: Mapped[float | None] = mapped_column(Double)
    wind_ms: Mapped[float | None] = mapped_column(Double)
    cloud_pct: Mapped[float | None] = mapped_column(Double)
    confidence: Mapped[float | None] = mapped_column(Double)
    source: Mapped[str] = mapped_column(
        Enum("dwd_cdc", "brightsky", "open_meteo", name="weather_source", schema="data",
             create_constraint=True),
        nullable=False,
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ForecastRun(Base):
    """Metadata for each forecast execution."""

    __tablename__ = "forecast_runs"
    __table_args__ = (
        Index("ix_forecast_runs_job_id", "job_id"),
        {"schema": "data"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id"), nullable=False
    )
    meter_id: Mapped[str] = mapped_column(String(100), nullable=False)
    analysis_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    horizon_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    model_alias: Mapped[str] = mapped_column(String(50), default="prophet", nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(50))
    data_snapshot_id: Mapped[str | None] = mapped_column(String(64))
    strategies: Mapped[dict | None] = mapped_column(JSONB)
    quantiles: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(
        Enum("queued", "running", "ok", "warn", "failed", name="forecast_status", schema="data",
             create_constraint=True),
        default="queued",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ForecastSeries(Base):
    """Prophet projection output. Hypertable on ts_utc."""

    __tablename__ = "forecast_series"
    __table_args__ = (
        Index("ix_forecast_series_forecast_ts", "forecast_id", "ts_utc"),
        {"schema": "data"},
    )

    ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    forecast_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data.forecast_runs.id"),
        primary_key=True, nullable=False,
    )
    y_hat: Mapped[float] = mapped_column(Double, nullable=False)
    q10: Mapped[float | None] = mapped_column(Double)
    q50: Mapped[float | None] = mapped_column(Double)
    q90: Mapped[float | None] = mapped_column(Double)


class HpfcSnapshot(Base):
    """HPFC curve version metadata."""

    __tablename__ = "hpfc_snapshots"
    __table_args__ = {"schema": "data"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    provider_id: Mapped[str] = mapped_column(String(100), nullable=False)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    curve_type: Mapped[str] = mapped_column(
        Enum("HPFC", "Spot", "Intraday", name="curve_type", schema="data",
             create_constraint=True),
        nullable=False,
    )
    delivery_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    delivery_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="EUR", nullable=False)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.files.id")
    )


class HpfcSeries(Base):
    """Hourly price forward curve data points."""

    __tablename__ = "hpfc_series"
    __table_args__ = (
        Index("ix_hpfc_series_snapshot_ts", "snapshot_id", "ts_utc"),
        {"schema": "data"},
    )

    ts_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, nullable=False
    )
    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("data.hpfc_snapshots.id"),
        primary_key=True, nullable=False,
    )
    price_mwh: Mapped[float] = mapped_column(Double, nullable=False)

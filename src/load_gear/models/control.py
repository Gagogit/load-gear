"""SQLAlchemy models for the control schema (jobs, files, reader_profiles, holidays)."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    BigInteger,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from load_gear.core.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "pending"
    INGESTING = "ingesting"
    QA_RUNNING = "qa_running"
    ANALYSIS_RUNNING = "analysis_running"
    FORECAST_RUNNING = "forecast_running"
    FINANCIAL_RUNNING = "financial_running"
    DONE = "done"
    WARN = "warn"
    FAILED = "failed"


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status", "status"),
        Index("ix_jobs_company_id", "company_id"),
        Index("ix_jobs_meter_id", "meter_id"),
        Index("ix_jobs_created_at", "created_at"),
        {"schema": "control"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus, name="job_status", schema="control", create_constraint=True),
        default=JobStatus.PENDING,
        nullable=False,
    )
    project_name: Mapped[str] = mapped_column(String(200), nullable=False, server_default="")
    company_id: Mapped[str | None] = mapped_column(String(100))
    meter_id: Mapped[str | None] = mapped_column(String(100))
    plz: Mapped[str | None] = mapped_column(String(5))
    user_id: Mapped[str] = mapped_column(String(100), nullable=False, server_default="")
    payload: Mapped[dict | None] = mapped_column(JSONB)
    current_phase: Mapped[str | None] = mapped_column(String(20))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_context: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    files: Mapped[list[File]] = relationship(back_populates="job", cascade="all, delete-orphan")


class File(Base):
    __tablename__ = "files"
    __table_args__ = (
        Index("ix_files_job_id", "job_id"),
        Index("ix_files_sha256", "sha256"),
        {"schema": "control"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("control.jobs.id", ondelete="CASCADE"), nullable=False
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    original_name: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100))
    meta_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="files")
    reader_profile: Mapped[ReaderProfile | None] = relationship(
        back_populates="file", cascade="all, delete-orphan", uselist=False
    )


class ReaderProfile(Base):
    __tablename__ = "reader_profiles"
    __table_args__ = (
        Index("ix_reader_profiles_file_id", "file_id"),
        {"schema": "control"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    file_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("control.files.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    rules: Mapped[dict | None] = mapped_column(JSONB)
    technical_quality: Mapped[dict | None] = mapped_column(JSONB)
    is_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    file: Mapped[File] = relationship(back_populates="reader_profile")


class Holiday(Base):
    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("date", "state_code", name="uq_holiday_date_state"),
        Index("ix_holidays_year", "year"),
        {"schema": "control"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    state_code: Mapped[str] = mapped_column(String(5), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    year: Mapped[int] = mapped_column(Integer, nullable=False)

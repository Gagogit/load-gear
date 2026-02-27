"""Pydantic request/response models for the API layer."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class JobCreateRequest(BaseModel):
    """POST /api/v1/jobs request body."""

    meter_id: str = Field(..., max_length=100, description="MaLo/Zählpunkt identifier")
    company_id: str | None = Field(None, max_length=100, description="Company identifier")
    plz: str | None = Field(None, max_length=5, description="Postal code for geo-matching")
    tasks: list[str] = Field(
        default_factory=lambda: ["Statistik"],
        description="Processing tasks: Statistik, Fehleranalyse, Imputation, Prognose, Aggregation",
    )
    horizon_months: int | None = Field(None, ge=1, le=60, description="Forecast horizon in months")
    unit: str | None = Field(None, description="Target unit: kW or kWh")
    interval_minutes: int | None = Field(None, description="Target interval: 15 or 60")
    scenarios: dict | None = Field(None, description="Scenario parameters (PV, battery, etc.)")


class JobResponse(BaseModel):
    """Single job in API responses."""

    id: uuid.UUID
    status: str
    company_id: str | None = None
    meter_id: str | None = None
    plz: str | None = None
    current_phase: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobDetailResponse(JobResponse):
    """GET /api/v1/jobs/{job_id} — includes payload."""

    payload: dict | None = None


class JobListResponse(BaseModel):
    """GET /api/v1/jobs response."""

    items: list[JobResponse]
    total: int


# --- File schemas ---


class FileResponse(BaseModel):
    """Single file in API responses."""

    id: uuid.UUID
    job_id: uuid.UUID
    storage_uri: str
    original_name: str
    sha256: str
    file_size: int
    mime_type: str | None = None
    meta_data: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FileUploadResponse(BaseModel):
    """POST /api/v1/files/upload response."""

    id: uuid.UUID
    sha256: str
    original_name: str
    file_size: int
    duplicate: bool = False


# --- Reader Profile schemas (P2a) ---


class ReaderProfileRules(BaseModel):
    """Detected or overridden file parsing rules."""

    encoding: str = Field(..., description="File encoding (utf-8, iso-8859-1, windows-1252)")
    delimiter: str = Field(..., description="Column delimiter (; , \\t)")
    header_row: int = Field(0, description="0-based index of the header row")
    timestamp_columns: list[str] = Field(..., description="Column name(s) forming the timestamp")
    value_column: str = Field(..., description="Column name containing the meter value")
    date_format: str = Field(..., description="strftime date format (e.g. %d.%m.%Y)")
    time_format: str = Field(..., description="strftime time format (e.g. %H:%M)")
    decimal_separator: str = Field(..., description="Decimal separator: , or .")
    unit: str = Field(..., description="Energy unit: kW, kWh, Wh")
    series_type: str = Field(..., description="interval or cumulative")
    timezone: str = Field("Europe/Berlin", description="Source timezone")


class ReaderProfileResponse(BaseModel):
    """GET /api/v1/files/{file_id}/reader-profile response."""

    id: uuid.UUID
    file_id: uuid.UUID
    rules: ReaderProfileRules | None = None
    technical_quality: dict | None = None
    is_override: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ReaderProfileOverrideRequest(BaseModel):
    """PUT /api/v1/files/{file_id}/reader-profile request body."""

    rules: ReaderProfileRules


# --- Ingest schemas (P2) ---


class IngestRequest(BaseModel):
    """POST /api/v1/ingest request body."""

    job_id: uuid.UUID
    file_id: uuid.UUID


class IngestStatusResponse(BaseModel):
    """GET /api/v1/ingest/{job_id}/status response."""

    job_id: uuid.UUID
    status: str
    current_phase: str | None = None
    total_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    warnings: list[str] = Field(default_factory=list)
    error_message: str | None = None


class NormalizedRowResponse(BaseModel):
    """Single normalized meter read row."""

    ts_utc: datetime
    meter_id: str
    value: float
    unit: str
    version: int
    quality_flag: int


class NormalizedListResponse(BaseModel):
    """GET /api/v1/ingest/{job_id}/normalized response."""

    items: list[NormalizedRowResponse]
    total: int

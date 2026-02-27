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


# --- QA schemas (P3) ---


class QARunRequest(BaseModel):
    """POST /api/v1/qa request body."""

    job_id: uuid.UUID


class QAFindingResponse(BaseModel):
    """Single QA check finding."""

    id: uuid.UUID
    job_id: uuid.UUID
    check_id: int
    check_name: str
    status: str  # ok / warn / error
    metric_key: str
    metric_value: float
    threshold: float | None = None
    affected_slots: dict | list | None = None
    recommendation: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QAReportResponse(BaseModel):
    """GET /api/v1/qa/{job_id}/report — full 9-check report."""

    job_id: uuid.UUID
    findings: list[QAFindingResponse]
    overall_status: str  # ok / warn / error
    created_at: datetime


class QAStatusResponse(BaseModel):
    """GET /api/v1/qa/{job_id}/status response."""

    job_id: uuid.UUID
    status: str
    checks_completed: int = 0
    checks_total: int = 9
    overall_status: str | None = None
    error_message: str | None = None


class QAProfileResponse(BaseModel):
    """GET /api/v1/qa/{job_id}/profile — hourly/weekday arrays."""

    job_id: uuid.UUID
    hourly_profile: list[float]  # 24 values (hour 0-23)
    weekday_profile: list[float]  # 7 values (Mon=0 .. Sun=6)


class AdminConfigResponse(BaseModel):
    """GET/PUT /api/v1/admin/config response."""

    min_kw: float = 0.0
    max_kw: float = 10000.0
    max_jump_kw: float = 5000.0
    top_n_peaks: int = 10
    min_completeness_pct: float = 95.0
    max_gap_duration_min: int = 180


# --- Analysis & Imputation schemas (P4) ---


class AnalysisRunRequest(BaseModel):
    """POST /api/v1/analysis request body."""

    job_id: uuid.UUID


class AnalysisStatusResponse(BaseModel):
    """GET /api/v1/analysis/{job_id}/status response."""

    job_id: uuid.UUID
    status: str
    current_phase: str | None = None
    sub_phase: str | None = None  # P4.1 / P4.2 / P4.3 / P4.4
    error_message: str | None = None


class DayFingerprintEntry(BaseModel):
    """Single day-type fingerprint."""

    avg_kw: list[float]  # 24 hourly averages
    count: int


class AnalysisProfileResponse(BaseModel):
    """GET /api/v1/analysis/{job_id}/profile response."""

    job_id: uuid.UUID
    meter_id: str
    day_fingerprints: dict[str, DayFingerprintEntry] | None = None
    seasonality: dict | None = None
    weather_correlations: dict | None = None
    asset_hints: dict | None = None
    impute_policy: dict | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DayLabelEntry(BaseModel):
    """Single day classification result."""

    date: str
    label: str
    confidence: float


class DayLabelsResponse(BaseModel):
    """GET /api/v1/analysis/{job_id}/day-labels response."""

    job_id: uuid.UUID
    labels: list[DayLabelEntry]
    total: int


class WeatherFeatureEntry(BaseModel):
    """Weather feature for a single timestamp."""

    ts_utc: datetime
    temp_c: float | None = None
    ghi_wm2: float | None = None
    confidence: float | None = None


class WeatherResponse(BaseModel):
    """GET /api/v1/analysis/{job_id}/weather response."""

    job_id: uuid.UUID
    features: list[WeatherFeatureEntry]
    correlations: dict | None = None


class ImputationReportResponse(BaseModel):
    """GET /api/v1/analysis/{job_id}/imputation response."""

    job_id: uuid.UUID
    slots_replaced: int
    method_summary: dict  # {profile: n, interpolation: n, weather: n}
    total_v2_rows: int


class NormalizedV2Response(BaseModel):
    """GET /api/v1/analysis/{job_id}/normalized-v2 response."""

    items: list[NormalizedRowResponse]
    total: int


# --- Forecast schemas (P5) ---


class ForecastRunRequest(BaseModel):
    """POST /api/v1/forecasts request body."""

    job_id: uuid.UUID
    horizon_start: datetime | None = Field(None, description="Start of forecast horizon (auto if None)")
    horizon_end: datetime | None = Field(None, description="End of forecast horizon (auto if None)")
    strategies: list[str] = Field(
        default_factory=lambda: ["calendar_mapping", "dst_correct"],
        description="Post-processing strategies to apply",
    )
    quantiles: list[float] = Field(
        default_factory=lambda: [0.1, 0.5, 0.9],
        description="Prediction quantiles (default: q10, q50, q90)",
    )


class ForecastRunResponse(BaseModel):
    """Forecast run metadata."""

    id: uuid.UUID
    job_id: uuid.UUID
    meter_id: str
    status: str
    horizon_start: datetime
    horizon_end: datetime
    quantiles: list[float] | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ForecastStatusResponse(BaseModel):
    """GET /api/v1/forecasts/{job_id}/status response."""

    job_id: uuid.UUID
    status: str
    current_phase: str | None = None
    forecast_run_id: uuid.UUID | None = None
    error_message: str | None = None


class ForecastSeriesResponse(BaseModel):
    """Single forecast series row."""

    ts_utc: datetime
    y_hat: float
    q10: float | None = None
    q50: float | None = None
    q90: float | None = None


class ForecastSeriesListResponse(BaseModel):
    """GET /api/v1/forecasts/{job_id}/series response."""

    job_id: uuid.UUID
    forecast_id: uuid.UUID
    rows: list[ForecastSeriesResponse]
    total: int


class ForecastSummaryResponse(BaseModel):
    """GET /api/v1/forecasts/{job_id}/summary response."""

    job_id: uuid.UUID
    forecast_id: uuid.UUID
    total_rows: int
    y_hat: dict  # {min, max, mean}
    q10: dict | None = None
    q50: dict | None = None
    q90: dict | None = None


# --- HPFC schemas (P6) ---


class HpfcUploadResponse(BaseModel):
    """POST /api/v1/hpfc/upload response."""

    snapshot_id: uuid.UUID
    provider_id: str
    rows_imported: int
    delivery_start: datetime
    delivery_end: datetime


class HpfcSnapshotResponse(BaseModel):
    """Single HPFC snapshot metadata."""

    id: uuid.UUID
    provider_id: str
    snapshot_at: datetime
    curve_type: str
    delivery_start: datetime
    delivery_end: datetime
    currency: str
    file_id: uuid.UUID | None = None

    model_config = {"from_attributes": True}


class HpfcSnapshotListResponse(BaseModel):
    """GET /api/v1/hpfc response."""

    items: list[HpfcSnapshotResponse]
    total: int


class HpfcSeriesResponse(BaseModel):
    """Single HPFC series data point."""

    ts_utc: datetime
    price_mwh: float


class HpfcSeriesListResponse(BaseModel):
    """GET /api/v1/hpfc/{snapshot_id}/series response."""

    snapshot_id: uuid.UUID
    rows: list[HpfcSeriesResponse]
    total: int


# --- Financial schemas (P6) ---


class FinancialCalcRequest(BaseModel):
    """POST /api/v1/financial/calculate request body."""

    job_id: uuid.UUID
    snapshot_id: uuid.UUID | None = Field(None, description="Specific HPFC snapshot (auto if None)")


class CostRowResponse(BaseModel):
    """Single cost row in the time series."""

    ts_utc: datetime
    consumption_kwh: float
    price_mwh: float
    cost_eur: float


class MonthlySummaryEntry(BaseModel):
    """Monthly cost aggregation."""

    month: str  # YYYY-MM
    total_cost_eur: float
    total_kwh: float
    avg_price_mwh: float


class FinancialResultResponse(BaseModel):
    """GET /api/v1/financial/{job_id}/result response."""

    calc_id: uuid.UUID
    job_id: uuid.UUID
    total_cost_eur: float
    monthly_summary: list[MonthlySummaryEntry]
    rows: list[CostRowResponse]


# --- Weather schemas (P7) ---


class WeatherImportRequest(BaseModel):
    """POST /api/v1/weather/import request body."""

    station_id: str = Field(..., max_length=20, description="DWD station ID (e.g. 00433)")
    lat: float = Field(..., ge=-90, le=90, description="Station latitude")
    lon: float = Field(..., ge=-180, le=180, description="Station longitude")
    params: list[str] = Field(
        default_factory=lambda: ["air_temperature", "solar"],
        description="DWD parameters to import",
    )
    start: datetime | None = Field(None, description="Optional start filter (UTC)")
    end: datetime | None = Field(None, description="Optional end filter (UTC)")


class WeatherImportResponse(BaseModel):
    """POST /api/v1/weather/import response."""

    station_id: str
    total_inserted: int
    counts_per_param: dict[str, int]


class WeatherStationInfo(BaseModel):
    """Station summary in list responses."""

    station_id: str
    obs_count: int
    earliest: datetime | None = None
    latest: datetime | None = None
    source: str


class WeatherStationListResponse(BaseModel):
    """GET /api/v1/weather/stations response."""

    items: list[WeatherStationInfo]
    total: int


class WeatherObservationRow(BaseModel):
    """Single weather observation in API responses."""

    ts_utc: datetime
    station_id: str
    temp_c: float | None = None
    ghi_wm2: float | None = None
    wind_ms: float | None = None
    cloud_pct: float | None = None
    confidence: float | None = None
    source: str

    model_config = {"from_attributes": True}


class WeatherObservationListResponse(BaseModel):
    """GET /api/v1/weather/stations/{station_id}/observations response."""

    station_id: str
    items: list[WeatherObservationRow]
    total: int

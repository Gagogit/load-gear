# Schema: data (Time Series Hypertables)
Schicht: B
Letzte Aktualisierung: 2026-02-27

The `data` schema holds all mass time series data. Tables are **TimescaleDB hypertables**
optimized for billions of rows. This is the single source of truth for queryable data.

Storage decisions: `/docs/architecture/decisions.md` ADR-002

---

## Table: `data.meter_reads` (Hypertable)

The "Golden Row" — normalized energy time series. Contains both v1 (raw) and v2 (imputed).

| Column | Type | Description |
|--------|------|-------------|
| ts_utc | TIMESTAMPTZ | Leading time reference (UTC) |
| meter_id | TEXT | Zählpunkt/MaLo identifier |
| job_id | UUID (FK → control.jobs) | Source job (lineage) |
| value | DOUBLE PRECISION | Measured/imputed value |
| unit | ENUM ('kW', 'kWh') | Value unit |
| version | SMALLINT | 1 = raw (P2 output), 2 = imputed (P4 output) |
| quality_flag | SMALLINT | 0=original, 1=interpolated, 2=profile-based, 3=weather-based |
| source_file_id | UUID (FK → control.files) | Original file (v1 lineage) |
| analysis_run_id | UUID | Analysis run that produced v2 (NULL for v1) |

**Hypertable:** Partitioned on ts_utc (1 month chunks)
**Indexes:** (meter_id, ts_utc, version), job_id
**Constraint:** Unique on (ts_utc, meter_id, version)

Note: v2 ownership belongs to Analysis service (ADR-001). QA never writes here.

---

## Table: `data.weather_observations` (Hypertable)

DWD weather station data. Source-centered storage (one row per station per hour).

| Column | Type | Description |
|--------|------|-------------|
| ts_utc | TIMESTAMPTZ | Observation timestamp (UTC, hourly) |
| station_id | TEXT | DWD station identifier |
| source_location | GEOGRAPHY(POINT) | Station coordinates (PostGIS) |
| temp_c | DOUBLE PRECISION | Dry-bulb temperature (°C) |
| ghi_wm2 | DOUBLE PRECISION | Global horizontal irradiance (W/m²) |
| wind_ms | DOUBLE PRECISION | Wind speed (m/s), nullable |
| cloud_pct | DOUBLE PRECISION | Cloud cover (%), nullable |
| confidence | DOUBLE PRECISION | 1.0 - (distance/50km), set during spatial join |
| source | ENUM ('dwd_cdc', 'brightsky', 'open_meteo') | Data provenance |
| ingested_at | TIMESTAMPTZ | When this row was imported |

**Hypertable:** Partitioned on ts_utc (3 month chunks)
**Indexes:** (station_id, ts_utc), GIST on source_location
**Spatial query:** `ORDER BY geom <-> source_location LIMIT 1` (KNN via PostGIS)

---

## Table: `data.forecast_series` (Hypertable)

Prophet projection output. One row per timestamp per forecast run.

| Column | Type | Description |
|--------|------|-------------|
| ts_utc | TIMESTAMPTZ | Forecast timestamp (UTC) |
| forecast_id | UUID (FK → control.forecast_runs) | Forecast run identifier |
| y_hat | DOUBLE PRECISION | Point forecast (predicted value) |
| q10 | DOUBLE PRECISION | 10th percentile (lower bound) |
| q50 | DOUBLE PRECISION | 50th percentile (median) |
| q90 | DOUBLE PRECISION | 90th percentile (upper bound) |

**Hypertable:** Partitioned on ts_utc (1 month chunks)
**Indexes:** (forecast_id, ts_utc)

---

## Table: `data.forecast_runs`

Metadata for each forecast execution. Referenced by forecast_series.

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Forecast run identifier |
| job_id | UUID (FK → control.jobs) | Parent job |
| meter_id | TEXT | Target meter |
| analysis_run_id | UUID | Analysis profile used |
| horizon_start | TIMESTAMPTZ | Forecast start (UTC) |
| horizon_end | TIMESTAMPTZ | Forecast end (UTC) |
| model_alias | TEXT | 'prophet' |
| model_version | TEXT | Semver or git hash |
| data_snapshot_id | TEXT | SHA-256 reproducibility hash |
| strategies | JSONB | Applied strategies array |
| quantiles | JSONB | Requested quantiles [10, 50, 90] |
| status | ENUM ('queued', 'running', 'ok', 'warn', 'failed') | Run status |
| created_at | TIMESTAMPTZ | Run start time |
| completed_at | TIMESTAMPTZ | Run completion time |

---

## Table: `data.hpfc_series`

Hourly Price Forward Curves from energy providers.

| Column | Type | Description |
|--------|------|-------------|
| ts_utc | TIMESTAMPTZ | Hour for which the price applies |
| snapshot_id | UUID (FK → data.hpfc_snapshots) | Curve version |
| price_mwh | DOUBLE PRECISION | Price in €/MWh |

## Table: `data.hpfc_snapshots`

| Column | Type | Description |
|--------|------|-------------|
| id | UUID (PK) | Snapshot identifier |
| provider_id | TEXT | Provider name (EPEXSpot, EEX, etc.) |
| snapshot_at | TIMESTAMPTZ | When this curve was created |
| curve_type | ENUM ('HPFC', 'Spot', 'Intraday') | Curve type |
| delivery_start | DATE | First delivery day |
| delivery_end | DATE | Last delivery day |
| currency | TEXT | 'EUR' |
| file_id | UUID (FK → control.files) | Source file reference |

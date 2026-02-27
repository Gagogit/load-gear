# LOAD-GEAR System Architecture
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Vision

LOAD-GEAR processes raw energy meter readings (Lastgänge) into validated forecasts
and financial calculations for commercial energy customers. The platform enables
scenario analysis (PV integration, peak shaving, battery storage).

## Data Flow

```
[Upload CSV/Excel] → P2 Ingest → P3 QA → P4 Analysis → P5 Forecast → P6 Financial
                         ↓           ↓          ↓             ↓            ↓
                     v1 (raw)    findings    v2 (clean)    v3 (proj)    cost calc
```

## Processing Pipeline

| Phase | Name | Service | Input | Output |
|-------|------|---------|-------|--------|
| P1 | Input | API | User form + file | Validated job.json |
| P2 | Homogenize | ingest | Raw file | v1 in meter_reads + reader_profile |
| P3 | QA | qa | v1 time series | 9-check report + quality_findings |
| P4 | Analysis | analysis | v1 + findings + weather | v2 in meter_reads + analysis_profile |
| P5 | Forecast | forecast | v2 + analysis_profile | v3 in forecast_series (q10/q50/q90) |
| P6 | Financial | financial | v3 + HPFC curves | Cost time series (€/h) + summaries |

## Storage Architecture

| System | Purpose | Data |
|--------|---------|------|
| PostgreSQL/TimescaleDB | Source of truth | All time series, metadata, analysis results |
| PostGIS | Geo operations | Weather station matching (KNN, ST_Distance) |
| GCS/MinIO | Archive only | Raw uploads (WORM), PDF reports, Prophet artifacts |

Binding decisions: `/docs/architecture/decisions.md`

## Schema Overview

Three PostgreSQL schemas with clear responsibilities:

- **`control`** — Job orchestration, file metadata, reader profiles
- **`analysis`** — Analysis profiles, day fingerprints, weather correlations
- **`data`** — Time series hypertables (meter_reads, weather_observations, forecast_series)

Full definitions: `/docs/schema/control.md`, `/docs/schema/data.md`, `/docs/schema/analysis.md`

## Service Layer (Controller → Service → Repository)

```
API Layer (FastAPI)          → Input validation, HTTP, auth placeholder
  ├── routes/jobs.py
  ├── routes/files.py
  ├── routes/ingest.py
  ├── routes/qa.py
  ├── routes/analysis.py
  ├── routes/forecasts.py
  ├── routes/financial.py
  ├── routes/weather.py
  └── routes/admin.py

Service Layer                → Business logic, orchestration
  ├── ingest/                → Reader profiles, normalization, GCS upload
  ├── qa/                    → 9 statistical checks
  ├── analysis/              → Day classification, weather join, imputation
  ├── forecast/              → Prophet training, rollout, export
  └── financial/             → HPFC matching, cost vector multiplication

Repository Layer             → SQLAlchemy async, DB-only
  ├── job_repo.py
  ├── file_repo.py
  ├── meter_repo.py
  ├── weather_repo.py
  ├── analysis_repo.py
  └── forecast_repo.py
```

## Job State Machine

See: `/docs/architecture/decisions.md` ADR-003

```
pending → ingesting → qa_running → analysis_running → forecast_running → done
              ↓            ↓              ↓                 ↓
           failed        failed         failed            failed
```

Jobs skip phases based on `tasks[]` — see ADR-004.

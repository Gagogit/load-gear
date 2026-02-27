# LOAD-GEAR Project Structure

## Source Layout
```
src/load_gear/
├── api/
│   ├── app.py                    # FastAPI factory, registers all routers
│   └── routes/
│       ├── admin.py              # /api/v1/admin (health, config)
│       ├── jobs.py               # /api/v1/jobs (CRUD)
│       ├── files.py              # /api/v1/files (upload, download, reader-profile)
│       ├── ingest.py             # /api/v1/ingest (POST ingest, GET status/normalized)
│       ├── qa.py                 # /api/v1/qa (POST qa, GET status/report/findings/profile)
│       ├── analysis.py           # /api/v1/analysis (POST, GET status/profile/day-labels/weather/imputation/normalized-v2)
│       ├── forecasts.py          # /api/v1/forecasts (POST, GET status/run/series/summary)
│       ├── hpfc.py               # /api/v1/hpfc (POST upload, GET list/detail/series, DELETE)
│       └── financial.py          # /api/v1/financial (POST calculate, GET result/export)
├── core/
│   ├── config.py                 # Pydantic config with YAML + env vars
│   ├── database.py               # Async engine + session factory + get_session dependency
│   └── storage.py                # LocalStorageBackend (GCS later)
├── models/
│   ├── control.py                # Job, File, ReaderProfile, Holiday (+ JobStatus enum)
│   ├── data.py                   # MeterRead, WeatherObservation, ForecastRun, ForecastSeries, HpfcSnapshot, HpfcSeries, FinancialRun
│   ├── analysis.py               # AnalysisProfile, QualityFinding, ImputationRun
│   └── schemas.py                # All Pydantic request/response models (P1-P6)
├── repositories/
│   ├── __init__.py               # Exports all 12 repos
│   ├── job_repo.py
│   ├── file_repo.py
│   ├── reader_profile_repo.py
│   ├── meter_read_repo.py        # bulk_insert, get_by_job_id (version param), count
│   ├── quality_finding_repo.py   # bulk_insert, get_by_job_id, delete_by_job_id
│   ├── analysis_profile_repo.py  # create, get_by_job_id, update
│   ├── imputation_run_repo.py    # create, get_by_job_id, get_latest
│   ├── forecast_run_repo.py      # create, get_by_id, get_by_job_id, update_status
│   ├── forecast_series_repo.py   # bulk_insert, get_by_forecast_id, get_summary
│   ├── hpfc_snapshot_repo.py     # create, get_by_id, list_all, get_latest_covering, delete
│   ├── hpfc_series_repo.py       # bulk_insert, get_by_snapshot_id, get_all, delete_by_snapshot_id
│   └── financial_run_repo.py     # create, get_by_id, get_by_job_id, update_status
└── services/
    ├── job_service.py            # State machine, VALID_TRANSITIONS, advance_job
    ├── ingest/
    │   ├── format_detector.py    # P2a: detect_format(raw_bytes) → rules dict
    │   ├── normalizer.py         # P2b: normalize(bytes, rules) → (rows, quality_stats)
    │   ├── ingest_service.py     # Orchestrator: run_ingest, get_ingest_status
    │   └── detectors/            # encoding, delimiter, datetime_format, numeric, series_type
    ├── qa/
    │   ├── config.py             # QAConfig singleton (admin-tunable thresholds)
    │   ├── qa_service.py         # Orchestrator: run_qa, get_qa_status/report/profile
    │   └── checks/               # 9 check modules (1-9)
    ├── analysis/
    │   ├── day_classifier.py     # P4.1: classify_days → (fingerprints, labels)
    │   ├── weather_enrichment.py # P4.2: enrich_weather (stub in v0.1)
    │   ├── asset_fingerprint.py  # P4.3: detect_assets (stub, ADR-005)
    │   ├── imputer.py            # P4.4: impute → (v2_rows, method_summary)
    │   └── analysis_service.py   # Orchestrator: run_analysis, get_analysis_status/profile
    ├── forecast/
    │   ├── prophet_trainer.py    # P5.1: train_and_predict (async, thread pool)
    │   ├── forecast_service.py   # Orchestrator: run_forecast, get_forecast_status/run/series/summary
    │   └── strategies/
    │       ├── calendar_mapping.py # Blend Prophet with day-class fingerprints
    │       ├── dst_correct.py      # DST transition day interval adjustment
    │       └── scaling.py          # Growth %, load shift + weather/asset stubs
    └── financial/
        ├── hpfc_service.py       # P6: HPFC CSV parser (Polars), upload, CRUD
        └── financial_service.py  # P6: Orchestrator: forecast × HPFC, monthly summaries, export
```

## Test Layout
```
tests/
├── test_jobs_api.py              # 7 tests
├── test_files_api.py             # 5 tests
├── test_state_machine.py         # 33 tests
├── test_format_detector.py       # 24 tests
├── test_normalizer.py            # 8 tests
├── test_reader_profile_repo.py   # 4 tests
├── test_reader_profile_api.py    # 4 tests
├── test_ingest_api.py            # 8 tests
├── test_qa_checks.py             # 18 tests
├── test_qa_api.py                # 12 tests
├── test_day_classifier.py        # 9 tests
├── test_imputer.py               # 6 tests
├── test_analysis_api.py          # 11 tests
├── test_prophet_trainer.py       # 6 tests
├── test_strategies.py            # 16 tests
├── test_forecast_api.py          # 10 tests
├── test_hpfc_service.py          # 7 tests
├── test_financial_calculator.py  # 8 tests
├── test_hpfc_api.py              # 8 tests
├── test_financial_api.py         # 8 tests
├── fixtures/                     # CSV test files
└── integration/
    ├── test_phase1.py            # 2 tests
    ├── test_phase2.py            # 2 tests
    ├── test_phase3.py            # 2 tests
    ├── test_phase4.py            # 2 tests
    ├── test_phase5.py            # 2 tests
    └── test_phase6.py            # 2 tests
```

## API Endpoints Summary (31 total)
- **Admin (2):** GET /health, GET/PUT /config
- **Jobs (4):** POST, GET list, GET detail, DELETE
- **Files (3):** POST upload, GET metadata, GET download, GET/PUT reader-profile
- **Ingest (3):** POST, GET status, GET normalized
- **QA (5):** POST, GET status/report/findings/profile
- **Analysis (7):** POST, GET status/profile/day-labels/weather/imputation/normalized-v2
- **Forecasts (5):** POST, GET status/run/series/summary
- **HPFC (5):** POST upload, GET list/detail/series, DELETE
- **Financial (3):** POST calculate, GET result/export

## Database: 14 tables across 3 schemas
- **control (4):** jobs, files, reader_profiles, holidays
- **data (7):** meter_reads, weather_observations, forecast_runs, forecast_series, hpfc_snapshots, hpfc_series, financial_runs
- **analysis (3):** analysis_profiles, quality_findings, imputation_runs

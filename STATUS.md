# STATUS — Current Phase

Phase: 1 — Foundation
Started: 2026-02-27

## Task-001: Project Setup
- Status: COMPLETED
- Decision: Used Pydantic BaseModel for config validation with YAML + env var overrides
- Decision: Database connection fails gracefully (returns "degraded" health, doesn't crash)
- Decision: App factory pattern (create_app) for testability
- Impact: All subsequent tasks can import from load_gear.core.config and load_gear.core.database
- Verified: app starts, health endpoint responds, OpenAPI docs accessible

## Task-002: Control Schema
- Status: COMPLETED
- Decision: Used SQLAlchemy Enum with schema-qualified name for JobStatus (control.job_status)
- Decision: Alembic env.py excludes PostGIS system tables (spatial_ref_sys) from autogenerate
- Decision: Downgrade explicitly drops the enum type to ensure clean re-upgrade
- Impact: All 4 control tables ready: jobs, files, reader_profiles, holidays
- Verified: upgrade → downgrade → upgrade cycle works cleanly

## Task-003: Data Schema
- Status: COMPLETED
- Decision: Manually wrote migration (autogenerate picked up control tables) — only data tables
- Decision: PostGIS GEOGRAPHY(POINT, 4326) column + GiST index via raw SQL (not in ORM model)
- Decision: TimescaleDB hypertables: meter_reads (1mo), weather_observations (3mo), forecast_series (1mo)
- Decision: 4 enum types in data schema: energy_unit, weather_source, forecast_status, curve_type
- Impact: All 6 data tables ready: meter_reads, weather_observations, forecast_runs, forecast_series, hpfc_snapshots, hpfc_series
- Verified: upgrade → downgrade → upgrade cycle works cleanly; hypertables + PostGIS confirmed

## Task-003a: Analysis Schema
- Status: COMPLETED
- Decision: Manually wrote migration (same autogenerate issue as task-003)
- Decision: check_status enum in analysis schema: ok, warn, error
- Decision: All JSONB columns nullable (incremental build-up as per task spec)
- Decision: imputation_runs FK to analysis_profiles (not directly to jobs only)
- Impact: All 3 analysis tables ready: analysis_profiles, quality_findings, imputation_runs
- Verified: upgrade → downgrade → upgrade cycle works cleanly

## Task-002r: Schema Integrity Review
- Status: COMPLETED
- Result: ALL CHECKS PASS — no forward-blockers for Phase 2
- 13 tables across 3 schemas, 12 FKs all valid, 6 enums correct
- 3 hypertables with appropriate chunk sizes
- ADR-001 (v2 ownership): analysis_run_id only on meter_reads + forecast_runs — correct
- ADR-003 (state machine): 8 states match exactly
- Minor findings (non-blocking): holidays.date is DateTime not DATE, holidays uses surrogate PK, hpfc_snapshots delivery dates are DateTime not DATE
- Spec typo noted: forecast_series FK listed as control.forecast_runs, correct impl is data.forecast_runs

## Task-004: Job State Machine & API
- Status: COMPLETED
- Decision: Controller→Service→Repository pattern (job_service depends on job_repo, routes depend on job_service)
- Decision: State machine in VALID_TRANSITIONS dict — covers all 8 states, terminal states have empty sets
- Decision: QA_RUNNING can transition to DONE/WARN directly (ADR-004 skip matrix for Statistik-only jobs)
- Decision: Only PENDING and FAILED jobs can be deleted (protect in-progress data)
- Decision: Pydantic from_attributes=True for ORM→response mapping
- Files created: models/schemas.py, repositories/job_repo.py, services/job_service.py, api/routes/jobs.py
- Tests: 33 unit (state machine) + 7 integration (API endpoints) = 40 passing
- Verified: POST 201, POST 422, GET 200, GET 404, DELETE 200, DELETE 404

## Task-005: File Upload & Storage
- Status: COMPLETED
- Decision: LocalStorageBackend with StorageBackend protocol (GCS adapter later)
- Decision: Files stored at raw/{year}/{file_id}.{ext} with local:// URI prefix
- Decision: SHA-256 dedup: duplicate upload returns existing file_id with duplicate=true
- Decision: job_id required on upload (links file to job via FK)
- Files created: core/storage.py, repositories/file_repo.py, api/routes/files.py
- Tests: 5 integration (upload, dedup, metadata, 404, download) — all use unique CSV content
- Verified: upload → metadata → download roundtrip, dedup works, 45 total tests pass

## Task-005r: API & State Machine Review
- Status: COMPLETED
- Result: ALL 31 CHECKS PASS — no issues found
- POST/GET job roundtrip: all fields consistent (11 checks)
- File upload/download: SHA-256, storage path, metadata, content roundtrip (9 checks)
- Error format: 404/422/409 all return consistent {detail: ...} (3 checks)
- List filters: status + meter_id filtering verified (5 checks)
- Delete constraints: pending deletable, gone on re-fetch (3 checks)

## Task-006: Phase 1 Integration Test
- Status: COMPLETED
- Created: tests/fixtures/sample_lastgang.csv (24 rows, 15-min, German format, semicolon-delimited)
- Created: tests/integration/test_phase1.py (full scenario + CSV format validation)
- Full scenario: create job → upload CSV → verify state → download → list filter → delete → verify cascade
- CASCADE delete verified: deleting job also removes linked files
- Sample CSV validates as realistic: DD.MM.YYYY, HH:MM, comma decimals, kWh, semicolons
- Final test count: 47 tests passing (33 state machine + 7 jobs + 5 files + 2 integration)

## PHASE 1 COMPLETE
All 9 tasks completed. 47 tests passing.

### Phase 1 Summary
- **13 tables** across 3 schemas (control/4, data/6, analysis/3)
- **3 Alembic migrations** with verified upgrade/downgrade cycles
- **3 TimescaleDB hypertables** + 1 PostGIS GEOGRAPHY column
- **4 API endpoints**: POST/GET/DELETE jobs, POST/GET/GET files
- **47 tests** all passing
- **7 ADRs** confirmed and implemented
- **Controller→Service→Repository** pattern established

---

# Phase 2 — Ingest Pipeline
Started: 2026-02-27

## Task-007: Reader Profile Repository + Pydantic Schemas
- Status: COMPLETED
- Decision: CRUD repo for control.reader_profiles (create, get_by_file_id, update)
- Decision: 6 Pydantic models added: ReaderProfileRules, ReaderProfileResponse, ReaderProfileOverrideRequest, IngestRequest, IngestStatusResponse, NormalizedRowResponse, NormalizedListResponse
- Files: repositories/reader_profile_repo.py, models/schemas.py (extended)

## Task-008: Format Detection Service (P2a)
- Status: COMPLETED
- Decision: 5 detector modules in services/ingest/detectors/ (encoding, delimiter, datetime_format, numeric, series_type)
- Decision: chardet for encoding, csv.Sniffer + frequency analysis for delimiter
- Decision: Unit detection order: MWh → kWh → kW → Wh (to avoid kWh matching kW)
- Decision: Cumulative detection via monotonic check (>90% increases)
- Decision: "uhrzeit" added to timestamp column name set
- Files: services/ingest/format_detector.py, services/ingest/detectors/*.py
- Tests: 24 unit tests covering German, ISO, cumulative, tab-delimited formats

## Task-009: Reader Profile API Endpoints
- Status: COMPLETED
- Decision: GET/PUT on /files/{id}/reader-profile (on existing files router)
- Decision: PUT sets is_override=True, preserving original detected rules
- Files: api/routes/files.py (extended)
- Tests: 4 integration tests

## Task-010: Normalization Service (P2b)
- Status: COMPLETED
- Decision: Polars Lazy API for CSV parsing (NO PANDAS)
- Decision: zoneinfo.ZoneInfo for Europe/Berlin → UTC conversion (DST-aware)
- Decision: Cumulative → interval via diff() on sorted timestamps
- Decision: ORM session.add() + flush() for bulk insert (not pg_insert — session lifecycle reliability)
- Files: services/ingest/normalizer.py, repositories/meter_read_repo.py
- Tests: 8 unit tests including DST spring/fall

## Task-011: Ingest Orchestration API
- Status: COMPLETED
- Decision: POST /ingest triggers P2a+P2b synchronously, returns quality stats
- Decision: Job transitions: pending → ingesting → qa_running (or done)
- Decision: Explicit File query instead of job.files lazy relationship (avoids MissingGreenlet)
- Decision: Unique meter_ids per test to prevent cross-test UniqueViolation
- Files: services/ingest/ingest_service.py, api/routes/ingest.py, api/app.py (router registration)
- Tests: 8 integration tests

## Task-012: Phase 2 Integration Test
- Status: COMPLETED
- Decision: Two E2E scenarios: interval data (24 rows) + cumulative data (8 rows → 7 deltas)
- Decision: Random values per test run to avoid SHA-256 dedup issues
- Files: tests/integration/test_phase2.py
- Tests: 2 integration tests, 97 total

## PHASE 2 COMPLETE
All 6 tasks completed. 97 tests passing (50 new).

### Phase 2 Summary
- **Format Detection (P2a)**: 5 detector modules, handles German/ISO/cumulative/Excel formats
- **Normalization (P2b)**: Polars-based, DST-aware UTC conversion, cumulative→interval
- **3 new API endpoints**: POST /ingest, GET /ingest/{id}/status, GET /ingest/{id}/normalized
- **2 reader-profile endpoints**: GET/PUT /files/{id}/reader-profile
- **97 tests** all passing

---

# Phase 3 — QA Engine
Started: 2026-02-27

## Task-013: QA Schemas + quality_finding Repository
- Status: COMPLETED
- Decision: 6 Pydantic models: QARunRequest, QAFindingResponse, QAReportResponse, QAStatusResponse, QAProfileResponse, AdminConfigResponse
- Decision: Repository with bulk_insert, get_by_job_id, get_by_job_and_check, delete_by_job_id (for re-runs)
- Files: repositories/quality_finding_repo.py, models/schemas.py (extended)

## Task-014: 9 QA Checks
- Status: COMPLETED
- Decision: Each check is a standalone module with run() function returning a finding dict
- Decision: Checks use NumPy for statistical calculations (percentiles, mean, std)
- Decision: kWh→kW conversion: value / (interval_minutes / 60)
- Decision: Profiles use Europe/Berlin local time for hour/weekday grouping
- Decision: DST dates computed dynamically (last Sunday of March/October)
- Decision: Baseload and hourly profile are informational (always status=ok)
- Decision: Load factor < 0.1 triggers warn
- Files: services/qa/checks/*.py (9 modules)

## Task-015: QA Orchestration Service
- Status: COMPLETED
- Decision: run_qa fetches all v1 rows, runs 9 checks sequentially, bulk inserts findings
- Decision: Auto-detect interval from data (most common positive delta)
- Decision: Previous findings deleted before re-run (idempotent)
- Decision: Job state after QA: Statistik-only → done/warn; needs analysis → analysis_running
- Decision: Error in any check + stats-only job → WARN (not FAILED)
- Files: services/qa/qa_service.py, services/qa/config.py

## Task-016: QA API Endpoints
- Status: COMPLETED
- Decision: 5 endpoints on /api/v1/qa prefix
- Decision: POST /qa returns 202 with check summary
- Decision: GET /report serializes ORM findings via Pydantic model_validate
- Files: api/routes/qa.py, api/app.py (router registration)

## Task-017: Admin Config Endpoints
- Status: COMPLETED
- Decision: Singleton QAConfig dataclass (in-memory, runtime-mutable)
- Decision: GET/PUT /admin/config on existing admin router
- Decision: Default thresholds: min_completeness=95%, max_kw=10000, max_gap=180min, top_n=10
- Files: api/routes/admin.py (extended), services/qa/config.py

## Task-018: QA Tests + Phase 3 Integration Test
- Status: COMPLETED
- Decision: 18 unit tests for all 9 checks (test_qa_checks.py)
- Decision: 12 API tests including 409 wrong-status, 404 not-found, admin config (test_qa_api.py)
- Decision: 2 E2E tests: full pipeline + gap detection (integration/test_phase3.py)
- Decision: Realistic kWh values (5-23 range) to stay under 10000 kW threshold
- Files: tests/test_qa_checks.py, tests/test_qa_api.py, tests/integration/test_phase3.py

## PHASE 3 COMPLETE
All 6 tasks completed. 129 tests passing (32 new).

### Phase 3 Summary
- **9 QA checks**: interval completeness, completeness %, gaps/duplicates, daily/monthly energy, peak load, baseload, load factor, hourly/weekday profile, DST conformity
- **QA orchestration**: auto-detects interval, saves findings to analysis.quality_findings, advances job state
- **5 new QA endpoints**: POST /qa, GET status/report/findings/profile
- **2 admin endpoints**: GET/PUT /admin/config
- **129 tests** all passing
- **QA is read-only** on time series (ADR-001 respected)

---

# Phase 4 — Analysis & Imputation
Started: 2026-02-27

## Task-019: Analysis Pydantic Schemas + Repositories
- Status: COMPLETED
- Decision: 9 Pydantic models: AnalysisRunRequest, AnalysisStatusResponse, AnalysisProfileResponse, DayFingerprintEntry, DayLabelEntry, DayLabelsResponse, WeatherResponse, ImputationReportResponse, NormalizedV2Response
- Decision: Two new repos: analysis_profile_repo (create, get_by_job_id, update), imputation_run_repo (create, get_by_job_id, get_latest)
- Files: repositories/analysis_profile_repo.py, repositories/imputation_run_repo.py, models/schemas.py (extended)

## Task-020: Day Classification Service (P4.1)
- Status: COMPLETED
- Decision: 7 day types: Werktag-Sommer, Werktag-Winter, Samstag, Sonntag, Feiertag, Brückentag, Störung
- Decision: German federal holidays computed dynamically via Easter algorithm (Anonymous Gregorian)
- Decision: Bridge day verification: load comparison >20% drop vs normal weekday reference
- Decision: Störung detection: daily load <10% of average weekday
- Decision: Summer months = April–September (for Sommer/Winter split)
- Decision: 24-hour avg kW fingerprints per day type
- Files: services/analysis/day_classifier.py
- Tests: 9 unit tests

## Task-021: Weather Enrichment + Asset Fingerprint Stubs (P4.2/P4.3)
- Status: COMPLETED
- Decision: Weather enrichment returns empty correlations when no weather data available
- Decision: Interface designed for future PostGIS KNN joins (weather_data param)
- Decision: Correlation computation via NumPy corrcoef when data available
- Decision: Asset fingerprinting stub per ADR-005: returns {"asset_hints": None}
- Files: services/analysis/weather_enrichment.py, services/analysis/asset_fingerprint.py

## Task-022: Imputation Engine (P4.4)
- Status: COMPLETED
- Decision: Priority chain: profile-based (flag=2) → linear interpolation (flag=1)
- Decision: Weather-based (flag=3) and asset-adjusted skipped in v0.1
- Decision: Gaps > max_gap_min (default 1440 min = 1 day) are not imputed
- Decision: v2 rows include all original values (flag=0) plus imputed slots
- Decision: Linear interpolation finds nearest before/after neighbors
- Files: services/analysis/imputer.py
- Tests: 6 unit tests

## Task-023: Analysis Orchestration Service + API
- Status: COMPLETED
- Decision: Orchestrator runs P4.1→P4.2→P4.3→P4.4 sequentially, sets current_phase per sub-phase
- Decision: Creates AnalysisProfile with day_fingerprints, seasonality, weather_correlations, impute_policy
- Decision: Creates ImputationRun record tracking slots_replaced and method_summary
- Decision: Job state after analysis: Prognose/Aggregation tasks → forecast_running; else → done
- Decision: 7 endpoints on /api/v1/analysis prefix (POST, GET status/profile/day-labels/weather/imputation/normalized-v2)
- Files: services/analysis/analysis_service.py, api/routes/analysis.py, api/app.py (router registration)

## Task-024: Phase 4 Tests + Integration Test
- Status: COMPLETED
- Decision: 9 unit tests for day classifier (holidays, seasons, Störung, bridge days)
- Decision: 6 unit tests for imputer (no gaps, profile fill, interpolation, large gaps, empty input)
- Decision: 11 API integration tests (POST/GET endpoints, 404/409 errors, job state advancement)
- Decision: 2 E2E tests: full pipeline with gap + complete data without imputation
- Files: tests/test_day_classifier.py, tests/test_imputer.py, tests/test_analysis_api.py, tests/integration/test_phase4.py

## PHASE 4 COMPLETE — STOPP
All 6 tasks completed. 157 tests passing (28 new). Awaiting approval for Phase 5.

### Phase 4 Summary
- **Day Classification (P4.1)**: 7 day types, German holiday detection, bridge day verification, Störung detection
- **Weather Enrichment (P4.2)**: Interface ready, stub in v0.1 (no weather data)
- **Asset Fingerprinting (P4.3)**: Stub per ADR-005
- **Imputation (P4.4)**: Profile-based + linear interpolation chain, quality flags 0-3
- **7 new API endpoints**: POST /analysis, GET status/profile/day-labels/weather/imputation/normalized-v2
- **v2 series**: Written to data.meter_reads (version=2) with lineage tracking via imputation_runs
- **157 tests** all passing
- **Analysis owns v2** (ADR-001 respected)

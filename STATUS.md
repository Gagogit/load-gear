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

## PHASE 1 COMPLETE — STOPP
All 9 tasks completed. Awaiting approval for Phase 2 (Ingest Pipeline).

### Phase 1 Summary
- **13 tables** across 3 schemas (control/4, data/6, analysis/3)
- **3 Alembic migrations** with verified upgrade/downgrade cycles
- **3 TimescaleDB hypertables** + 1 PostGIS GEOGRAPHY column
- **4 API endpoints**: POST/GET/DELETE jobs, POST/GET/GET files
- **47 tests** all passing
- **7 ADRs** confirmed and implemented
- **Controller→Service→Repository** pattern established

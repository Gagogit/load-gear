# Task-Backlog

## Phase 1 — Foundation (Schema, API Skeleton, Job State Machine)

1. [x] task-001.md — Project setup: pyproject.toml, FastAPI app shell, DB connection, folder init files
2. [x] task-002.md — Database schema: control tables (jobs, files, reader_profiles, holidays)
3. [x] task-003.md — Database schema: data tables (meter_reads, weather_observations, forecast_series, hpfc)
4. [x] task-003a.md — Database schema: analysis tables (analysis_profiles, quality_findings, imputation_runs)
5. [x] task-002r.md — Review: all schemas match spec, no contradictions, migrations work
6. [x] task-004.md — Job state machine: status transitions, POST/GET/DELETE /api/v1/jobs endpoints
7. [x] task-005.md — File upload: POST /api/v1/files/upload, GET /files/{id}, GCS raw/ storage
8. [x] task-005r.md — Review: API + schema integration, state machine correctness
9. [x] task-006.md — Integration test: create job → upload file → verify DB state

STOPP — Freigabe für Phase 2 erforderlich

## Phase 2 — Ingest Pipeline (P2: Reader Profiles, Normalization, v1)

(to be planned after Phase 1 approval)

## Phase 3 — QA Engine (P3: 9 Statistical Checks)

(to be planned after Phase 2 approval)

## Phase 4 — Analysis & Imputation (P4: Day Classification, Weather, v2)

(to be planned after Phase 3 approval)

## Phase 5 — Forecast (P5: Prophet Integration)

(to be planned after Phase 4 approval)

## Phase 6 — Financial (P6: HPFC Cost Calculation)

(to be planned after Phase 5 approval)

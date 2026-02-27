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

## Phase 2 — Ingest Pipeline (P2: Reader Profiles, Normalization, v1)

10. [x] Task-007 — Reader Profile Repository + Pydantic Schemas (CRUD for reader_profiles, P2 models)
11. [x] Task-008 — Format Detection Service (P2a: encoding, delimiter, datetime, numeric, series_type)
12. [x] Task-009 — Reader Profile API Endpoints (GET/PUT /files/{id}/reader-profile)
13. [x] Task-010 — Normalization Service (P2b: Polars-based, UTC conversion, cumulative→interval)
14. [x] Task-011 — Ingest Orchestration API (POST /ingest, GET status, GET normalized)
15. [x] Task-012 — Phase 2 Integration Test (97 tests total)

## Phase 3 — QA Engine (P3: 9 Statistical Checks)

16. [x] Task-013 — QA Schemas + quality_finding Repository
17. [x] Task-014 — 9 QA Checks (interval completeness, completeness %, gaps/duplicates, daily/monthly energy, peak load, baseload, load factor, hourly/weekday profile, DST conformity)
18. [x] Task-015 — QA Orchestration Service (run_qa, get_qa_status, get_qa_report, get_qa_profile)
19. [x] Task-016 — QA API Endpoints (POST /qa, GET status/report/findings/profile)
20. [x] Task-017 — Admin Config Endpoints (GET/PUT /admin/config)
21. [x] Task-018 — QA Tests + Phase 3 Integration Test (129 tests total)

## Phase 4 — Analysis & Imputation (P4: Day Classification, Weather, v2)

22. [x] Task-019 — Analysis Pydantic Schemas + Repositories (analysis_profile_repo, imputation_run_repo)
23. [x] Task-020 — Day Classification Service (P4.1: 7 day types, German holidays, bridge days, Störung detection)
24. [x] Task-021 — Weather Enrichment + Asset Fingerprint Stubs (P4.2/P4.3, ADR-005)
25. [x] Task-022 — Imputation Engine (P4.4: profile-based + linear interpolation, quality flags 0-3, v2 writes)
26. [x] Task-023 — Analysis Orchestration Service + API (7 endpoints on /api/v1/analysis)
27. [x] Task-024 — Phase 4 Tests + Integration Test (157 tests total)

## Phase 5 — Forecast (P5: Prophet Integration)

28. [x] Task-025 — Forecast Pydantic Schemas + Repositories (forecast_run_repo, forecast_series_repo, 6 Pydantic models)
29. [x] Task-026 — Prophet Training Service (P5.1: thread pool executor, German holidays, quantiles q10/q50/q90)
30. [x] Task-027 — Strategy Implementation (P5.2: calendar mapping, DST correction, scaling + stubs)
31. [x] Task-028 — Forecast Orchestration Service + API (5 endpoints on /api/v1/forecasts)
32. [x] Task-029 — Phase 5 Tests + Integration Test (191 tests total)

STOPP — Freigabe für Phase 6 erforderlich

## Phase 6 — Financial (P6: HPFC Cost Calculation)

(to be planned after Phase 5 approval)

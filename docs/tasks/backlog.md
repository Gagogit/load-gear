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

## Phase 6 — Financial (P6: HPFC Cost Calculation)

33. [x] Task-030 — Alembic Migration 004 + FinancialRun ORM Model (FINANCIAL_RUNNING state, data.financial_runs table, state machine updates)
34. [x] Task-031 — HPFC + Financial Pydantic Schemas + Repositories (8 Pydantic models, hpfc_snapshot_repo, hpfc_series_repo, financial_run_repo)
35. [x] Task-032 — HPFC Upload Service + API (Polars CSV parser, 5 endpoints on /api/v1/hpfc)
36. [x] Task-033 — Financial Calculation Service + API (forecast × HPFC vector multiply, monthly summaries, CSV/XLSX export, 3 endpoints on /api/v1/financial)
37. [x] Task-034 — Phase 6 Tests + Integration Test (230 tests total)

## Phase 7 — Weather Integration & Asset Intelligence

38. [x] Task-035 — DWD Weather Station Import Service (Polars CSV parser, J/cm²→W/m², CET→UTC, weather_observation_repo with PostGIS KNN)
39. [x] Task-036 — Weather API Fallback (BrightSky + Open-Meteo, 10km cache dedup, confidence-based trigger)
40. [x] Task-037 — Spatial-Temporal Join + Weather Correlation Engine (PostGIS KNN, temp/GHI/wind correlations, lag analysis -3h to +3h)
41. [x] Task-038 — Asset Fingerprinting Implementation (PV midday dip + GHI corr, battery night charge + variance ratio, KWK baseload CV + seasonal)
42. [x] Task-039 — Enhanced Imputation + Forecast Strategies (weather flag=3, weather_conditioned + asset_scenarios strategies)
43. [x] Task-040 — Weather Admin Endpoints (4 endpoints on /api/v1/weather: import, stations, observations, delete)
44. [x] Task-041 — PLZ Geocoding Service (909 centroids, 3-digit/2-digit prefix fallback, wired into analysis P4.2)
45. [x] Task-042 — Phase 7 Tests + Integration Test (292 tests total)

# STATUS — Current Phase

Phases 1–7 complete. Phase 7 archived to docs/status/STATUS_phase7_full.md.

## Phase 8 — Multi-Provider HPFC (DONE)

| Task | Description | Status |
|------|-------------|--------|
| MP-01 | Add `provider_id` column to FinancialRun ORM + Alembic migration 007 | done |
| MP-02 | `hpfc_snapshot_repo`: `get_latest_covering_by_provider()`, `list_providers()` | done |
| MP-03 | `financial_run_repo`: `list_by_job_id()`, `get_latest_by_job_id()` alias | done |
| MP-04 | `financial_service`: extract `_calc_single()`, implement `run_financial_multi()`, `get_financial_results()` | done |
| MP-05 | Thread `provider_ids` through `pipeline_service` → `run_financial_multi()` | done |
| MP-06 | Pydantic schemas: `ProviderFinancialResult`, `FinancialMultiResultResponse`, `ProviderListResponse` | done |
| MP-07 | API routes: POST /calculate (multi), GET /result (all), GET /result/{provider_id}, GET /export?provider_id= | done |
| MP-08 | GET /hpfc/providers endpoint (route before /{snapshot_id}) | done |
| MP-09 | Pipeline route: `provider_ids` form field, comma-separated parsing | done |
| MP-10 | Frontend: provider multiselect dropdown + Anbietervergleich result table | done |
| MP-11 | Tests: 6 new multi-provider tests + existing test updates (377 total) | done |

### Key Deliverables
- **1:N Financial**: one ForecastRun produces multiple FinancialRuns, one per provider + baseline
- **Baseline always**: computed regardless of provider_ids, uses any available HPFC snapshot
- **Graceful errors**: missing provider HPFC produces error entry in results, no pipeline abort
- **Provider filter**: `get_latest_covering_by_provider()` filters by provider_id + delivery range
- **Provider list**: `GET /hpfc/providers` returns distinct provider_ids for frontend dropdown
- **Per-provider detail**: `GET /financial/{job_id}/result/{provider_id}` returns full cost rows
- **Export per provider**: `GET /financial/{job_id}/export?provider_id=X` exports specific provider CSV
- **Backward compat**: `run_financial()` delegates to `run_financial_multi()`, old callers still work
- **Frontend**: multiselect dropdown loads providers from API, result table shows cost comparison per provider
- **377 tests** all passing

### Architecture
```
Job → forecast_running → financial_running
  → run_financial_multi(job_id, provider_ids=["vattenfall", "eon"])
    → _calc_single(provider_id="baseline", snapshot=any)     → FinancialRun
    → _calc_single(provider_id="vattenfall", snapshot=vf)    → FinancialRun
    → _calc_single(provider_id="eon", snapshot=None)         → error entry
  → job.status = DONE
```

### Files Changed (14)
1. `src/load_gear/models/data.py` — provider_id on FinancialRun
2. `alembic/versions/007_add_financial_provider_id.py` — migration
3. `src/load_gear/repositories/hpfc_snapshot_repo.py` — 2 new methods
4. `src/load_gear/repositories/financial_run_repo.py` — 2 new methods
5. `src/load_gear/services/financial/financial_service.py` — refactored (multi-provider)
6. `src/load_gear/services/pipeline_service.py` — provider_ids param
7. `src/load_gear/models/schemas.py` — 3 new schemas
8. `src/load_gear/api/routes/financial.py` — 4 endpoints updated/added
9. `src/load_gear/api/routes/hpfc.py` — GET /providers
10. `src/load_gear/api/routes/pipeline.py` — provider_ids form field
11. `src/load_gear/static/index.html` — dropdown + result table
12. `tests/test_financial_multi_provider.py` — 6 new tests
13. `tests/test_financial_api.py` — adapted to multi-provider response
14. `tests/integration/test_phase6.py` — adapted to multi-provider response

## Platform Summary (after Phase 8)
- **14 tables** across 3 schemas (control/4, data/7, analysis/3)
- **7 Alembic migrations**
- **9 job states**: PENDING → INGESTING → QA_RUNNING → ANALYSIS_RUNNING → FORECAST_RUNNING → FINANCIAL_RUNNING → DONE/WARN/FAILED
- **38 API endpoints** across 10 routers
- **13 repositories**
- **377 tests** all passing
- **Full pipeline**: job → ingest → QA → analysis → forecast → financial (multi-provider) → done

# LOAD-GEAR Energy Intelligence

Energy data platform: raw meter readings (v1) → QA/statistics (9 checks) → analysis & imputation (v2) → Prophet forecast (v3) → financial calculation (HPFC).

## Tech-Stack
- Python 3.12+ / FastAPI (async-first)
- PostgreSQL 16 + TimescaleDB (time series) + PostGIS (geo)
- Polars (Lazy API) + NumPy — NO PANDAS
- Prophet (Meta) for forecasting
- SQLAlchemy 2.0 (async) + psycopg3
- GCS/MinIO for raw file archive only (not source of truth)

## Architecture
- Controller → Service → Repository pattern
- Async-first: all DB and API operations non-blocking
- Data lineage: every value traces to job_id + source file
- Time reference: ts_utc is leading; Europe/Berlin only for output/reporting
- Single source of truth: TimescaleDB for all queryable time series
- GCS only for: raw uploads (WORM), PDF reports, Prophet model artifacts

## Data Evolution
- v1 = raw normalized meter reads (after parsing/homogenization)
- v2 = imputed/cleaned series (after QA + analysis, owned by analysis service)
- v3 = forecast projection (Prophet output with quantiles q10/q50/q90)

## Coding Rules
- Full type hints on all functions, no Any
- Every service function has error handling
- No new dependency without entry in `/docs/architecture/decisions.md`
- Tests: unit per task, integration per phase boundary
- Commit messages: imperative mood, reference task ID
Full: `/docs/CODING-GUIDELINES.md`

## Work Rule
Work from: `/docs/tasks/backlog.md`
1. Find next open task
2. Open task file, load all listed documents
3. Execute task
4. Document decisions in STATUS.md
5. Check off task in backlog.md
6. Next task
At phase boundary: archive STATUS.md to /docs/status/ → stop → wait for approval.

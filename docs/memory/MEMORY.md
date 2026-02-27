# LOAD-GEAR Project Memory

## Project Location
- Path: `/home/cs/Schreibtisch/DEv/load-gear`
- GitHub: `https://github.com/Gagogit/load-gear`
- Git auth: PAT embedded in remote URL (user rotates tokens frequently)

## User
- Name: cs / chs@link2lead.de
- Prefers: concise output, no unnecessary questions, fast execution
- Language: German OS, English code/docs

## Current State (Phase 6 COMPLETE)
- **230 tests**, all passing, fully idempotent
- Phases 1-6 done. Full history archived at `docs/status/STATUS_phase6.md`
- See `STATUS.md` and `docs/tasks/backlog.md` for task history

## Architecture Pattern
- Controller → Service → Repository (async-first)
- FastAPI + SQLAlchemy 2.0 async + psycopg3
- PostgreSQL 16 + TimescaleDB + PostGIS
- Polars (NO PANDAS) + NumPy
- Test pattern: ASGITransport + httpx.AsyncClient, unique meter_ids per test

## Key Files (see [project-structure.md](project-structure.md) for full list)
- `src/load_gear/api/app.py` — FastAPI factory, all routers registered
- `src/load_gear/models/` — control.py, data.py, analysis.py (ORM), schemas.py (Pydantic)
- `src/load_gear/services/` — ingest/, qa/, analysis/, forecast/, financial/ (each with orchestrator)
- `src/load_gear/repositories/` — job, file, reader_profile, meter_read, quality_finding, analysis_profile, imputation_run, forecast_run, forecast_series, hpfc_snapshot, hpfc_series, financial_run
- `.venv/bin/python` — virtualenv Python (no system `python` available)

## Data Evolution
- v1 = raw normalized (P2 ingest)
- v2 = imputed/cleaned (P4 analysis) — quality_flag: 0=original, 1=interpolated, 2=profile, 3=weather
- v3 = forecast (P5 Prophet) — written to data.forecast_series with y_hat, q10, q50, q90
- cost = forecast × HPFC (P6 financial) — stored in data.financial_runs with JSONB monthly_summary

## Job State Machine
`pending → ingesting → qa_running → analysis_running → forecast_running → financial_running → done/warn/failed`
- Aggregation task: full 6-phase pipeline through financial_running
- Prognose task: skips financial_running, goes forecast_running → done
- TASK_TERMINAL_PHASE maps task name → terminal state

## Lessons Learned (see [debugging.md](debugging.md))
- Use `session.add()` + `flush()` for bulk insert, NOT `pg_insert` (session lifecycle)
- Use explicit queries instead of lazy relationships in async (MissingGreenlet)
- Use unique meter_ids per test (`uuid.uuid4().hex[:8]`)
- Use small realistic values in test data to avoid threshold issues (peak kW)
- `.replace(".", ",")` on full CSV line corrupts dates — only replace in value strings

## Work Rules
- Always update `STATUS.md` and `docs/tasks/backlog.md` after each phase
- Commit messages: imperative mood, reference task IDs
- Phase boundary: archive STATUS → stop → wait for approval

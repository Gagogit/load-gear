# Debugging Notes & Lessons Learned

## Database / ORM Issues

### pg_insert ON CONFLICT DO NOTHING — don't use for session-tracked inserts
- psycopg3 returns rowcount=-1 with ON CONFLICT DO NOTHING
- Data isn't tracked by ORM session lifecycle → commits fail silently
- **Fix:** Use `session.add(Model(**data))` + `flush()` for each row

### MissingGreenlet on lazy relationships
- Accessing `job.files` in async context raises MissingGreenlet
- **Fix:** Use explicit `select(File).where(File.job_id == job_id)` queries

### UniqueViolation on meter_reads across test runs
- Hardcoded meter_ids like "INGEST_METER" cause PK conflicts
- **Fix:** Use `f"PREFIX_{uuid.uuid4().hex[:8]}"` for unique meter_ids per test

## Test Data Issues

### Random monotonically increasing values detected as cumulative
- Values like v, v+1, v+2, v+3 always increase → series_type detector says "cumulative"
- **Fix:** Use fluctuating values: v, v+3, v-1, v+2

### `.replace(".", ",")` corrupts dates
- Applied to full CSV line: `01.01.2025` becomes `01,01,2025`
- **Fix:** Only replace in the value string: `f"{val:.1f}".replace(".", ",")`

### SHA-256 file dedup in tests
- Same CSV content → same SHA-256 → upload returns existing file
- **Fix:** Use `random.uniform()` or `random.randint()` to vary values per test run

### Peak kW threshold exceeded in tests
- Large base values (100-9999) × 4 (kWh→kW for 15-min) → exceeds 10000 kW default
- **Fix:** Use small realistic values (5-23 kWh range) with small offset for uniqueness

## Format Detection Issues

### kW unit matched before kWh
- Original order checked kWh first, but `\bkW\b(?!h)` failed on `power_kW`
- **Fix:** Check order: MWh → kWh → kW(not followed by h) → Wh

### "Uhrzeit" not recognized as timestamp column
- `ts_names` set didn't include "uhrzeit" (only "zeit")
- **Fix:** Added "uhrzeit" to the detection set

## Alembic / Enum Issues

### PostgreSQL enum values are UPPERCASE in this project
- Migration 001 created job_status with `sa.Enum('PENDING', 'INGESTING', ...)` — stored as uppercase
- When adding new values: `ALTER TYPE control.job_status ADD VALUE 'FINANCIAL_RUNNING' BEFORE 'DONE'`
- Use member names (UPPERCASE), not `.value` (lowercase)

## Environment
- No system `python` binary — use `.venv/bin/python`
- PostgreSQL running locally with TimescaleDB + PostGIS extensions
- Tests run against real PostgreSQL (not SQLite mocks)

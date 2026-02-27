# Task 002: Database Schema — Control Tables

Lade:
  `/docs/schema/control.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  SQLAlchemy models + Alembic migration for the control schema:
  jobs, files, reader_profiles, holidays.

Schritte:
  1. Initialize Alembic in the project (alembic init)
  2. Create src/load_gear/models/control.py with SQLAlchemy models:
     - Job (with status enum, payload JSONB)
     - File (with sha256, storage_uri)
     - ReaderProfile (with rules JSONB, technical_quality JSONB)
     - Holiday (with composite PK: date + state_code)
  3. Create first Alembic migration: "001_control_schema"
  4. Run migration against a test database
  5. Verify all tables exist with correct columns and constraints

Akzeptanzkriterien:
  - `alembic upgrade head` creates all 4 tables in control schema
  - `alembic downgrade base` removes them cleanly
  - Job status enum includes all states from ADR-003
  - Foreign keys: files.job_id → jobs.id, reader_profiles.file_id → files.id
  - Indexes on: jobs.status, jobs.company_id, jobs.meter_id, files.sha256

Einschränkungen:
  - Only control schema in this task
  - Data and analysis schemas come in task-003 and task-003a

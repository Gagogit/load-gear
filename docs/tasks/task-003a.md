# Task 003a: Database Schema — Analysis Tables

Lade:
  `/docs/schema/analysis.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  SQLAlchemy models + Alembic migration for the analysis schema:
  analysis_profiles, quality_findings, imputation_runs.

Schritte:
  1. Create src/load_gear/models/analysis.py with SQLAlchemy models
  2. Create Alembic migration: "003_analysis_schema"
  3. quality_findings: include check status enum (ok, warn, error)
  4. analysis_profiles: all JSONB columns nullable (for incremental build-up)
  5. Verify migration

Akzeptanzkriterien:
  - Migration creates all 3 tables
  - quality_findings has index on (job_id, check_id)
  - analysis_profiles.asset_hints accepts NULL (ADR-005)
  - Foreign keys to control.jobs where specified

Einschränkungen:
  - No business logic
  - No data insertion

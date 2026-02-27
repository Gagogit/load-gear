# Task 002r: Review — Schema Integrity

Lade:
  `/docs/architecture/overview.md`
  `/docs/architecture/decisions.md`
  `/STATUS.md`

Ziel:
  Verify that all database schemas (control, data, analysis) are consistent
  with the architecture and don't create forward-blockers.

Akzeptanzkriterien:
  - No contradictions between schema definitions and architecture overview
  - All foreign keys reference existing tables
  - Job status enum matches ADR-003 state machine exactly
  - v2 ownership is clear: only analysis tables reference analysis_run_id on meter_reads
  - TimescaleDB hypertable chunk sizes are reasonable
  - All decisions in STATUS.md are justified and traceable
  - No forward-blockers for Phase 2 (ingest pipeline)

Bei Befund:
  Create fix-task and insert before task-004 in backlog.md.

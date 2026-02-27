# Task 006: Phase 1 Integration Test

Lade:
  `/docs/architecture/overview.md`
  `/docs/references/api-endpoints.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  End-to-end integration test proving Phase 1 components work together:
  create job → upload file → link file to job → verify full DB state.

Schritte:
  1. Create tests/integration/test_phase1.py
  2. Test scenario:
     a. POST /api/v1/jobs with valid payload → get job_id, status=pending
     b. POST /api/v1/files/upload with sample CSV → get file_id, sha256
     c. GET /api/v1/jobs/{job_id} → verify status and payload
     d. GET /api/v1/files/{file_id} → verify metadata matches upload
     e. GET /api/v1/files/{file_id}/download → verify content matches original
     f. DELETE /api/v1/jobs/{job_id} → verify deletion
  3. Create tests/fixtures/sample_lastgang.csv — small sample meter reading file
  4. Ensure test can run with test database (SQLite for CI or PostgreSQL)

Akzeptanzkriterien:
  - Full scenario runs without errors
  - All HTTP status codes are correct (201, 200, 404 after delete)
  - Database state is consistent at each step
  - Sample CSV file is realistic (15-min intervals, German format)
  - Test cleans up after itself

Einschränkungen:
  - No ingest/parsing logic — just raw file storage
  - This is the final task before Phase 1 approval

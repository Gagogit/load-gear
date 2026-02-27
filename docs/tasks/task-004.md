# Task 004: Job State Machine & API Endpoints

Lade:
  `/docs/architecture/decisions.md`
  `/docs/references/api-endpoints.md`
  `/docs/schema/control.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  Working job CRUD endpoints with state machine validation.
  POST /jobs creates a job, GET returns status, DELETE cancels.

Schritte:
  1. Create src/load_gear/models/schemas.py — Pydantic request/response models:
     - JobCreateRequest (meter_id, company, plz, horizon, tasks[], scenarios{})
     - JobResponse (id, status, created_at, _links)
     - JobListResponse
  2. Create src/load_gear/repositories/job_repo.py — async CRUD for jobs
  3. Create src/load_gear/services/job_service.py — state machine transitions:
     - validate_transition(current_status, new_status) → bool
     - create_job(payload) → Job
     - advance_job(job_id, new_status) → Job
  4. Create src/load_gear/api/routes/jobs.py — endpoints:
     - POST /api/v1/jobs
     - GET /api/v1/jobs (with filters)
     - GET /api/v1/jobs/{job_id}
     - DELETE /api/v1/jobs/{job_id}
  5. Register router in app.py
  6. Write unit tests for state machine transitions
  7. Write integration test: create job → get job → verify status=pending

Akzeptanzkriterien:
  - POST /jobs with valid payload returns 201 + job_id
  - POST /jobs with missing required fields returns 422
  - GET /jobs/{id} returns full job with status
  - DELETE /jobs/{id} on pending job returns 200
  - State machine rejects invalid transitions (e.g., pending → done)
  - All tests pass

Einschränkungen:
  - No ingest/QA/analysis logic — just the job shell + state machine
  - tasks[] is stored but not acted on yet

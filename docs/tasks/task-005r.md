# Task 005r: Review — API & State Machine Integration

Lade:
  `/docs/architecture/overview.md`
  `/docs/architecture/decisions.md`
  `/STATUS.md`

Ziel:
  Verify that the job API, file upload, and state machine work together correctly
  and match the architecture spec.

Akzeptanzkriterien:
  - POST /jobs → GET /jobs/{id} returns consistent data
  - File upload stores to correct path, SHA-256 matches
  - State machine transitions follow ADR-003 exactly
  - No invalid state transitions possible through the API
  - Error responses follow consistent format
  - All STATUS.md decisions from Phase 1 are coherent

Bei Befund:
  Create fix-task and insert before task-006 in backlog.md.

# Coding Guidelines
Schicht: B
Letzte Aktualisierung: 2026-02-27

## Language & Runtime
- Python 3.12+ — use modern syntax (match/case, type unions with |)
- Async-first: all DB and API operations use async/await
- NO PANDAS — use Polars (Lazy API) for all data transformations

## Type Hints
- Full type hints on every function signature
- No `Any` type — use specific types or generics
- Use `from __future__ import annotations` in every module
- Pydantic models for all API request/response schemas

## Project Structure (Controller → Service → Repository)
- **Controllers** (api/routes/): HTTP concerns only — validate input, call service, return response
- **Services** (services/): Business logic — orchestration, computation, no DB knowledge
- **Repositories** (repositories/): Database access only — SQLAlchemy queries, no business logic
- Services never import from other services directly — use interfaces/protocols
- Repositories never call other repositories

## Naming
- Files: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Database columns: `snake_case` (matching Python)

## Imports
Order: stdlib → third-party → local, separated by blank lines.
Use absolute imports from package root: `from load_gear.services.qa import QAService`

## Error Handling
- Service layer raises domain exceptions (e.g., `JobNotFoundError`, `ParseError`)
- Controller layer catches and maps to HTTP status codes
- Never catch bare `Exception` — catch specific types
- Always log errors with context (job_id, meter_id)

## Database
- SQLAlchemy 2.0 async with psycopg3
- Alembic for migrations
- Every schema change = new migration file
- Use parameterized queries — never string-format SQL

## Testing
- pytest + pytest-asyncio
- Unit tests per service method
- Integration test per phase boundary (tests the contract between phases)
- Test files mirror source: `tests/services/test_qa.py` for `services/qa/`
- Use factories for test data, not fixtures with side effects

## Commits
- Imperative mood: "Add QA check for interval completeness"
- Reference task ID: "task-003: Implement reader profile detection"
- One logical change per commit

## Data Lineage
- Every `meter_reads` row has `job_id` + `source_file_id`
- Every v2 row has `analysis_run_id`
- Every forecast has `data_snapshot_id` (reproducibility hash)

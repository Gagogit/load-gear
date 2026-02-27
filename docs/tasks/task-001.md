# Task 001: Project Setup

Lade:
  `/docs/architecture/overview.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  Functional Python project with FastAPI app, database connection, and all
  package __init__.py files. The app must start and respond to /api/v1/admin/health.

Schritte:
  1. Update pyproject.toml for load-gear (name, dependencies, scripts)
  2. Create src/load_gear/__init__.py and all sub-package __init__.py files
  3. Create src/load_gear/core/config.py (YAML config loader, env vars)
  4. Create src/load_gear/core/database.py (async SQLAlchemy engine + session)
  5. Create src/load_gear/api/app.py (FastAPI app with lifespan, CORS, router includes)
  6. Create src/load_gear/api/routes/admin.py (GET /api/v1/admin/health endpoint)
  7. Create src/load_gear/__main__.py (uvicorn entry point)
  8. Create .gitignore
  9. Verify: `python -m load_gear` starts and GET /health returns 200

Akzeptanzkriterien:
  - `pip install -e .` succeeds
  - `python -m load_gear` starts FastAPI on port 8000
  - GET /api/v1/admin/health returns {"status": "ok"}
  - All imports resolve without errors
  - Database engine connects (or fails gracefully if no PostgreSQL)

Einschränkungen:
  - No business logic in this task
  - No database migrations yet (comes in task-002)
  - PostgreSQL connection may fail if DB not running — that's OK for this task

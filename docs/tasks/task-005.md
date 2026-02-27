# Task 005: File Upload & Storage

Lade:
  `/docs/schema/control.md`
  `/docs/modules/ingest.md`
  `/docs/references/api-endpoints.md`
  `/docs/CODING-GUIDELINES.md`

Ziel:
  File upload endpoint that stores original files, computes SHA-256,
  and creates file metadata in control.files.

Schritte:
  1. Create src/load_gear/core/storage.py — abstract file storage:
     - StorageBackend protocol with save(path, data) and get(path) methods
     - LocalStorageBackend (stores to local filesystem, simulates GCS for dev)
     - Future: GCSStorageBackend
  2. Create src/load_gear/repositories/file_repo.py — async CRUD for files
  3. Create src/load_gear/api/routes/files.py — endpoints:
     - POST /api/v1/files/upload (multipart/form-data)
     - GET /api/v1/files/{file_id} (metadata)
     - GET /api/v1/files/{file_id}/download (stream file)
  4. File upload logic:
     - Compute SHA-256 of uploaded file
     - Check for duplicate (same SHA-256) → return existing file_id
     - Store original in storage backend under raw/{year}/{file_id}.{ext}
     - Create control.files row with metadata
  5. Register router in app.py
  6. Write test: upload CSV → verify metadata → download and compare

Akzeptanzkriterien:
  - POST /files/upload with CSV returns 201 + file_id + sha256
  - Duplicate upload (same SHA-256) returns existing file_id (idempotent)
  - GET /files/{id} returns metadata (size, hash, name, mime_type)
  - GET /files/{id}/download returns the original file content
  - Files are stored in raw/ directory structure
  - Test passes with sample CSV file

Einschränkungen:
  - No reader profile detection yet (comes in Phase 2)
  - Local filesystem storage for v0.1 (GCS adapter later)
  - No job_id linking yet (file can exist independently)

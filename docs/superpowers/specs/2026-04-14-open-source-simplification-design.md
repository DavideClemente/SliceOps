# SliceOps Open-Source Simplification

**Date:** 2026-04-14
**Goal:** Strip auth, billing, and user management from SliceOps. Keep the core 3D print slicing API as a clean open-source project.

## Context

SliceOps wraps PrusaSlicer and BambuStudio behind a REST API. The current codebase includes GitHub OAuth, JWT auth, PostgreSQL user storage, API key management, plan-based billing/rate-limiting, and admin endpoints. None of this is needed for an open-source release — the value is the slicing logic.

## What Stays

### Core Slicing API
- `POST /api/v1/slice` — upload STL (multipart or URL), get slicing results
- `GET /api/v1/jobs/{job_id}` — poll async job status
- `GET /api/v1/jobs/{job_id}/download` — download G-code / 3MF output
- `GET /api/v1/health` — health check

### Slicer Services
- `PrusaSlicer` — CLI subprocess, G-code parsing
- `BambuStudio` — CLI subprocess, 3MF extraction, G-code parsing
- `BaseSlicer` abstract class and shared types (`SliceParams`, `SliceResult`)

### Async Job Processing
- Celery + Redis broker/backend
- `run_slice_job` task for large files (>10MB threshold)
- `sweep_expired_files` periodic task via Celery Beat (every 5 minutes)
- Sync path for small files remains unchanged

### Temp Storage
- Job files in `/tmp/sliceops/` with per-job directories
- 15-minute TTL, automatic cleanup via sweep task

### IP-Based Rate Limiting
- Redis-backed, per-IP, per-minute window
- Single configurable limit via `SLICEOPS_RATE_LIMIT` env var (default: 10 req/min)
- No plan tiers, no monthly quotas
- Returns standard `X-RateLimit-*` response headers
- 429 Too Many Requests when exceeded

### Observability
- Prometheus metrics via `prometheus-fastapi-instrumentator`
- Request ID middleware

### Docker Compose
- Redis 7-alpine
- API server (FastAPI + Uvicorn)
- Celery worker
- Celery Beat scheduler
- No PostgreSQL

## What Gets Removed

### Entire `app/auth/` Directory
- `oauth.py` — GitHub OAuth flow
- `jwt.py` — JWT token creation/validation
- `service.py` — API key lifecycle management in Redis
- `dependencies.py` — `get_api_key`, `require_api_key` FastAPI dependencies
- `models.py` — `ApiKeyData` and related Pydantic models

### Entire `app/db/` Directory
- `engine.py` — SQLAlchemy async engine/session
- `models.py` — `User` and `ApiKey` ORM models

### Entire `alembic/` Directory
- `env.py`, `versions/001_create_users_and_api_keys.py`
- `alembic.ini` config file

### Route Files
- `app/api/auth_routes.py` — `/auth/github`, `/auth/callback`, `/auth/refresh`
- `app/api/account_routes.py` — `/account/keys` CRUD
- `app/api/admin_routes.py` — `/api/v1/admin/keys` management

### CLI
- `app/cli.py` — Typer-based key management commands

### Config
- `config/plans.yaml` (already deleted)
- All auth/db/OAuth settings from `app/config.py`

### Tests
- `test_auth_routes.py`, `test_account_routes.py`, `test_jwt.py`, `test_oauth.py`
- `test_key_validation.py`, `test_rate_limit.py` (rewrite for IP-based)
- Auth-related fixtures from `conftest.py`

## What Changes

### `app/config.py` (Settings)
Remove: `database_url`, `github_client_id`, `github_client_secret`, `jwt_secret`, `jwt_algorithm`, `access_token_expire_minutes`, `refresh_token_expire_days`, `base_url`, `admin_api_key`, `auth_enabled`, `plans_file`

Add: `rate_limit` (int, default 10 — requests per minute per IP)

Keep: `redis_url`, `prusa_slicer_path`, `bambu_studio_path`, `slicer_timeout_seconds`, `temp_dir`, `celery_broker_url`, `celery_result_backend`

### `app/api/routes.py`
- Remove `get_api_key` / `require_rate_limit` dependencies from endpoints
- Remove file size check against plan limits (keep a global configurable max if desired)
- Remove usage counter increment after successful slices
- Remove `api_key` from job store entries
- Add IP-based rate limit dependency

### `app/rate_limit/`
- Rewrite to use client IP instead of API key
- Single limit (no plan tiers)
- Remove monthly quota logic
- `app/rate_limit/dependencies.py` — new `require_rate_limit` that extracts IP from request

### `app/store/job_store.py`
- Remove `api_key` field from job data

### `app/main.py`
- Remove auth/account/admin router includes
- Remove database startup/shutdown lifecycle hooks
- Remove plan loading

### `app/worker/tasks.py`
- Remove any auth service or API key references

### `docker-compose.yml`
- Remove PostgreSQL service and its volume

### `pyproject.toml`
Remove dependencies: `sqlalchemy[asyncio]`, `asyncpg`, `alembic`, `pyjwt`, `httpx-oauth`, `typer`

### Tests
- Remove all auth/account/admin/JWT/OAuth test files
- Update `conftest.py` — remove auth fixtures, add IP-based rate limit fixtures
- Update `test_routes.py` — remove auth mocking from slice/job/download tests
- Keep and update: `test_prusa_slicer.py`, `test_bambu_studio.py`, `test_job_store.py`, `test_temp_storage.py`, `test_tasks.py`, `test_request_id.py`, `test_models.py`, `test_config.py`

## Dependencies (After)

### Runtime
- fastapi >=0.115
- uvicorn >=0.30
- redis >=5.0
- celery[redis] >=5.4
- pydantic >=2.9
- pydantic-settings >=2.6
- httpx >=0.27
- prometheus-fastapi-instrumentator >=7.0
- pyyaml >=6.0

### Dev
- pytest
- pytest-asyncio
- httpx (test client)

## File Structure (After)

```
app/
  __init__.py
  main.py
  config.py
  models.py              # request/response Pydantic models
  api/
    __init__.py
    routes.py             # /api/v1/slice, /jobs, /health
  services/
    __init__.py
    slicer.py             # BaseSlicer, SliceParams, SliceResult
    prusa_slicer.py
    bambu_studio.py
  storage/
    __init__.py
    temp_storage.py
  store/
    __init__.py
    job_store.py
  rate_limit/
    __init__.py
    service.py
    dependencies.py
  worker/
    __init__.py
    celery_app.py
    tasks.py
  middleware/
    __init__.py
    request_id.py
tests/
  conftest.py
  test_routes.py
  test_prusa_slicer.py
  test_bambu_studio.py
  test_job_store.py
  test_temp_storage.py
  test_tasks.py
  test_request_id.py
  test_models.py
  test_config.py
docker-compose.yml
pyproject.toml
.env.example
```

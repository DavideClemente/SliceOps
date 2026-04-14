# Open-Source Simplification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Strip all auth, billing, user management, and PostgreSQL from SliceOps, keeping the core 3D slicing API with IP-based rate limiting.

**Architecture:** FastAPI API backed by Redis (job store, rate limiting, Celery broker). No database. No auth. Rate limiting is IP-based with a single configurable limit. Async jobs via Celery for large files.

**Tech Stack:** FastAPI, Redis, Celery, Pydantic, httpx, Prometheus

---

## File Structure (After)

```
app/
  __init__.py
  main.py                          # MODIFY — remove auth/db imports and routers
  config.py                        # MODIFY — remove auth/db/plan settings, add rate_limit
  models/
    request.py                     # KEEP as-is
    response.py                    # KEEP as-is
  api/
    __init__.py                    # KEEP
    routes.py                      # MODIFY — remove auth deps, add IP rate limit
    dependencies.py                # KEEP as-is
  services/
    __init__.py                    # KEEP
    slicer.py                      # KEEP as-is
    prusa_slicer.py                # KEEP as-is
    bambu_studio.py                # KEEP as-is
  storage/
    __init__.py                    # KEEP
    temp_storage.py                # KEEP as-is
  store/
    __init__.py                    # KEEP
    job_store.py                   # KEEP as-is
  rate_limit/
    __init__.py                    # KEEP
    service.py                     # REWRITE — IP-based, single limit
    dependencies.py                # REWRITE — extract IP, no auth
  worker/
    __init__.py                    # KEEP
    celery_app.py                  # KEEP as-is
    tasks.py                       # KEEP as-is
  middleware/
    __init__.py                    # KEEP
    request_id.py                  # KEEP as-is
    logging_config.py              # KEEP as-is

DELETE:
  app/auth/                        # entire directory
  app/db/                          # entire directory
  app/cli.py
  app/api/auth_routes.py
  app/api/account_routes.py
  app/api/admin_routes.py
  alembic/                         # entire directory
  alembic.ini
  config/                          # entire directory (plans.yaml already deleted)
  tests/test_auth_routes.py
  tests/test_account_routes.py
  tests/test_jwt.py
  tests/test_oauth.py
  tests/test_key_validation.py
  tests/test_auth.py
  tests/test_rate_limit.py         # DELETE old, will recreate
  tests/test_config_new.py
```

---

### Task 1: Delete Auth, DB, and Billing Modules

**Files:**
- Delete: `app/auth/` (entire directory)
- Delete: `app/db/` (entire directory)
- Delete: `app/cli.py`
- Delete: `app/api/auth_routes.py`
- Delete: `app/api/account_routes.py`
- Delete: `app/api/admin_routes.py`
- Delete: `alembic/` (entire directory)
- Delete: `alembic.ini`
- Delete: `config/` (entire directory)

- [ ] **Step 1: Delete auth directory**

```bash
rm -rf app/auth/
```

- [ ] **Step 2: Delete db directory**

```bash
rm -rf app/db/
```

- [ ] **Step 3: Delete CLI module**

```bash
rm app/cli.py
```

- [ ] **Step 4: Delete auth/account/admin route files**

```bash
rm app/api/auth_routes.py app/api/account_routes.py app/api/admin_routes.py
```

- [ ] **Step 5: Delete Alembic directory and config**

```bash
rm -rf alembic/ alembic.ini
```

- [ ] **Step 6: Delete config directory**

```bash
rm -rf config/
```

- [ ] **Step 7: Delete obsolete test files**

```bash
rm tests/test_auth_routes.py tests/test_account_routes.py tests/test_jwt.py tests/test_oauth.py tests/test_key_validation.py tests/test_auth.py tests/test_rate_limit.py tests/test_config_new.py
```

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor: delete auth, db, billing, and CLI modules"
```

---

### Task 2: Simplify Config

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing test for simplified config**

Replace `tests/test_config.py` entirely:

```python
from app.config import Settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("SLICEOPS_PRUSA_SLICER_PATH", raising=False)
    settings = Settings(_env_file=None)
    assert settings.sync_threshold_mb == 10
    assert settings.temp_dir == "/tmp/sliceops"
    assert settings.gcode_ttl_minutes == 15
    assert settings.slicer_timeout_seconds == 300
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.prusa_slicer_path == "prusa-slicer"
    assert settings.rate_limit == 10
    assert settings.max_file_size_mb == 100


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SLICEOPS_SYNC_THRESHOLD_MB", "25")
    monkeypatch.setenv("SLICEOPS_TEMP_DIR", "/custom/tmp")
    monkeypatch.setenv("SLICEOPS_RATE_LIMIT", "30")
    monkeypatch.setenv("SLICEOPS_MAX_FILE_SIZE_MB", "50")
    settings = Settings()
    assert settings.sync_threshold_mb == 25
    assert settings.temp_dir == "/custom/tmp"
    assert settings.rate_limit == 30
    assert settings.max_file_size_mb == 50


def test_no_auth_or_db_fields():
    """Config should not have auth, db, or billing fields."""
    settings = Settings()
    assert not hasattr(settings, "database_url")
    assert not hasattr(settings, "github_client_id")
    assert not hasattr(settings, "jwt_secret")
    assert not hasattr(settings, "admin_api_key")
    assert not hasattr(settings, "plans_file")
    assert not hasattr(settings, "auth_enabled")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — `Settings` still has old fields, missing `rate_limit` and `max_file_size_mb`.

- [ ] **Step 3: Rewrite config**

Replace `app/config.py` entirely:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SLICEOPS_", "env_file": ".env"}

    # Slicers
    prusa_slicer_path: str = "prusa-slicer"
    bambu_studio_path: str = "bambu-studio"
    slicer_timeout_seconds: int = 300

    # Storage
    temp_dir: str = "/tmp/sliceops"
    gcode_ttl_minutes: int = 15
    sync_threshold_mb: int = 10
    max_file_size_mb: int = 100

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Job store
    job_ttl_seconds: int = 3600

    # Rate limiting (requests per minute per IP)
    rate_limit: int = 10

    # Logging + CORS
    cors_origins: list[str] = ["*"]
    log_level: str = "INFO"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "refactor: simplify config to remove auth/db/billing settings"
```

---

### Task 3: Rewrite Rate Limiting to IP-Based

**Files:**
- Rewrite: `app/rate_limit/service.py`
- Rewrite: `app/rate_limit/dependencies.py`
- Create: `tests/test_rate_limit.py`

- [ ] **Step 1: Write failing test for IP-based rate limit service**

Replace `tests/test_rate_limit.py`:

```python
import pytest
from unittest.mock import AsyncMock

from app.rate_limit.service import RateLimitService


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def service(mock_redis):
    return RateLimitService(redis_client=mock_redis, requests_per_minute=10)


class TestRateLimitService:
    async def test_under_limit_allowed(self, service, mock_redis):
        mock_redis.get.return_value = "5"
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is True
        assert limit == 10
        assert remaining == 4

    async def test_at_limit_blocked(self, service, mock_redis):
        mock_redis.get.return_value = "10"
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is False
        assert remaining == 0

    async def test_no_previous_requests(self, service, mock_redis):
        mock_redis.get.return_value = None
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is True
        assert remaining == 9

    async def test_increment(self, service, mock_redis):
        await service.increment("192.168.1.1")
        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: FAIL — `RateLimitService` has old signature.

- [ ] **Step 3: Rewrite rate limit service**

Replace `app/rate_limit/service.py`:

```python
from datetime import datetime, timezone

from redis.asyncio import Redis


class RateLimitService:
    def __init__(self, redis_client: Redis, requests_per_minute: int = 10) -> None:
        self._redis = redis_client
        self._limit = requests_per_minute

    async def check(self, client_ip: str) -> tuple[bool, int, int, int]:
        """Returns (allowed, limit, remaining, reset_seconds)."""
        now = datetime.now(timezone.utc)
        key = f"sliceops:ratelimit:{client_ip}:{now.strftime('%Y%m%d%H%M')}"

        current = await self._redis.get(key)
        count = int(current) if current else 0

        remaining = max(0, self._limit - count)
        reset_seconds = 60 - now.second

        if count >= self._limit:
            return False, self._limit, 0, reset_seconds

        return True, self._limit, remaining - 1, reset_seconds

    async def increment(self, client_ip: str) -> None:
        now = datetime.now(timezone.utc)
        key = f"sliceops:ratelimit:{client_ip}:{now.strftime('%Y%m%d%H%M')}"
        await self._redis.incr(key)
        await self._redis.expire(key, 120)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: PASS

- [ ] **Step 5: Write failing test for rate limit dependency**

Add to `tests/test_rate_limit.py`:

```python
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.rate_limit.dependencies import require_rate_limit


class TestRateLimitDependency:
    async def test_allowed_sets_headers(self):
        mock_service = AsyncMock()
        mock_service.check.return_value = (True, 10, 9, 55)
        mock_service.increment.return_value = None

        request = MagicMock()
        request.app.state.rate_limit_service = mock_service
        request.client.host = "1.2.3.4"
        request.state = MagicMock()

        await require_rate_limit(request)

        mock_service.check.assert_called_once_with("1.2.3.4")
        mock_service.increment.assert_called_once_with("1.2.3.4")
        assert request.state.rate_limit_headers == {
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": "9",
            "X-RateLimit-Reset": "55",
        }

    async def test_blocked_raises_429(self):
        mock_service = AsyncMock()
        mock_service.check.return_value = (False, 10, 0, 45)

        request = MagicMock()
        request.app.state.rate_limit_service = mock_service
        request.client.host = "1.2.3.4"

        with pytest.raises(HTTPException) as exc_info:
            await require_rate_limit(request)
        assert exc_info.value.status_code == 429
```

- [ ] **Step 6: Run test to verify it fails**

```bash
pytest tests/test_rate_limit.py::TestRateLimitDependency -v
```

Expected: FAIL — `require_rate_limit` still takes `api_key` parameter.

- [ ] **Step 7: Rewrite rate limit dependency**

Replace `app/rate_limit/dependencies.py`:

```python
from fastapi import Request, HTTPException


async def require_rate_limit(request: Request) -> None:
    rate_limit_service = request.app.state.rate_limit_service
    client_ip = request.client.host

    allowed, limit, remaining, reset_seconds = await rate_limit_service.check(client_ip)

    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Reset": str(reset_seconds),
    }

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(reset_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            },
        )

    await rate_limit_service.increment(client_ip)
```

- [ ] **Step 8: Run test to verify it passes**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add app/rate_limit/service.py app/rate_limit/dependencies.py tests/test_rate_limit.py
git commit -m "refactor: rewrite rate limiting to IP-based"
```

---

### Task 4: Update Routes (Remove Auth, Add IP Rate Limiting)

**Files:**
- Modify: `app/api/routes.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Rewrite routes to remove auth dependencies**

Replace `app/api/routes.py`:

```python
import logging
import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask
from typing import Optional

from app.api.dependencies import ingest_file
from app.config import Settings
from app.models.request import SliceRequest, SUPPORTED_SLICERS
from app.models.response import (
    SyncSliceResponse,
    AsyncSliceResponse,
    JobStatusResponse,
    SliceResult as SliceResultResponse,
)
from app.rate_limit.dependencies import require_rate_limit
from app.worker.tasks import run_slice_job

logger = logging.getLogger("sliceops.routes")

router = APIRouter(prefix="/api/v1")
settings = Settings()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post("/slice")
async def slice_model(
    request: Request,
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
    layer_height: float = Form(0.2),
    infill_percent: int = Form(20),
    print_speed: Optional[float] = Form(None),
    support_material: bool = Form(False),
    filament_type: str = Form("PLA"),
    filament_cost: float = Form(20.0),
    nozzle_size: float = Form(0.4),
    slicer: str = Form("prusa-slicer"),
):
    await require_rate_limit(request)

    try:
        content, filename = await ingest_file(request, file, file_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        validated = SliceRequest(
            layer_height=layer_height,
            infill_percent=infill_percent,
            print_speed=print_speed,
            support_material=support_material,
            filament_type=filament_type,
            filament_cost=filament_cost,
            nozzle_size=nozzle_size,
            slicer=slicer,
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if slicer not in SUPPORTED_SLICERS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported slicer: {slicer}. Supported: {', '.join(SUPPORTED_SLICERS)}",
        )

    # Global file size limit
    app_settings: Settings = request.app.state.settings
    max_size = app_settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {app_settings.max_file_size_mb}MB",
        )

    job_id = str(uuid.uuid4())
    storage = request.app.state.storage
    storage.create_job_dir(job_id)
    storage.save_file(job_id, "model.stl", content)
    job_store = request.app.state.job_store

    logger.info("Slice requested", extra={"job_id": job_id, "slicer": slicer})

    params_dict = {
        "layer_height": layer_height,
        "infill_percent": infill_percent,
        "print_speed": print_speed,
        "support_material": support_material,
        "filament_type": filament_type,
        "filament_cost": filament_cost,
        "nozzle_size": nozzle_size,
        "slicer": slicer,
    }

    file_size_mb = len(content) / (1024 * 1024)

    if file_size_mb < settings.sync_threshold_mb:
        slicers = request.app.state.slicers
        slicer_service = slicers[slicer]
        from app.services.slicer import SliceParams

        slicer_params = SliceParams(
            layer_height=layer_height,
            infill_percent=infill_percent,
            print_speed=print_speed,
            support_material=support_material,
            filament_type=filament_type,
            nozzle_size=nozzle_size,
        )
        job_dir = storage.get_job_dir(job_id)
        stl_path = storage.get_file_path(job_id, "model.stl") or f"{job_dir}/model.stl"

        try:
            result = await slicer_service.slice(stl_path, job_dir, slicer_params)
        except TimeoutError:
            storage.cleanup_job(job_id)
            raise HTTPException(status_code=504, detail="Slicer timed out")
        except RuntimeError as e:
            storage.cleanup_job(job_id)
            logger.error("Slice failed", extra={"job_id": job_id, "error": str(e)})
            raise HTTPException(status_code=500, detail=str(e))

        storage.delete_file(job_id, "model.stl")

        cost = result.compute_cost(filament_cost)
        download_url = f"/api/v1/jobs/{job_id}/download"

        response_result = SliceResultResponse(
            estimated_time_seconds=result.estimated_time_seconds,
            estimated_time_human=result.human_time,
            filament_used_grams=result.filament_used_grams,
            filament_used_meters=result.filament_used_meters,
            layer_count=result.layer_count,
            estimated_cost=cost,
            gcode_download_url=download_url,
        )

        await job_store.set(job_id, {
            "status": "completed",
            "result": response_result.model_dump(),
            "output_filename": result.output_filename,
        })

        logger.info("Slice completed", extra={"job_id": job_id})
        return SyncSliceResponse(job_id=job_id, result=response_result)

    else:
        task = run_slice_job.delay(job_id=job_id, params_dict=params_dict)

        await job_store.set(job_id, {
            "status": "pending",
            "celery_task_id": task.id,
        })

        response = AsyncSliceResponse(
            job_id=job_id,
            poll_url=f"/api/v1/jobs/{job_id}",
        )
        return JSONResponse(content=response.model_dump(), status_code=202)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request):
    job_store = request.app.state.job_store
    job = await job_store.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    status = job["status"]

    if status in ("pending", "processing") and "celery_task_id" in job:
        from celery.result import AsyncResult
        from app.worker.celery_app import celery_app

        task_result = AsyncResult(job["celery_task_id"], app=celery_app)
        if task_result.ready():
            if task_result.successful():
                result_data = task_result.result
                result_data["gcode_download_url"] = f"/api/v1/jobs/{job_id}/download"
                await job_store.update(job_id, status="completed", result=result_data)
                status = "completed"
                job["result"] = result_data
            else:
                await job_store.update(job_id, status="failed")
                status = "failed"
        elif task_result.state == "STARTED":
            status = "processing"

    result = job.get("result")
    return JobStatusResponse(job_id=job_id, status=status, result=result)


@router.get("/jobs/{job_id}/download")
async def download_output(job_id: str, request: Request):
    job_store = request.app.state.job_store
    job = await job_store.get(job_id)

    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = request.app.state.storage
    output_filename = job.get("output_filename", "output.gcode")

    output_path = storage.get_file_path(job_id, output_filename)
    if output_path is None:
        raise HTTPException(status_code=404, detail="Output file not found")

    if output_filename.endswith(".3mf"):
        media_type = "application/vnd.ms-package.3dmanufacturing-3dmodel+xml"
        download_name = f"{job_id}.gcode.3mf"
    else:
        media_type = "application/octet-stream"
        download_name = f"{job_id}.gcode"

    cleanup = BackgroundTask(storage.cleanup_job, job_id)

    return FileResponse(
        output_path,
        media_type=media_type,
        filename=download_name,
        background=cleanup,
    )
```

- [ ] **Step 2: Rewrite route tests**

Replace `tests/test_routes.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestHealthEndpoint:
    async def test_health(self, client):
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestSliceEndpointSync:
    async def test_slice_sync_with_upload(self, client, sample_stl, tmp_path, mock_storage):
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)
        mock_storage.get_job_dir.return_value = str(job_dir)

        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", sample_stl, "application/octet-stream")},
            data={"layer_height": "0.2", "infill_percent": "20", "filament_cost": "20.0"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["mode"] == "sync"
        assert body["status"] == "completed"
        assert body["result"]["estimated_time_seconds"] == 3720
        assert body["result"]["estimated_cost"] == 0.57

    async def test_slice_requires_file_or_url(self, client):
        resp = await client.post(
            "/api/v1/slice",
            data={"layer_height": "0.2"},
        )
        assert resp.status_code == 400


class TestSliceEndpointAsync:
    async def test_large_file_returns_async(self, client, mock_storage, tmp_path):
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)

        large_content = b"x" * (11 * 1024 * 1024)

        with patch("app.api.routes.run_slice_job") as mock_task:
            mock_async_result = MagicMock()
            mock_async_result.id = "celery-task-id"
            mock_task.delay.return_value = mock_async_result

            resp = await client.post(
                "/api/v1/slice",
                files={"file": ("big.stl", large_content, "application/octet-stream")},
            )

        assert resp.status_code == 202
        body = resp.json()
        assert body["mode"] == "async"
        assert body["status"] == "accepted"
        assert "job_id" in body
        assert "poll_url" in body


class TestJobStatusEndpoint:
    async def test_job_not_found(self, client, mock_job_store):
        mock_job_store.get.return_value = None
        resp = await client.get("/api/v1/jobs/nonexistent")
        assert resp.status_code == 404

    async def test_job_completed(self, client, mock_job_store):
        mock_job_store.get.return_value = {
            "status": "completed",
            "result": {
                "estimated_time_seconds": 100,
                "estimated_time_human": "1m 40s",
                "filament_used_grams": 5.0,
                "filament_used_meters": 1.7,
                "layer_count": 50,
                "estimated_cost": 0.10,
                "gcode_download_url": "/api/v1/jobs/job-1/gcode",
            },
        }
        resp = await client.get("/api/v1/jobs/job-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"


class TestOutputDownload:
    async def test_download_not_found(self, client, mock_job_store):
        mock_job_store.get.return_value = None
        resp = await client.get("/api/v1/jobs/nonexistent/download")
        assert resp.status_code == 404

    async def test_download_gcode(self, client, mock_job_store, mock_storage, tmp_path):
        job_dir = tmp_path / "job-1"
        job_dir.mkdir()
        gcode_file = job_dir / "output.gcode"
        gcode_file.write_text("G28\nG1 X0 Y0\n")
        mock_storage.get_file_path.return_value = str(gcode_file)
        mock_storage.get_job_dir.return_value = str(job_dir)

        mock_job_store.get.return_value = {"status": "completed", "output_filename": "output.gcode"}

        resp = await client.get("/api/v1/jobs/job-1/download")
        assert resp.status_code == 200
        assert "G28" in resp.text

    async def test_download_3mf(self, client, mock_job_store, mock_storage, tmp_path):
        import zipfile
        job_dir = tmp_path / "job-2"
        job_dir.mkdir()
        archive_path = job_dir / "output.gcode.3mf"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("plate_1.gcode", "G28\n")
        mock_storage.get_file_path.return_value = str(archive_path)

        mock_job_store.get.return_value = {"status": "completed", "output_filename": "output.gcode.3mf"}

        resp = await client.get("/api/v1/jobs/job-2/download")
        assert resp.status_code == 200


class TestFileSizeLimit:
    async def test_file_too_large_returns_413(self, client, mock_storage, tmp_path, app):
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)

        # Set max to 1MB
        app.state.settings.max_file_size_mb = 1

        large_content = b"x" * (2 * 1024 * 1024)
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("big.stl", large_content, "application/octet-stream")},
        )
        assert resp.status_code == 413


class TestParameterValidation:
    async def test_invalid_infill_returns_422(self, client):
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            data={"infill_percent": "150"},
        )
        assert resp.status_code == 422

    async def test_unsupported_slicer_returns_400(self, client):
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            data={"slicer": "unknown-slicer"},
        )
        assert resp.status_code == 400
```

- [ ] **Step 3: Run tests to verify they pass**

```bash
pytest tests/test_routes.py -v
```

Expected: FAIL — `app/main.py` still imports deleted modules. Will fix in Task 5.

- [ ] **Step 4: Commit routes and test changes**

```bash
git add app/api/routes.py tests/test_routes.py
git commit -m "refactor: remove auth from routes, add global file size limit"
```

---

### Task 5: Update Main App and Conftest

**Files:**
- Modify: `app/main.py`
- Modify: `tests/conftest.py`

- [ ] **Step 1: Rewrite main.py**

Replace `app/main.py`:

```python
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import router
from app.config import Settings
from app.middleware.logging_config import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.services.bambu_studio import BambuStudioService
from app.services.prusa_slicer import PrusaSlicerService
from app.storage.temp_storage import TempStorage
from app.store.job_store import JobStore
from app.rate_limit.service import RateLimitService


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    setup_logging(level=settings.log_level)

    app.state.settings = settings
    app.state.storage = TempStorage(base_dir=settings.temp_dir)
    app.state.slicers = {
        "prusa-slicer": PrusaSlicerService(
            executable=settings.prusa_slicer_path,
            timeout=settings.slicer_timeout_seconds,
        ),
        "bambu-studio": BambuStudioService(
            executable=settings.bambu_studio_path,
            timeout=settings.slicer_timeout_seconds,
        ),
    }

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client
    app.state.job_store = JobStore(redis_client, ttl_seconds=settings.job_ttl_seconds)
    app.state.rate_limit_service = RateLimitService(
        redis_client, requests_per_minute=settings.rate_limit
    )

    yield

    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SliceOps",
        description="3D printing time and cost estimation API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    Instrumentator().instrument(app)

    return app


app = create_app()
```

- [ ] **Step 2: Rewrite conftest.py**

Replace `tests/conftest.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.services.slicer import SliceResult
from app.config import Settings


@pytest.fixture
def mock_storage(tmp_path):
    storage = MagicMock()
    storage.create_job_dir.side_effect = lambda jid: str(tmp_path / jid)
    storage.get_job_dir.side_effect = lambda jid: str(tmp_path / jid) if (tmp_path / jid).exists() else None
    storage.save_file.side_effect = lambda jid, name, content: str(tmp_path / jid / name)
    storage.get_file_path.return_value = None
    storage.delete_file.return_value = None
    storage.cleanup_job.return_value = None
    return storage


@pytest.fixture
def mock_slicer():
    slicer = AsyncMock()
    slicer.slice.return_value = SliceResult(
        estimated_time_seconds=3720,
        filament_used_grams=28.4,
        filament_used_meters=9.5,
        layer_count=150,
    )
    return slicer


@pytest.fixture
def mock_job_store():
    store = AsyncMock()
    store.get.return_value = None
    store.set.return_value = None
    store.update.return_value = None
    return store


@pytest.fixture
def mock_rate_limit_service():
    service = AsyncMock()
    service.check.return_value = (True, 10, 9, 60)
    service.increment.return_value = None
    return service


@pytest.fixture
def app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    application = create_app()
    application.state.settings = Settings(_env_file=None)
    application.state.storage = mock_storage
    application.state.slicers = {
        "prusa-slicer": mock_slicer,
        "bambu-studio": mock_slicer,
    }
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_stl():
    return b"solid cube\n  facet normal 0 0 -1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n      vertex 1 1 0\n    endloop\n  endfacet\nendsolid cube"
```

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass. If any test file references deleted modules, it will fail and needs deletion (should have been caught in Task 1).

- [ ] **Step 4: Commit**

```bash
git add app/main.py tests/conftest.py
git commit -m "refactor: simplify main app and test fixtures"
```

---

### Task 6: Update pyproject.toml, docker-compose, and .env.example

**Files:**
- Modify: `pyproject.toml`
- Modify: `docker-compose.yml`
- Modify: `.env.example`

- [ ] **Step 1: Update pyproject.toml**

Replace `pyproject.toml`:

```toml
[project]
name = "sliceops"
version = "0.1.0"
description = "3D printing time and cost estimation API via slicer CLI"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "celery[redis]>=5.4.0",
    "redis>=5.0.0",
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "httpx>=0.27.0",
    "python-multipart>=0.0.9",
    "prometheus-fastapi-instrumentator>=7.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.27.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
markers = [
    "integration: requires slicer CLI installed",
]
```

- [ ] **Step 2: Update docker-compose.yml**

Replace `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    restart: unless-stopped
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  api:
    build: .
    restart: unless-stopped
    ports:
      - "8000:8000"
    env_file: .env
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
      - SLICEOPS_TEMP_DIR=/tmp/sliceops
      - SLICEOPS_PRUSA_SLICER_PATH=prusa-slicer
      - SLICEOPS_BAMBU_STUDIO_PATH=bambu-studio
    depends_on:
      redis:
        condition: service_healthy
    tmpfs:
      - /tmp/sliceops:size=512M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  worker:
    build: .
    restart: unless-stopped
    command: uv run celery -A app.worker.celery_app worker --loglevel=info --concurrency=2
    env_file: .env
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
      - SLICEOPS_TEMP_DIR=/tmp/sliceops
      - SLICEOPS_PRUSA_SLICER_PATH=prusa-slicer
      - SLICEOPS_BAMBU_STUDIO_PATH=bambu-studio
    depends_on:
      redis:
        condition: service_healthy
    tmpfs:
      - /tmp/sliceops:size=512M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  beat:
    build: .
    restart: unless-stopped
    command: uv run celery -A app.worker.celery_app beat --loglevel=info
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
    depends_on:
      redis:
        condition: service_healthy
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

volumes:
  redis-data:
```

- [ ] **Step 3: Update .env.example**

Replace `.env.example`:

```
# SliceOps Configuration

# Slicers
SLICEOPS_PRUSA_SLICER_PATH=prusa-slicer
SLICEOPS_BAMBU_STUDIO_PATH=bambu-studio

# Redis
SLICEOPS_REDIS_URL=redis://localhost:6379/0

# Rate limiting (requests per minute per IP)
SLICEOPS_RATE_LIMIT=10

# Max upload file size in MB
SLICEOPS_MAX_FILE_SIZE_MB=100
```

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml docker-compose.yml .env.example
git commit -m "refactor: remove Postgres from docker-compose, clean up dependencies"
```

---

### Task 7: Run Full Test Suite and Fix Any Remaining Issues

**Files:**
- Potentially any file with lingering references

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Check for any remaining imports of deleted modules**

```bash
grep -r "from app.auth" app/ tests/ || echo "Clean"
grep -r "from app.db" app/ tests/ || echo "Clean"
grep -r "from app.cli" app/ tests/ || echo "Clean"
grep -r "ApiKeyData" app/ tests/ || echo "Clean"
grep -r "auth_enabled" app/ tests/ || echo "Clean"
grep -r "database_url" app/ tests/ || echo "Clean"
grep -r "plans_file" app/ tests/ || echo "Clean"
grep -r "admin_api_key" app/ tests/ || echo "Clean"
```

Expected: All "Clean". If any references remain, fix them.

- [ ] **Step 3: Verify no stale test files reference deleted modules**

```bash
pytest tests/ --collect-only 2>&1 | grep -i error || echo "Collection clean"
```

Expected: "Collection clean"

- [ ] **Step 4: Commit any fixes**

If fixes were needed:

```bash
git add -A
git commit -m "fix: remove remaining references to deleted auth/db modules"
```

---

### Task 8: Final Verification

- [ ] **Step 1: Run full test suite one more time**

```bash
pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 2: Verify the app can start (import check)**

```bash
python -c "from app.main import create_app; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Check file structure is clean**

```bash
find app/ -name "*.py" | sort
```

Verify no auth/db/cli files remain.

- [ ] **Step 4: Final commit if needed, then done**

```bash
git log --oneline -10
```

Verify commit history is clean and tells the story of the simplification.

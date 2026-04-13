# SliceOps API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python API service that accepts STL files, slices them via OrcaSlicer CLI, and returns print time/cost estimates plus G-code.

**Architecture:** FastAPI REST API with Celery + Redis for async job processing. OrcaSlicer CLI wrapped behind a pluggable slicer interface. Aggressive temp file cleanup for STL/G-code privacy.

**Tech Stack:** Python 3.12+, FastAPI, Celery, Redis, uv, Pydantic v2, Docker, OrcaSlicer CLI

**Spec:** `docs/superpowers/specs/2026-04-14-sliceops-api-design.md`

---

## File Structure

```
sliceops/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app factory, lifespan, router inclusion
│   ├── config.py             # Pydantic Settings (env vars, defaults)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py         # POST /slice, GET /jobs/{id}, GET /jobs/{id}/gcode, GET /health
│   │   └── dependencies.py   # File ingestion dependency (upload vs URL)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── request.py        # SliceRequest Pydantic model
│   │   └── response.py       # SliceResponse, AsyncResponse, JobStatus, ErrorResponse
│   ├── services/
│   │   ├── __init__.py
│   │   ├── slicer.py         # BaseSlicer ABC + SliceParams + SliceResult dataclasses
│   │   └── orca_slicer.py    # OrcaSlicerService implementation
│   ├── worker/
│   │   ├── __init__.py
│   │   ├── celery_app.py     # Celery app instance + config
│   │   └── tasks.py          # slice_model Celery task
│   └── storage/
│       ├── __init__.py
│       └── temp_storage.py   # TempStorage: create/get/cleanup job dirs, TTL sweep
├── tests/
│   ├── __init__.py
│   ├── conftest.py           # Shared fixtures (test client, temp dirs, mock slicer)
│   ├── test_config.py
│   ├── test_models.py
│   ├── test_temp_storage.py
│   ├── test_slicer.py
│   ├── test_orca_slicer.py
│   ├── test_routes.py
│   ├── test_tasks.py
│   └── fixtures/
│       └── test_cube.stl     # Minimal ASCII STL cube (~1KB)
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

---

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Initialize git repository**

```bash
cd /Users/davide.clemente/Documents/GitHub/SliceOps
git init
```

- [ ] **Step 2: Initialize uv project**

```bash
uv init --name sliceops --python 3.12
```

- [ ] **Step 3: Replace pyproject.toml with project configuration**

Replace the generated `pyproject.toml` with:

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
    "integration: requires OrcaSlicer CLI installed",
]
```

- [ ] **Step 4: Install dependencies**

```bash
uv sync --all-extras
```

- [ ] **Step 5: Create package init files**

Create empty `app/__init__.py` and `tests/__init__.py`.

- [ ] **Step 6: Create test STL fixture**

Create `tests/fixtures/test_cube.stl` — a minimal ASCII STL cube:

```
solid cube
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 1 0 0
      vertex 1 1 0
    endloop
  endfacet
  facet normal 0 0 -1
    outer loop
      vertex 0 0 0
      vertex 1 1 0
      vertex 0 1 0
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 1
      vertex 1 1 1
      vertex 1 0 1
    endloop
  endfacet
  facet normal 0 0 1
    outer loop
      vertex 0 0 1
      vertex 0 1 1
      vertex 1 1 1
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 1 0 1
      vertex 1 0 0
    endloop
  endfacet
  facet normal 0 -1 0
    outer loop
      vertex 0 0 0
      vertex 0 0 1
      vertex 1 0 1
    endloop
  endfacet
  facet normal 1 0 0
    outer loop
      vertex 1 0 0
      vertex 1 0 1
      vertex 1 1 1
    endloop
  endfacet
  facet normal 1 0 0
    outer loop
      vertex 1 0 0
      vertex 1 1 1
      vertex 1 1 0
    endloop
  endfacet
  facet normal 0 1 0
    outer loop
      vertex 0 1 0
      vertex 1 1 0
      vertex 1 1 1
    endloop
  endfacet
  facet normal 0 1 0
    outer loop
      vertex 0 1 0
      vertex 1 1 1
      vertex 0 1 1
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 1 0
      vertex 0 1 1
    endloop
  endfacet
  facet normal -1 0 0
    outer loop
      vertex 0 0 0
      vertex 0 1 1
      vertex 0 0 1
    endloop
  endfacet
endsolid cube
```

- [ ] **Step 7: Verify setup**

```bash
uv run pytest --collect-only
```

Expected: no errors, 0 tests collected.

- [ ] **Step 8: Create .gitignore and commit**

Create `.gitignore`:
```
__pycache__/
*.pyc
.venv/
*.egg-info/
dist/
.env
/tmp/
```

```bash
git add pyproject.toml uv.lock app/__init__.py tests/__init__.py tests/fixtures/test_cube.stl .gitignore .python-version
git commit -m "feat: initialize SliceOps project with uv and dependencies"
```

---

### Task 2: Configuration

**Files:**
- Create: `app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing test for config defaults**

Create `tests/test_config.py`:

```python
from app.config import Settings


def test_default_settings():
    settings = Settings()
    assert settings.sync_threshold_mb == 10
    assert settings.temp_dir == "/tmp/sliceops"
    assert settings.gcode_ttl_minutes == 15
    assert settings.slicer_timeout_seconds == 300
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.orca_slicer_path == "orca-slicer"


def test_settings_from_env(monkeypatch):
    monkeypatch.setenv("SLICEOPS_SYNC_THRESHOLD_MB", "25")
    monkeypatch.setenv("SLICEOPS_TEMP_DIR", "/custom/tmp")
    settings = Settings()
    assert settings.sync_threshold_mb == 25
    assert settings.temp_dir == "/custom/tmp"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_config.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Implement config**

Create `app/config.py`:

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_prefix": "SLICEOPS_"}

    sync_threshold_mb: int = 10
    temp_dir: str = "/tmp/sliceops"
    gcode_ttl_minutes: int = 15
    slicer_timeout_seconds: int = 300
    redis_url: str = "redis://localhost:6379/0"
    orca_slicer_path: str = "orca-slicer"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add Settings config with env var support"
```

---

### Task 3: Pydantic Request & Response Models

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/request.py`
- Create: `app/models/response.py`
- Create: `tests/test_models.py`

- [ ] **Step 1: Write failing tests for request model**

Create `tests/test_models.py`:

```python
import pytest
from pydantic import ValidationError

from app.models.request import SliceRequest
from app.models.response import SliceResult, SyncSliceResponse, AsyncSliceResponse, JobStatusResponse


class TestSliceRequest:
    def test_defaults(self):
        req = SliceRequest()
        assert req.layer_height == 0.2
        assert req.infill_percent == 20
        assert req.print_speed is None
        assert req.support_material is False
        assert req.filament_type == "PLA"
        assert req.filament_cost == 20.0
        assert req.nozzle_size == 0.4

    def test_custom_values(self):
        req = SliceRequest(
            layer_height=0.1,
            infill_percent=80,
            print_speed=100.0,
            support_material=True,
            filament_type="PETG",
            filament_cost=25.0,
            nozzle_size=0.6,
        )
        assert req.layer_height == 0.1
        assert req.infill_percent == 80
        assert req.filament_type == "PETG"

    def test_infill_percent_validation_too_high(self):
        with pytest.raises(ValidationError):
            SliceRequest(infill_percent=101)

    def test_infill_percent_validation_negative(self):
        with pytest.raises(ValidationError):
            SliceRequest(infill_percent=-1)

    def test_layer_height_must_be_positive(self):
        with pytest.raises(ValidationError):
            SliceRequest(layer_height=0)


class TestSliceResult:
    def test_slice_result(self):
        result = SliceResult(
            estimated_time_seconds=3720,
            estimated_time_human="1h 2m",
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
            estimated_cost=0.57,
            gcode_download_url="/api/v1/jobs/abc-123/gcode",
        )
        assert result.estimated_time_seconds == 3720
        assert result.estimated_cost == 0.57


class TestSyncSliceResponse:
    def test_sync_response(self):
        result = SliceResult(
            estimated_time_seconds=100,
            estimated_time_human="1m 40s",
            filament_used_grams=5.0,
            filament_used_meters=1.7,
            layer_count=50,
            estimated_cost=0.10,
            gcode_download_url="/api/v1/jobs/abc/gcode",
        )
        resp = SyncSliceResponse(job_id="abc", result=result)
        assert resp.mode == "sync"
        assert resp.status == "completed"
        assert resp.result.estimated_time_seconds == 100


class TestAsyncSliceResponse:
    def test_async_response(self):
        resp = AsyncSliceResponse(job_id="abc-123", poll_url="/api/v1/jobs/abc-123")
        assert resp.mode == "async"
        assert resp.status == "accepted"
        assert resp.job_id == "abc-123"


class TestJobStatusResponse:
    def test_pending_job(self):
        resp = JobStatusResponse(job_id="abc", status="pending")
        assert resp.result is None

    def test_completed_job(self):
        result = SliceResult(
            estimated_time_seconds=100,
            estimated_time_human="1m 40s",
            filament_used_grams=5.0,
            filament_used_meters=1.7,
            layer_count=50,
            estimated_cost=0.10,
            gcode_download_url="/api/v1/jobs/abc/gcode",
        )
        resp = JobStatusResponse(job_id="abc", status="completed", result=result)
        assert resp.result is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_models.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement request model**

Create `app/models/__init__.py` (empty).

Create `app/models/request.py`:

```python
from pydantic import BaseModel, Field


class SliceRequest(BaseModel):
    layer_height: float = Field(default=0.2, gt=0, description="Layer height in mm")
    infill_percent: int = Field(default=20, ge=0, le=100, description="Infill percentage")
    print_speed: float | None = Field(default=None, gt=0, description="Print speed in mm/s")
    support_material: bool = Field(default=False, description="Enable support material")
    filament_type: str = Field(default="PLA", description="Filament type (PLA, PETG, ABS, TPU)")
    filament_cost: float = Field(default=20.0, ge=0, description="Filament cost per kg")
    nozzle_size: float = Field(default=0.4, gt=0, description="Nozzle diameter in mm")
```

- [ ] **Step 4: Implement response models**

Create `app/models/response.py`:

```python
from pydantic import BaseModel


class SliceResult(BaseModel):
    estimated_time_seconds: int
    estimated_time_human: str
    filament_used_grams: float
    filament_used_meters: float
    layer_count: int
    estimated_cost: float
    gcode_download_url: str


class SyncSliceResponse(BaseModel):
    mode: str = "sync"
    status: str = "completed"
    job_id: str
    result: SliceResult


class AsyncSliceResponse(BaseModel):
    mode: str = "async"
    status: str = "accepted"
    job_id: str
    poll_url: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    result: SliceResult | None = None


class ErrorResponse(BaseModel):
    error: str
    detail: str = ""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_models.py -v
```

Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add app/models/ tests/test_models.py
git commit -m "feat: add Pydantic request and response models"
```

---

### Task 4: Temp Storage Service

**Files:**
- Create: `app/storage/__init__.py`
- Create: `app/storage/temp_storage.py`
- Create: `tests/test_temp_storage.py`

- [ ] **Step 1: Write failing tests for temp storage**

Create `tests/test_temp_storage.py`:

```python
import os
import time
from pathlib import Path

from app.storage.temp_storage import TempStorage


class TestTempStorage:
    def test_create_job_dir(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        job_id = "test-job-1"
        job_dir = storage.create_job_dir(job_id)
        assert Path(job_dir).exists()
        assert Path(job_dir).name == job_id

    def test_get_job_dir(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        job_dir = storage.get_job_dir("job-1")
        assert job_dir is not None
        assert Path(job_dir).exists()

    def test_get_job_dir_nonexistent(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        assert storage.get_job_dir("nonexistent") is None

    def test_save_file(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        content = b"solid cube\nendsolid cube"
        path = storage.save_file("job-1", "model.stl", content)
        assert Path(path).exists()
        assert Path(path).read_bytes() == content

    def test_get_file_path(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        path = storage.get_file_path("job-1", "model.stl")
        assert path is not None
        assert Path(path).exists()

    def test_get_file_path_nonexistent(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        assert storage.get_file_path("job-1", "missing.stl") is None

    def test_cleanup_job(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        storage.cleanup_job("job-1")
        assert not Path(tmp_path / "job-1").exists()

    def test_cleanup_nonexistent_job_no_error(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.cleanup_job("nonexistent")  # should not raise

    def test_delete_file(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        storage.delete_file("job-1", "model.stl")
        assert storage.get_file_path("job-1", "model.stl") is None

    def test_sweep_expired_jobs(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("old-job")
        storage.save_file("old-job", "model.stl", b"data")
        # Backdate the directory mtime
        old_time = time.time() - 3600
        job_dir = tmp_path / "old-job"
        os.utime(job_dir, (old_time, old_time))

        storage.create_job_dir("new-job")
        storage.save_file("new-job", "model.stl", b"data")

        removed = storage.sweep_expired(ttl_minutes=15)
        assert "old-job" in removed
        assert not Path(tmp_path / "old-job").exists()
        assert Path(tmp_path / "new-job").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_temp_storage.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement temp storage**

Create `app/storage/__init__.py` (empty).

Create `app/storage/temp_storage.py`:

```python
import os
import shutil
import time
from pathlib import Path


class TempStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self, job_id: str) -> str:
        job_dir = self._base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return str(job_dir)

    def get_job_dir(self, job_id: str) -> str | None:
        job_dir = self._base / job_id
        if job_dir.exists():
            return str(job_dir)
        return None

    def save_file(self, job_id: str, filename: str, content: bytes) -> str:
        file_path = self._base / job_id / filename
        file_path.write_bytes(content)
        return str(file_path)

    def get_file_path(self, job_id: str, filename: str) -> str | None:
        file_path = self._base / job_id / filename
        if file_path.exists():
            return str(file_path)
        return None

    def delete_file(self, job_id: str, filename: str) -> None:
        file_path = self._base / job_id / filename
        if file_path.exists():
            file_path.unlink()

    def cleanup_job(self, job_id: str) -> None:
        job_dir = self._base / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)

    def sweep_expired(self, ttl_minutes: int) -> list[str]:
        cutoff = time.time() - (ttl_minutes * 60)
        removed: list[str] = []
        if not self._base.exists():
            return removed
        for entry in self._base.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry)
                removed.append(entry.name)
        return removed
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_temp_storage.py -v
```

Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add app/storage/ tests/test_temp_storage.py
git commit -m "feat: add TempStorage service with TTL sweep"
```

---

### Task 5: Slicer Interface & OrcaSlicer Implementation

**Files:**
- Create: `app/services/__init__.py`
- Create: `app/services/slicer.py`
- Create: `app/services/orca_slicer.py`
- Create: `tests/test_slicer.py`
- Create: `tests/test_orca_slicer.py`

- [ ] **Step 1: Write failing tests for slicer dataclasses and interface**

Create `tests/test_slicer.py`:

```python
from app.services.slicer import SliceParams, SliceResult, BaseSlicer


class TestSliceParams:
    def test_defaults(self):
        params = SliceParams()
        assert params.layer_height == 0.2
        assert params.infill_percent == 20
        assert params.print_speed is None
        assert params.support_material is False
        assert params.filament_type == "PLA"
        assert params.nozzle_size == 0.4

    def test_custom(self):
        params = SliceParams(layer_height=0.1, infill_percent=80, filament_type="PETG")
        assert params.layer_height == 0.1
        assert params.infill_percent == 80


class TestSliceResult:
    def test_creation(self):
        result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )
        assert result.estimated_time_seconds == 3720
        assert result.filament_used_grams == 28.4

    def test_human_time_hours_and_minutes(self):
        result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "1h 2m"

    def test_human_time_minutes_only(self):
        result = SliceResult(
            estimated_time_seconds=90,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "1m 30s"

    def test_human_time_seconds_only(self):
        result = SliceResult(
            estimated_time_seconds=45,
            filament_used_grams=0,
            filament_used_meters=0,
            layer_count=0,
        )
        assert result.human_time == "45s"

    def test_cost_calculation(self):
        result = SliceResult(
            estimated_time_seconds=100,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )
        # 28.4g at $20/kg = 28.4 * 20 / 1000 = 0.568 -> rounded to 0.57
        cost = result.compute_cost(filament_cost_per_kg=20.0)
        assert cost == 0.57


class TestBaseSlicerIsAbstract:
    def test_cannot_instantiate(self):
        import pytest
        with pytest.raises(TypeError):
            BaseSlicer()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_slicer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement slicer interface**

Create `app/services/__init__.py` (empty).

Create `app/services/slicer.py`:

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class SliceParams:
    layer_height: float = 0.2
    infill_percent: int = 20
    print_speed: float | None = None
    support_material: bool = False
    filament_type: str = "PLA"
    nozzle_size: float = 0.4


@dataclass
class SliceResult:
    estimated_time_seconds: int
    filament_used_grams: float
    filament_used_meters: float
    layer_count: int

    @property
    def human_time(self) -> str:
        total = self.estimated_time_seconds
        hours = total // 3600
        minutes = (total % 3600) // 60
        seconds = total % 60
        if hours > 0:
            return f"{hours}h {minutes}m"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        return f"{seconds}s"

    def compute_cost(self, filament_cost_per_kg: float) -> float:
        return round(self.filament_used_grams * filament_cost_per_kg / 1000, 2)


class BaseSlicer(ABC):
    @abstractmethod
    async def slice(self, stl_path: str, output_dir: str, params: SliceParams) -> SliceResult:
        ...
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_slicer.py -v
```

Expected: all passed.

- [ ] **Step 5: Write failing tests for OrcaSlicer G-code parsing**

Create `tests/test_orca_slicer.py`:

```python
from app.services.orca_slicer import OrcaSlicerService


SAMPLE_GCODE_METADATA = """\
; generated by OrcaSlicer
; estimated printing time (normal mode) = 1h 2m 0s
; filament used [mm] = 9500.00
; filament used [g] = 28.40
; filament used [cm3] = 22.50
; filament cost = 0.57
; total layers count = 150
G28 ; home all axes
G1 X0 Y0 Z0.2 F3000
"""


class TestGcodeParsing:
    def test_parse_time(self):
        result = OrcaSlicerService._parse_gcode_metadata(SAMPLE_GCODE_METADATA)
        assert result.estimated_time_seconds == 3720

    def test_parse_filament_grams(self):
        result = OrcaSlicerService._parse_gcode_metadata(SAMPLE_GCODE_METADATA)
        assert result.filament_used_grams == 28.4

    def test_parse_filament_meters(self):
        result = OrcaSlicerService._parse_gcode_metadata(SAMPLE_GCODE_METADATA)
        assert result.filament_used_meters == 9.5

    def test_parse_layer_count(self):
        result = OrcaSlicerService._parse_gcode_metadata(SAMPLE_GCODE_METADATA)
        assert result.layer_count == 150

    def test_parse_time_minutes_only(self):
        gcode = "; estimated printing time (normal mode) = 5m 30s\n"
        result = OrcaSlicerService._parse_gcode_metadata(gcode)
        assert result.estimated_time_seconds == 330

    def test_parse_time_hours_minutes_seconds(self):
        gcode = "; estimated printing time (normal mode) = 2h 15m 45s\n"
        result = OrcaSlicerService._parse_gcode_metadata(gcode)
        assert result.estimated_time_seconds == 8145
```

- [ ] **Step 6: Run tests to verify they fail**

```bash
uv run pytest tests/test_orca_slicer.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 7: Implement OrcaSlicer service**

Create `app/services/orca_slicer.py`:

```python
import asyncio
import re
from pathlib import Path

from app.services.slicer import BaseSlicer, SliceParams, SliceResult


class OrcaSlicerService(BaseSlicer):
    def __init__(self, executable: str = "orca-slicer", timeout: int = 300) -> None:
        self._executable = executable
        self._timeout = timeout

    async def slice(self, stl_path: str, output_dir: str, params: SliceParams) -> SliceResult:
        gcode_path = str(Path(output_dir) / "output.gcode")
        cmd = self._build_command(stl_path, gcode_path, params)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=self._timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            raise TimeoutError(f"Slicer timed out after {self._timeout}s")

        if process.returncode != 0:
            error_msg = stderr.decode().strip() or stdout.decode().strip()
            raise RuntimeError(f"Slicer failed (exit {process.returncode}): {error_msg}")

        gcode_content = Path(gcode_path).read_text()
        return self._parse_gcode_metadata(gcode_content)

    def _build_command(self, stl_path: str, gcode_path: str, params: SliceParams) -> list[str]:
        cmd = [
            self._executable,
            "--slice", "0",
            "--outputdir", str(Path(gcode_path).parent),
        ]
        # OrcaSlicer uses settings overrides via CLI
        # For now, pass the STL directly — settings are applied via defaults
        # Future: generate settings JSON for full parameter control
        cmd.append(stl_path)
        return cmd

    @staticmethod
    def _parse_gcode_metadata(gcode_content: str) -> SliceResult:
        time_seconds = 0
        filament_grams = 0.0
        filament_mm = 0.0
        layer_count = 0

        for line in gcode_content.splitlines():
            line = line.strip()

            time_match = re.match(
                r";\s*estimated printing time \(normal mode\)\s*=\s*(.+)", line
            )
            if time_match:
                time_seconds = _parse_time_string(time_match.group(1).strip())

            grams_match = re.match(r";\s*filament used \[g\]\s*=\s*([\d.]+)", line)
            if grams_match:
                filament_grams = float(grams_match.group(1))

            mm_match = re.match(r";\s*filament used \[mm\]\s*=\s*([\d.]+)", line)
            if mm_match:
                filament_mm = float(mm_match.group(1))

            layer_match = re.match(r";\s*total layers count\s*=\s*(\d+)", line)
            if layer_match:
                layer_count = int(layer_match.group(1))

        return SliceResult(
            estimated_time_seconds=time_seconds,
            filament_used_grams=filament_grams,
            filament_used_meters=round(filament_mm / 1000, 2),
            layer_count=layer_count,
        )


def _parse_time_string(time_str: str) -> int:
    total = 0
    hours = re.search(r"(\d+)h", time_str)
    minutes = re.search(r"(\d+)m", time_str)
    seconds = re.search(r"(\d+)s", time_str)
    if hours:
        total += int(hours.group(1)) * 3600
    if minutes:
        total += int(minutes.group(1)) * 60
    if seconds:
        total += int(seconds.group(1))
    return total
```

- [ ] **Step 8: Run tests to verify they pass**

```bash
uv run pytest tests/test_orca_slicer.py tests/test_slicer.py -v
```

Expected: all passed.

- [ ] **Step 9: Commit**

```bash
git add app/services/ tests/test_slicer.py tests/test_orca_slicer.py
git commit -m "feat: add slicer interface and OrcaSlicer CLI implementation"
```

---

### Task 6: Celery Worker Setup

**Files:**
- Create: `app/worker/__init__.py`
- Create: `app/worker/celery_app.py`
- Create: `app/worker/tasks.py`
- Create: `tests/test_tasks.py`

- [ ] **Step 1: Write failing test for the slice task**

Create `tests/test_tasks.py`:

```python
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.services.slicer import SliceResult, SliceParams
from app.worker.tasks import run_slice_job


class TestSliceTask:
    def test_run_slice_job_success(self, tmp_path):
        stl_path = tmp_path / "job-1" / "model.stl"
        stl_path.parent.mkdir()
        stl_path.write_bytes(b"solid cube\nendsolid cube")

        mock_result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )

        with patch("app.worker.tasks.get_slicer") as mock_get_slicer, \
             patch("app.worker.tasks.get_storage") as mock_get_storage, \
             patch("app.worker.tasks._run_async") as mock_run_async:

            mock_slicer = MagicMock()
            mock_get_slicer.return_value = mock_slicer
            mock_run_async.return_value = mock_result

            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage
            mock_storage.get_job_dir.return_value = str(tmp_path / "job-1")

            result = run_slice_job(
                job_id="job-1",
                params_dict={
                    "layer_height": 0.2,
                    "infill_percent": 20,
                    "filament_type": "PLA",
                    "filament_cost": 20.0,
                },
            )

            assert result["estimated_time_seconds"] == 3720
            assert result["filament_used_grams"] == 28.4
            assert result["estimated_cost"] == 0.57
            mock_storage.delete_file.assert_called_once_with("job-1", "model.stl")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tasks.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Implement Celery app**

Create `app/worker/__init__.py` (empty).

Create `app/worker/celery_app.py`:

```python
from celery import Celery

from app.config import Settings

settings = Settings()

celery_app = Celery(
    "sliceops",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
)
```

- [ ] **Step 4: Implement slice task**

Create `app/worker/tasks.py`:

```python
import asyncio

from app.worker.celery_app import celery_app
from app.config import Settings
from app.services.slicer import BaseSlicer, SliceParams, SliceResult
from app.services.orca_slicer import OrcaSlicerService
from app.storage.temp_storage import TempStorage

_settings = Settings()


def get_slicer() -> BaseSlicer:
    return OrcaSlicerService(
        executable=_settings.orca_slicer_path,
        timeout=_settings.slicer_timeout_seconds,
    )


def get_storage() -> TempStorage:
    return TempStorage(base_dir=_settings.temp_dir)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="sliceops.slice_model", bind=True)
def run_slice_job(self, job_id: str, params_dict: dict) -> dict:
    storage = get_storage()
    slicer = get_slicer()

    job_dir = storage.get_job_dir(job_id)
    if job_dir is None:
        raise FileNotFoundError(f"Job directory not found: {job_id}")

    stl_path = storage.get_file_path(job_id, "model.stl")
    if stl_path is None:
        raise FileNotFoundError(f"STL file not found for job: {job_id}")

    filament_cost = params_dict.pop("filament_cost", 20.0)
    params = SliceParams(**{k: v for k, v in params_dict.items() if k in SliceParams.__dataclass_fields__})

    result: SliceResult = _run_async(slicer.slice(stl_path, job_dir, params))

    # Delete STL immediately after slicing
    storage.delete_file(job_id, "model.stl")

    return {
        "estimated_time_seconds": result.estimated_time_seconds,
        "estimated_time_human": result.human_time,
        "filament_used_grams": result.filament_used_grams,
        "filament_used_meters": result.filament_used_meters,
        "layer_count": result.layer_count,
        "estimated_cost": result.compute_cost(filament_cost),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_tasks.py -v
```

Expected: all passed.

- [ ] **Step 6: Commit**

```bash
git add app/worker/ tests/test_tasks.py
git commit -m "feat: add Celery worker and slice task"
```

---

### Task 7: API Routes & FastAPI App

**Files:**
- Create: `app/api/__init__.py`
- Create: `app/api/dependencies.py`
- Create: `app/api/routes.py`
- Create: `app/main.py`
- Create: `tests/conftest.py`
- Create: `tests/test_routes.py`

- [ ] **Step 1: Write shared test fixtures**

Create `tests/conftest.py`:

```python
import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.services.slicer import SliceResult


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
def app(mock_storage, mock_slicer):
    application = create_app()
    application.state.storage = mock_storage
    application.state.slicer = mock_slicer
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

- [ ] **Step 2: Write failing tests for routes**

Create `tests/test_routes.py`:

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
        # Create the job dir so the mock works
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
        # Create a file larger than sync threshold (default 10MB)
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)

        large_content = b"x" * (11 * 1024 * 1024)  # 11MB

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
    async def test_job_not_found(self, client):
        resp = await client.get("/api/v1/jobs/nonexistent")
        assert resp.status_code == 404

    async def test_job_completed(self, client, app):
        # Store a completed result in app state
        app.state.job_results = {
            "job-1": {
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
        }
        resp = await client.get("/api/v1/jobs/job-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"


class TestGcodeDownload:
    async def test_gcode_not_found(self, client):
        resp = await client.get("/api/v1/jobs/nonexistent/gcode")
        assert resp.status_code == 404

    async def test_gcode_download(self, client, app, mock_storage, tmp_path):
        # Set up a gcode file
        job_dir = tmp_path / "job-1"
        job_dir.mkdir()
        gcode_file = job_dir / "output.gcode"
        gcode_file.write_text("G28\nG1 X0 Y0\n")
        mock_storage.get_file_path.return_value = str(gcode_file)
        mock_storage.get_job_dir.return_value = str(job_dir)

        app.state.job_results = {"job-1": {"status": "completed"}}

        resp = await client.get("/api/v1/jobs/job-1/gcode")
        assert resp.status_code == 200
        assert "G28" in resp.text
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 4: Implement dependencies**

Create `app/api/__init__.py` (empty).

Create `app/api/dependencies.py`:

```python
from fastapi import Request, UploadFile, Form, File
from typing import Optional

from app.models.request import SliceRequest


async def ingest_file(
    request: Request,
    file: Optional[UploadFile] = File(None),
    file_url: Optional[str] = Form(None),
) -> tuple[bytes, str]:
    """Extract STL file content from upload or URL. Returns (content, filename)."""
    if file is not None and file.filename:
        content = await file.read()
        return content, file.filename

    if file_url is not None:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(file_url)
            resp.raise_for_status()
            filename = file_url.split("/")[-1] or "model.stl"
            return resp.content, filename

    raise ValueError("Either 'file' or 'file_url' must be provided")
```

- [ ] **Step 5: Implement routes**

Create `app/api/routes.py`:

```python
import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import Optional

from app.api.dependencies import ingest_file
from app.config import Settings
from app.models.request import SliceRequest
from app.models.response import (
    SyncSliceResponse,
    AsyncSliceResponse,
    JobStatusResponse,
    SliceResult as SliceResultResponse,
    ErrorResponse,
)
from app.worker.tasks import run_slice_job

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
):
    try:
        content, filename = await ingest_file(request, file, file_url)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    job_id = str(uuid.uuid4())
    storage = request.app.state.storage
    storage.create_job_dir(job_id)
    storage.save_file(job_id, "model.stl", content)

    params_dict = {
        "layer_height": layer_height,
        "infill_percent": infill_percent,
        "print_speed": print_speed,
        "support_material": support_material,
        "filament_type": filament_type,
        "filament_cost": filament_cost,
        "nozzle_size": nozzle_size,
    }

    file_size_mb = len(content) / (1024 * 1024)

    if file_size_mb < settings.sync_threshold_mb:
        # Sync path
        slicer = request.app.state.slicer
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
            result = await slicer.slice(stl_path, job_dir, slicer_params)
        except TimeoutError:
            storage.cleanup_job(job_id)
            raise HTTPException(status_code=504, detail="Slicer timed out")
        except RuntimeError as e:
            storage.cleanup_job(job_id)
            raise HTTPException(status_code=500, detail=str(e))

        # Delete STL immediately
        storage.delete_file(job_id, "model.stl")

        cost = result.compute_cost(filament_cost)
        gcode_url = f"/api/v1/jobs/{job_id}/gcode"

        response_result = SliceResultResponse(
            estimated_time_seconds=result.estimated_time_seconds,
            estimated_time_human=result.human_time,
            filament_used_grams=result.filament_used_grams,
            filament_used_meters=result.filament_used_meters,
            layer_count=result.layer_count,
            estimated_cost=cost,
            gcode_download_url=gcode_url,
        )

        # Store result for job status lookups
        if not hasattr(request.app.state, "job_results"):
            request.app.state.job_results = {}
        request.app.state.job_results[job_id] = {
            "status": "completed",
            "result": response_result.model_dump(),
        }

        return SyncSliceResponse(job_id=job_id, result=response_result)

    else:
        # Async path
        task = run_slice_job.delay(job_id=job_id, params_dict=params_dict)

        if not hasattr(request.app.state, "job_results"):
            request.app.state.job_results = {}
        request.app.state.job_results[job_id] = {
            "status": "pending",
            "celery_task_id": task.id,
        }

        return AsyncSliceResponse(
            job_id=job_id,
            poll_url=f"/api/v1/jobs/{job_id}",
        )


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request):
    job_results = getattr(request.app.state, "job_results", {})

    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")

    job = job_results[job_id]
    status = job["status"]

    # Check Celery task status if pending/processing
    if status in ("pending", "processing") and "celery_task_id" in job:
        from celery.result import AsyncResult
        from app.worker.celery_app import celery_app

        task_result = AsyncResult(job["celery_task_id"], app=celery_app)
        if task_result.ready():
            if task_result.successful():
                result_data = task_result.result
                result_data["gcode_download_url"] = f"/api/v1/jobs/{job_id}/gcode"
                job["status"] = "completed"
                job["result"] = result_data
                status = "completed"
            else:
                job["status"] = "failed"
                status = "failed"
        elif task_result.state == "STARTED":
            status = "processing"

    result = job.get("result")
    return JobStatusResponse(job_id=job_id, status=status, result=result)


@router.get("/jobs/{job_id}/gcode")
async def download_gcode(job_id: str, request: Request):
    job_results = getattr(request.app.state, "job_results", {})
    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")

    storage = request.app.state.storage
    gcode_path = storage.get_file_path(job_id, "output.gcode")
    if gcode_path is None:
        raise HTTPException(status_code=404, detail="G-code file not found")

    return FileResponse(
        gcode_path,
        media_type="application/octet-stream",
        filename=f"{job_id}.gcode",
    )
```

- [ ] **Step 6: Implement FastAPI app factory**

Create `app/main.py`:

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings
from app.services.orca_slicer import OrcaSlicerService
from app.storage.temp_storage import TempStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    app.state.storage = TempStorage(base_dir=settings.temp_dir)
    app.state.slicer = OrcaSlicerService(
        executable=settings.orca_slicer_path,
        timeout=settings.slicer_timeout_seconds,
    )
    app.state.job_results = {}
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SliceOps",
        description="3D printing time and cost estimation API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()
```

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/test_routes.py -v
```

Expected: all passed.

- [ ] **Step 8: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit**

```bash
git add app/api/ app/main.py tests/conftest.py tests/test_routes.py
git commit -m "feat: add API routes, FastAPI app, and route tests"
```

---

### Task 8: Docker & Docker Compose

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] **Step 1: Create Dockerfile**

Create `Dockerfile`:

```dockerfile
FROM python:3.12-slim

# Install system deps for OrcaSlicer (will need adjustment based on actual OrcaSlicer requirements)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copy dependency files first for caching
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ app/

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Create docker-compose.yml**

Create `docker-compose.yml`:

```yaml
services:
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
      - SLICEOPS_TEMP_DIR=/tmp/sliceops
    depends_on:
      - redis
    tmpfs:
      - /tmp/sliceops:size=512M
    volumes:
      - ./app:/app/app

  worker:
    build: .
    command: uv run celery -A app.worker.celery_app worker --loglevel=info
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
      - SLICEOPS_TEMP_DIR=/tmp/sliceops
    depends_on:
      - redis
    tmpfs:
      - /tmp/sliceops:size=512M

  beat:
    build: .
    command: uv run celery -A app.worker.celery_app beat --loglevel=info
    environment:
      - SLICEOPS_REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
```

- [ ] **Step 3: Commit**

```bash
git add Dockerfile docker-compose.yml
git commit -m "feat: add Dockerfile and docker-compose for API, worker, and Redis"
```

---

### Task 9: Celery Beat Cleanup Task

**Files:**
- Modify: `app/worker/tasks.py`
- Modify: `app/worker/celery_app.py`

- [ ] **Step 1: Write failing test for cleanup task**

Add to `tests/test_tasks.py`:

```python
class TestCleanupTask:
    def test_sweep_expired_files(self, tmp_path):
        with patch("app.worker.tasks.get_storage") as mock_get_storage:
            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage
            mock_storage.sweep_expired.return_value = ["old-job-1", "old-job-2"]

            from app.worker.tasks import sweep_expired_files
            removed = sweep_expired_files()
            assert removed == ["old-job-1", "old-job-2"]
            mock_storage.sweep_expired.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_tasks.py::TestCleanupTask -v
```

Expected: FAIL — `ImportError: cannot import name 'sweep_expired_files'`

- [ ] **Step 3: Add cleanup task to tasks.py**

Add to end of `app/worker/tasks.py`:

```python
@celery_app.task(name="sliceops.sweep_expired")
def sweep_expired_files() -> list[str]:
    storage = get_storage()
    return storage.sweep_expired(ttl_minutes=_settings.gcode_ttl_minutes)
```

- [ ] **Step 4: Add beat schedule to celery_app.py**

Add to `app/worker/celery_app.py` after `celery_app.conf.update(...)`:

```python
celery_app.conf.beat_schedule = {
    "sweep-expired-files": {
        "task": "sliceops.sweep_expired",
        "schedule": 300.0,  # Every 5 minutes
    },
}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/test_tasks.py -v
```

Expected: all passed.

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add app/worker/tasks.py app/worker/celery_app.py tests/test_tasks.py
git commit -m "feat: add Celery Beat cleanup task for expired files"
```

---

### Task 10: Final Verification

- [ ] **Step 1: Run full test suite with coverage**

```bash
uv run pytest -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 2: Verify FastAPI app starts**

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 2
curl http://localhost:8000/api/v1/health
kill %1
```

Expected: `{"status":"ok"}`

- [ ] **Step 3: Verify OpenAPI docs are generated**

```bash
uv run python -c "from app.main import app; import json; print(json.dumps(app.openapi(), indent=2))" | head -20
```

Expected: JSON output showing OpenAPI spec with `/api/v1/slice`, `/api/v1/jobs/{job_id}`, etc.

- [ ] **Step 4: Final commit if any cleanup needed**

```bash
git status
```

If clean, no action needed.

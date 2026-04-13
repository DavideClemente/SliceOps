# SliceOps API Design Spec

## Overview

SliceOps is a Python API service that estimates 3D printing times and costs by invoking a slicer CLI. It accepts STL files (via upload or URL), slices them with configurable parameters, and returns print time, filament usage, cost estimates, and the generated G-code file.

**Primary consumer:** Other services/systems calling programmatically (not end users directly).

## Tech Stack

- **Language:** Python
- **Framework:** FastAPI
- **Task queue:** Celery + Redis
- **Slicer:** OrcaSlicer CLI (primary), architecture supports adding others later
- **Dependency management:** uv (pyproject.toml + uv.lock)
- **Containerization:** Docker + Docker Compose

## API Endpoints

### `POST /api/v1/slice`

Single entry point for slicing. The server decides whether to process synchronously or asynchronously based on file size (configurable threshold, default 10MB).

- Under threshold: processes synchronously, returns full results inline.
- Over threshold: returns a `job_id` with status `accepted`, caller polls for results.
- Response includes a `mode` field (`sync` or `async`) so the caller knows which path was taken.

### `GET /api/v1/jobs/{job_id}`

Returns job status (`pending`, `processing`, `completed`, `failed`). When `completed`, includes slicing results and a time-limited G-code download URL.

### `GET /api/v1/jobs/{job_id}/gcode`

One-time or short-TTL download of the generated G-code file. File is deleted after retrieval or TTL expiry.

### `GET /api/v1/health`

Health check endpoint.

## Request Parameters

| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | multipart file | one of file/url | - | STL file upload |
| `file_url` | string (URL) | one of file/url | - | URL to fetch STL from |
| `layer_height` | float (mm) | no | 0.2 | Layer height |
| `infill_percent` | int (0-100) | no | 20 | Infill percentage |
| `print_speed` | float (mm/s) | no | slicer default | Print speed |
| `support_material` | bool | no | false | Enable support material |
| `filament_type` | string | no | "PLA" | PLA, PETG, ABS, TPU, etc. |
| `filament_cost` | float (per kg) | no | 20.0 | Cost in user's currency |
| `nozzle_size` | float (mm) | no | 0.4 | Nozzle diameter |

## Response Models

### Sync response

```json
{
  "mode": "sync",
  "status": "completed",
  "result": {
    "estimated_time_seconds": 3720,
    "estimated_time_human": "1h 2m",
    "filament_used_grams": 28.4,
    "filament_used_meters": 9.5,
    "layer_count": 150,
    "estimated_cost": 0.57,
    "gcode_download_url": "/api/v1/jobs/{job_id}/gcode"
  }
}
```

### Async response (on submission)

```json
{
  "mode": "async",
  "status": "accepted",
  "job_id": "abc-123",
  "poll_url": "/api/v1/jobs/abc-123"
}
```

### Job poll response (when completed)

Same shape as sync response, with `job_id` included.

### Error responses

Standard HTTP codes with consistent body:

- 400: Bad input
- 413: File too large
- 422: Unsupported/corrupt file format
- 500: Slicer failure
- 504: Slicer timeout

```json
{
  "error": "message",
  "detail": "..."
}
```

## Project Structure

```
sliceops/
├── app/
│   ├── main.py              # FastAPI app, startup/shutdown
│   ├── api/
│   │   ├── routes.py         # Endpoint definitions
│   │   └── dependencies.py   # Request validation, file handling
│   ├── models/
│   │   ├── request.py        # Pydantic request models
│   │   └── response.py       # Pydantic response models
│   ├── services/
│   │   ├── slicer.py         # Abstract slicer interface
│   │   └── orca_slicer.py    # OrcaSlicer CLI implementation
│   ├── worker/
│   │   ├── celery_app.py     # Celery configuration
│   │   └── tasks.py          # Celery task definitions
│   ├── storage/
│   │   └── temp_storage.py   # Temp file management + cleanup
│   └── config.py             # Settings (thresholds, defaults, paths)
├── tests/
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml        # App + Redis + Worker
```

## Slicer Integration

### Slicer interface

Abstract base class `BaseSlicer` with a `slice(stl_path, params) -> SliceResult` method. Adding a new slicer means implementing this interface — no other changes required.

### OrcaSlicer CLI

`OrcaSlicerService` wraps the CLI:

1. Writes STL to a temp file (if received via upload).
2. Invokes `orca-slicer --slice <stl_path> --output <gcode_path>` with flags for layer height, infill, speed, supports, filament type, nozzle size.
3. Parses G-code metadata comments (e.g., `; estimated printing time`, `; filament used [g]`) to extract results.
4. Computes cost from `filament_used_grams` and `filament_cost` per kg.

### Error handling

- CLI not found or crashes: 500 with clear error message.
- Invalid STL (corrupt, not manifold): slicer reports error, return 422.
- CLI timeout (configurable, default 5 min): kill process, return 504.

### Sync/async threshold

- Default: file size < 10MB = sync.
- Configurable via environment variable (`SLICEOPS_SYNC_THRESHOLD_MB`).

## File Security & Cleanup

Privacy is the top priority. STL files are potentially proprietary — they must not persist.

### Principles

- Files exist on disk only because OrcaSlicer CLI requires filesystem paths.
- Minimize the window files are on disk.

### File lifecycle

| Scenario | STL lifetime | G-code lifetime |
|---|---|---|
| Sync request | Deleted immediately after slicing | Deleted after response is sent or short TTL (5 min) for download URL |
| Async request | Deleted immediately after slicing | Deleted after first download or TTL (configurable, default 15 min) |
| Failed job | Deleted immediately | Never created |

### Implementation

- All temp files go into a job-specific directory: `/tmp/sliceops/{job_id}/`.
- Entire directory is wiped on cleanup.
- Celery Beat periodic task sweeps directories past their TTL (safety net).
- Temp directory is a `tmpfs` mount in Docker (RAM-backed, never touches persistent storage, wiped on container restart).

### Additional safeguards

- No file listing endpoint. G-code is only accessible with the job ID (UUID4).
- G-code download invalidates the file (one-time retrieval by default, configurable).

## Testing Strategy

### Unit tests

- Request/response model validation (Pydantic).
- Slicer interface contract (mock the CLI, test G-code metadata parsing).
- Temp storage lifecycle (creation, cleanup, TTL expiry).
- Sync/async threshold logic.
- Cost calculation from filament weight + cost per kg.

### Integration tests

- Full sync slice request with a small test STL and real OrcaSlicer CLI.
- Full async flow: submit, poll, download G-code, verify cleanup.
- File upload and URL fetch paths.
- Error cases: corrupt STL, missing parameters, oversized file.

### Tooling

- `pytest` + `httpx` (FastAPI async test client).
- Small test STL fixtures committed to the repo (simple cube, ~1KB).
- Integration tests gated behind `@pytest.mark.integration` (require OrcaSlicer, run in Docker/CI).

## Authentication

No authentication in the initial version. Expected to be handled at the infrastructure level (API gateway) or added later.

## Configuration

All configurable via environment variables:

| Variable | Default | Description |
|---|---|---|
| `SLICEOPS_SYNC_THRESHOLD_MB` | 10 | File size threshold for sync vs async |
| `SLICEOPS_TEMP_DIR` | `/tmp/sliceops` | Temp file directory |
| `SLICEOPS_GCODE_TTL_MINUTES` | 15 | TTL for G-code files before cleanup |
| `SLICEOPS_SLICER_TIMEOUT_SECONDS` | 300 | Max time for slicer CLI execution |
| `SLICEOPS_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `SLICEOPS_ORCA_SLICER_PATH` | `orca-slicer` | Path to OrcaSlicer CLI binary |

# SliceOps

REST API for 3D printing time and cost estimation. Upload an STL file, pick a slicer, and get back print time, filament usage, layer count, cost estimate, and downloadable G-code.

## Features

- **Two slicers** — PrusaSlicer and BambuStudio, selectable per request
- **Sync & async** — small files return results immediately; large files are queued via Celery
- **Plan-based limits** — rate limiting, monthly quotas, and file size caps defined in a single YAML file
- **API key auth** — create, list, and revoke keys through admin endpoints or CLI
- **Observability** — structured JSON logging with request ID correlation, Prometheus metrics at `/metrics`
- **Docker-ready** — full Compose stack (API, Celery worker, beat scheduler, Redis)

## Quick Start

### Docker (recommended)

```bash
docker compose up
```

This starts four services:

| Service | Purpose |
|---|---|
| **redis** | State store (jobs, auth, rate limits, Celery broker) |
| **api** | FastAPI app on port 8000 |
| **worker** | Celery worker for async slice jobs |
| **beat** | Periodic cleanup of expired job files |

### Local development

Prerequisites: Python 3.12+, Redis running locally, [uv](https://docs.astral.sh/uv/).

```bash
# Install dependencies
uv sync

# Start the API server
uv run uvicorn app.main:app --reload

# In separate terminals:
uv run celery -A app.worker.celery_app worker --loglevel=info
uv run celery -A app.worker.celery_app beat --loglevel=info
```

You also need at least one slicer binary available. Set the path in `.env`:

```env
SLICEOPS_PRUSA_SLICER_PATH=/path/to/prusa-slicer
SLICEOPS_BAMBU_STUDIO_PATH=/path/to/bambu-studio
```

## Usage

### Create an API key

```bash
# Via CLI
uv run sliceops create-key --owner alice --plan free

# Via admin API (requires SLICEOPS_ADMIN_API_KEY to be set)
curl -X POST "http://localhost:8000/api/v1/admin/keys?owner=alice&plan=free" \
  -H "X-API-Key: <admin-key>"
```

### Slice a model

```bash
curl -X POST http://localhost:8000/api/v1/slice \
  -H "X-API-Key: so_live_..." \
  -F "file=@model.stl" \
  -F "layer_height=0.2" \
  -F "infill_percent=20" \
  -F "slicer=prusa-slicer"
```

Response (sync):

```json
{
  "mode": "sync",
  "status": "completed",
  "job_id": "abc-123",
  "result": {
    "estimated_time_seconds": 3720,
    "estimated_time_human": "1h 2m",
    "filament_used_grams": 28.4,
    "filament_used_meters": 9.5,
    "layer_count": 150,
    "estimated_cost": 0.57,
    "gcode_download_url": "/api/v1/jobs/abc-123/download"
  }
}
```

For files larger than 10 MB, the response is `202 Accepted` with a `poll_url` to check status.

### Download G-code

```bash
curl -O -J http://localhost:8000/api/v1/jobs/abc-123/download \
  -H "X-API-Key: so_live_..."
```

## API Reference

### Public endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check (no auth) |
| POST | `/api/v1/slice` | Submit model for slicing |
| GET | `/api/v1/jobs/{job_id}` | Poll job status |
| GET | `/api/v1/jobs/{job_id}/download` | Download sliced output |
| GET | `/metrics` | Prometheus metrics (no auth) |

### Admin endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/api/v1/admin/keys` | Create API key |
| GET | `/api/v1/admin/keys` | List all keys |
| DELETE | `/api/v1/admin/keys/{key}` | Revoke a key |
| GET | `/api/v1/admin/keys/{key}/usage` | Monthly usage stats |

### Slice parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file` | file | — | STL file upload (or provide `file_url`) |
| `file_url` | string | — | URL to fetch STL from |
| `layer_height` | float | 0.2 | Layer height in mm |
| `infill_percent` | int | 20 | Infill density (0–100) |
| `print_speed` | float | — | Print speed in mm/s |
| `support_material` | bool | false | Enable supports |
| `filament_type` | string | PLA | PLA, PETG, ABS, ASA, TPU, NYLON, PC |
| `filament_cost` | float | 20.0 | Cost per kg |
| `nozzle_size` | float | 0.4 | Nozzle diameter in mm |
| `slicer` | string | prusa-slicer | `prusa-slicer` or `bambu-studio` |

## Plan Configuration

Plan limits are defined in `config/plans.yaml`:

```yaml
free:
  rate_limit: 5           # requests per minute
  monthly_quota: 50       # slices per month
  max_file_size_mb: 25    # max upload in MB

paid:
  rate_limit: 60
  monthly_quota: 5000
  max_file_size_mb: 100
```

To add a new plan, add a block — no code changes required:

```yaml
pro:
  rate_limit: 120
  monthly_quota: 20000
  max_file_size_mb: 500
```

Override the file location with `SLICEOPS_PLANS_FILE=/path/to/plans.yaml`.

## Configuration

All settings are configurable via `SLICEOPS_*` environment variables or a `.env` file.

| Variable | Default | Description |
|---|---|---|
| `SLICEOPS_REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `SLICEOPS_AUTH_ENABLED` | `true` | Enable/disable API key authentication |
| `SLICEOPS_ADMIN_API_KEY` | `""` | Admin key (empty = admin endpoints disabled) |
| `SLICEOPS_PLANS_FILE` | `config/plans.yaml` | Path to plan limits YAML |
| `SLICEOPS_SYNC_THRESHOLD_MB` | `10` | Files below this size are sliced synchronously |
| `SLICEOPS_SLICER_TIMEOUT_SECONDS` | `300` | Timeout per slice operation |
| `SLICEOPS_GCODE_TTL_MINUTES` | `15` | How long output files are kept |
| `SLICEOPS_TEMP_DIR` | `/tmp/sliceops` | Temporary storage for job files |
| `SLICEOPS_PRUSA_SLICER_PATH` | `prusa-slicer` | PrusaSlicer executable path |
| `SLICEOPS_BAMBU_STUDIO_PATH` | `bambu-studio` | BambuStudio executable path |
| `SLICEOPS_CORS_ORIGINS` | `["*"]` | Allowed CORS origins |
| `SLICEOPS_LOG_LEVEL` | `INFO` | Logging level |
| `SLICEOPS_JOB_TTL_SECONDS` | `3600` | Job data retention in Redis |

## CLI

```bash
uv run sliceops create-key --owner <name> [--plan <plan>]
uv run sliceops list-keys
uv run sliceops revoke-key <key>
```

## Tests

```bash
uv run pytest -v
```

## Project Structure

```
SliceOps/
├── app/
│   ├── api/
│   │   ├── routes.py            # Public API endpoints
│   │   ├── admin_routes.py      # Admin key management
│   │   └── dependencies.py      # File ingestion helper
│   ├── auth/
│   │   ├── models.py            # ApiKeyData model
│   │   ├── service.py           # Redis-backed auth service
│   │   └── dependencies.py      # API key validation dependency
│   ├── rate_limit/
│   │   ├── service.py           # Rate limit + quota enforcement
│   │   └── dependencies.py      # Rate limit dependency
│   ├── services/
│   │   ├── slicer.py            # Base slicer, SliceParams, SliceResult
│   │   ├── prusa_slicer.py      # PrusaSlicer integration
│   │   └── bambu_studio.py      # BambuStudio integration
│   ├── middleware/
│   │   ├── request_id.py        # X-Request-ID tracking
│   │   └── logging_config.py    # Structured JSON logging
│   ├── storage/
│   │   └── temp_storage.py      # Job file management + TTL cleanup
│   ├── store/
│   │   └── job_store.py         # Redis job state store
│   ├── worker/
│   │   └── celery_app.py        # Celery config + beat schedule
│   │   └── tasks.py             # Async slice + sweep tasks
│   ├── models/
│   │   ├── request.py           # SliceRequest validation
│   │   └── response.py          # Response schemas
│   ├── config.py                # Settings + PlanLimits loader
│   ├── cli.py                   # Typer CLI for key management
│   └── main.py                  # FastAPI app factory + lifespan
├── config/
│   └── plans.yaml               # Plan limits (rate, quota, file size)
├── tests/
├── docker-compose.yml
├── Dockerfile
└── pyproject.toml
```

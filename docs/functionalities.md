# SliceOps — Functionalities

## API Endpoints

### Public (`/api/v1`)

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/health` | GET | No | Health check |
| `/slice` | POST | API key | Submit a 3D model for slicing |
| `/jobs/{job_id}` | GET | API key | Poll job status |
| `/jobs/{job_id}/download` | GET | API key | Download G-code output |
| `/metrics` | GET | No | Prometheus metrics |

### Admin (`/api/v1/admin`)

| Endpoint | Method | Description |
|---|---|---|
| `/keys` | POST | Create API key (owner + plan) |
| `/keys` | GET | List all keys |
| `/keys/{key}` | DELETE | Revoke a key |
| `/keys/{key}/usage` | GET | Monthly usage stats |

---

## Slicing

- **Sync path**: Files < 10MB — sliced immediately, result returned in response
- **Async path**: Files >= 10MB — queued to Celery, returns poll URL (status 202)
- **Supported slicers**: `prusa-slicer`, `bambu-studio`
- **Output**: Estimated time, filament usage (grams/meters), layer count, cost estimate, downloadable G-code/.3mf

**Slice parameters**: layer_height, infill_percent, print_speed, support_material, filament_type (PLA/PETG/ABS/ASA/TPU/NYLON/PC), filament_cost, nozzle_size, slicer

---

## Auth & Rate Limiting

- **API keys**: Format `so_live_{token}`, stored in Redis, plan-based
- **Auth toggle**: `SLICEOPS_AUTH_ENABLED=false` disables auth (returns dummy "paid" key)
- **Plan limits** defined in `config/plans.yaml`:
  - `rate_limit` — requests per minute
  - `monthly_quota` — slices per month
  - `max_file_size_mb` — max upload size
- Adding a plan = add a YAML block, zero code changes

---

## CLI (`sliceops`)

```bash
sliceops create-key --owner alice --plan free
sliceops list-keys
sliceops revoke-key <key>
```

---

## Background Workers (Celery)

- **Slice worker**: Processes async slice jobs (concurrency=2)
- **Beat scheduler**: Runs `sweep-expired-files` every 5 minutes (cleans job dirs older than 15min)

---

## Infrastructure

- **Storage**: Temp directories per job (`/tmp/sliceops/{job_id}/`), auto-cleaned after download or TTL
- **Redis**: Job store, auth keys, rate limit counters, Celery broker/backend
- **Middleware**: Request ID tracking (X-Request-ID), CORS, structured JSON logging
- **Docker Compose**: 4 services — Redis, API, Worker, Beat (all configured via env vars)

---

## Configuration

All settings via `SLICEOPS_*` env vars or `.env` file. Key ones:

| Setting | Default | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection |
| `AUTH_ENABLED` | `true` | Toggle authentication |
| `ADMIN_API_KEY` | `""` | Admin endpoint access |
| `PLANS_FILE` | `config/plans.yaml` | Plan limits config |
| `SYNC_THRESHOLD_MB` | `10` | Sync vs async cutoff |
| `SLICER_TIMEOUT_SECONDS` | `300` | Per-slice timeout |
| `GCODE_TTL_MINUTES` | `15` | File cleanup TTL |

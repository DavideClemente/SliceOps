# SliceOps

**3D printing estimation API as a service.** Upload an STL, get back print time, filament usage, cost estimate, and production-ready G-code — in seconds.

## What it does

SliceOps wraps industry-standard slicers behind a simple REST API. Send a 3D model, configure your print settings, and receive accurate estimates without running slicer software yourself.

- Print time estimation (seconds + human-readable)
- Filament usage in grams and meters
- Layer count
- Cost calculation based on your filament price
- Downloadable G-code / 3MF output

## Supported slicers

- **PrusaSlicer**
- **BambuStudio**

Choose per request — same API, same response format.

## Supported filaments

PLA, PETG, ABS, ASA, TPU, NYLON, PC

## API Overview

### Authentication

All requests require an API key via the `X-API-Key` header.

### Slice a model

```bash
curl -X POST https://api.sliceops.dev/api/v1/slice \
  -H "X-API-Key: so_live_..." \
  -F "file=@model.stl" \
  -F "layer_height=0.2" \
  -F "infill_percent=20" \
  -F "slicer=prusa-slicer"
```

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

Small files are processed immediately. Larger files return a `202 Accepted` with a poll URL for async processing.

You can also pass a `file_url` instead of uploading directly.

### Check job status

```bash
curl https://api.sliceops.dev/api/v1/jobs/{job_id} \
  -H "X-API-Key: so_live_..."
```

### Download G-code

```bash
curl -O -J https://api.sliceops.dev/api/v1/jobs/{job_id}/download \
  -H "X-API-Key: so_live_..."
```

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check |
| POST | `/api/v1/slice` | Submit a model for slicing |
| GET | `/api/v1/jobs/{job_id}` | Poll job status |
| GET | `/api/v1/jobs/{job_id}/download` | Download sliced output |

## Slice parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `file` | file | — | STL file upload (or use `file_url`) |
| `file_url` | string | — | URL to fetch the STL from |
| `layer_height` | float | 0.2 | Layer height in mm |
| `infill_percent` | int | 20 | Infill density (0-100) |
| `print_speed` | float | — | Print speed in mm/s |
| `support_material` | bool | false | Enable support structures |
| `filament_type` | string | PLA | PLA, PETG, ABS, ASA, TPU, NYLON, PC |
| `filament_cost` | float | 20.0 | Cost per kg in your currency |
| `nozzle_size` | float | 0.4 | Nozzle diameter in mm |
| `slicer` | string | prusa-slicer | `prusa-slicer` or `bambu-studio` |

## Plans

| | Free | Paid |
|---|---|---|
| Requests per minute | 5 | 60 |
| Slices per month | 50 | 5,000 |
| Max file size | 25 MB | 100 MB |

## Error codes

| Status | Meaning |
|---|---|
| 400 | Bad request (missing file, invalid slicer) |
| 401 | Missing or invalid API key |
| 403 | API key revoked |
| 413 | File exceeds plan's size limit |
| 422 | Invalid parameter values |
| 429 | Rate limit or monthly quota exceeded |

Rate limit responses include `Retry-After`, `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers.

## License

Proprietary. All rights reserved.

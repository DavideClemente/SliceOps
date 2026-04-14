import asyncio
import json

import redis as sync_redis

from app.worker.celery_app import celery_app
from app.config import Settings
from app.services.slicer import BaseSlicer, SliceParams, SliceResult
from app.services.bambu_studio import BambuStudioService
from app.services.prusa_slicer import PrusaSlicerService
from app.storage.temp_storage import TempStorage

_settings = Settings()


def get_slicer(name: str = "prusa-slicer") -> BaseSlicer:
    if name == "bambu-studio":
        return BambuStudioService(
            executable=_settings.bambu_studio_path,
            timeout=_settings.slicer_timeout_seconds,
        )
    return PrusaSlicerService(
        executable=_settings.prusa_slicer_path,
        timeout=_settings.slicer_timeout_seconds,
    )


def get_storage() -> TempStorage:
    return TempStorage(base_dir=_settings.temp_dir)


def _get_sync_redis() -> sync_redis.Redis:
    return sync_redis.Redis.from_url(_settings.redis_url, decode_responses=True)


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="sliceops.slice_model", bind=True)
def run_slice_job(self, job_id: str, params_dict: dict) -> dict:
    storage = get_storage()
    slicer_name = params_dict.pop("slicer", "prusa-slicer")
    slicer = get_slicer(slicer_name)

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

    result_data = {
        "estimated_time_seconds": result.estimated_time_seconds,
        "estimated_time_human": result.human_time,
        "filament_used_grams": result.filament_used_grams,
        "filament_used_meters": result.filament_used_meters,
        "layer_count": result.layer_count,
        "estimated_cost": result.compute_cost(filament_cost),
        "output_filename": result.output_filename,
    }

    # Update job in Redis
    r = _get_sync_redis()
    job_key = f"sliceops:job:{job_id}"
    r.hset(job_key, "output_filename", result.output_filename)
    r.close()

    return result_data


@celery_app.task(name="sliceops.sweep_expired")
def sweep_expired_files() -> list[str]:
    storage = get_storage()
    return storage.sweep_expired(ttl_minutes=_settings.gcode_ttl_minutes)

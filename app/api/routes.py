import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask
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

    # Validate parameters
    try:
        validated = SliceRequest(
            layer_height=layer_height,
            infill_percent=infill_percent,
            print_speed=print_speed,
            support_material=support_material,
            filament_type=filament_type,
            filament_cost=filament_cost,
            nozzle_size=nozzle_size,
        )
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    max_size = settings.max_file_size_mb * 1024 * 1024
    if len(content) > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.max_file_size_mb}MB",
        )

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
        request.app.state.job_results[job_id] = {
            "status": "completed",
            "result": response_result.model_dump(),
        }

        return SyncSliceResponse(job_id=job_id, result=response_result)

    else:
        # Async path
        task = run_slice_job.delay(job_id=job_id, params_dict=params_dict)

        request.app.state.job_results[job_id] = {
            "status": "pending",
            "celery_task_id": task.id,
        }

        response = AsyncSliceResponse(
            job_id=job_id,
            poll_url=f"/api/v1/jobs/{job_id}",
        )
        return JSONResponse(content=response.model_dump(), status_code=202)


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str, request: Request):
    job_results = getattr(request.app.state, "job_results", {})

    if job_id not in job_results:
        raise HTTPException(status_code=404, detail="Job not found")

    job = job_results[job_id]
    status = job["status"]

    # For async jobs, check Celery task state
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

    # Clean up job after file is sent
    cleanup = BackgroundTask(storage.cleanup_job, job_id)

    return FileResponse(
        gcode_path,
        media_type="application/octet-stream",
        filename=f"{job_id}.gcode",
        background=cleanup,
    )

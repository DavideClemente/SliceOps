import logging
import uuid

from fastapi import APIRouter, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from starlette.background import BackgroundTask
from typing import Optional

from app.api.dependencies import ingest_file
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

    if file_size_mb < app_settings.sync_threshold_mb:
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

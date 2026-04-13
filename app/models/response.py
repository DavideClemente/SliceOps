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

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

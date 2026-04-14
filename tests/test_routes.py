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
    async def test_job_not_found(self, client, mock_job_store):
        mock_job_store.get.return_value = None
        resp = await client.get("/api/v1/jobs/nonexistent")
        assert resp.status_code == 404

    async def test_job_completed(self, client, mock_job_store):
        mock_job_store.get.return_value = {
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
        resp = await client.get("/api/v1/jobs/job-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"


class TestOutputDownload:
    async def test_download_not_found(self, client, mock_job_store):
        mock_job_store.get.return_value = None
        resp = await client.get("/api/v1/jobs/nonexistent/download")
        assert resp.status_code == 404

    async def test_download_gcode(self, client, mock_job_store, mock_storage, tmp_path):
        job_dir = tmp_path / "job-1"
        job_dir.mkdir()
        gcode_file = job_dir / "output.gcode"
        gcode_file.write_text("G28\nG1 X0 Y0\n")
        mock_storage.get_file_path.return_value = str(gcode_file)
        mock_storage.get_job_dir.return_value = str(job_dir)

        mock_job_store.get.return_value = {"status": "completed", "output_filename": "output.gcode"}

        resp = await client.get("/api/v1/jobs/job-1/download")
        assert resp.status_code == 200
        assert "G28" in resp.text

    async def test_download_3mf(self, client, mock_job_store, mock_storage, tmp_path):
        import zipfile
        job_dir = tmp_path / "job-2"
        job_dir.mkdir()
        archive_path = job_dir / "output.gcode.3mf"
        with zipfile.ZipFile(archive_path, "w") as zf:
            zf.writestr("plate_1.gcode", "G28\n")
        mock_storage.get_file_path.return_value = str(archive_path)

        mock_job_store.get.return_value = {"status": "completed", "output_filename": "output.gcode.3mf"}

        resp = await client.get("/api/v1/jobs/job-2/download")
        assert resp.status_code == 200


class TestFileSizeLimit:
    async def test_file_too_large_returns_413(self, client, mock_storage, tmp_path, app):
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)

        # Override plan limits for testing
        from app.config import PlanLimits
        low_limits = PlanLimits(rate_limit=60, monthly_quota=5000, max_file_size_mb=1)
        app.state.settings._plan_limits["free"] = low_limits
        app.state.settings._plan_limits["pro"] = low_limits

        large_content = b"x" * (2 * 1024 * 1024)  # 2MB
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("big.stl", large_content, "application/octet-stream")},
        )
        assert resp.status_code == 413


class TestParameterValidation:
    async def test_invalid_infill_returns_422(self, client):
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            data={"infill_percent": "150"},
        )
        assert resp.status_code == 422

    async def test_unsupported_slicer_returns_400(self, client):
        resp = await client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            data={"slicer": "unknown-slicer"},
        )
        assert resp.status_code == 400

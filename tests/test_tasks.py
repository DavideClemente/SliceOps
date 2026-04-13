from unittest.mock import AsyncMock, patch, MagicMock
import pytest

from app.services.slicer import SliceResult, SliceParams
from app.worker.tasks import run_slice_job


class TestSliceTask:
    def test_run_slice_job_success(self, tmp_path):
        stl_path = tmp_path / "job-1" / "model.stl"
        stl_path.parent.mkdir()
        stl_path.write_bytes(b"solid cube\nendsolid cube")

        mock_result = SliceResult(
            estimated_time_seconds=3720,
            filament_used_grams=28.4,
            filament_used_meters=9.5,
            layer_count=150,
        )

        with patch("app.worker.tasks.get_slicer") as mock_get_slicer, \
             patch("app.worker.tasks.get_storage") as mock_get_storage, \
             patch("app.worker.tasks._run_async") as mock_run_async:

            mock_slicer = MagicMock()
            mock_get_slicer.return_value = mock_slicer
            mock_run_async.return_value = mock_result

            mock_storage = MagicMock()
            mock_get_storage.return_value = mock_storage
            mock_storage.get_job_dir.return_value = str(tmp_path / "job-1")

            result = run_slice_job(
                job_id="job-1",
                params_dict={
                    "layer_height": 0.2,
                    "infill_percent": 20,
                    "filament_type": "PLA",
                    "filament_cost": 20.0,
                },
            )

            assert result["estimated_time_seconds"] == 3720
            assert result["filament_used_grams"] == 28.4
            assert result["estimated_cost"] == 0.57
            mock_storage.delete_file.assert_called_once_with("job-1", "model.stl")

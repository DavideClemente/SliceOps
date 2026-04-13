import os
import time
from pathlib import Path

from app.storage.temp_storage import TempStorage


class TestTempStorage:
    def test_create_job_dir(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        job_id = "test-job-1"
        job_dir = storage.create_job_dir(job_id)
        assert Path(job_dir).exists()
        assert Path(job_dir).name == job_id

    def test_get_job_dir(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        job_dir = storage.get_job_dir("job-1")
        assert job_dir is not None
        assert Path(job_dir).exists()

    def test_get_job_dir_nonexistent(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        assert storage.get_job_dir("nonexistent") is None

    def test_save_file(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        content = b"solid cube\nendsolid cube"
        path = storage.save_file("job-1", "model.stl", content)
        assert Path(path).exists()
        assert Path(path).read_bytes() == content

    def test_get_file_path(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        path = storage.get_file_path("job-1", "model.stl")
        assert path is not None
        assert Path(path).exists()

    def test_get_file_path_nonexistent(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        assert storage.get_file_path("job-1", "missing.stl") is None

    def test_cleanup_job(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        storage.cleanup_job("job-1")
        assert not Path(tmp_path / "job-1").exists()

    def test_cleanup_nonexistent_job_no_error(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.cleanup_job("nonexistent")  # should not raise

    def test_delete_file(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("job-1")
        storage.save_file("job-1", "model.stl", b"data")
        storage.delete_file("job-1", "model.stl")
        assert storage.get_file_path("job-1", "model.stl") is None

    def test_sweep_expired_jobs(self, tmp_path):
        storage = TempStorage(base_dir=str(tmp_path))
        storage.create_job_dir("old-job")
        storage.save_file("old-job", "model.stl", b"data")
        # Backdate the directory mtime
        old_time = time.time() - 3600
        job_dir = tmp_path / "old-job"
        os.utime(job_dir, (old_time, old_time))

        storage.create_job_dir("new-job")
        storage.save_file("new-job", "model.stl", b"data")

        removed = storage.sweep_expired(ttl_minutes=15)
        assert "old-job" in removed
        assert not Path(tmp_path / "old-job").exists()
        assert Path(tmp_path / "new-job").exists()

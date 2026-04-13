import os
import shutil
import time
from pathlib import Path


class TempStorage:
    def __init__(self, base_dir: str) -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    def create_job_dir(self, job_id: str) -> str:
        job_dir = self._base / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return str(job_dir)

    def get_job_dir(self, job_id: str) -> str | None:
        job_dir = self._base / job_id
        if job_dir.exists():
            return str(job_dir)
        return None

    def save_file(self, job_id: str, filename: str, content: bytes) -> str:
        file_path = self._base / job_id / filename
        file_path.write_bytes(content)
        return str(file_path)

    def get_file_path(self, job_id: str, filename: str) -> str | None:
        file_path = self._base / job_id / filename
        if file_path.exists():
            return str(file_path)
        return None

    def delete_file(self, job_id: str, filename: str) -> None:
        file_path = self._base / job_id / filename
        if file_path.exists():
            file_path.unlink()

    def cleanup_job(self, job_id: str) -> None:
        job_dir = self._base / job_id
        if job_dir.exists():
            shutil.rmtree(job_dir)

    def sweep_expired(self, ttl_minutes: int) -> list[str]:
        cutoff = time.time() - (ttl_minutes * 60)
        removed: list[str] = []
        if not self._base.exists():
            return removed
        for entry in self._base.iterdir():
            if entry.is_dir() and entry.stat().st_mtime < cutoff:
                shutil.rmtree(entry)
                removed.append(entry.name)
        return removed

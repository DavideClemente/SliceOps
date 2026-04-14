import pytest
from unittest.mock import AsyncMock

from app.store.job_store import JobStore


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.hset = AsyncMock()
    r.hgetall = AsyncMock(return_value={})
    r.expire = AsyncMock()
    r.exists = AsyncMock(return_value=True)
    return r


@pytest.fixture
def job_store(mock_redis):
    return JobStore(mock_redis, ttl_seconds=3600)


class TestJobStore:
    async def test_set_stores_data(self, job_store, mock_redis):
        await job_store.set("job-1", {"status": "pending", "celery_task_id": "abc"})
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once_with("sliceops:job:job-1", 3600)

    async def test_get_returns_none_for_missing(self, job_store, mock_redis):
        mock_redis.hgetall.return_value = {}
        result = await job_store.get("nonexistent")
        assert result is None

    async def test_get_returns_deserialized_data(self, job_store, mock_redis):
        mock_redis.hgetall.return_value = {
            "status": "completed",
            "result": '{"time": 100}',
        }
        result = await job_store.get("job-1")
        assert result["status"] == "completed"
        assert result["result"] == {"time": 100}

    async def test_update_partial_fields(self, job_store, mock_redis):
        await job_store.update("job-1", status="completed")
        mock_redis.hset.assert_called_once()
        mock_redis.expire.assert_called_once()

    async def test_update_skips_missing_job(self, job_store, mock_redis):
        mock_redis.exists.return_value = False
        await job_store.update("nonexistent", status="completed")
        mock_redis.hset.assert_not_called()

import os

import pytest
from unittest.mock import AsyncMock

from httpx import AsyncClient, ASGITransport

from app.auth.models import ApiKeyData
from app.main import create_app
from app.config import Settings
from app.services.slicer import SliceResult


def _make_key(plan="free", active=True):
    return ApiKeyData(key="so_live_testkey", owner="tester", plan=plan, active=active, created_at="2025-01-01T00:00:00Z")


def _mock_redis_for_key(api_key_data: ApiKeyData):
    """Create a mock redis that returns cached key data."""
    mock_redis = AsyncMock()
    mock_redis.get.return_value = api_key_data.model_dump_json()
    mock_redis.setex.return_value = None
    return mock_redis


@pytest.fixture
def rl_app(mock_storage, mock_slicer, mock_job_store):
    """App with auth enabled + rate limiting."""
    os.environ["SLICEOPS_AUTH_ENABLED"] = "true"
    application = create_app()
    settings = Settings()
    settings.auth_enabled = True
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store

    # Mock redis to return cached key data
    application.state.redis = _mock_redis_for_key(_make_key())

    rate_limit_service = AsyncMock()
    rate_limit_service.check_rate_limit.return_value = (True, 5, 4, 60)
    rate_limit_service.check_monthly_quota.return_value = (True, 50, 0)
    rate_limit_service.increment_rate_limit.return_value = None
    rate_limit_service.increment_usage.return_value = None
    application.state.rate_limit_service = rate_limit_service

    os.environ["SLICEOPS_AUTH_ENABLED"] = "false"
    return application


@pytest.fixture
async def rl_client(rl_app):
    transport = ASGITransport(app=rl_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestRateLimit:
    async def test_under_limit_passes(self, rl_client, rl_app, mock_storage, tmp_path):
        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)
        mock_storage.get_job_dir.return_value = str(job_dir)

        resp = await rl_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 200

    async def test_over_rate_limit_returns_429(self, rl_client, rl_app):
        rl_app.state.rate_limit_service.check_rate_limit.return_value = (False, 5, 0, 45)

        resp = await rl_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 429
        assert "Retry-After" in resp.headers

    async def test_quota_exceeded_returns_429(self, rl_client, rl_app):
        rl_app.state.rate_limit_service.check_rate_limit.return_value = (True, 5, 4, 60)
        rl_app.state.rate_limit_service.check_monthly_quota.return_value = (False, 50, 50)

        resp = await rl_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 429
        assert "quota" in resp.json()["detail"].lower()

    async def test_paid_has_higher_limits(self, rl_client, rl_app, mock_storage, tmp_path):
        # Switch to paid plan via redis cache
        rl_app.state.redis = _mock_redis_for_key(_make_key(plan="pro"))
        rl_app.state.rate_limit_service.check_rate_limit.return_value = (True, 60, 59, 60)
        rl_app.state.rate_limit_service.check_monthly_quota.return_value = (True, 5000, 0)

        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)
        mock_storage.get_job_dir.return_value = str(job_dir)

        resp = await rl_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 200

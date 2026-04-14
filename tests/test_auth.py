import json
import os

import pytest
from unittest.mock import AsyncMock

from httpx import AsyncClient, ASGITransport

from app.auth.models import ApiKeyData
from app.main import create_app
from app.config import Settings
from app.services.slicer import SliceResult


def _make_key(key="so_live_testkey", owner="tester", plan="free", active=True):
    return ApiKeyData(key=key, owner=owner, plan=plan, active=active, created_at="2025-01-01T00:00:00Z")


def _mock_redis_for_key(api_key_data: ApiKeyData | None):
    """Create a mock redis that returns cached key data."""
    mock_redis = AsyncMock()
    if api_key_data is not None:
        mock_redis.get.return_value = api_key_data.model_dump_json()
    else:
        mock_redis.get.return_value = None
    mock_redis.setex.return_value = None
    return mock_redis


@pytest.fixture
def auth_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    """App with auth ENABLED."""
    os.environ["SLICEOPS_AUTH_ENABLED"] = "true"
    application = create_app()
    settings = Settings()
    settings.auth_enabled = True
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service

    # Default: no key in cache, no key in DB → 401
    application.state.redis = _mock_redis_for_key(None)

    os.environ["SLICEOPS_AUTH_ENABLED"] = "false"
    return application


@pytest.fixture
async def auth_client(auth_app):
    transport = ASGITransport(app=auth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAuthRequired:
    async def test_missing_api_key_returns_401(self, auth_client):
        resp = await auth_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
        )
        assert resp.status_code == 401

    async def test_invalid_api_key_returns_401(self, auth_client, auth_app):
        # Redis cache miss, DB lookup returns None
        auth_app.state.redis = _mock_redis_for_key(None)
        with pytest.MonkeyPatch.context() as m:
            m.setattr("app.auth.dependencies._lookup_key_in_db", AsyncMock(return_value=None))
            resp = await auth_client.post(
                "/api/v1/slice",
                files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
                headers={"X-API-Key": "invalid_key"},
            )
        assert resp.status_code == 401

    async def test_revoked_key_returns_403(self, auth_client, auth_app):
        # Return a revoked key from cache
        revoked_key = _make_key(active=False)
        auth_app.state.redis = _mock_redis_for_key(revoked_key)
        resp = await auth_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 403

    async def test_valid_key_allows_access(self, auth_client, auth_app, mock_storage, tmp_path):
        # Return a valid key from cache
        valid_key = _make_key(active=True)
        auth_app.state.redis = _mock_redis_for_key(valid_key)

        job_dir = tmp_path / "test-job"
        job_dir.mkdir()
        mock_storage.create_job_dir.return_value = str(job_dir)
        mock_storage.get_job_dir.return_value = str(job_dir)

        resp = await auth_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
            headers={"X-API-Key": "so_live_testkey"},
        )
        assert resp.status_code == 200


class TestHealthUnauthenticated:
    async def test_health_no_auth_needed(self, auth_client):
        resp = await auth_client.get("/api/v1/health")
        assert resp.status_code == 200

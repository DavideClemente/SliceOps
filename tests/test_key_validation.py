import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.models import ApiKeyData
from app.db.models import ApiKey, User
from app.main import create_app


@pytest.fixture
def key_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    import os
    os.environ["SLICEOPS_AUTH_ENABLED"] = "true"
    application = create_app()
    settings = Settings()
    settings.auth_enabled = True
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    mock_redis.setex.return_value = None
    application.state.redis = mock_redis

    os.environ["SLICEOPS_AUTH_ENABLED"] = "false"
    return application


@pytest.fixture
async def key_client(key_app):
    transport = ASGITransport(app=key_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestKeyValidationWithPostgres:
    async def test_missing_key_returns_401(self, key_client):
        resp = await key_client.post(
            "/api/v1/slice",
            files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
        )
        assert resp.status_code == 401

    async def test_invalid_key_returns_401(self, key_client):
        with patch("app.auth.dependencies._lookup_key_in_db", return_value=None):
            resp = await key_client.post(
                "/api/v1/slice",
                files={"file": ("cube.stl", b"solid cube\nendsolid cube", "application/octet-stream")},
                headers={"X-API-Key": "so_live_invalid"},
            )
        assert resp.status_code == 401

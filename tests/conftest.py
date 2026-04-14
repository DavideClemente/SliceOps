import os

import pytest
from unittest.mock import MagicMock, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.services.slicer import SliceResult
from app.config import Settings

# Disable auth for existing tests by default
os.environ.setdefault("SLICEOPS_AUTH_ENABLED", "false")


@pytest.fixture
def mock_storage(tmp_path):
    storage = MagicMock()
    storage.create_job_dir.side_effect = lambda jid: str(tmp_path / jid)
    storage.get_job_dir.side_effect = lambda jid: str(tmp_path / jid) if (tmp_path / jid).exists() else None
    storage.save_file.side_effect = lambda jid, name, content: str(tmp_path / jid / name)
    storage.get_file_path.return_value = None
    storage.delete_file.return_value = None
    storage.cleanup_job.return_value = None
    return storage


@pytest.fixture
def mock_slicer():
    slicer = AsyncMock()
    slicer.slice.return_value = SliceResult(
        estimated_time_seconds=3720,
        filament_used_grams=28.4,
        filament_used_meters=9.5,
        layer_count=150,
    )
    return slicer


@pytest.fixture
def mock_job_store():
    store = AsyncMock()
    store.get.return_value = None
    store.set.return_value = None
    store.update.return_value = None
    return store


@pytest.fixture
def mock_auth_service():
    service = AsyncMock()
    service.validate_key.return_value = None
    service.create_key.return_value = None
    service.revoke_key.return_value = False
    service.list_keys.return_value = []
    return service


@pytest.fixture
def mock_rate_limit_service():
    service = AsyncMock()
    # Default: allow everything
    service.check_rate_limit.return_value = (True, 60, 59, 60)
    service.check_monthly_quota.return_value = (True, 5000, 0)
    service.increment_rate_limit.return_value = None
    service.increment_usage.return_value = None
    return service


@pytest.fixture
def app(mock_storage, mock_slicer, mock_job_store, mock_auth_service, mock_rate_limit_service):
    application = create_app()
    application.state.settings = Settings()
    application.state.storage = mock_storage
    application.state.slicers = {
        "prusa-slicer": mock_slicer,
        "bambu-studio": mock_slicer,
    }
    application.state.job_store = mock_job_store
    application.state.auth_service = mock_auth_service
    application.state.rate_limit_service = mock_rate_limit_service
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_stl():
    return b"solid cube\n  facet normal 0 0 -1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n      vertex 1 1 0\n    endloop\n  endfacet\nendsolid cube"


@pytest.fixture
def auth_headers():
    return {"X-API-Key": "so_live_test_key_for_auth_tests"}

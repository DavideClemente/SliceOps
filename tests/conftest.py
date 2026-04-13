import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.services.slicer import SliceResult


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
def app(mock_storage, mock_slicer):
    application = create_app()
    application.state.storage = mock_storage
    application.state.slicer = mock_slicer
    return application


@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def sample_stl():
    return b"solid cube\n  facet normal 0 0 -1\n    outer loop\n      vertex 0 0 0\n      vertex 1 0 0\n      vertex 1 1 0\n    endloop\n  endfacet\nendsolid cube"

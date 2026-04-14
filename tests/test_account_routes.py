import secrets
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.jwt import create_access_token
from app.db.models import ApiKey, User
from app.main import create_app


@pytest.fixture
def account_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    settings.jwt_secret = "test-jwt-secret"
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def account_client(account_app):
    transport = ASGITransport(app=account_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


def _make_token(user_id: uuid.UUID, plan: str = "free") -> str:
    return create_access_token(
        user_id=user_id, plan=plan, secret="test-jwt-secret", expires_minutes=30
    )


def _make_api_key(user_id: uuid.UUID) -> ApiKey:
    return ApiKey(
        id=uuid.uuid4(),
        user_id=user_id,
        key="so_live_" + secrets.token_urlsafe(32),
        active=True,
        created_at=datetime.now(timezone.utc),
    )


class TestGetKey:
    async def test_no_key_returns_empty(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            resp = await account_client.get(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        assert resp.json()["key"] is None

    async def test_returns_existing_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            resp = await account_client.get(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["key"] == api_key.key
        assert body["active"] is True


class TestCreateKey:
    async def test_creates_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            with patch("app.api.account_routes._create_api_key", return_value=api_key):
                resp = await account_client.post(
                    "/account/keys",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 201
        assert resp.json()["key"] == api_key.key

    async def test_conflict_if_key_exists(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            resp = await account_client.post(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 409


class TestDeleteKey:
    async def test_deletes_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)
        api_key = _make_api_key(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=api_key):
            with patch("app.api.account_routes._revoke_api_key", return_value=True):
                resp = await account_client.delete(
                    "/account/keys",
                    headers={"Authorization": f"Bearer {token}"},
                )
        assert resp.status_code == 200

    async def test_404_if_no_key(self, account_client, account_app):
        user_id = uuid.uuid4()
        token = _make_token(user_id)

        with patch("app.api.account_routes._get_user_api_key", return_value=None):
            resp = await account_client.delete(
                "/account/keys",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 404


class TestUnauthorized:
    async def test_no_token_returns_401(self, account_client):
        resp = await account_client.get("/account/keys")
        assert resp.status_code == 401

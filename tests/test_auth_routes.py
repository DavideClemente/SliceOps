import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.auth.jwt import create_access_token, create_refresh_token
from app.db.models import User
from app.main import create_app


@pytest.fixture
def oauth_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def oauth_client(oauth_app):
    transport = ASGITransport(app=oauth_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestGitHubRedirect:
    async def test_returns_redirect_url(self, oauth_client, oauth_app):
        oauth_app.state.settings.github_client_id = "test-client-id"
        oauth_app.state.settings.base_url = "http://localhost:8000"
        resp = await oauth_client.get("/auth/github")
        assert resp.status_code == 200
        body = resp.json()
        assert "url" in body
        assert "github.com" in body["url"]
        assert "test-client-id" in body["url"]


class TestGitHubCallback:
    async def test_callback_creates_user_and_returns_tokens(self, oauth_client, oauth_app):
        oauth_app.state.settings.github_client_id = "test-id"
        oauth_app.state.settings.github_client_secret = "test-secret"
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        oauth_app.state.settings.base_url = "http://localhost:8000"

        mock_user = User(
            id=uuid.uuid4(),
            github_id=12345,
            github_username="testuser",
            email="test@example.com",
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes.GitHubOAuth") as MockOAuth:
            mock_oauth = AsyncMock()
            mock_oauth.exchange_code.return_value = "gho_abc123"
            mock_oauth.get_user_info.return_value = {
                "id": 12345,
                "login": "testuser",
                "email": "test@example.com",
            }
            MockOAuth.return_value = mock_oauth

            with patch("app.api.auth_routes._get_or_create_user", return_value=mock_user):
                resp = await oauth_client.get("/auth/callback?code=test-code")

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"

    async def test_callback_missing_code_returns_400(self, oauth_client):
        resp = await oauth_client.get("/auth/callback")
        assert resp.status_code == 400


class TestRefreshToken:
    async def test_refresh_returns_new_access_token(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"

        user_id = uuid.uuid4()
        refresh = create_refresh_token(user_id=user_id, secret="test-jwt-secret", expires_days=30)

        mock_user = User(
            id=user_id,
            github_id=12345,
            github_username="testuser",
            email=None,
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes._get_user_by_id", return_value=mock_user):
            resp = await oauth_client.post(
                "/auth/refresh",
                json={"refresh_token": refresh},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body

    async def test_refresh_with_invalid_token_returns_401(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        resp = await oauth_client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid-token"},
        )
        assert resp.status_code == 401


class TestMeEndpoint:
    async def test_me_returns_user_info(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-jwt-secret", expires_minutes=30
        )

        mock_user = User(
            id=user_id,
            github_id=12345,
            github_username="testuser",
            email="test@example.com",
            plan="free",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.auth_routes._get_user_by_id", return_value=mock_user):
            resp = await oauth_client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )

        assert resp.status_code == 200
        body = resp.json()
        assert body["github_username"] == "testuser"
        assert body["plan"] == "free"

    async def test_me_without_token_returns_401(self, oauth_client, oauth_app):
        oauth_app.state.settings.jwt_secret = "test-jwt-secret"
        resp = await oauth_client.get("/auth/me")
        assert resp.status_code == 401

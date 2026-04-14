import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.auth.oauth import GitHubOAuth


class TestGitHubOAuth:
    def test_get_authorization_url(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")
        url = oauth.get_authorization_url(redirect_uri="http://localhost/callback")
        assert "github.com" in url
        assert "client_id=test-id" in url
        assert "redirect_uri=" in url

    @pytest.mark.asyncio
    async def test_exchange_code_for_token(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")

        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value={"access_token": "gho_abc123"})
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", return_value=mock_response):
            token = await oauth.exchange_code("test-code", redirect_uri="http://localhost/callback")
        assert token == "gho_abc123"

    @pytest.mark.asyncio
    async def test_get_user_info(self):
        oauth = GitHubOAuth(client_id="test-id", client_secret="test-secret")

        mock_response = AsyncMock()
        mock_response.json = MagicMock(return_value={
            "id": 12345,
            "login": "testuser",
            "email": "test@example.com",
        })
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", return_value=mock_response):
            user_info = await oauth.get_user_info("gho_abc123")
        assert user_info["id"] == 12345
        assert user_info["login"] == "testuser"
        assert user_info["email"] == "test@example.com"

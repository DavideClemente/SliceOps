import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest

from app.auth.jwt import create_access_token, create_refresh_token, decode_token


class TestCreateAccessToken:
    def test_creates_valid_token(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=30
        )
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_expected_claims(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=30
        )
        payload = decode_token(token, secret="test-secret")
        assert payload["sub"] == str(user_id)
        assert payload["plan"] == "free"
        assert payload["type"] == "access"


class TestCreateRefreshToken:
    def test_creates_valid_token(self):
        user_id = uuid.uuid4()
        token = create_refresh_token(
            user_id=user_id, secret="test-secret", expires_days=30
        )
        payload = decode_token(token, secret="test-secret")
        assert payload["sub"] == str(user_id)
        assert payload["type"] == "refresh"


class TestDecodeToken:
    def test_invalid_token_returns_none(self):
        result = decode_token("garbage.token.here", secret="test-secret")
        assert result is None

    def test_wrong_secret_returns_none(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="secret-a", expires_minutes=30
        )
        result = decode_token(token, secret="secret-b")
        assert result is None

    def test_expired_token_returns_none(self):
        user_id = uuid.uuid4()
        token = create_access_token(
            user_id=user_id, plan="free", secret="test-secret", expires_minutes=-1
        )
        result = decode_token(token, secret="test-secret")
        assert result is None

"""Tests for new config settings added in Task 2."""
from app.config import Settings


def test_database_url_default():
    s = Settings()
    assert s.database_url == "postgresql+asyncpg://sliceops:sliceops@localhost:5432/sliceops"


def test_github_oauth_fields_exist():
    s = Settings()
    assert isinstance(s.github_client_id, str)
    assert isinstance(s.github_client_secret, str)


def test_stripe_fields_exist():
    s = Settings()
    assert isinstance(s.stripe_secret_key, str)
    assert isinstance(s.stripe_webhook_secret, str)
    assert isinstance(s.stripe_pro_price_id, str)


def test_jwt_fields_exist_with_defaults():
    s = Settings()
    assert isinstance(s.jwt_secret, str)
    assert s.jwt_access_token_minutes == 30
    assert s.jwt_refresh_token_days == 30


def test_base_url_default():
    s = Settings()
    assert s.base_url == "http://localhost:8000"

import pytest
from unittest.mock import AsyncMock

from app.rate_limit.service import RateLimitService


@pytest.fixture
def mock_redis():
    return AsyncMock()


@pytest.fixture
def service(mock_redis):
    return RateLimitService(redis_client=mock_redis, requests_per_minute=10)


class TestRateLimitService:
    async def test_under_limit_allowed(self, service, mock_redis):
        mock_redis.get.return_value = "5"
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is True
        assert limit == 10
        assert remaining == 4

    async def test_at_limit_blocked(self, service, mock_redis):
        mock_redis.get.return_value = "10"
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is False
        assert remaining == 0

    async def test_no_previous_requests(self, service, mock_redis):
        mock_redis.get.return_value = None
        allowed, limit, remaining, reset = await service.check("192.168.1.1")
        assert allowed is True
        assert remaining == 9

    async def test_increment(self, service, mock_redis):
        await service.increment("192.168.1.1")
        mock_redis.incr.assert_called_once()
        mock_redis.expire.assert_called_once()


from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app.rate_limit.dependencies import require_rate_limit


class TestRateLimitDependency:
    async def test_allowed_sets_headers(self):
        mock_service = AsyncMock()
        mock_service.check.return_value = (True, 10, 9, 55)
        mock_service.increment.return_value = None

        request = MagicMock()
        request.app.state.rate_limit_service = mock_service
        request.client.host = "1.2.3.4"
        request.state = MagicMock()

        await require_rate_limit(request)

        mock_service.check.assert_called_once_with("1.2.3.4")
        mock_service.increment.assert_called_once_with("1.2.3.4")
        assert request.state.rate_limit_headers == {
            "X-RateLimit-Limit": "10",
            "X-RateLimit-Remaining": "9",
            "X-RateLimit-Reset": "55",
        }

    async def test_blocked_raises_429(self):
        mock_service = AsyncMock()
        mock_service.check.return_value = (False, 10, 0, 45)

        request = MagicMock()
        request.app.state.rate_limit_service = mock_service
        request.client.host = "1.2.3.4"

        with pytest.raises(HTTPException) as exc_info:
            await require_rate_limit(request)
        assert exc_info.value.status_code == 429

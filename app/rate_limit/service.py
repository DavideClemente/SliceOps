from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import Settings


class RateLimitService:
    def __init__(self, redis_client: Redis, settings: Settings) -> None:
        self._redis = redis_client
        self._settings = settings

    async def check_rate_limit(self, key: str, plan: str) -> tuple[bool, int, int, int]:
        """Returns (allowed, limit, remaining, reset_seconds)."""
        limits = self._settings.get_plan_limits(plan)
        rate_limit = limits.rate_limit
        now = datetime.now(timezone.utc)
        minute_key = f"sliceops:ratelimit:{key}:{now.strftime('%Y%m%d%H%M')}"

        current = await self._redis.get(minute_key)
        count = int(current) if current else 0

        remaining = max(0, rate_limit - count)
        reset_seconds = 60 - now.second

        if count >= rate_limit:
            return False, rate_limit, 0, reset_seconds

        return True, rate_limit, remaining - 1, reset_seconds

    async def increment_rate_limit(self, key: str) -> None:
        now = datetime.now(timezone.utc)
        minute_key = f"sliceops:ratelimit:{key}:{now.strftime('%Y%m%d%H%M')}"
        await self._redis.incr(minute_key)
        await self._redis.expire(minute_key, 120)

    async def check_monthly_quota(self, key: str, plan: str) -> tuple[bool, int, int]:
        """Returns (allowed, quota, used)."""
        limits = self._settings.get_plan_limits(plan)
        quota = limits.monthly_quota
        now = datetime.now(timezone.utc)
        month_key = f"sliceops:usage:{key}:{now.strftime('%Y-%m')}"

        current = await self._redis.get(month_key)
        used = int(current) if current else 0

        return used < quota, quota, used

    async def increment_usage(self, key: str) -> None:
        now = datetime.now(timezone.utc)
        month_key = f"sliceops:usage:{key}:{now.strftime('%Y-%m')}"
        await self._redis.incr(month_key)
        # Expire after ~90 days
        await self._redis.expire(month_key, 90 * 86400)

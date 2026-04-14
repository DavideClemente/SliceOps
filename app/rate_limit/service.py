from datetime import datetime, timezone

from redis.asyncio import Redis


class RateLimitService:
    def __init__(self, redis_client: Redis, requests_per_minute: int = 10) -> None:
        self._redis = redis_client
        self._limit = requests_per_minute

    async def check(self, client_ip: str) -> tuple[bool, int, int, int]:
        """Returns (allowed, limit, remaining, reset_seconds)."""
        now = datetime.now(timezone.utc)
        key = f"sliceops:ratelimit:{client_ip}:{now.strftime('%Y%m%d%H%M')}"

        current = await self._redis.get(key)
        count = int(current) if current else 0

        remaining = max(0, self._limit - count)
        reset_seconds = 60 - now.second

        if count >= self._limit:
            return False, self._limit, 0, reset_seconds

        return True, self._limit, remaining - 1, reset_seconds

    async def increment(self, client_ip: str) -> None:
        now = datetime.now(timezone.utc)
        key = f"sliceops:ratelimit:{client_ip}:{now.strftime('%Y%m%d%H%M')}"
        await self._redis.incr(key)
        await self._redis.expire(key, 120)

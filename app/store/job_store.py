import json

from redis.asyncio import Redis


class JobStore:
    def __init__(self, redis_client: Redis, ttl_seconds: int = 3600) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, job_id: str) -> str:
        return f"sliceops:job:{job_id}"

    async def set(self, job_id: str, data: dict) -> None:
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
        key = self._key(job_id)
        await self._redis.hset(key, mapping=serialized)
        await self._redis.expire(key, self._ttl)

    async def get(self, job_id: str) -> dict | None:
        data = await self._redis.hgetall(self._key(job_id))
        if not data:
            return None
        return self._deserialize(data)

    async def update(self, job_id: str, **fields: object) -> None:
        key = self._key(job_id)
        if not await self._redis.exists(key):
            return
        serialized = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in fields.items()}
        await self._redis.hset(key, mapping=serialized)
        await self._redis.expire(key, self._ttl)

    @staticmethod
    def _deserialize(data: dict[str, str]) -> dict:
        result = {}
        for k, v in data.items():
            try:
                result[k] = json.loads(v)
            except (json.JSONDecodeError, TypeError):
                result[k] = v
        return result

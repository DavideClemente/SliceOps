import secrets
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.auth.models import ApiKeyData


class AuthService:
    def __init__(self, redis_client: Redis, valid_plans: list[str] | None = None) -> None:
        self._redis = redis_client
        self._valid_plans = valid_plans

    def _key(self, api_key: str) -> str:
        return f"sliceops:apikey:{api_key}"

    async def create_key(self, owner: str, plan: str = "free") -> ApiKeyData:
        if self._valid_plans and plan not in self._valid_plans:
            raise ValueError(f"Unknown plan: '{plan}'. Available: {self._valid_plans}")
        key = "so_live_" + secrets.token_urlsafe(32)
        data = ApiKeyData(
            key=key,
            owner=owner,
            plan=plan,
            active=True,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        await self._redis.hset(self._key(key), mapping={
            "key": data.key,
            "owner": data.owner,
            "plan": data.plan,
            "active": "1",
            "created_at": data.created_at,
        })
        return data

    async def validate_key(self, key: str) -> ApiKeyData | None:
        data = await self._redis.hgetall(self._key(key))
        if not data:
            return None
        return ApiKeyData(
            key=data["key"],
            owner=data["owner"],
            plan=data["plan"],
            active=data["active"] == "1",
            created_at=data["created_at"],
        )

    async def revoke_key(self, key: str) -> bool:
        redis_key = self._key(key)
        if not await self._redis.exists(redis_key):
            return False
        await self._redis.hset(redis_key, "active", "0")
        return True

    async def list_keys(self) -> list[ApiKeyData]:
        keys: list[ApiKeyData] = []
        async for redis_key in self._redis.scan_iter("sliceops:apikey:*"):
            data = await self._redis.hgetall(redis_key)
            if data:
                keys.append(ApiKeyData(
                    key=data["key"],
                    owner=data["owner"],
                    plan=data["plan"],
                    active=data["active"] == "1",
                    created_at=data["created_at"],
                ))
        return keys

    async def get_usage(self, key: str) -> dict:
        now = datetime.now(timezone.utc)
        month_key = f"sliceops:usage:{key}:{now.strftime('%Y-%m')}"
        count = await self._redis.get(month_key)
        return {
            "key": key,
            "month": now.strftime("%Y-%m"),
            "slice_count": int(count) if count else 0,
        }

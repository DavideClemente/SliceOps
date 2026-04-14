import json

from fastapi import Request, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.auth.models import ApiKeyData
from app.config import Settings
from app.db.engine import get_session_factory
from app.db.models import ApiKey


CACHE_TTL = 60  # seconds


async def _lookup_key_in_db(key: str) -> ApiKey | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiKey).options(joinedload(ApiKey.user)).where(ApiKey.key == key)
        )
        return result.scalar_one_or_none()


async def get_api_key(request: Request) -> ApiKeyData:
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        return ApiKeyData(
            key="disabled",
            owner="anonymous",
            plan="pro",
            active=True,
            created_at="",
        )

    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    redis = request.app.state.redis

    # Check Redis cache first
    cache_key = f"sliceops:keycache:{key}"
    cached = await redis.get(cache_key)
    if cached:
        data = json.loads(cached)
        if not data["active"]:
            raise HTTPException(status_code=403, detail="API key has been revoked")
        return ApiKeyData(**data)

    # Fallback to Postgres
    api_key = await _lookup_key_in_db(key)
    if api_key is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not api_key.active:
        raise HTTPException(status_code=403, detail="API key has been revoked")

    key_data = ApiKeyData(
        key=api_key.key,
        owner=api_key.user.github_username,
        plan=api_key.user.plan,
        active=api_key.active,
        created_at=api_key.created_at.isoformat(),
    )

    # Cache in Redis
    await redis.setex(cache_key, CACHE_TTL, key_data.model_dump_json())

    return key_data

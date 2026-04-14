import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.auth_routes import _require_jwt
from app.auth.models import ApiKeyResponse
from app.db.engine import get_session_factory
from app.db.models import ApiKey

account_router = APIRouter(prefix="/account", tags=["account"])


async def _get_user_api_key(user_id: uuid.UUID) -> ApiKey | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(ApiKey).where(ApiKey.user_id == user_id, ApiKey.active.is_(True))
        )
        return result.scalar_one_or_none()


async def _create_api_key(user_id: uuid.UUID) -> ApiKey:
    key_value = "so_live_" + secrets.token_urlsafe(32)
    session_factory = get_session_factory()
    async with session_factory() as session:
        api_key = ApiKey(user_id=user_id, key=key_value)
        session.add(api_key)
        await session.commit()
        await session.refresh(api_key)
        return api_key


async def _revoke_api_key(api_key: ApiKey) -> bool:
    session_factory = get_session_factory()
    async with session_factory() as session:
        api_key = await session.get(ApiKey, api_key.id)
        if api_key is None:
            return False
        api_key.active = False
        await session.commit()
        return True


@account_router.get("/keys")
async def get_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    api_key = await _get_user_api_key(user_id)
    if api_key is None:
        return {"key": None, "active": None, "created_at": None}
    return ApiKeyResponse(key=api_key.key, active=api_key.active, created_at=api_key.created_at)


@account_router.post("/keys", status_code=201)
async def create_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    existing = await _get_user_api_key(user_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="API key already exists. Revoke it first to generate a new one.")
    api_key = await _create_api_key(user_id)
    return ApiKeyResponse(key=api_key.key, active=api_key.active, created_at=api_key.created_at)


@account_router.delete("/keys")
async def delete_key(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    api_key = await _get_user_api_key(user_id)
    if api_key is None:
        raise HTTPException(status_code=404, detail="No active API key found")
    await _revoke_api_key(api_key)
    return {"status": "revoked"}

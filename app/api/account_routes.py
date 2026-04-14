import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.api.auth_routes import _require_jwt
from app.auth.models import ApiKeyResponse, BillingStatusResponse
from app.billing.service import BillingService
from app.db.engine import get_session_factory
from app.db.models import ApiKey, User

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


async def _get_user(user_id: uuid.UUID) -> User | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()


@account_router.get("/billing")
async def get_billing(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return BillingStatusResponse(
        plan=user.plan,
        stripe_customer_id=user.stripe_customer_id,
        stripe_subscription_id=user.stripe_subscription_id,
    )


@account_router.post("/billing/checkout")
async def create_checkout(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.plan == "pro":
        raise HTTPException(status_code=400, detail="Already on Pro plan. Use billing portal to manage subscription.")

    settings = request.app.state.settings
    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )
    url = billing.create_checkout_session(
        user_id=user.id,
        customer_email=user.email or "",
        success_url=f"{settings.base_url}/account/billing?success=true",
        cancel_url=f"{settings.base_url}/account/billing?cancelled=true",
        stripe_customer_id=user.stripe_customer_id,
    )
    return {"checkout_url": url}


@account_router.post("/billing/portal")
async def create_portal(request: Request):
    payload = _require_jwt(request)
    user_id = uuid.UUID(payload["sub"])
    user = await _get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account found. Subscribe to Pro first.")

    settings = request.app.state.settings
    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )
    url = billing.create_portal_session(
        customer_id=user.stripe_customer_id,
        return_url=f"{settings.base_url}/account/billing",
    )
    return {"portal_url": url}

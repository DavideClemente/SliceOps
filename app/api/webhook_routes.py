import uuid
import logging

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.billing.service import BillingService
from app.db.engine import get_session_factory
from app.db.models import User

logger = logging.getLogger("sliceops.webhooks")

webhook_router = APIRouter(prefix="/webhooks", tags=["webhooks"])


async def _update_user_plan(
    user_id: uuid.UUID,
    plan: str,
    stripe_customer_id: str | None = None,
    stripe_subscription_id: str | None = None,
) -> None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user is None:
            logger.warning("Webhook: user not found", extra={"user_id": str(user_id)})
            return
        user.plan = plan
        if stripe_customer_id:
            user.stripe_customer_id = stripe_customer_id
        if stripe_subscription_id:
            user.stripe_subscription_id = stripe_subscription_id
        await session.commit()


async def _get_user_by_stripe_customer(customer_id: str) -> User | None:
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(
            select(User).where(User.stripe_customer_id == customer_id)
        )
        return result.scalar_one_or_none()


@webhook_router.post("/stripe")
async def stripe_webhook(request: Request):
    settings = request.app.state.settings
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    billing = BillingService(
        secret_key=settings.stripe_secret_key,
        webhook_secret=settings.stripe_webhook_secret,
        pro_price_id=settings.stripe_pro_price_id,
    )

    try:
        event = billing.verify_webhook(
            payload=payload,
            sig_header=sig_header,
            webhook_secret=settings.stripe_webhook_secret,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.type
    data = event.data.object

    if event_type == "checkout.session.completed":
        user_id_str = data.get("metadata", {}).get("user_id")
        if user_id_str:
            await _update_user_plan(
                user_id=uuid.UUID(user_id_str),
                plan="pro",
                stripe_customer_id=data.get("customer"),
                stripe_subscription_id=data.get("subscription"),
            )
            logger.info("User upgraded to pro", extra={"user_id": user_id_str})

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer")
        if customer_id:
            user = await _get_user_by_stripe_customer(customer_id)
            if user:
                await _update_user_plan(
                    user_id=user.id,
                    plan="free",
                    stripe_subscription_id=None,
                )
                logger.info("User downgraded to free", extra={"user_id": str(user.id)})

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer")
        if customer_id:
            user = await _get_user_by_stripe_customer(customer_id)
            if user:
                logger.info("Subscription updated", extra={"user_id": str(user.id)})

    return {"status": "ok"}

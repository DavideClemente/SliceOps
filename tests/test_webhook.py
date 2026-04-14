import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.db.models import User
from app.main import create_app


@pytest.fixture
def webhook_app(mock_storage, mock_slicer, mock_job_store, mock_rate_limit_service):
    from app.config import Settings
    application = create_app()
    settings = Settings()
    settings.stripe_secret_key = "sk_test_123"
    settings.stripe_webhook_secret = "whsec_test"
    settings.stripe_pro_price_id = "price_123"
    application.state.settings = settings
    application.state.storage = mock_storage
    application.state.slicers = {"prusa-slicer": mock_slicer, "bambu-studio": mock_slicer}
    application.state.job_store = mock_job_store
    application.state.rate_limit_service = mock_rate_limit_service
    application.state.auth_service = AsyncMock()
    return application


@pytest.fixture
async def webhook_client(webhook_app):
    transport = ASGITransport(app=webhook_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestStripeWebhook:
    async def test_checkout_completed_upgrades_user(self, webhook_client, webhook_app):
        user_id = uuid.uuid4()

        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"
        mock_event.data.object = {
            "metadata": {"user_id": str(user_id)},
            "customer": "cus_123",
            "subscription": "sub_123",
        }

        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.return_value = mock_event
            MockBilling.return_value = mock_billing

            with patch("app.api.webhook_routes._update_user_plan") as mock_update:
                mock_update.return_value = None
                resp = await webhook_client.post(
                    "/webhooks/stripe",
                    content=b'{"type": "checkout.session.completed"}',
                    headers={"stripe-signature": "test-sig"},
                )

        assert resp.status_code == 200
        mock_update.assert_called_once_with(
            user_id=user_id,
            plan="pro",
            stripe_customer_id="cus_123",
            stripe_subscription_id="sub_123",
        )

    async def test_subscription_deleted_downgrades_user(self, webhook_client, webhook_app):
        user_id = uuid.uuid4()

        mock_event = MagicMock()
        mock_event.type = "customer.subscription.deleted"
        mock_event.data.object = {
            "metadata": {"user_id": str(user_id)},
            "customer": "cus_123",
        }

        mock_user = User(
            id=user_id,
            github_id=123,
            github_username="test",
            plan="pro",
            stripe_customer_id="cus_123",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.return_value = mock_event
            MockBilling.return_value = mock_billing

            with patch("app.api.webhook_routes._get_user_by_stripe_customer", return_value=mock_user):
                with patch("app.api.webhook_routes._update_user_plan") as mock_update:
                    mock_update.return_value = None
                    resp = await webhook_client.post(
                        "/webhooks/stripe",
                        content=b'{"type": "customer.subscription.deleted"}',
                        headers={"stripe-signature": "test-sig"},
                    )

        assert resp.status_code == 200

    async def test_invalid_signature_returns_400(self, webhook_client, webhook_app):
        with patch("app.api.webhook_routes.BillingService") as MockBilling:
            mock_billing = MagicMock()
            mock_billing.verify_webhook.side_effect = ValueError("bad sig")
            MockBilling.return_value = mock_billing

            resp = await webhook_client.post(
                "/webhooks/stripe",
                content=b"bad",
                headers={"stripe-signature": "bad-sig"},
            )
        assert resp.status_code == 400

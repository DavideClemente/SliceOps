import uuid
from unittest.mock import patch, MagicMock

import pytest

from app.billing.service import BillingService


class TestCreateCheckoutSession:
    def test_creates_session_and_returns_url(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            url = svc.create_checkout_session(
                user_id=uuid.uuid4(),
                customer_email="test@example.com",
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
            )
        assert url == "https://checkout.stripe.com/pay/cs_test_abc"
        mock_create.assert_called_once()

    def test_uses_existing_customer_id(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://checkout.stripe.com/pay/cs_test_abc"

        with patch("stripe.checkout.Session.create", return_value=mock_session) as mock_create:
            svc.create_checkout_session(
                user_id=uuid.uuid4(),
                customer_email="test@example.com",
                success_url="http://localhost/success",
                cancel_url="http://localhost/cancel",
                stripe_customer_id="cus_existing",
            )
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["customer"] == "cus_existing"
        assert "customer_email" not in call_kwargs


class TestCreatePortalSession:
    def test_creates_portal_session(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_123",
            pro_price_id="price_123",
        )
        mock_session = MagicMock()
        mock_session.url = "https://billing.stripe.com/p/session/test"

        with patch("stripe.billing_portal.Session.create", return_value=mock_session):
            url = svc.create_portal_session(
                customer_id="cus_123",
                return_url="http://localhost/account",
            )
        assert url == "https://billing.stripe.com/p/session/test"


class TestVerifyWebhook:
    def test_valid_signature(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            pro_price_id="price_123",
        )
        mock_event = MagicMock()
        mock_event.type = "checkout.session.completed"

        with patch("stripe.Webhook.construct_event", return_value=mock_event):
            event = svc.verify_webhook(payload=b"body", sig_header="sig", webhook_secret="whsec_test")
        assert event.type == "checkout.session.completed"

    def test_invalid_signature_raises(self):
        svc = BillingService(
            secret_key="sk_test_123",
            webhook_secret="whsec_test",
            pro_price_id="price_123",
        )
        import stripe
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.error.SignatureVerificationError("bad sig", "sig"),
        ):
            with pytest.raises(ValueError):
                svc.verify_webhook(payload=b"body", sig_header="sig", webhook_secret="whsec_test")

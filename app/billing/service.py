import uuid

import stripe


class BillingService:
    def __init__(self, secret_key: str, webhook_secret: str, pro_price_id: str) -> None:
        self.secret_key = secret_key
        self.webhook_secret = webhook_secret
        self.pro_price_id = pro_price_id
        stripe.api_key = secret_key

    def create_checkout_session(
        self,
        user_id: uuid.UUID,
        customer_email: str,
        success_url: str,
        cancel_url: str,
        stripe_customer_id: str | None = None,
    ) -> str:
        params: dict = {
            "mode": "subscription",
            "line_items": [{"price": self.pro_price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": {"user_id": str(user_id)},
        }
        if stripe_customer_id:
            params["customer"] = stripe_customer_id
        else:
            params["customer_email"] = customer_email

        session = stripe.checkout.Session.create(**params)
        return session.url

    def create_portal_session(self, customer_id: str, return_url: str) -> str:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=return_url,
        )
        return session.url

    def verify_webhook(self, payload: bytes, sig_header: str, webhook_secret: str):
        try:
            return stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        except stripe.error.SignatureVerificationError as e:
            raise ValueError(f"Invalid webhook signature: {e}")

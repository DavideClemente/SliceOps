import uuid
from datetime import datetime, timedelta, timezone

import jwt


def create_access_token(
    user_id: uuid.UUID, plan: str, secret: str, expires_minutes: int = 30
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "plan": plan,
        "type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=expires_minutes),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    user_id: uuid.UUID, secret: str, expires_days: int = 30
) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=expires_days),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except (jwt.InvalidTokenError, jwt.ExpiredSignatureError):
        return None

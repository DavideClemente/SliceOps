from fastapi import Request, HTTPException

from app.auth.models import ApiKeyData
from app.config import Settings


async def get_api_key(request: Request) -> ApiKeyData:
    settings: Settings = request.app.state.settings
    if not settings.auth_enabled:
        # Return a dummy key when auth is disabled
        return ApiKeyData(
            key="disabled",
            owner="anonymous",
            plan="paid",
            active=True,
            created_at="",
        )

    key = request.headers.get("X-API-Key")
    if not key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    auth_service = request.app.state.auth_service
    api_key_data = await auth_service.validate_key(key)

    if api_key_data is None:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if not api_key_data.active:
        raise HTTPException(status_code=403, detail="API key has been revoked")

    return api_key_data

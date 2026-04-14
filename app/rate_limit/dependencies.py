from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse

from app.auth.models import ApiKeyData


async def require_rate_limit(request: Request, api_key: ApiKeyData) -> None:
    rate_limit_service = request.app.state.rate_limit_service

    # Check rate limit
    allowed, limit, remaining, reset_seconds = await rate_limit_service.check_rate_limit(
        api_key.key, api_key.plan
    )
    # Store headers for later use
    request.state.rate_limit_headers = {
        "X-RateLimit-Limit": str(limit),
        "X-RateLimit-Remaining": str(max(0, remaining)),
        "X-RateLimit-Reset": str(reset_seconds),
    }

    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "Retry-After": str(reset_seconds),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_seconds),
            },
        )

    # Check monthly quota
    quota_allowed, quota, used = await rate_limit_service.check_monthly_quota(
        api_key.key, api_key.plan
    )
    if not quota_allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Monthly quota exceeded ({used}/{quota} slices)",
            headers={"X-Monthly-Quota": str(quota), "X-Monthly-Used": str(used)},
        )

    # Increment rate limit counter
    await rate_limit_service.increment_rate_limit(api_key.key)

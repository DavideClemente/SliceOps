from fastapi import Request, HTTPException


async def require_rate_limit(request: Request) -> None:
    rate_limit_service = request.app.state.rate_limit_service
    client_ip = request.client.host

    allowed, limit, remaining, reset_seconds = await rate_limit_service.check(client_ip)

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

    await rate_limit_service.increment(client_ip)

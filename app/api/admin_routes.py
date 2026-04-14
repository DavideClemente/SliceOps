from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

admin_router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _require_admin(request: Request) -> None:
    settings = request.app.state.settings
    if not settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Admin API key not configured")
    provided = request.headers.get("X-API-Key")
    if provided != settings.admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")


@admin_router.post("/keys")
async def create_key(request: Request, owner: str, plan: str = "free"):
    _require_admin(request)
    settings = request.app.state.settings
    plan = plan.lower()
    try:
        settings.get_plan_limits(plan)
    except KeyError:
        available = list(settings._plan_limits.keys())
        raise HTTPException(status_code=400, detail=f"Invalid plan: {plan}. Available: {available}")
    auth_service = request.app.state.auth_service
    key_data = await auth_service.create_key(owner=owner, plan=plan)
    return key_data.model_dump()


@admin_router.get("/keys")
async def list_keys(request: Request):
    _require_admin(request)
    auth_service = request.app.state.auth_service
    keys = await auth_service.list_keys()
    return [k.model_dump() for k in keys]


@admin_router.delete("/keys/{key}")
async def revoke_key(request: Request, key: str):
    _require_admin(request)
    auth_service = request.app.state.auth_service
    success = await auth_service.revoke_key(key)
    if not success:
        raise HTTPException(status_code=404, detail="Key not found")
    return {"status": "revoked", "key": key}


@admin_router.get("/keys/{key}/usage")
async def key_usage(request: Request, key: str):
    _require_admin(request)
    auth_service = request.app.state.auth_service
    return await auth_service.get_usage(key)


@admin_router.get("/metrics")
async def metrics(request: Request):
    _require_admin(request)
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)

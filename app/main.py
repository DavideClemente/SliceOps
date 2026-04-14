from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.routes import router
from app.config import Settings
from app.middleware.logging_config import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.services.bambu_studio import BambuStudioService
from app.services.prusa_slicer import PrusaSlicerService
from app.storage.temp_storage import TempStorage
from app.store.job_store import JobStore
from app.rate_limit.service import RateLimitService

settings = Settings()


class RateLimitHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        headers = getattr(request.state, "rate_limit_headers", None)
        if headers:
            for key, value in headers.items():
                response.headers[key] = value
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging(level=settings.log_level)

    app.state.settings = settings
    app.state.storage = TempStorage(base_dir=settings.temp_dir)
    app.state.slicers = {
        "prusa-slicer": PrusaSlicerService(
            executable=settings.prusa_slicer_path,
            timeout=settings.slicer_timeout_seconds,
        ),
        "bambu-studio": BambuStudioService(
            executable=settings.bambu_studio_path,
            timeout=settings.slicer_timeout_seconds,
        ),
    }

    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client
    app.state.job_store = JobStore(redis_client, ttl_seconds=settings.job_ttl_seconds)
    app.state.rate_limit_service = RateLimitService(
        redis_client, requests_per_minute=settings.rate_limit
    )

    yield

    await redis_client.aclose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SliceOps",
        description="3D printing time and cost estimation API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RateLimitHeaderMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    Instrumentator().instrument(app)

    return app


app = create_app()

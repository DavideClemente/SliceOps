from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_fastapi_instrumentator import Instrumentator

from app.api.routes import router
from app.config import Settings
from app.middleware.logging_config import setup_logging
from app.middleware.request_id import RequestIDMiddleware
from app.services.bambu_studio import BambuStudioService
from app.services.prusa_slicer import PrusaSlicerService
from app.storage.temp_storage import TempStorage
from app.store.job_store import JobStore
from app.auth.service import AuthService
from app.rate_limit.service import RateLimitService
from app.db.engine import get_engine, get_session_factory, close_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
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

    # Redis client
    redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis = redis_client

    # Job store (Phase 2)
    app.state.job_store = JobStore(redis_client, ttl_seconds=settings.job_ttl_seconds)

    # Auth service (Phase 3)
    app.state.auth_service = AuthService(redis_client)

    # Rate limit service (Phase 4)
    app.state.rate_limit_service = RateLimitService(redis_client, settings)

    # Database engine
    get_engine(settings)
    get_session_factory(settings)

    yield

    await redis_client.aclose()
    await close_engine()


def create_app() -> FastAPI:
    app = FastAPI(
        title="SliceOps",
        description="3D printing time and cost estimation API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=Settings().cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    from app.api.admin_routes import admin_router
    app.include_router(admin_router)

    from app.api.auth_routes import auth_router
    app.include_router(auth_router)

    from app.api.account_routes import account_router
    app.include_router(account_router)

    Instrumentator().instrument(app)

    return app


app = create_app()

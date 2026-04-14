from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.config import Settings
from app.services.bambu_studio import BambuStudioService
from app.services.prusa_slicer import PrusaSlicerService
from app.storage.temp_storage import TempStorage


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
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
    app.state.job_results = {}
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="SliceOps",
        description="3D printing time and cost estimation API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)
    return app


app = create_app()

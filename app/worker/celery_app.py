from celery import Celery

from app.config import Settings

settings = Settings()

celery_app = Celery(
    "sliceops",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    result_expires=3600,
)

celery_app.conf.beat_schedule = {
    "sweep-expired-files": {
        "task": "sliceops.sweep_expired",
        "schedule": 300.0,  # Every 5 minutes
    },
}

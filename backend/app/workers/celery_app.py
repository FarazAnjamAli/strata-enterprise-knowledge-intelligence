"""Celery application: document ingestion worker + beat scheduler."""

from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "strata",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.file_processor", "app.workers.cleanup"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    # ack after completion + redeliver on worker death: a killed worker's
    # task re-runs automatically instead of vanishing mid-'processing'
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long parse jobs: don't hoard tasks
    broker_connection_retry_on_startup=True,
    beat_schedule={
        "requeue-stuck-files": {
            "task": "strata.requeue_stuck_files",
            "schedule": 600.0,  # every 10 min
        },
    },
)


@celery_app.task(name="strata.ping")
def ping() -> str:
    return "pong"

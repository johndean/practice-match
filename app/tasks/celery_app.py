"""Celery application. Sub-project 1 ships only `ping` so the worker service
deploys healthy; the Census ingest tasks (Sub-project 3) register here."""
from celery import Celery  # type: ignore[import-untyped]  # celery ships no py.typed marker / stubs

from app.config import settings

celery_app = Celery("practice_match", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="celery",
)


@celery_app.task(name="practice_match.ping")  # type: ignore[untyped-decorator]  # celery.Celery.task is untyped upstream
def ping() -> str:
    return "pong"

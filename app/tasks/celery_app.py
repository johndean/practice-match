"""Celery application. Sub-project 1 shipped only `ping` so the worker service deployed healthy;
Task I6 adds the mail pipeline and the nightly purges, and the Census ingest tasks (Sub-project 3)
register here too.

The task FUNCTIONS live in `app.mail.tasks`; only their names appear here. `include` is what makes
the worker import that module at start-up (without it beat would publish `mail.send` to a worker
that had never registered it), and it is lazy — resolved on finalisation, not at import — so
`app.mail.tasks` importing `celery_app` from here is not a cycle.
"""
from celery import Celery  # type: ignore[import-untyped]  # celery ships no py.typed marker / stubs
from celery.schedules import crontab  # type: ignore[import-untyped]  # celery ships no py.typed marker / stubs

from app.config import settings

celery_app = Celery("practice_match", broker=settings.redis_url, backend=settings.redis_url, include=["app.mail.tasks"])
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue="celery",
    # Spec §5's pipeline: the outbox is drained every minute (an email is at most a minute behind
    # the click that caused it), and the two retention jobs run in the quiet hour.
    beat_schedule={
        "mail-send-minutely": {"task": "mail.send", "schedule": 60.0},
        "sessions-purge-nightly": {"task": "mail.purge_sessions", "schedule": crontab(minute=30, hour=4)},
        "outbox-purge-nightly": {"task": "mail.purge_outbox", "schedule": crontab(minute=40, hour=4)},
    },
)


@celery_app.task(name="practice_match.ping")  # type: ignore[untyped-decorator]  # celery.Celery.task is untyped upstream
def ping() -> str:
    return "pong"

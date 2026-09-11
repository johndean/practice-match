"""Celery application. Sub-project 1 shipped only `ping` so the worker service deployed healthy;
Task I6 adds the mail pipeline and the nightly purges, and the Census ingest tasks (Sub-project 3)
register here too.

The task FUNCTIONS live in `app.mail.tasks` and `app.tasks.census`; only their names appear here.
`include` is what makes the worker import those modules at start-up (without it beat would
publish `mail.send` to a worker that had never registered it), and it is lazy — resolved on
finalisation, not at import — so `app.mail.tasks` importing `celery_app` from here is not a cycle.

Census (Sub-project 3, Task A8) MERGES two entries into `beat_schedule` below rather than
replacing it (controller amendment A-C0 ¶2): `tests/test_celery.py
::test_the_mail_pipeline_tasks_are_registered_and_scheduled` asserts SET EQUALITY on every
scheduled task name, so a future accidental wipe of either sub-project's entries still goes red.
Annual ACS/CBP loads are not scheduled at all (spec §9: manual approval) — those run through
`scripts/census_load.py` and are made live only by an operator's `activate` (never a Celery task
— A-C7 (8)).
"""
from celery import Celery  # type: ignore[import-untyped]  # celery ships no py.typed marker / stubs
from celery.schedules import crontab  # type: ignore[import-untyped]  # celery ships no py.typed marker / stubs

from app.config import settings

celery_app = Celery("practice_match", broker=settings.redis_url, backend=settings.redis_url, include=["app.mail.tasks", "app.tasks.census"])
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
# Census's own two automatic cadences (spec §9): QWI is the only load that runs on a schedule,
# kept to 20 quarters (`qwi.trim`); the licence audit re-checks every registered terms URL and
# flags drift for staff review. `.update(...)` on the dict `conf.update(beat_schedule={...})` just
# built ABOVE — never a second `beat_schedule={...}` keyword, which would replace it outright
# (A-C0 ¶2).
celery_app.conf.beat_schedule.update({
    "qwi-quarterly": {"task": "census.load_qwi", "schedule": crontab(minute=0, hour=6, day_of_month="15", month_of_year="2,5,8,11")},
    "license-audit-quarterly": {"task": "census.license_audit", "schedule": crontab(minute=0, hour=7, day_of_month="1", month_of_year="1,4,7,10")},
    # Task B4b: rebuilds every geocoded listing's market_metric rows from the active vintages.
    # Cheap and purely local (no Census I/O), so it runs nightly rather than quarterly like the
    # loads above. `census.backfill_listing` (the per-listing, on-demand counterpart) has no
    # beat entry -- it runs once, right after a listing is geocoded, never on a schedule.
    "materialize-nightly": {"task": "census.materialize_metrics", "schedule": crontab(minute=0, hour=3)},
    # D-NS9: the polygon table, half an hour after the listing table. The two are independent --
    # neither reads the other's rows -- and the stagger keeps two heavy read-only passes over
    # acs_measure off one database at the same moment. Never on the request path (spec §10).
    "geo-metric-nightly": {"task": "census.materialize_geo_metrics", "schedule": crontab(minute=30, hour=3)},
})


@celery_app.task(name="practice_match.ping")  # type: ignore[untyped-decorator]  # celery.Celery.task is untyped upstream
def ping() -> str:
    return "pong"

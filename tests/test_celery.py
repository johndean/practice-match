from app.config import settings
from app.tasks.celery_app import celery_app, ping


def test_ping_task_returns_pong():
    assert ping() == "pong"


def test_broker_and_backend_are_the_configured_redis():
    assert celery_app.conf.broker_url == settings.redis_url
    assert celery_app.conf.result_backend == settings.redis_url


def test_task_is_registered_under_its_stable_name():
    assert "practice_match.ping" in celery_app.tasks


def test_the_mail_pipeline_tasks_are_registered_and_scheduled():
    """Task I6. Beat publishes by NAME, so a name that no worker has registered is a message that
    disappears — which for `mail.send` means every verification link sitting in the outbox while
    sign-up keeps answering "check your email". `include` is what makes the worker import the
    module that registers them, and it is checked here because nothing else would notice its loss.

    Widened by Task A8 (controller amendment A-C0 ¶2) the same commit Census adds
    `qwi-quarterly`/`license-audit-quarterly`: the schedule is MERGED, never replaced, so the set
    equality below proves both sub-projects' entries survive together — a future wipe of either
    one still goes red. `app.tasks.census` is re-imported here for the same reason `app.mail.tasks`
    already is: `include=[...]` only makes `celery worker`/`celery beat` import a module at
    start-up, never a bare `celery_app.tasks` access under pytest."""
    from app.mail import tasks as MT  # importing the module is what registers them, exactly as the worker does
    from app.tasks import census as CT  # ditto, for census.load_qwi / census.license_audit

    assert (MT.send_task.name, MT.purge_sessions_task.name, MT.purge_outbox_task.name) == ("mail.send", "mail.purge_sessions", "mail.purge_outbox")
    assert (CT.load_qwi_task.name, CT.license_audit_task.name) == ("census.load_qwi", "census.license_audit")
    assert {"mail.send", "mail.purge_sessions", "mail.purge_outbox"} <= set(celery_app.tasks)
    assert {"census.load_qwi", "census.license_audit"} <= set(celery_app.tasks)
    assert "app.mail.tasks" in celery_app.conf.include
    assert "app.tasks.census" in celery_app.conf.include
    schedule = celery_app.conf.beat_schedule
    assert schedule["mail-send-minutely"] == {"task": "mail.send", "schedule": 60.0}
    assert schedule["qwi-quarterly"]["task"] == "census.load_qwi"
    assert schedule["license-audit-quarterly"]["task"] == "census.license_audit"
    assert schedule["materialize-nightly"]["task"] == "census.materialize_metrics"
    assert schedule["geo-metric-nightly"]["task"] == "census.materialize_geo_metrics"
    # D-NS9: 03:30 UTC, half an hour after materialize-nightly's 03:00 -- the two are independent
    # (neither reads the other's table) and the stagger keeps two heavy read-only passes over
    # acs_measure off one database at the same moment. Never on the request path (spec §10).
    assert schedule["geo-metric-nightly"]["schedule"].hour == {3} and schedule["geo-metric-nightly"]["schedule"].minute == {30}
    # Task B4b widens this set (never replaces it) the same way Task A8 originally did: a future
    # accidental wipe of any sub-project's entries -- Census's own materialisation beat included
    # -- still goes red here.
    assert {entry["task"] for entry in schedule.values()} == {
        "mail.send", "mail.purge_sessions", "mail.purge_outbox", "census.load_qwi", "census.license_audit",
        "census.materialize_metrics", "census.materialize_geo_metrics", "media.sweep",
    }
    for name in ("sessions-purge-nightly", "outbox-purge-nightly"):
        assert schedule[name]["schedule"].hour == {4}, name


def test_the_media_queue_and_its_sweep_are_registered_and_scheduled():
    """Spec 2026-09-09 E. The set-equality assertions above are what stop a future edit wiping
    either sub-project's entries; these are this sub-project's rows in them.

    `app.tasks.media` is imported here for the reason this file's own docstring already gives of
    `app.mail.tasks` and `app.tasks.census`: `include=[...]` only makes `celery worker`/`celery
    beat` import a module at start-up, never a bare `celery_app.tasks` access under pytest. Without
    the import the two lookups below raise `KeyError` and this case would be testing the import
    system rather than the wiring."""
    from app.tasks import media as MM  # importing the module is what registers them

    assert (MM.process_photo_task.name, MM.sweep_task.name) == ("media.process_photo", "media.sweep")
    assert {"media.process_photo", "media.sweep"} <= set(celery_app.tasks)
    assert "app.tasks.media" in celery_app.conf.include
    assert celery_app.conf.task_routes["media.*"] == {"queue": "media"}
    assert celery_app.conf.beat_schedule["media-sweep-5min"] == {"task": "media.sweep", "schedule": 300.0}
    for name in ("media.process_photo", "media.sweep"):
        task = celery_app.tasks[name]
        # `acks_late` acks on RETURN, so a retry is always a fresh message rather than a
        # redelivery; `reject_on_worker_lost` redelivers the message of a child killed mid-run, and
        # the redelivered run finds the row PROCESSING and writes nothing. The two together are
        # what make `media.sweep`'s rule (2) the only thing that can recover a dead child's row.
        assert task.acks_late and task.reject_on_worker_lost
        # The hard limit is `record.LOST_AFTER` minus a minute, which is what makes a PROCESSING row
        # older than six minutes a lost child rather than a slow one.
        assert (task.time_limit, task.soft_time_limit) == (300, 240)
    # Never in a deployed environment: `Settings` refuses `CELERY_TASK_ALWAYS_EAGER` outside
    # `ENVIRONMENT=test`, and the pytest process sets it nowhere -- so a task published here would
    # go to the broker, exactly as it does on QA.
    assert celery_app.conf.task_always_eager is False

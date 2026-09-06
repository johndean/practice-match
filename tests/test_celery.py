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
    module that registers them, and it is checked here because nothing else would notice its loss."""
    from app.mail import tasks as MT  # importing the module is what registers them, exactly as the worker does

    assert (MT.send_task.name, MT.purge_sessions_task.name, MT.purge_outbox_task.name) == ("mail.send", "mail.purge_sessions", "mail.purge_outbox")
    assert {"mail.send", "mail.purge_sessions", "mail.purge_outbox"} <= set(celery_app.tasks)
    assert "app.mail.tasks" in celery_app.conf.include
    schedule = celery_app.conf.beat_schedule
    assert schedule["mail-send-minutely"] == {"task": "mail.send", "schedule": 60.0}
    assert {entry["task"] for entry in schedule.values()} == {"mail.send", "mail.purge_sessions", "mail.purge_outbox"}
    for name in ("sessions-purge-nightly", "outbox-purge-nightly"):
        assert schedule[name]["schedule"].hour == {4}, name

from app.config import settings
from app.tasks.celery_app import celery_app, ping


def test_ping_task_returns_pong():
    assert ping() == "pong"


def test_broker_and_backend_are_the_configured_redis():
    assert celery_app.conf.broker_url == settings.redis_url
    assert celery_app.conf.result_backend == settings.redis_url


def test_task_is_registered_under_its_stable_name():
    assert "practice_match.ping" in celery_app.tasks

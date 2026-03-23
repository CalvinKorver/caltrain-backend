from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from app.config import get_settings

s = get_settings()

celery_app = Celery(
    "caltrain_alerts",
    broker=s.redis_url,
    backend=s.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_default_queue="default",
    task_queues=(
        Queue("default", Exchange("default"), routing_key="default"),
    ),
)

# Beat schedule (interval-based).
celery_app.conf.beat_schedule = {
    "poll_511": {
        "task": "app.tasks.poll_tasks.poll_511",
        "schedule": float(s.poll_511_interval_seconds),
    },
    "poll_reddit": {
        "task": "app.tasks.poll_tasks.poll_reddit",
        "schedule": float(s.poll_reddit_interval_seconds),
    },
}

celery_app.autodiscover_tasks(["app.tasks"])

# Explicit import so workers always register tasks defined in `poll_tasks.py`.
# Without this, Celery can publish beat messages for `app.tasks.poll_tasks.*`
# while the worker never imports/registers that module.
import app.tasks.poll_tasks  # noqa: F401


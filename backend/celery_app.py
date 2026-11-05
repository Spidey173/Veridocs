"""
Celery distributed task application for Veridocs.
Handles asynchronous background job processing for heavy OCR, multi-hundred-page
SEC 10-K filings, and embedding index construction without blocking FastAPI HTTP requests.
"""

import logging
from celery import Celery
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

celery_app = Celery(
    "veridocs",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
    include=["tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.JOB_TIMEOUT_SECONDS,
    task_soft_time_limit=max(60, settings.JOB_TIMEOUT_SECONDS - 60),
    worker_concurrency=settings.ASYNC_WORKER_CONCURRENCY,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)

if settings.CELERY_TASK_ALWAYS_EAGER:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )


def is_celery_broker_reachable() -> bool:
    """
    Check if the configured Celery/Redis broker is active and reachable.
    Provides sub-second failure detection to allow seamless graceful fallback.
    """
    if settings.CELERY_TASK_ALWAYS_EAGER:
        return True

    try:
        import redis
        client = redis.from_url(
            settings.CELERY_BROKER_URL,
            socket_timeout=0.6,
            socket_connect_timeout=0.6,
        )
        return bool(client.ping())
    except Exception as e:
        logger.debug(f"Celery broker not reachable at {settings.CELERY_BROKER_URL}: {e}")
        return False

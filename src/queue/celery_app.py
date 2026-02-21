"""
Celery application configuration.

Defines the Celery instance, queues, and serialization settings.
All workers import this module to get the shared Celery app.
"""

from celery import Celery
from kombu import Exchange, Queue

from src.core.config import settings

# Create Celery app
# Using Redis DB 0 as broker, Redis DB 1 as result backend
celery_app = Celery("mas_dd")

# Replace the last character of REDIS_URL to use DB 1 for results
# e.g. redis://localhost:6379/0 -> redis://localhost:6379/1
_result_backend = settings.REDIS_URL.rsplit("/", 1)[0] + "/1"

celery_app.conf.update(
    # Broker (message queue)
    broker_url=settings.REDIS_URL,
    # Result backend (where task results are stored)
    result_backend=_result_backend,
    # Serialization: use JSON for safety and debuggability
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Timezone
    timezone="UTC",
    enable_utc=True,
    # Reliability settings
    task_acks_late=True,  # ACK after task completes, not before
    worker_prefetch_multiplier=1,  # Fetch one task at a time
    task_reject_on_worker_lost=True,  # Re-queue if worker crashes
    # Task result settings
    result_expires=3600,  # Results expire after 1 hour
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    # Queue definitions
    task_queues=(
        Queue(
            "high_priority",
            Exchange("high_priority"),
            routing_key="high_priority",
            queue_arguments={"x-max-priority": 10},
        ),
        Queue(
            "default",
            Exchange("default"),
            routing_key="default",
            queue_arguments={"x-max-priority": 5},
        ),
        Queue(
            "low_priority",
            Exchange("low_priority"),
            routing_key="low_priority",
            queue_arguments={"x-max-priority": 1},
        ),
    ),
    # Default queue
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
)

# Auto-discover tasks from all workers modules
celery_app.autodiscover_tasks(
    [
        "src.workers",
    ]
)

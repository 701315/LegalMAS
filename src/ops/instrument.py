# src/ops/instrument.py

"""
Instrumentation — connects Prometheus metrics to FastAPI.

Sets up:
1. Auto HTTP metrics (request count, latency, status codes)
2. /metrics endpoint for Prometheus scraping
3. Build info metric

Call setup_metrics(app) once in src/api/main.py.
"""

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from core.config import settings
from core.logging import get_logger
from ops.metrics import get_metrics

logger = get_logger(__name__)


def setup_metrics(app: FastAPI) -> None:
    """
    Attach Prometheus instrumentation to FastAPI app.

    After calling this function:
    - Every HTTP request is measured (latency, status code)
    - GET /metrics returns all metrics in Prometheus format
    - Build info is recorded
    """
    if not settings.METRICS_ENABLED:
        logger.info("Metrics disabled (METRICS_ENABLED=false)")
        return

    # Auto HTTP metrics. We exclude health and metrics endpoints to reduce noise.
    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/health", "/metrics"],
    ).instrument(app).expose(app, endpoint="/metrics")

    # Record build info (version can be wired to CI later)
    metrics = get_metrics()
    metrics.build_info.info(
        {
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT,
        }
    )

    logger.info("Prometheus metrics enabled at /metrics")

# src/ops/instrument.py

"""
FastAPI instrumentation setup for Prometheus metrics.

Подключает HTTP‑инструментацию к FastAPI приложению и публикует endpoint
`/metrics` для scrape со стороны Prometheus.

Что делает setup_metrics(app):
- проверяет `settings.METRICS_ENABLED`; если метрики отключены,
  просто логирует это и ничего не настраивает;
- подключает `prometheus_fastapi_instrumentator`, чтобы автоматически
  собирать HTTP‑метрики по запросам:
  количество запросов, latency и группировку по status code;
- исключает `/health` и `/metrics` из автосбора, чтобы уменьшить шум;
- публикует `GET /metrics`, который отдаёт все зарегистрированные
  метрики в формате Prometheus;
- записывает build info через `get_metrics().build_info.info(...)`
  с версией приложения и окружением (`settings.ENVIRONMENT`).

Назначение:
- быть единственной точкой интеграции между FastAPI и registry из `ops.metrics`;
- вызываться один раз при старте API, обычно в `src/api/main.py`.
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

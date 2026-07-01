# src/ops/instrument.py

"""
FastAPI instrumentation setup for Prometheus metrics.

Решение registry mismatch:
- Старая версия использовала prometheus_fastapi_instrumentator,
  который пишет в global default registry.
- Наш MetricsRegistry живёт в dedicated CollectorRegistry.
- Instrumentator.expose() рендерил только default registry →
  custom metrics были невидимы через /metrics.

Новый подход:
- Регистрируем явный GET /metrics endpoint через FastAPI router.
  Это избегает проблемы с trailing slash redirect, которую даёт
  app.mount() в Starlette.
- HTTP request metrics собираем через PrometheusMiddleware,
  которая пишет в наш MetricsRegistry.
- prometheus_fastapi_instrumentator больше не используется.

Что делает setup_metrics(app):
- Проверяет METRICS_ENABLED; если False — ничего не делает.
- Регистрирует GET /metrics → рендерит dedicated registry.
- Добавляет PrometheusMiddleware для HTTP metrics.
- Записывает build_info.
"""

from __future__ import annotations

import time

from fastapi import FastAPI
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from core.config import settings
from core.logging import get_logger
from ops.metrics import get_metrics, get_prometheus_registry

logger = get_logger(__name__)

# Пути, исключённые из HTTP metrics — создают шум без смысла.
_EXCLUDED_PATHS = frozenset({
    "/metrics",
    "/health",
    "/favicon.ico",
    "/docs",
    "/openapi.json",
    "/redoc",
})


class PrometheusMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware для сбора HTTP request metrics.

    Пишет в dedicated MetricsRegistry (не в default prometheus registry).

    Собирает:
    - http_requests_total{method, handler, status_code}
    - http_request_duration_seconds{method, handler}

    handler = path template из matched route
    (например /api/v1/documents/{document_id}),
    что предотвращает cardinality explosion от UUID в путях.
    Для неизвестных маршрутов используется фактический path.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Исключаем служебные пути из измерений.
        if request.url.path in _EXCLUDED_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            handler = _get_route_template(request)
            method = request.method

            try:
                m = get_metrics()
                m.http_requests_total.labels(
                    method=method,
                    handler=handler,
                    status_code=str(status_code),
                ).inc()
                m.http_request_duration_seconds.labels(
                    method=method,
                    handler=handler,
                ).observe(duration)
            except Exception:
                # Metrics never break the response pipeline.
                pass


def _get_route_template(request: Request) -> str:
    """
    Извлечь path template из matched route.

    FastAPI/Starlette кладёт matched route в request.scope["route"].
    Если маршрут не нашёлся — возвращаем фактический path
    (это нормально для 404-запросов).
    """
    route = request.scope.get("route")
    if route is not None and hasattr(route, "path"):
        return str(route.path)
    return request.url.path


def setup_metrics(app: FastAPI) -> None:
    """
    Attach Prometheus instrumentation to FastAPI app.

    После вызова:
    - GET /metrics отдаёт все метрики из dedicated registry в Prometheus format.
    - Каждый HTTP request (кроме excluded paths) измеряется через middleware.
    - Build info записана в метрику build_info.

    Вызывается один раз при старте API из src/api/main.py.
    """
    if not settings.METRICS_ENABLED:
        logger.info("Metrics disabled (METRICS_ENABLED=false), skipping setup")
        return

    # Регистрируем GET /metrics как обычный FastAPI endpoint.
    # Это надёжнее чем app.mount(), который делает redirect
    # /metrics → /metrics/ (trailing slash), что ломает Prometheus scraper.
    @app.get("/metrics", include_in_schema=False)
    async def metrics_endpoint() -> Response:
        """Prometheus metrics endpoint — рендерит dedicated registry."""
        body = generate_latest(get_prometheus_registry())
        return Response(
            content=body,
            media_type=CONTENT_TYPE_LATEST,
        )

    # HTTP request metrics через middleware.
    # Добавляем ПОСЛЕ регистрации /metrics, чтобы /metrics
    # был в _EXCLUDED_PATHS и не измерял сам себя.
    app.add_middleware(PrometheusMiddleware)

    # Build info.
    get_metrics().build_info.info(
        {
            "version": "0.1.0",
            "environment": settings.ENVIRONMENT,
        }
    )

    logger.info("Prometheus metrics enabled", endpoint="/metrics")


    
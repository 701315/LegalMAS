# src/core/tracing.py

"""
OpenTelemetry distributed tracing setup.

Простым языком:
Этот модуль отвечает за инициализацию системы трейсинга.
Он настраивает:
- куда отправлять трейсы (в Tempo через OTLP HTTP)
- какой процент запросов записывать (sampling)
- как называется наш сервис в трейсах
- какие компоненты инструментировать автоматически

Публичный API модуля:

Для API процесса:
- setup_tracing_provider() — инициализирует TracerProvider + SQLAlchemy + httpx.
- instrument_fastapi_app(app) — подключает FastAPI instrumentation.
- shutdown_tracing() — корректно завершает работу при shutdown.

Для Celery worker процесса:
- setup_worker_tracing() — инициализирует TracerProvider + SQLAlchemy + httpx
  в worker process.
- shutdown_worker_tracing() — завершает tracing при shutdown worker process.

Для Celery trace propagation:
- inject_trace_context(headers) — сериализует текущий trace context
  в Celery headers.
- extract_trace_context(headers) — извлекает trace context из Celery headers.
- start_celery_consumer_span(...) — создаёт worker-side execute span.
- finish_celery_consumer_span(...) — корректно закрывает worker-side span.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Флаг инициализации — защита от двойной инициализации в одном процессе.
# Важно:
# - API процесс и worker process инициализируются отдельно.
# - В каждом процессе tracing должен подняться ровно один раз.
# ---------------------------------------------------------------------------
_tracing_initialized = False


# ---------------------------------------------------------------------------
# Export filtering
# ---------------------------------------------------------------------------

def _is_technical_path(path: str) -> bool:
    """
    Проверить, что path относится к техническим endpoint'ам,
    которые не нужно экспортировать в Tempo.

    Важно:
    - /metrics должен исключаться
    - /api/v1/tenant/metrics НЕ должен исключаться
    """
    normalized = path.strip()

    if normalized == "/metrics" or normalized.startswith("/metrics/"):
        return True
    if normalized == "/health" or normalized.startswith("/health/"):
        return True
    if normalized == "/ready" or normalized.startswith("/ready/"):
        return True
    if normalized == "/docs" or normalized.startswith("/docs/"):
        return True
    if normalized == "/redoc" or normalized.startswith("/redoc/"):
        return True
    if normalized == "/openapi.json":
        return True
    if normalized == "/favicon.ico":
        return True

    return False


def _should_export_span(span: Any) -> bool:
    """
    Решить, нужно ли экспортировать span в Tempo.

    Простым языком:
    Иногда FastAPI instrumentation всё равно создаёт spans для /metrics,
    даже если excluded_urls настроен. Чтобы убрать такой шум надёжно,
    фильтруем spans прямо перед отправкой в Tempo.

    Это работает надёжнее, чем полагаться только на excluded_urls.

    Что НЕ выкидываем:
    - /api/v1/tenant/metrics
    Потому что это бизнесовый endpoint, а не технический scrape endpoint.
    """
    name = str(getattr(span, "name", "") or "")
    attrs = dict(getattr(span, "attributes", {}) or {})

    # 1. Быстрый фильтр по имени span.
    # FastAPI server spans обычно имеют имя вида:
    #   GET /metrics
    #   GET /docs
    if name.startswith("GET /metrics") or name.startswith("HEAD /metrics"):
        return False
    if name.startswith("GET /docs") or name.startswith("HEAD /docs"):
        return False
    if name.startswith("GET /redoc") or name.startswith("HEAD /redoc"):
        return False
    if name.startswith("GET /openapi.json") or name.startswith("HEAD /openapi.json"):
        return False
    if name.startswith("GET /favicon.ico") or name.startswith("HEAD /favicon.ico"):
        return False

    # 2. Более надёжный фильтр по attrs, если instrumentation положил path туда.
    path_candidates = [
        attrs.get("http.route"),
        attrs.get("http.target"),
        attrs.get("url.path"),
        attrs.get("http.path"),
    ]

    for candidate in path_candidates:
        if isinstance(candidate, str) and _is_technical_path(candidate):
            return False

    return True


class _FilteringSpanExporter:
    """
    Обёртка над реальным exporter'ом, которая отбрасывает технические spans.

    Простым языком:
    Даже если instrumentation создал span для /metrics,
    этот exporter не даст ему уйти в Tempo.

    Это последний и самый надёжный рубеж фильтрации.
    """

    def __init__(self, wrapped_exporter: Any) -> None:
        self._wrapped_exporter = wrapped_exporter

    def export(self, spans: Sequence[Any]) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult  # noqa: PLC0415

        filtered_spans = [span for span in spans if _should_export_span(span)]

        if not filtered_spans:
            return SpanExportResult.SUCCESS

        return self._wrapped_exporter.export(filtered_spans)

    def shutdown(self) -> None:
        self._wrapped_exporter.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        force_flush = getattr(self._wrapped_exporter, "force_flush", None)
        if callable(force_flush):
            return bool(force_flush(timeout_millis))
        return True
    

def setup_tracing_provider() -> None:
    """
    Инициализировать TracerProvider для API процесса.
    SQLAlchemy и httpx instrumentation подключаются здесь же.

    Вызывается один раз на уровне модуля в main.py,
    ДО создания FastAPI app.
    """
    global _tracing_initialized

    from core.config import settings  # noqa: PLC0415

    if not settings.OTEL_ENABLED:
        _logger.info("OpenTelemetry tracing is disabled (OTEL_ENABLED=False)")
        return

    if _tracing_initialized:
        _logger.debug("TracerProvider already initialized, skipping")
        return

    _logger.info(
        "Initializing OpenTelemetry tracing provider",
        extra={
            "otel_service_name": settings.OTEL_SERVICE_NAME,
            "otel_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            "otel_sampler": settings.OTEL_TRACES_SAMPLER,
            "otel_sampler_arg": settings.OTEL_TRACES_SAMPLER_ARG,
        },
    )

    try:
        _init_tracer_provider(settings)
        _instrument_sqlalchemy()
        _instrument_httpx()
        _tracing_initialized = True
        _logger.info("OpenTelemetry tracing provider initialized successfully")
    except Exception:
        _logger.exception(
            "Failed to initialize OpenTelemetry tracing provider — "
            "application will continue without tracing"
        )


def setup_worker_tracing() -> None:
    """
    Инициализировать TracerProvider для Celery worker процесса.

    Простым языком:
    Worker — это отдельный Python-процесс, ему нужен свой TracerProvider.
    Мы используем отдельное service.name:
      legalmas-api-worker
    чтобы в Tempo/Grafana отличать API spans от worker spans.

    Вызывается:
    - в prefork child process через worker_process_init
    - в solo worker main process через worker_init
    """
    global _tracing_initialized

    from core.config import settings  # noqa: PLC0415

    if not settings.OTEL_ENABLED:
        return

    if _tracing_initialized:
        _logger.debug("Worker TracerProvider already initialized, skipping")
        return

    worker_service_name = f"{settings.OTEL_SERVICE_NAME}-worker"

    _logger.info(
        "Initializing OpenTelemetry tracing for worker process",
        extra={
            "otel_service_name": worker_service_name,
            "otel_endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        },
    )

    try:
        _init_tracer_provider(
            settings,
            service_name_override=worker_service_name,
        )
        _instrument_sqlalchemy()
        _instrument_httpx()
        _tracing_initialized = True
        _logger.info("Worker OpenTelemetry tracing initialized successfully")
    except Exception:
        _logger.exception(
            "Failed to initialize worker OpenTelemetry tracing — "
            "worker will continue without tracing"
        )


def instrument_fastapi_app(app: object) -> None:
    """
    Подключить FastAPI instrumentation к уже созданному app.

    Вызывается ПОСЛЕ app = FastAPI(...), но ДО старта приложения.
    """
    from core.config import settings  # noqa: PLC0415

    if not settings.OTEL_ENABLED:
        return

    _instrument_fastapi(app)


def shutdown_tracing() -> None:
    """
    Корректно завершить tracing в API процессе.
    """
    _shutdown_provider()


def shutdown_worker_tracing() -> None:
    """
    Корректно завершить tracing в worker процессе.
    """
    _shutdown_provider()


# ---------------------------------------------------------------------------
# Trace context propagation для Celery
# ---------------------------------------------------------------------------

def inject_trace_context(headers: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Сериализовать текущий OpenTelemetry trace context в словарь headers.

    Простым языком:
    Когда API/worker публикует Celery-задачу, мы кладём в headers
    traceparent/tracestate. Worker потом извлечёт их и продолжит
    тот же trace.

    Если tracing выключен или активного span нет — возвращаем headers как есть.
    """
    carrier: dict[str, Any] = dict(headers or {})

    try:
        from core.config import settings  # noqa: PLC0415

        if not settings.OTEL_ENABLED:
            return carrier

        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.propagate import inject  # noqa: PLC0415

        span_ctx = trace.get_current_span().get_span_context()
        if not span_ctx.is_valid:
            return carrier

        inject(carrier)
    except Exception:  # noqa: BLE001
        # Propagation никогда не должна ломать publish path.
        pass

    return carrier


def extract_trace_context(headers: dict[str, Any] | None) -> object | None:
    """
    Извлечь trace context из Celery headers.

    Возвращает OpenTelemetry Context или None.
    """
    if not headers:
        return None

    try:
        from core.config import settings  # noqa: PLC0415

        if not settings.OTEL_ENABLED:
            return None

        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.propagate import extract  # noqa: PLC0415

        ctx = extract(headers)
        span_ctx = trace.get_current_span(ctx).get_span_context()
        if span_ctx.is_valid:
            return ctx
    except Exception:  # noqa: BLE001
        pass

    return None


def start_celery_consumer_span(
    *,
    task_name: str,
    task_id: str | None,
    queue: str | None,
    headers: dict[str, Any] | None,
    request_id: str | None = None,
    tenant_id: str | None = None,
    deal_id: str | None = None,
    run_id: str | None = None,
    document_id: str | None = None,
) -> tuple[Any | None, Any | None]:
    """
    Создать worker-side execute span для Celery task.

    Простым языком:
    Worker получает Celery message, извлекает trace context из headers
    и создаёт новый span:
      celery.execute/<task_name>

    Этот span становится current span на время выполнения задачи,
    поэтому:
    - SQLAlchemy spans становятся его дочерними spans
    - httpx spans становятся его дочерними spans
    - structlog автоматически получает trace_id/span_id

    Возвращает:
      (span, token)
    или
      (None, None) если tracing выключен/не поднялся.
    """
    try:
        from core.config import settings  # noqa: PLC0415

        if not settings.OTEL_ENABLED:
            return None, None

        from opentelemetry import context as context_api  # noqa: PLC0415
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.trace import SpanKind  # noqa: PLC0415

        parent_ctx = extract_trace_context(headers) or context_api.get_current()

        tracer = trace.get_tracer("legalmas.celery.worker")

        attributes = _compact_attributes(
            {
                "messaging.system": "celery",
                "messaging.destination": queue,
                "messaging.destination_kind": "queue",
                "messaging.operation": "process",
                "celery.task_name": task_name,
                "celery.task_id": task_id,
                "celery.queue": queue,
                "app.request_id": request_id,
                "app.tenant_id": tenant_id,
                "app.deal_id": deal_id,
                "app.run_id": run_id,
                "app.document_id": document_id,
            }
        )

        span = tracer.start_span(
            name=f"celery.execute/{task_name}",
            context=parent_ctx,
            kind=SpanKind.CONSUMER,
            attributes=attributes,
        )

        new_ctx = trace.set_span_in_context(span, parent_ctx)
        token = context_api.attach(new_ctx)
        return span, token

    except Exception:  # noqa: BLE001
        return None, None


def finish_celery_consumer_span(
    span: Any | None,
    token: Any | None,
    *,
    state: str | None = None,
    error_message: str | None = None,
) -> None:
    """
    Завершить worker-side Celery span и отвязать context token.
    """
    try:
        if span is not None:
            from opentelemetry.trace import Status, StatusCode  # noqa: PLC0415

            if state == "FAILURE":
                span.set_status(
                    Status(
                        StatusCode.ERROR,
                        error_message or "Celery task failed",
                    )
                )
            span.end()
    finally:
        try:
            if token is not None:
                from opentelemetry import context as context_api  # noqa: PLC0415
                context_api.detach(token)
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------------------
# Внутренние функции инициализации
# ---------------------------------------------------------------------------

def _shutdown_provider() -> None:
    """Общая логика shutdown для API и worker."""
    global _tracing_initialized

    from core.config import settings  # noqa: PLC0415

    if not settings.OTEL_ENABLED:
        return

    if not _tracing_initialized:
        return

    try:
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415

        provider = trace.get_tracer_provider()
        if isinstance(provider, TracerProvider):
            provider.shutdown()
            _tracing_initialized = False
            _logger.info("OpenTelemetry tracer provider shut down successfully")
    except Exception:
        _logger.exception("Failed to shutdown OpenTelemetry tracer provider")


def _init_tracer_provider(
    settings: object,
    *,
    service_name_override: str | None = None,
) -> None:
    """Создать и зарегистрировать TracerProvider с OTLP HTTP exporter."""
    from opentelemetry import trace  # noqa: PLC0415
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import (  # noqa: PLC0415
        OTLPSpanExporter,
    )
    from opentelemetry.sdk.resources import (  # noqa: PLC0415
        DEPLOYMENT_ENVIRONMENT,
        SERVICE_NAME,
        SERVICE_VERSION,
        Resource,
    )
    from opentelemetry.sdk.trace import TracerProvider  # noqa: PLC0415
    from opentelemetry.sdk.trace.export import BatchSpanProcessor  # noqa: PLC0415

    effective_service_name = service_name_override or settings.OTEL_SERVICE_NAME

    resource = Resource.create(
        {
            SERVICE_NAME: effective_service_name,
            SERVICE_VERSION: "0.1.0",
            DEPLOYMENT_ENVIRONMENT: settings.ENVIRONMENT,
        }
    )

    sampler = _build_sampler(settings)
    provider = TracerProvider(resource=resource, sampler=sampler)

    raw_exporter = OTLPSpanExporter(
        endpoint=settings.OTEL_EXPORTER_OTLP_ENDPOINT,
        timeout=10,
    )

    # Оборачиваем exporter фильтром.
    # Это надёжно выкинет /metrics, /docs, /openapi.json и другие
    # технические spans ещё до отправки в Tempo.
    exporter = _FilteringSpanExporter(raw_exporter)

    processor = BatchSpanProcessor(
        exporter,
        max_queue_size=2048,
        max_export_batch_size=512,
        schedule_delay_millis=5000,
    )
    provider.add_span_processor(processor)

    trace.set_tracer_provider(provider)

    _logger.info(
        "TracerProvider initialized",
        extra={
            "service_name": effective_service_name,
            "endpoint": settings.OTEL_EXPORTER_OTLP_ENDPOINT,
            "sampler": settings.OTEL_TRACES_SAMPLER,
        },
    )


def _build_sampler(settings: object) -> object:
    """Построить sampler по настройкам."""
    from opentelemetry.sdk.trace.sampling import (  # noqa: PLC0415
        ParentBased,
        TraceIdRatioBased,
    )

    sampler_arg = float(settings.OTEL_TRACES_SAMPLER_ARG)
    sampler_arg = max(0.0, min(1.0, sampler_arg))

    sampler_name = settings.OTEL_TRACES_SAMPLER

    if sampler_name == "parentbased_traceidratio":
        return ParentBased(root=TraceIdRatioBased(sampler_arg))
    if sampler_name == "traceidratio":
        return TraceIdRatioBased(sampler_arg)
    if sampler_name == "always_on":
        from opentelemetry.sdk.trace.sampling import ALWAYS_ON  # noqa: PLC0415
        return ALWAYS_ON
    if sampler_name == "always_off":
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF  # noqa: PLC0415
        return ALWAYS_OFF

    _logger.warning(
        "Unknown sampler '%s', falling back to parentbased_traceidratio(1.0)",
        sampler_name,
    )
    return ParentBased(root=TraceIdRatioBased(1.0))


def _instrument_fastapi(app: object) -> None:
    """Подключить FastAPI instrumentation."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor  # noqa: PLC0415

        FastAPIInstrumentor.instrument_app(
            app,
            # Простым языком:
            # OpenTelemetry FastAPI instrumentation в реальности может матчить
            # path не совсем так, как ожидается по документации.
            # Поэтому для надёжного исключения /metrics используем более
            # широкий паттерн начала строки.
            #
            # Важно:
            # - исключаем именно технический /metrics endpoint;
            # - /api/v1/tenant/metrics НЕ подпадает, потому что начинается
            #   не с "/metrics", а с "/api/v1/tenant/metrics".
            excluded_urls=(
                "^/metrics($|/.*)"
                "|^/health($|/.*)"
                "|^/ready($|/.*)"
                "|^/docs($|/.*)"
                "|^/redoc($|/.*)"
                "|^/openapi\\.json$"
                "|^/favicon\\.ico$"
            ),
            server_request_hook=_enrich_span_from_request_context,
        )
        _logger.info("FastAPI instrumentation enabled")
    except Exception:
        _logger.exception("Failed to instrument FastAPI")


def _enrich_span_from_request_context(span: object, scope: dict) -> None:
    """Обогатить FastAPI span бизнес-полями из logging context."""
    _ = scope

    try:
        from opentelemetry.trace import Span  # noqa: PLC0415

        if not isinstance(span, Span):
            return
        if not span.is_recording():
            return

        from core.logging import (  # noqa: PLC0415
            deal_id_var,
            request_id_var,
            run_id_var,
            tenant_id_var,
        )

        fields = {
            "app.tenant_id": tenant_id_var.get(),
            "app.deal_id": deal_id_var.get(),
            "app.request_id": request_id_var.get(),
            "app.run_id": run_id_var.get(),
        }
        for key, value in fields.items():
            if value:
                span.set_attribute(key, value)

    except Exception:  # noqa: BLE001
        pass


def _instrument_sqlalchemy() -> None:
    """
    Подключить SQLAlchemy instrumentation к существующему engine.

    Важно:
    engine уже создан заранее в db/session.py,
    поэтому инструментируем именно engine.sync_engine.
    """
    try:
        from db.session import engine  # noqa: PLC0415
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor  # noqa: PLC0415

        SQLAlchemyInstrumentor().instrument(
            engine=engine.sync_engine,
            enable_commenter=True,
            commenter_options={
                "opentelemetry_values": True,
            },
        )
        _logger.info("SQLAlchemy instrumentation enabled")
    except Exception:
        _logger.exception("Failed to instrument SQLAlchemy")


def _instrument_httpx() -> None:
    """Подключить httpx instrumentation."""
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor  # noqa: PLC0415

        HTTPXClientInstrumentor().instrument()
        _logger.info("httpx instrumentation enabled")
    except Exception:
        _logger.exception("Failed to instrument httpx")


def _compact_attributes(values: dict[str, Any]) -> dict[str, Any]:
    """
    Убрать None/пустые значения из span attributes.

    Важно:
    OpenTelemetry attributes должны быть простыми типами.
    """
    compacted: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        compacted[key] = value
    return compacted



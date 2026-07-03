# src/mas_queue/task_dispatcher.py

"""
Helper для отправки Celery-задач с автоматическим пробросом:
1) correlation context через kwargs
2) OpenTelemetry trace context через Celery headers

Что уже было:
- send_task_with_context() подмешивал request_id, tenant_id, deal_id, run_id,
  actor_role в kwargs задачи.
- Благодаря этому worker logs были correlation-aware.

Что добавлено в B.1:
- producer span вокруг celery_app.send_task(...)
- trace context propagation через Celery headers
- worker сможет продолжить тот же trace что и API

Итог:
- в Grafana Tempo будет видно:
  HTTP request -> celery.publish/<task_name> -> celery.execute/<task_name>
- в worker логах появятся trace_id/span_id
"""

from __future__ import annotations

from typing import Any

from celery.result import AsyncResult

from core.logging import (
    actor_role_var,
    deal_id_var,
    get_logger,
    request_id_var,
    run_id_var,
    tenant_id_var,
)
from mas_queue.celery_app import celery_app

logger = get_logger(__name__)


def send_task_with_context(
    task_name: str,
    kwargs: dict[str, Any] | None = None,
    *,
    queue: str | None = None,
    countdown: float | None = None,
    eta: Any | None = None,
    priority: int | None = None,
    **send_task_kwargs: Any,
) -> AsyncResult:
    """
    Отправить Celery-задачу с автоматическим пробросом:

    1) correlation context через kwargs:
       - request_id
       - tenant_id
       - deal_id
       - run_id
       - actor_role

    2) OpenTelemetry trace context через headers:
       - traceparent
       - tracestate

    И с producer span:
       celery.publish/<task_name>

    Не перезаписывает существующие поля в kwargs.
    Non-trace headers сохраняются.
    """
    merged_kwargs: dict[str, Any] = dict(kwargs or {})

    # ---------------------------------------------------------------------
    # Слой 1: Correlation context через kwargs.
    # Это существующая рабочая логика — не ломаем.
    # ---------------------------------------------------------------------
    context_fields: dict[str, Any] = {
        "request_id": request_id_var.get(),
        "tenant_id": tenant_id_var.get(),
        "deal_id": deal_id_var.get(),
        "run_id": run_id_var.get(),
        "actor_role": actor_role_var.get(),
    }

    injected_fields: list[str] = []
    for key, value in context_fields.items():
        if value is not None and key not in merged_kwargs:
            merged_kwargs[key] = value
            injected_fields.append(key)

    if injected_fields:
        logger.debug(
            "Injected correlation context into Celery task kwargs",
            task_name=task_name,
            injected_fields=injected_fields,
        )

    # ---------------------------------------------------------------------
    # Send options (queue/countdown/eta/priority и прочее).
    # ---------------------------------------------------------------------
    send_options: dict[str, Any] = dict(send_task_kwargs)

    if queue is not None:
        send_options["queue"] = queue
    if countdown is not None:
        send_options["countdown"] = countdown
    if eta is not None:
        send_options["eta"] = eta
    if priority is not None:
        send_options["priority"] = priority

    # ---------------------------------------------------------------------
    # Headers.
    # Сохраняем любые внешние headers, которые caller мог передать.
    # Потом добавим/обновим trace headers.
    # ---------------------------------------------------------------------
    existing_headers: dict[str, Any] = dict(send_options.pop("headers", None) or {})

    # ---------------------------------------------------------------------
    # Слой 2: Producer span + trace propagation через headers.
    #
    # Простым языком:
    # Мы создаём span "celery.publish/<task_name>" прямо вокруг send_task().
    # Затем сериализуем текущий trace context этого producer span в headers.
    # Worker на другой стороне извлечёт эти headers и продолжит trace как child.
    #
    # Если tracing выключен — просто отправляем задачу как раньше.
    # ---------------------------------------------------------------------
    try:
        from core.config import settings  # noqa: PLC0415

        if not settings.OTEL_ENABLED:
            return celery_app.send_task(
                task_name,
                kwargs=merged_kwargs,
                headers=existing_headers or None,
                **send_options,
            )

        from core.tracing import inject_trace_context  # noqa: PLC0415
        from opentelemetry import trace  # noqa: PLC0415
        from opentelemetry.trace import SpanKind  # noqa: PLC0415

        tracer = trace.get_tracer("legalmas.celery.publisher")

        effective_queue = queue or send_options.get("queue") or ""

        # Producer span — именно он станет parent для worker execute span.
        with tracer.start_as_current_span(
            name=f"celery.publish/{task_name}",
            kind=SpanKind.PRODUCER,
            attributes=_compact_attributes(
                {
                    "messaging.system": "celery",
                    "messaging.destination": effective_queue,
                    "messaging.destination_kind": "queue",
                    "messaging.operation": "publish",
                    "celery.task_name": task_name,
                    "celery.queue": effective_queue,
                    "app.request_id": merged_kwargs.get("request_id"),
                    "app.tenant_id": merged_kwargs.get("tenant_id"),
                    "app.deal_id": merged_kwargs.get("deal_id"),
                    "app.run_id": merged_kwargs.get("run_id"),
                    "app.document_id": (
                        merged_kwargs.get("document_id") or merged_kwargs.get("doc_id")
                    ),
                }
            ),
        ) as span:
            # Inject traceparent/tracestate от producer span.
            existing_headers = inject_trace_context(existing_headers)

            result = celery_app.send_task(
                task_name,
                kwargs=merged_kwargs,
                headers=existing_headers or None,
                **send_options,
            )

            # Полезно видеть task_id прямо в publish span.
            if result is not None and getattr(result, "id", None):
                span.set_attribute("celery.task_id", result.id)

            return result

    except Exception:
        # Tracing никогда не должен ломать publish path.
        logger.exception(
            "Failed to attach tracing to Celery publish path; "
            "sending task without tracing",
            task_name=task_name,
        )
        return celery_app.send_task(
            task_name,
            kwargs=merged_kwargs,
            headers=existing_headers or None,
            **send_options,
        )


def _compact_attributes(values: dict[str, Any]) -> dict[str, Any]:
    """Убрать None/пустые значения из attributes для span."""
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


    
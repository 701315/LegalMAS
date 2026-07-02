# src/mas_queue/task_dispatcher.py

"""
Helper для отправки Celery-задач с автоматическим пробросом correlation context.

Проблема:
- celery_app.send_task(..., kwargs={...}) часто вызывается без request_id,
  tenant_id, deal_id, run_id, actor_role;
- из-за этого логи Celery worker'а хуже связываются с исходным HTTP-запросом.

Решение:
- send_task_with_context() автоматически подмешивает context vars
  из текущего request/task scope в kwargs задачи;
- существующие keys в kwargs не перезаписываются.
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
    Отправить Celery-задачу с автоматическим пробросом correlation context.

    Не перезаписывает существующие поля в kwargs.
    """
    merged_kwargs: dict[str, Any] = dict(kwargs or {})

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

    send_options: dict[str, Any] = dict(send_task_kwargs)

    if queue is not None:
        send_options["queue"] = queue
    if countdown is not None:
        send_options["countdown"] = countdown
    if eta is not None:
        send_options["eta"] = eta
    if priority is not None:
        send_options["priority"] = priority

    return celery_app.send_task(
        task_name,
        kwargs=merged_kwargs,
        **send_options,
    )



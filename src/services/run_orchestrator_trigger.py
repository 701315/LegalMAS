# src/services/run_orchestrator_trigger.py

"""
Триггер пере-запуска run-пайплайна через Celery.

Модуль предоставляет функцию retrigger_run_pipeline, которую воркеры
пайплайна вызывают после завершения своей стадии, чтобы заново передать
управление оркестратору Run.

Функция безопасно инициирует Celery‑таску "workers.start_run_pipeline":
- ничего не делает, если run_id не передан;
- не решает, что именно запускать дальше, а только ставит задачу
  оркестратора в очередь с пробросом run_id, deal_id, tenant_id и
  флага force_reclassify;
- дополнительно использует send_task_with_context(), чтобы автоматически
  подмешать correlation context (request_id, actor_role, tenant_id, deal_id, run_id)
  из текущего request/task scope, если он ещё не указан явно.
"""

from __future__ import annotations

from typing import Any

from mas_queue.task_dispatcher import send_task_with_context


def retrigger_run_pipeline(
    *,
    run_id: str | None,
    deal_id: str | None = None,
    tenant_id: str | None = None,
    force_reclassify: bool = False,
) -> None:
    """
    Безопасный retrigger оркестратора:
    - не делает ничего, если run_id не передан;
    - не решает, что запускать дальше — только будит workers.start_run_pipeline.

    Важно:
    - явные значения kwargs имеют приоритет;
    - отсутствующие correlation fields helper подмешает автоматически
      из текущего logging context.
    """
    if not run_id:
        return

    task_kwargs: dict[str, Any] = {
        "run_id": run_id,
        "force_reclassify": force_reclassify,
    }

    if deal_id is not None:
        task_kwargs["deal_id"] = deal_id

    if tenant_id is not None:
        task_kwargs["tenant_id"] = tenant_id

    send_task_with_context(
        "workers.start_run_pipeline",
        kwargs=task_kwargs,
    )



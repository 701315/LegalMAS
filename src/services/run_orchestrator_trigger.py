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
  флага force_reclassify.

Используется воркерами convert/extract/structure/chunk_builder/
build_primary_language_source/pii_sanitizer как единая точка входа
для повторного запуска пайплайна Run, чтобы не дублировать работу с
celery_app.send_task и именем таски "workers.start_run_pipeline".
"""

from mas_queue.celery_app import celery_app


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
    """
    if not run_id:
        return

    celery_app.send_task(
        "workers.start_run_pipeline",
        kwargs={
            "run_id": run_id,
            "deal_id": deal_id,
            "tenant_id": tenant_id,
            "force_reclassify": force_reclassify,
        },
    )

    
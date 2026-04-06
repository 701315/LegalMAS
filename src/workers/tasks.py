# src/workers/tasks.py

"""
Task registry — единая точка регистрации всех Celery-задач.

Назначение:
  - при импортировании этого модуля регистрируются все Celery-таски проекта;
  - здесь НЕТ бизнес-логики, только импорты модулей/функций с декораторами задач;
  - это делает список фоновых задач явным и удобным для обзора.

Как использовать и развивать:
  - когда добавляешь новый worker в src/workers/*.py и объявляешь в нём Celery-таску
    через @celery_app.task(...), добавь сюда импорт этой задачи;
  - сами функции здесь не вызываются, цель — именно побочный эффект регистрации;
  - предупреждения линтера о "неиспользуемых" импортируемых объектах подавляются
    через noqa: F401.

Важно:
  - этот модуль больше НЕ импортируется из mas_queue.celery_app, чтобы избежать
    циклических импортов;
  - регистрация задач происходит за счёт импорта worker-модулей Celery-приложением
    (через include/autodiscover_tasks);
  - этот файл остаётся как удобный список всех задач проекта.
"""

# Импортируем все воркеры, которые содержат Celery-таски

# импорт и подготовка файлов
from workers.import_worker import import_bundle  # noqa: F401
from workers.convert_worker import convert_to_pdf  # noqa: F401

# оркестрация Run (запуск пайплайна по сделке)
from workers.run_orchestrator import start_run_pipeline  # noqa: F401

# основной пайплайн обработки документов
from workers.build_primary_language_source import build_primary_language_source  # noqa: F401
from workers.extract_worker import extract_document  # noqa: F401
from workers.pii_sanitizer import sanitize_document  # noqa: F401
from workers.structure_builder import build_structure  # noqa: F401
from workers.classifier import classify_document  # noqa: F401
from workers.chunk_builder import build_chunks  # noqa: F401

# запуск checks: scheduler + атомарные checks + финализация run
from workers.check_runner_worker import (  # noqa: F401
    run_deal_checks,
    run_single_check,
    finalize_run_if_ready,
)

# Дополнительно: построение связей и экспорты
from workers.relations_worker import build_relations  # noqa: F401
from workers.exporter import export_results  # noqa: F401
from workers.export_pending import export_process_pending  # noqa: F401


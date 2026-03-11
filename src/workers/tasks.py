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
"""

# Импортируем все воркеры, которые содержат Celery-таски

# Stage 4–7 / основной пайплайн обработки документов
from workers.import_worker import import_bundle  # noqa: F401
from workers.extract_worker import extract_document  # noqa: F401
from workers.pii_sanitizer import sanitize_document  # noqa: F401
from workers.structure_builder import build_structure  # noqa: F401
from workers.classifier import classify_document  # noqa: F401
from workers.runner import run_checks  # noqa: F401
from workers.exporter import export_results  # noqa: F401

# Построение связей и семей документов
from workers.relations_worker import build_relations  # noqa: F401

# Обслуживание очереди отложенных экспортов
from workers.export_pending import export_process_pending  # noqa: F401

# Orchestrator сейчас не является Celery-таской, поэтому сюда не импортируется
# (он вызывается напрямую из приложения как синхронная функция start_pipeline).

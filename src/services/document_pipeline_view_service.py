# src/services/document_pipeline_view_service.py

"""
⚠️  ФАСАД ОБРАТНОЙ СОВМЕСТИМОСТИ.

Реальная логика перенесена в пакет src/services/pipeline_view/.
Этот файл сохранён, чтобы НЕ менять импорты в остальном коде проекта.

Единственный внешний потребитель:
  src/api/endpoints/document_pipeline_view.py
"""

from services.pipeline_view.service import DocumentPipelineViewService

__all__ = ["DocumentPipelineViewService"]

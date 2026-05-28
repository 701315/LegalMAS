# src/services/pipeline_view/__init__.py

"""
Document pipeline view — пакет для построения представления пайплайна документа.

Реэкспортирует основной сервис для удобства импорта:
    from services.pipeline_view import DocumentPipelineViewService
"""

from services.pipeline_view.service import DocumentPipelineViewService

__all__ = ["DocumentPipelineViewService"]

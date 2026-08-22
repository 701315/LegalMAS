# src/services/structure/builder.py

"""
Compatibility facade for the document structure pipeline.

Этот модуль сохраняет старый внешний контракт:
    StructureBuilder.build(document_id, elements) -> ClauseTree

Реальная логика построения структуры (TOC-детекция, выбор заголовков,
coverage/confidence, иерархия, cross‑refs, degraded‑fallback) вынесена
в пайплайн. StructureBuilder остаётся тонкой обёрткой, чтобы существующий
код мог использовать прежний класс, не зная о новой архитектуре.

Multi-document расширение (v2):
    StructureBuilder.build_file_structure(document_id, elements) -> FileStructureResult
    Новый метод для multi-doc режима. Старый .build() не изменён.
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.models import ClauseTree, FileStructureResult
from services.structure._pipeline._core_builder import build_file_structure, build_structure

logger = get_logger(__name__)


class StructureBuilder:
    """
    Compatibility facade around the structure pipeline.

    Внешний контракт сохраняется:
        StructureBuilder.build(document_id, elements) -> ClauseTree

    Новый метод (v2):
        StructureBuilder.build_file_structure(document_id, elements) -> FileStructureResult
    """

    def build(
        self,
        document_id: str,
        elements: list[dict] | None,
    ) -> ClauseTree:
        """
        Legacy точка входа. Контракт не изменён.

        Используется worker'ом structure_builder.py (существующий код).
        Возвращает ClauseTree для всего файла как единого документа.
        """
        return build_structure(
            document_id=document_id,
            elements=elements,
        )

    def build_file_structure(
        self,
        document_id: str,
        elements: list[dict] | None,
        *,
        document_version_id: str | None = None,
    ) -> FileStructureResult:
        """
        Новая точка входа для multi-document режима (v2).

        Для непрофессионального программиста:
        Этот метод — будущая замена .build() для нового режима работы.
        Возвращает не одно дерево, а FileStructureResult: список деревьев
        по сегментам + FileGraph (граф файла с метаданными всех сегментов).

        Пока STRUCTURE_ENABLE_SEGMENTATION=False (дефолт в settings):
        - возвращает FileStructureResult с одним сегментом = весь файл;
        - primary_tree внутри идентичен результату .build();
        - полная backward compatibility.

        Когда STRUCTURE_ENABLE_SEGMENTATION=True (Sprint 2):
        - файл будет разбит на логические сегменты (договор, приложения и т.д.);
        - для каждого сегмента будет построено отдельное дерево.

        Аргументы:
        - document_id:         ID физического файла
        - elements:            список элементов layout из EXTRACT/PII стадий
        - document_version_id: ID версии документа (для метаданных FileGraph)
        """
        return build_file_structure(
            document_id=document_id,
            elements=elements,
            document_version_id=document_version_id,
        )

# src/services/structure/builder.py

"""
Compatibility facade for the document structure pipeline.

Этот модуль сохраняет старый внешний контракт:
    StructureBuilder.build(document_id, elements) -> ClauseTree

Реальная логика построения структуры (TOC-детекция, выбор заголовков,
coverage/confidence, иерархия, cross‑refs, degraded‑fallback) вынесена
в пайплайн. StructureBuilder остаётся тонкой обёрткой, чтобы существующий
код мог использовать прежний класс, не зная о новой архитектуре.
"""

from __future__ import annotations

from core.logging import get_logger
from services.structure.models import ClauseTree
from services.structure.pipeline import build_structure


logger = get_logger(__name__)


class StructureBuilder:
    """
    Compatibility facade around the structure pipeline.

    Внешний контракт сохраняется:
    StructureBuilder.build(document_id, elements) -> ClauseTree
    """

    def build(
        self,
        document_id: str,
        elements: list[dict] | None,
    ) -> ClauseTree:
        return build_structure(
            document_id=document_id,
            elements=elements,
        )
    
    
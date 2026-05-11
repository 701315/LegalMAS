# src/services/document_language_detection.py

"""
Shared document language detection service.

Назначение:
- единая точка раннего language detection для PDF-документов;
- используется и pre-run language discovery orchestrator'ом,
  и build_primary_language_source worker'ом;
- не пишет в БД и не знает про Deal/Document status — только строит
  quick layout и возвращает список найденных языков.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.logging import get_logger
from services.layout_language_filter import detect_languages_in_layout
from services.quick_pdf_layout import build_quick_layout_from_pdf


logger = get_logger(__name__)


@dataclass(slots=True)
class DocumentLanguageDetectionResult:
    quick_layout: dict
    detected_languages: list[str]


def detect_document_languages_from_pdf_bytes(
    *,
    pdf_bytes: bytes,
    document_id: str,
    document_version_id: str,
) -> DocumentLanguageDetectionResult:
    """
    Построить quick layout и определить языки документа.

    Для непрофессионального программиста:
    - quick_layout — это лёгкое промежуточное представление PDF,
      достаточное для раннего анализа структуры и языка;
    - detected_languages — список кодов языков, найденных в документе,
      например ["en"] или ["ru", "en"].

    Эта функция ничего не пишет в БД — только вычисляет и возвращает результат.
    """
    quick_layout = build_quick_layout_from_pdf(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    detected_languages = detect_languages_in_layout(quick_layout) or []

    logger.info(
        "Document language detection complete",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "detected_languages": detected_languages,
        },
    )

    return DocumentLanguageDetectionResult(
        quick_layout=quick_layout,
        detected_languages=detected_languages,
    )



    
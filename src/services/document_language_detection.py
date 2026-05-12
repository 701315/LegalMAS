# src/services/document_language_detection.py

"""
Shared document language detection service.

Назначение:
- единая точка раннего language detection для документов;
- используется и pre-run language discovery orchestrator'ом,
  и build_primary_language_source worker'ом;
- не пишет в БД и не знает про Deal/Document status — только строит
  лёгкое представление входных данных и возвращает список найденных языков.

Поддерживаемые входы:
- PDF bytes -> quick layout -> language detection;
- plain OCR text -> lightweight text layout -> language detection.

Важно:
- этот модуль ничего не знает про Celery, БД и статусы документов;
- он только вычисляет и возвращает результат;
- worker-слои сами решают, как сохранять completed / failed.
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


def _normalize_detected_languages(value: list[str] | None) -> list[str]:
    """
    Нормализовать список языков:
    - убрать пустые значения;
    - привести к lower-case;
    - убрать дубли;
    - отсортировать для стабильного результата.
    """
    if not value:
        return []

    normalized: set[str] = set()

    for item in value:
        if not isinstance(item, str):
            continue
        lang = item.strip().lower()
        if lang:
            normalized.add(lang)

    return sorted(normalized)


def _build_quick_layout_from_text(*, text: str) -> dict:
    """
    Построить минимальный layout-совместимый объект из plain text.

    Для непрофессионального программиста:
    - downstream language detector уже умеет работать с layout-подобной структурой;
    - для OCR текста нам не нужен полноценный PDF layout;
    - достаточно отдать простой документ с одной страницей и одним текстовым блоком.

    Почему это хорошо:
    - не дублируем логику определения языков;
    - и PDF, и OCR text идут через один и тот же detect_languages_in_layout(...).
    """
    cleaned_text = (text or "").strip()

    return {
        "pages": [
            {
                "page_number": 1,
                "blocks": [
                    {
                        "type": "text",
                        "text": cleaned_text,
                    }
                ],
            }
        ]
    }


def detect_document_languages_from_pdf_bytes(
    *,
    pdf_bytes: bytes,
    document_id: str,
    document_version_id: str,
) -> DocumentLanguageDetectionResult:
    """
    Построить quick layout и определить языки документа по PDF bytes.

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

    detected_languages = _normalize_detected_languages(
        detect_languages_in_layout(quick_layout) or []
    )

    logger.info(
        "Document language detection from PDF complete",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "detected_languages": detected_languages,
            "source_type": "pdf_bytes",
        },
    )

    return DocumentLanguageDetectionResult(
        quick_layout=quick_layout,
        detected_languages=detected_languages,
    )


def detect_document_languages_from_text(
    *,
    text: str,
    document_id: str,
    document_version_id: str,
) -> DocumentLanguageDetectionResult:
    """
    Определить языки документа по уже извлечённому OCR/plain text.

    Для непрофессионального программиста:
    - OCR worker сначала достаёт текст из скана или изображения;
    - потом передаёт этот текст сюда;
    - здесь текст превращается в лёгкий layout-объект, совместимый
      с общим механизмом language detection.

    Эта функция ничего не пишет в БД — только вычисляет и возвращает результат.
    """
    cleaned_text = (text or "").strip()
    quick_layout = _build_quick_layout_from_text(text=cleaned_text)

    detected_languages = _normalize_detected_languages(
        detect_languages_in_layout(quick_layout) or []
    )

    logger.info(
        "Document language detection from text complete",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "detected_languages": detected_languages,
            "source_type": "text",
            "text_length": len(cleaned_text),
        },
    )

    return DocumentLanguageDetectionResult(
        quick_layout=quick_layout,
        detected_languages=detected_languages,
    )

    
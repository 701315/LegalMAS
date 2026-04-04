# src/services/quick_pdf_layout.py

"""
Quick PDF layout service.

Назначение:
- быстро получить layout документа из PDF-байтов для раннего языкового анализа;
- переиспользовать существующий pdf_extractor, а не дублировать extraction-логику;
- дать build_primary_language_source.py единый контракт:
    build_quick_layout_from_pdf(...) -> layout dict

ВАЖНО:
- это не отдельный альтернативный extractor;
- это тонкая обёртка над services.pdf_extractor;
- результат подходит для:
  - detect_languages_in_layout(...)
  - filter_layout_to_language(...)
  - будущего построения одноязычного PDF.

Ограничения:
- сейчас используется тот же extract_pdf(), что и в основном extract_worker.
  Это значит, что на текущем этапе "quick" означает не "упрощённый OCR-free parser",
  а "ранний layout-contract wrapper".
- позже этот сервис можно оптимизировать отдельно, не меняя worker-код.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.exceptions import PermanentError
from core.logging import get_logger
from services.pdf_extractor import (
    ExtractionResult,
    build_text_layout_raw,
    extract_pdf,
)

logger = get_logger(__name__)


@dataclass
class QuickLayoutResult:
    """
    Результат быстрого построения layout из PDF.

    layout:
    - layout в формате text_layout_raw, пригодный для language pipeline.

    extraction:
    - исходный результат extract_pdf, если вызывающему коду нужны
      дополнительные метрики / стратегия / ошибки.
    """

    layout: dict[str, Any]
    extraction: ExtractionResult


def build_quick_layout_from_pdf(
    pdf_bytes: bytes,
    document_id: str,
    document_version_id: str,
) -> dict[str, Any]:
    """
    Построить layout для раннего анализа документа.

    Это упрощённая точка входа для большинства вызовов:
    вызывающий код получает только layout dict.
    Если нужен ещё и ExtractionResult, используй build_quick_layout_result_from_pdf().
    """
    result = build_quick_layout_result_from_pdf(
        pdf_bytes=pdf_bytes,
        document_id=document_id,
        document_version_id=document_version_id,
    )
    return result.layout


def build_quick_layout_result_from_pdf(
    pdf_bytes: bytes,
    document_id: str,
    document_version_id: str,
) -> QuickLayoutResult:
    """
    Построить layout и вернуть вместе с сырым ExtractionResult.

    Когда использовать:
    - если нужно не только layout, но и техническая диагностика:
      page_count, strategy, avg_ocr_confidence, errors.

    Ошибки:
    - если extract_pdf вернул критически пустой результат, поднимаем PermanentError;
    - если extraction содержит ошибки, но при этом элементы всё же есть,
      layout всё равно возвращаем — это production-safe поведение.
    """
    if not pdf_bytes:
        raise PermanentError(
            f"Quick PDF layout build failed: empty pdf_bytes for document {document_id}"
        )

    logger.info(
        "Quick PDF layout: starting",
        document_id=document_id,
        document_version_id=document_version_id,
        size=len(pdf_bytes),
    )

    extraction = extract_pdf(pdf_bytes, document_id=document_id)

    if extraction.errors:
        logger.warning(
            "Quick PDF layout: extractor returned errors",
            document_id=document_id,
            document_version_id=document_version_id,
            page_count=extraction.page_count,
            strategy=extraction.strategy,
            errors=extraction.errors,
        )

    if not extraction.page_count:
        raise PermanentError(
            f"Quick PDF layout build failed: extractor returned 0 pages "
            f"for document {document_id}"
        )

    if not extraction.elements:
        raise PermanentError(
            f"Quick PDF layout build failed: no elements extracted "
            f"for document {document_id}"
        )

    layout = build_text_layout_raw(
        extraction=extraction,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    layout = _attach_quick_layout_metadata(layout, extraction)

    logger.info(
        "Quick PDF layout: complete",
        document_id=document_id,
        document_version_id=document_version_id,
        page_count=extraction.page_count,
        strategy=extraction.strategy,
        elements=len(extraction.elements),
        tables=len(extraction.tables),
        avg_ocr_confidence=round(extraction.avg_ocr_confidence, 3)
        if extraction.avg_ocr_confidence is not None
        else None,
    )

    return QuickLayoutResult(
        layout=layout,
        extraction=extraction,
    )


def _attach_quick_layout_metadata(
    layout: dict[str, Any],
    extraction: ExtractionResult,
) -> dict[str, Any]:
    """
    Добавить в metadata следы раннего построения layout.

    Это нужно для диагностики и для будущей эволюции пайплайна:
    будет видно, что layout был построен на pre-extract этапе.
    """
    result = dict(layout)
    metadata = dict(result.get("metadata") or {})
    quick_layout_meta = dict(metadata.get("quick_layout") or {})

    quick_layout_meta.update(
        {
            "built_for": "build_primary_language_source",
            "page_count": extraction.page_count,
            "strategy": extraction.strategy,
            "avg_ocr_confidence": round(extraction.avg_ocr_confidence, 3)
            if extraction.avg_ocr_confidence is not None
            else None,
            "element_count": len(extraction.elements),
            "table_count": len(extraction.tables),
            "errors": list(extraction.errors or []),
        }
    )

    metadata["quick_layout"] = quick_layout_meta
    result["metadata"] = metadata
    return result


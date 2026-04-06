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

# ---------------------------------------------------------------------------
# Quality thresholds
# ---------------------------------------------------------------------------

# Минимум символов в документе, чтобы считать extraction хоть сколько-то содержательным.
_MIN_TOTAL_EXTRACTED_CHARS = 20

# Минимальная доля элементов с непустым текстом.
_MIN_NON_EMPTY_TEXT_RATIO = 0.50

# Минимальная доля элементов с валидным bbox.
_MIN_VALID_BBOX_RATIO = 0.60

# Минимальная доля элементов, которые одновременно содержат текст и валидный bbox.
_MIN_USABLE_ELEMENT_RATIO = 0.40


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
    - если extract_pdf вернул критически пустой или деградированный результат,
      поднимаем PermanentError;
    - если extraction содержит ошибки, но layout всё ещё пригоден,
      layout возвращаем, а деградацию отражаем в metadata.
    """
    if not pdf_bytes:
        raise PermanentError(
            f"Quick PDF layout build failed: empty pdf_bytes for document {document_id}"
        )

    if not _looks_like_pdf(pdf_bytes):
        raise PermanentError(
            f"Quick PDF layout build failed: source is not a PDF "
            f"for document {document_id}"
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

    quality = _assess_extraction_quality(extraction)

    if quality["hard_failed"]:
        raise PermanentError(
            f"Quick PDF layout build failed: degraded extraction for document "
            f"{document_id}; reason={quality['degraded_reason']}"
        )

    layout = build_text_layout_raw(
        extraction=extraction,
        document_id=document_id,
        document_version_id=document_version_id,
    )

    layout = _attach_quick_layout_metadata(layout, extraction, quality)

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
        degraded=quality["degraded"],
        degraded_reason=quality["degraded_reason"],
        total_chars=quality["total_extracted_chars"],
        valid_bbox_ratio=quality["valid_bbox_ratio"],
        usable_element_ratio=quality["usable_element_ratio"],
    )

    return QuickLayoutResult(
        layout=layout,
        extraction=extraction,
    )


def _looks_like_pdf(file_bytes: bytes) -> bool:
    """
    Быстрая эвристика: проверяем, похож ли вход на PDF.

    Политика:
    - сначала строгая проверка на сигнатуру в начале файла;
    - затем fallback для редких кейсов с мусором/BOM перед %PDF-.
    """
    if not file_bytes:
        return False

    if file_bytes.startswith(b"%PDF-"):
        return True

    header_window = file_bytes[:1024]
    looks_like = b"%PDF-" in header_window

    if looks_like:
        logger.warning(
            "Quick PDF layout: PDF signature found not at byte 0",
            header_prefix=header_window[:32],
        )

    return looks_like


def _attach_quick_layout_metadata(
    layout: dict[str, Any],
    extraction: ExtractionResult,
    quality: dict[str, Any],
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
            "total_extracted_chars": quality["total_extracted_chars"],
            "non_empty_text_elements": quality["non_empty_text_elements"],
            "valid_bbox_elements": quality["valid_bbox_elements"],
            "usable_elements": quality["usable_elements"],
            "non_empty_text_ratio": quality["non_empty_text_ratio"],
            "valid_bbox_ratio": quality["valid_bbox_ratio"],
            "usable_element_ratio": quality["usable_element_ratio"],
            "degraded": quality["degraded"],
            "degraded_reason": quality["degraded_reason"],
        }
    )

    metadata["quick_layout"] = quick_layout_meta
    result["metadata"] = metadata
    return result


def _assess_extraction_quality(extraction: ExtractionResult) -> dict[str, Any]:
    """
    Оценить пригодность extraction для downstream language/layout pipeline.

    Возвращает:
    - degraded: bool  -> extraction подозрительный, но ещё пригодный
    - hard_failed: bool -> extraction слишком плохой, pipeline надо остановить
    """
    elements = extraction.elements or []
    total_elements = len(elements)

    non_empty_text_elements = 0
    valid_bbox_elements = 0
    usable_elements = 0
    total_extracted_chars = 0

    for el in elements:
        text = str(getattr(el, "text", "") or "")
        bbox = getattr(el, "bbox", None)

        has_text = bool(text.strip())
        if has_text:
            non_empty_text_elements += 1
            total_extracted_chars += len(text.strip())

        if _is_valid_bbox(bbox):
            valid_bbox_elements += 1
            if has_text:
                usable_elements += 1

    non_empty_text_ratio = (
        non_empty_text_elements / total_elements if total_elements else 0.0
    )
    valid_bbox_ratio = (
        valid_bbox_elements / total_elements if total_elements else 0.0
    )
    usable_element_ratio = (
        usable_elements / total_elements if total_elements else 0.0
    )

    degraded_reasons: list[str] = []
    hard_fail_reasons: list[str] = []

    if total_elements == 0:
        hard_fail_reasons.append("no_elements")

    if total_extracted_chars < _MIN_TOTAL_EXTRACTED_CHARS:
        hard_fail_reasons.append(
            f"too_few_chars:{total_extracted_chars}"
        )

    if non_empty_text_ratio < _MIN_NON_EMPTY_TEXT_RATIO:
        degraded_reasons.append(
            f"low_non_empty_text_ratio:{non_empty_text_ratio:.3f}"
        )

    if valid_bbox_ratio < _MIN_VALID_BBOX_RATIO:
        degraded_reasons.append(
            f"low_valid_bbox_ratio:{valid_bbox_ratio:.3f}"
        )

    if usable_element_ratio < _MIN_USABLE_ELEMENT_RATIO:
        degraded_reasons.append(
            f"low_usable_element_ratio:{usable_element_ratio:.3f}"
        )

    # Если extractor сам вернул ошибки и при этом usable layout слабый —
    # считаем это уже hard failure.
    if extraction.errors and usable_element_ratio < _MIN_USABLE_ELEMENT_RATIO:
        hard_fail_reasons.append("extractor_errors_with_low_usable_ratio")

    degraded = bool(degraded_reasons or hard_fail_reasons)
    hard_failed = bool(hard_fail_reasons)

    all_reasons = hard_fail_reasons + degraded_reasons

    return {
        "degraded": degraded,
        "hard_failed": hard_failed,
        "degraded_reason": ";".join(all_reasons) if all_reasons else None,
        "total_elements": total_elements,
        "non_empty_text_elements": non_empty_text_elements,
        "valid_bbox_elements": valid_bbox_elements,
        "usable_elements": usable_elements,
        "total_extracted_chars": total_extracted_chars,
        "non_empty_text_ratio": round(non_empty_text_ratio, 4),
        "valid_bbox_ratio": round(valid_bbox_ratio, 4),
        "usable_element_ratio": round(usable_element_ratio, 4),
    }


def _is_valid_bbox(bbox: Any) -> bool:
    """
    Проверить, что bbox выглядит пригодным для layout-анализа.
    Ожидаем [x0, top, x1, bottom], где x1 > x0 и bottom > top.
    """
    if not isinstance(bbox, (list, tuple)) or len(bbox) < 4:
        return False

    try:
        x0 = float(bbox[0])
        top = float(bbox[1])
        x1 = float(bbox[2])
        bottom = float(bbox[3])
    except (TypeError, ValueError):
        return False

    return x1 > x0 and bottom > top


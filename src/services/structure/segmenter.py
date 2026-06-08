# src/services/structure/segmenter.py

"""
Детерминированная сегментация физического файла на логические сегменты.

Этот модуль является публичным фасадом: единственный внешний API —
функция ``segment_elements()``.

Вся внутренняя логика вынесена в пакет ``services.structure._segmenter``:
- config          — числовые пороги и лимиты
- types           — dataclass-модели boundary layer
- patterns        — regex-семейства и pattern-helpers
- element_utils   — safe-accessors и element-type предикаты
- heuristics      — текстовые / контекстные эвристики boundary-позиции
- confidence      — маппинг score → label
- artifacts       — детекция running headers / page artifacts
- candidates      — сбор и валидация boundary-кандидатов
- assembly        — сборка сегментов, scope, metadata propagation
- purity          — post-segmentation purity recovery (P1)
- toc_suppression — подавление ложных boundary-family границ на TOC / catalog pages (P5/A3)
"""

from __future__ import annotations

from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.models import SegmentDocument

from ._segmenter.artifacts import detect_repeated_page_artifacts
from ._segmenter.assembly import (
    assign_primary_segment,
    attach_scope_names,
    build_segments_from_candidates,
    make_single_segment,
    propagate_segment_metadata,
)
from ._segmenter.candidates import (
    collect_boundary_candidates,
    validate_boundary_candidates,
)
from ._segmenter.config import (
    DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD,
    MAX_REASONABLE_SEGMENTS,
)
from ._segmenter.patterns import extract_appendix_number, infer_boundary_family_from_text
from ._segmenter.purity import recover_segment_purity_candidates
from ._segmenter.toc_suppression import build_boundary_suppression_context

logger = get_logger(__name__)

# ── Compatibility re-exports ─────────────────────────────────────────────────
# Тесты и другие модули могут импортировать эти имена напрямую из segmenter.
_extract_appendix_number = extract_appendix_number


def _resolve_boundary_family_for_suppression(text: str) -> str | None:
    """Callback для ``build_boundary_suppression_context``.

    Переиспользует canonical boundary-family grammar из ``patterns``,
    чтобы suppression и основной detection не расходились.

    Возвращает canonical family string ("appendix" / "amendment") или None.
    """
    return infer_boundary_family_from_text(text)


# ── Публичный API ────────────────────────────────────────────────────────────

def segment_elements(
    document_id: str,
    elements: list[dict[str, Any]],
) -> list[SegmentDocument]:
    """Разбивает elements[] на логические SegmentDocuments.

    Гарантии:
    - никогда не бросает исключение наружу;
    - всегда возвращает >= 1 сегмент;
    - если надёжных границ нет — возвращает один сегмент на весь файл.
    """
    try:
        return _segment_elements_impl(document_id=document_id, elements=elements)
    except Exception as e:
        logger.exception(
            "STRUCTURE segmenter failed, falling back to single segment",
            extra={
                "document_id": document_id,
                "elements_count": len(elements or []),
                "error": str(e),
            },
        )
        return [make_single_segment(document_id=document_id, elements=elements or [])]


# ── Orchestration ────────────────────────────────────────────────────────────

def _segment_elements_impl(
    *,
    document_id: str,
    elements: list[dict[str, Any]],
) -> list[SegmentDocument]:
    """Основная реализация сегментации: координирует все внутренние слои."""
    if not document_id:
        document_id = "<unknown>"

    if not isinstance(elements, list) or not elements:
        return [make_single_segment(document_id=document_id, elements=[])]

    clean_elements = [el for el in elements if isinstance(el, dict)]
    if not clean_elements:
        return [make_single_segment(document_id=document_id, elements=[])]

    # 1. Артефакты повторяющихся заголовков.
    artifacts = detect_repeated_page_artifacts(clean_elements)

    # 2. P5/A3: TOC / catalog boundary-family suppression context.
    suppression_context = build_boundary_suppression_context(
        clean_elements,
        resolve_boundary_family=_resolve_boundary_family_for_suppression,
    )

    if suppression_context.suppressed_boundary_families_by_page:
        logger.info(
            "STRUCTURE segmenter_boundary_suppression_context",
            extra={
                "document_id": document_id,
                **suppression_context.to_dict(),
            },
        )

    # 3. Сбор boundary-кандидатов.
    candidates = collect_boundary_candidates(
        clean_elements,
        artifacts=artifacts,
        suppression_context=suppression_context,
    )

    # 4. Валидация кандидатов.
    validated_candidates = validate_boundary_candidates(clean_elements, candidates)

    # 5. Порог уверенности.
    threshold = float(
        getattr(
            settings,
            "SEGMENT_CONFIDENCE_THRESHOLD",
            DEFAULT_SEGMENT_CONFIDENCE_THRESHOLD,
        )
    )

    accepted_candidates = [
        c for c in validated_candidates if c.confidence_score >= threshold
    ]

    # 6. P1: purity recovery.
    if accepted_candidates:
        accepted_candidates = recover_segment_purity_candidates(
            document_id=document_id,
            elements=clean_elements,
            accepted_candidates=accepted_candidates,
            threshold=threshold,
            suppression_context=suppression_context,
        )

    # 7. Single-segment fallback.
    if not accepted_candidates:
        single = make_single_segment(document_id=document_id, elements=clean_elements)
        propagate_segment_metadata(elements=clean_elements, segments=[single])

        logger.info(
            "STRUCTURE segmenter_single_segment_mode",
            extra={
                "document_id": document_id,
                "elements_count": len(clean_elements),
                "candidates_found": len(candidates),
                "validated_candidates": len(validated_candidates),
                "accepted_candidates": 0,
                "threshold": threshold,
                "rejected_reasons_preview": [
                    {
                        "element_index": c.element_index,
                        "page": c.page,
                        "segment_type": c.segment_type,
                        "confidence_score": round(c.confidence_score, 3),
                        "reasons": list(c.reasons),
                    }
                    for c in validated_candidates[:10]
                ],
            },
        )
        return [single]

    # 8. Сборка сегментов.
    segments = build_segments_from_candidates(
        document_id=document_id,
        elements=clean_elements,
        candidates=accepted_candidates,
    )

    if not segments:
        single = make_single_segment(document_id=document_id, elements=clean_elements)
        propagate_segment_metadata(elements=clean_elements, segments=[single])
        return [single]

    # 9. Слишком много сегментов — safety fallback.
    if len(segments) > MAX_REASONABLE_SEGMENTS:
        logger.warning(
            "STRUCTURE segmenter_too_many_segments_fallback_to_single",
            extra={
                "document_id": document_id,
                "segments_count": len(segments),
                "max_reasonable_segments": MAX_REASONABLE_SEGMENTS,
            },
        )
        single = make_single_segment(document_id=document_id, elements=clean_elements)
        propagate_segment_metadata(elements=clean_elements, segments=[single])
        return [single]

    # 10. Финализация: primary, scopes, metadata.
    assign_primary_segment(segments)
    attach_scope_names(segments)
    propagate_segment_metadata(elements=clean_elements, segments=segments)

    logger.info(
        "STRUCTURE segmenter_completed",
        extra={
            "document_id": document_id,
            "elements_count": len(clean_elements),
            "segments_count": len(segments),
            "segment_types": [s.segment_type for s in segments],
            "scope_names": [getattr(s, "scope_name", None) for s in segments],
            "accepted_boundaries": [
                {
                    "element_index": c.element_index,
                    "page": c.page,
                    "segment_type": c.segment_type,
                    "confidence_score": round(c.confidence_score, 3),
                    "reasons": list(c.reasons),
                }
                for c in accepted_candidates
            ],
        },
    )

    return segments



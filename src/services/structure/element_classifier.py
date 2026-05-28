# src/services/structure/element_classifier.py

"""
Element classifier для structural pipeline.

Роль модуля:
- давать каждому элементу документа semantic type label;
- определять TOC-related элементы через локальный scoring;
- НЕ принимать authoritative policy decisions о suppression.

Ключевой принцип разделения ответственности:
- Classifier знает: "эта строка ПОХОЖА на TOC line" (semantic label).
- Pipeline знает: "TOC достаточно надёжен, чтобы suppress body" (policy).

Почему guard НЕ считается здесь:
- evaluate_toc_alignment() требует сматченный ParsedTOC (после attach_toc_matches).
- headings для matching ещё не построены на этапе classify_elements().
- Значит любой guard здесь будет работать без alignment и всегда давать reject_toc.
- Authoritative guard считается в pipeline после первого прохода build_heading_candidates().

Что classifier делает с TOC:
- detect_toc_block() + parse_toc_entries() для contextual boost.
- Локальный _toc_line_score() для per-element scoring.
- Provisional TOC context (без alignment) для аннотации элементов.
- Финальные toc_guard_* metadata проставляет pipeline через _annotate_elements_with_guard().
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.structure.toc_guard import (
    TOC_GUARD_PARTIAL,
    TOC_GUARD_REJECT,
    TOCGuardVerdict,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING as SEMANTIC_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING as SEMANTIC_TYPE_SUBSECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
)
from services.structure.legal_heading_rules import (
    compute_heading_continuity_signals,
)

# ============================================================================
# Импорты из внутренних модулей (не экспортируются наружу)
# ============================================================================

from services.structure.element_classifier._config import *
from services.structure.element_classifier._text_utils import (
    _normalize_text,
)
from services.structure.element_classifier._toc_context import _TocContext
from services.structure.element_classifier._page_stats import _build_page_stats
from services.structure.element_classifier._semantic_resolver import (
    _compute_semantic_element_type,
    _compute_heading_confidence_from_classification,
)
from services.structure.element_classifier._classify_single import _classify_single_element
from services.structure.element_classifier._classify_reason import ClassificationReason, ClassificationResult
from services.structure.element_classifier._logging import _log_classification_summary


logger = get_logger(__name__)


# ============================================================================
# Public element type constants
# ============================================================================

ELEMENT_TYPE_HEADING_CANDIDATE = "heading_candidate"
ELEMENT_TYPE_BODY_TEXT = "body_text"
ELEMENT_TYPE_TABLE_CONTENT = "table_content"
ELEMENT_TYPE_REQUISITES_BLOCK = "requisites_block"
ELEMENT_TYPE_SIGNATURE_BLOCK = "signature_block"

# TOC semantic types.
# Важно: это semantic labels, а не policy decisions.
# toc_header   — явный заголовок оглавления ("Содержание", "Table of Contents").
# toc_line     — строка с высоким локальным TOC score (>= 0.78).
# possible_toc — строка со средним TOC score (0.52–0.78).
# toc_false_positive — строка похожа на TOC локально, но по природе является body/definition.
ELEMENT_TYPE_TOC_HEADER = "toc_header"
ELEMENT_TYPE_TOC_LINE = "toc_line"
ELEMENT_TYPE_POSSIBLE_TOC = "possible_toc"
ELEMENT_TYPE_TOC_FALSE_POSITIVE = "toc_false_positive"

ELEMENT_TYPE_LIST_ITEM = "list_item"
ELEMENT_TYPE_PAGE_ARTIFACT = "page_artifact"
ELEMENT_TYPE_UNKNOWN_LAYOUT = "unknown_layout"

SUPPORTED_ELEMENT_TYPES: frozenset[str] = frozenset(
    {
        ELEMENT_TYPE_HEADING_CANDIDATE,
        ELEMENT_TYPE_BODY_TEXT,
        ELEMENT_TYPE_TABLE_CONTENT,
        ELEMENT_TYPE_REQUISITES_BLOCK,
        ELEMENT_TYPE_SIGNATURE_BLOCK,
        ELEMENT_TYPE_TOC_HEADER,
        ELEMENT_TYPE_TOC_LINE,
        ELEMENT_TYPE_POSSIBLE_TOC,
        ELEMENT_TYPE_TOC_FALSE_POSITIVE,
        ELEMENT_TYPE_LIST_ITEM,
        ELEMENT_TYPE_PAGE_ARTIFACT,
        ELEMENT_TYPE_UNKNOWN_LAYOUT,
    }
)


# ============================================================================
# Public API
# ============================================================================

def classify_elements(
    elements: list[dict[str, Any]] | None,
    *,
    document_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Rule-based semantic classification элементов документа.

    Что делает:
    - определяет semantic type каждого элемента;
    - аннотирует TOC-related элементы через локальный scoring;
    - проставляет provisional TOC context (toc_in_parsed_block) для pipeline.

    Что НЕ делает:
    - НЕ принимает policy decisions о suppression;
    - НЕ считает authoritative guard (нет headings для alignment);
    - НЕ удаляет элементы физически.

    После classify_elements() pipeline должен вызвать:
    1. build_heading_candidates() — первый проход;
    2. analyze_toc_with_guard() — authoritative guard;
    3. _annotate_elements_with_guard() — проставить guard metadata.
    """
    if not elements:
        return []

    prepared = [dict(el) for el in elements if isinstance(el, dict)]
    if not prepared:
        return []

    page_stats = _build_page_stats(prepared)

    # Строим локальный TOC context один раз до цикла.
    # Используется только для contextual boost и semantic labels.
    toc_ctx = _TocContext.build(prepared)

    classified: list[dict[str, Any]] = []
    toc_fp_count = 0

    for idx, element in enumerate(prepared):
        result = _classify_single_element(
            element=element,
            index=idx,
            elements=prepared,
            page_stats=page_stats,
            toc_ctx=toc_ctx,
        )

        if result.element_type == ELEMENT_TYPE_TOC_FALSE_POSITIVE:
            toc_fp_count += 1

        meta = dict(result.metadata or {})

        # ── Этап 2: вычисляем semantic_element_type ──────────────────────
        # Это уточнённый semantic label поверх базового element_type.
        # Используется heading_scoring и heading_builder для более точных решений.
        text_for_semantic = _normalize_text(str(element.get("text") or ""))
        semantic_type = _compute_semantic_element_type(
            text=text_for_semantic,
            element_type=result.element_type,
            raw_type=result.raw_type,
        )
        meta["semantic_element_type"] = semantic_type

        # ── Heading confidence (первичная оценка classifier-а) ────────────
        heading_conf = _compute_heading_confidence_from_classification(
            element_type=result.element_type,
            classification_confidence=result.confidence,
            semantic_type=semantic_type,
        )
        meta["heading_confidence"] = heading_conf

        # ── Heading reject reasons (от classifier, не от scorer) ──────────
        # Собираем reject reasons на уровне classifier.
        # Scorer может добавить свои позже.
        classifier_reject_reasons: list[str] = []
        if semantic_type == SEMANTIC_TYPE_DEFINITION_ITEM:
            classifier_reject_reasons.append("definition_item_by_classifier")
        if semantic_type == SEMANTIC_TYPE_SIGNATURE_BLOCK:
            classifier_reject_reasons.append("signature_or_requisites_by_classifier")
        if semantic_type == SEMANTIC_TYPE_APPENDIX_HEADING:
            classifier_reject_reasons.append("appendix_heading_by_classifier")
        meta["heading_reject_reasons"] = classifier_reject_reasons

        # ── Continuity signals ────────────────────────────────────────────
        # Вычисляем только для потенциальных heading candidates.
        # Для body/toc/artifact элементов сигналы не нужны.
        if semantic_type in {
            SEMANTIC_TYPE_SECTION_HEADING,
            SEMANTIC_TYPE_SUBSECTION_HEADING,
            SEMANTIC_TYPE_APPENDIX_HEADING,
        }:
            prev_el = prepared[idx - 1] if idx > 0 else None
            next_el = prepared[idx + 1] if idx + 1 < len(prepared) else None
            continuity_signals = compute_heading_continuity_signals(
                prev_element=prev_el,
                next_element=next_el,
            )
        else:
            continuity_signals = {}
        meta["continuity_signals"] = continuity_signals

        # Помечаем, входит ли элемент в parsed TOC block.
        # Pipeline использует это как дополнительный сигнал.
        meta["toc_in_parsed_block"] = idx in toc_ctx.toc_source_indexes

        # Placeholder для guard metadata — будут проставлены pipeline.
        # Это предотвращает KeyError в downstream коде, который читает эти поля.
        meta.setdefault("toc_guard_decision", None)
        meta.setdefault("toc_guard_quality", None)
        meta.setdefault("toc_guard_reliability", None)
        meta.setdefault("toc_soft_block_only", None)
        meta.setdefault("body_recovered_from_toc", False)
        meta.setdefault("toc_false_positive_by_guard", False)

        normalized = dict(element)
        normalized["raw_element_type"] = str(element.get("type") or "").strip() or None
        normalized["element_type"] = result.element_type
        normalized["element_classification_confidence"] = round(result.confidence, 3)
        normalized["element_classification_reasons"] = [
            {"code": r.code, "weight": r.weight, "note": r.note}
            for r in result.reasons
        ]
        existing_meta = dict(normalized.get("metadata") or {})
        existing_meta.update(meta)
        normalized["metadata"] = existing_meta

        classified.append(normalized)

    _log_classification_summary(
        document_id=document_id,
        classified=classified,
        toc_ctx=toc_ctx,
        toc_fp_count=toc_fp_count,
    )
    return classified


def annotate_elements_with_guard(
    elements: list[dict[str, Any]],
    guard: TOCGuardVerdict,
) -> tuple[list[dict[str, Any]], int, int]:
    """
    Проставляет authoritative guard metadata на уже классифицированные элементы.

    Вызывается из pipeline ПОСЛЕ analyze_toc_with_guard().

    Что делает:
    - проставляет toc_guard_decision, toc_guard_quality, toc_guard_reliability;
    - для элементов из false_positive_indexes меняет element_type на toc_false_positive;
    - для элементов из recoverable_indexes помечает body_recovered_from_toc=True;
    - проставляет toc_soft_block_only для partial/reject режима.

    Возвращает:
    - annotated elements list;
    - body_recovered_count — число элементов помеченных как recovered;
    - guard_fp_count — число элементов переклассифицированных guard-ом как FP.
    """
    annotated: list[dict[str, Any]] = []
    body_recovered_count = 0
    guard_fp_count = 0

    # Защита: guard.false_positive_indexes и recoverable_indexes содержат
    # element indexes из classify_elements(). Если elements был изменён
    # между classify и annotate — индексы съедут.
    # Проверяем что размер совпадает.
    max_guard_idx = max(
        (max(guard.false_positive_indexes, default=-1),
         max(guard.recoverable_indexes, default=-1))
    )
    if max_guard_idx >= len(elements):
        logger.warning(
            "annotate_elements_with_guard: guard indexes out of range, "
            "elements list may have been modified between classify and annotate",
            extra={
                "elements_count": len(elements),
                "max_guard_index": max_guard_idx,
                "false_positive_indexes_count": len(guard.false_positive_indexes),
                "recoverable_indexes_count": len(guard.recoverable_indexes),
            },
        )

    is_soft_mode = guard.decision in {TOC_GUARD_PARTIAL, TOC_GUARD_REJECT}

    for idx, element in enumerate(elements):
        normalized = dict(element)
        meta = dict(normalized.get("metadata") or {})

        # Проставляем guard summary на каждый элемент
        meta["toc_guard_decision"] = guard.decision
        meta["toc_guard_quality"] = guard.toc_quality
        meta["toc_guard_reliability"] = guard.toc_reliability
        meta["toc_soft_block_only"] = is_soft_mode

        # Guard false positive override:
        # если guard пометил element index как false positive —
        # принудительно меняем element_type, независимо от локального scoring.
        # Это критичное требование чек-листа.
        if idx in guard.false_positive_indexes:
            normalized["element_type"] = ELEMENT_TYPE_TOC_FALSE_POSITIVE
            meta["toc_false_positive_by_guard"] = True
            meta["body_recovered_from_toc"] = False
            guard_fp_count += 1

        # Body recovery:
        # если элемент входит в recoverable_indexes guard-а
        # и тип всё ещё TOC-related — помечаем как recovered.
        elif idx in guard.recoverable_indexes:
            if normalized.get("element_type") in {
                ELEMENT_TYPE_TOC_LINE,
                ELEMENT_TYPE_POSSIBLE_TOC,
            }:
                meta["body_recovered_from_toc"] = True
                body_recovered_count += 1

        normalized["metadata"] = meta
        annotated.append(normalized)

    return annotated, body_recovered_count, guard_fp_count


# ============================================================================
# Публичный экспорт
# ============================================================================

__all__ = [
    # Типы элементов
    "ELEMENT_TYPE_HEADING_CANDIDATE",
    "ELEMENT_TYPE_BODY_TEXT",
    "ELEMENT_TYPE_TABLE_CONTENT",
    "ELEMENT_TYPE_REQUISITES_BLOCK",
    "ELEMENT_TYPE_SIGNATURE_BLOCK",
    "ELEMENT_TYPE_TOC_HEADER",
    "ELEMENT_TYPE_TOC_LINE",
    "ELEMENT_TYPE_POSSIBLE_TOC",
    "ELEMENT_TYPE_TOC_FALSE_POSITIVE",
    "ELEMENT_TYPE_LIST_ITEM",
    "ELEMENT_TYPE_PAGE_ARTIFACT",
    "ELEMENT_TYPE_UNKNOWN_LAYOUT",
    "SUPPORTED_ELEMENT_TYPES",
    # Dataclass'ы
    "ClassificationReason",
    "ClassificationResult",
    # Публичные функции
    "classify_elements",
    "annotate_elements_with_guard",
]

    
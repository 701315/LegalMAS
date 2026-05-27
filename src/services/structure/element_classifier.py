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

import re
from dataclasses import dataclass, field
from typing import Any

from core.logging import get_logger
from services.structure.toc_guard import (
    TOC_GUARD_PARTIAL,
    TOC_GUARD_REJECT,
    TOCGuardVerdict,
)
from services.structure.toc_parser import (
    TOCBlock,
    ParsedTOC,
    detect_toc_block,
    parse_toc_entries,
)
from services.structure.models import (
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING as SEMANTIC_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING as SEMANTIC_TYPE_SUBSECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM as SEMANTIC_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE as SEMANTIC_TYPE_ENUMERATED_CLAUSE,
    SEMANTIC_ELEMENT_TYPE_LIST_ITEM as SEMANTIC_TYPE_LIST_ITEM,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING as SEMANTIC_TYPE_APPENDIX_HEADING,
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK as SEMANTIC_TYPE_SIGNATURE_BLOCK,
    SEMANTIC_ELEMENT_TYPE_BODY_TEXT as SEMANTIC_TYPE_BODY_TEXT,
)
from services.structure.legal_heading_rules import (
    looks_like_definition_item,
    looks_like_appendix_heading,
    looks_like_signature_heading,
    looks_like_requisites_heading,
    compute_heading_continuity_signals,
    numeric_uid_depth,
)
from services.structure.heading_patterns import parse_raw_heading


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
# Configuration
# ============================================================================

BOUNDARY_KEYWORDS_RU = (
    "приложение",
    "акт",
    "дополнительное соглашение",
    "доп соглашение",
    "соглашение",
    "протокол",
)

TOC_HEADER_PATTERNS = (
    r"^содержание$",
    r"^оглавление$",
    r"^table of contents$",
    r"^contents$",
)

TOC_LINE_UID_PREFIX = (
    "1 ",
    "1.",
    "i ",
    "i.",
    "ii ",
    "ii.",
    "iii ",
    "iii.",
    "a ",
    "a.",
)

REQUISITES_KEYWORDS_RU = (
    "реквизиты",
    "реквизиты сторон",
    "юридический адрес",
    "почтовый адрес",
    "адрес местонахождения",
    "адрес для корреспонденции",
    "инн",
    "кпп",
    "огрн",
    "окпо",
    "оквэд",
    "банк",
    "бик",
    "корреспондентский счет",
    "корр. счет",
    "кор счет",
    "расчетный счет",
    "расчётный счёт",
    "р/с",
    "к/с",
    "iban",
    "swift",
    "e-mail",
    "email",
    "телефон",
    "тел.",
    "факс",
    "адрес",
)

SIGNATURE_KEYWORDS_RU = (
    "подписи сторон",
    "подписи",
    "подпись",
    "стороны подписали",
    "от заказчика",
    "от исполнителя",
    "от поставщика",
    "от покупателя",
    "от арендатора",
    "от арендодателя",
    "от подрядчика",
    "от заказчика:",
    "от исполнителя:",
    "генеральный директор",
    "директор",
    "уполномоченный представитель",
    "м.п.",
    "мп",
)

PAGE_ARTIFACT_PATTERNS = (
    r"^стр\.?\s*\d+\s*$",
    r"^страница\s+\d+\s*$",
    r"^page\s+\d+\s*$",
    r"^\d+\s*/\s*\d+\s*$",
    r"^-\s*\d+\s*-$",
    r"^\d+$",
)

DOT_LEADER_RE = re.compile(
    r"""
    (?:
        [\.\·•_]{3,}
        |
        (?:\.\s*){3,}
    )
    """,
    re.VERBOSE,
)

UID_HEADING_RE = re.compile(
    r"""
    ^
    (?:
        \d{1,3}(?:\.\d{1,3})*\.?
        |
        [IVXLCM]{1,8}\.?
        |
        [A-ZА-ЯЁ]\)
        |
        [A-ZА-ЯЁ]\.
    )
    \s+
    .+
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

ROOT_HEADING_NO_DOT_RE = re.compile(
    r"""
    ^
    \d{1,3}
    \s+
    .{2,}
    $
    """,
    re.VERBOSE,
)

LIST_ITEM_RE = re.compile(
    r"""
    ^
    (?:
        [–\-•◦▪●]\s+
        |
        \d{1,3}[)\u00B0]\s+
        |
        [A-ZА-ЯЁa-zа-яё][)\.]\s+
    )
    .+
    $
    """,
    re.VERBOSE,
)

ROMAN_LIST_ITEM_RE = re.compile(
    r"""
    ^
    [IVXLCM]{1,8}[)\.]
    \s+
    .+
    $
    """,
    re.VERBOSE | re.IGNORECASE,
)

NORMALIZE_NUM_SIGN_RE = re.compile(r"\b(?:№|N|No\.?)\s*")
WHITESPACE_RE = re.compile(r"\s+")
PUNCT_SPACES_RE = re.compile(r"\s*([:;,.])\s*")


# ============================================================================
# Data models
# ============================================================================

@dataclass(slots=True)
class ClassificationReason:
    code: str
    weight: float
    note: str


@dataclass(slots=True)
class ClassificationResult:
    element_type: str
    confidence: float
    reasons: list[ClassificationReason]
    raw_type: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class _TocContext:
    """
    Локальный TOC-контекст для classifier.

    Содержит только то, что classifier может знать самостоятельно:
    - результат detect_toc_block / parse_toc_entries;
    - локальный contextual state (видели ли header, на какой странице).

    НЕ содержит authoritative guard verdict —
    он придёт из pipeline после alignment.
    """
    toc_block: TOCBlock | None = None
    parsed_toc: ParsedTOC | None = None

    # TOC source element indexes из parsed entries — для contextual enrichment
    toc_source_indexes: set[int] = field(default_factory=set)

    # Contextual state в процессе итерации
    header_seen: bool = False
    header_page: int | None = None
    recent_strong_toc_indexes: list[int] = field(default_factory=list)

    @classmethod
    def build(cls, elements: list[dict[str, Any]]) -> "_TocContext":
        """
        Строит TocContext из elements.
        Вызывается один раз до цикла classify.
        """
        toc_block = detect_toc_block(elements)
        parsed_toc = parse_toc_entries(toc_block)

        # Собираем все source_element_indexes из parsed entries.
        # Это позволяет быстро проверить "входит ли элемент в TOC block"
        # без повторного прохода по entries.
        source_indexes: set[int] = set()
        for entry in parsed_toc.entries:
            for idx in (entry.source_element_indexes or []):
                if isinstance(idx, int) and idx >= 0:
                    source_indexes.add(idx)

        return cls(
            toc_block=toc_block,
            parsed_toc=parsed_toc,
            toc_source_indexes=source_indexes,
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
# Internal helpers: page statistics
# ============================================================================

def _build_page_stats(elements: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    page_to_tops: dict[int, list[float]] = {}
    page_to_bottoms: dict[int, list[float]] = {}

    for el in elements:
        page = _safe_int(el.get("page"), default=1)
        bbox = _safe_bbox(el.get("bbox"))
        top = bbox[1]
        bottom = bbox[3]
        page_to_tops.setdefault(page, []).append(top)
        page_to_bottoms.setdefault(page, []).append(bottom)

    stats: dict[int, dict[str, float]] = {}
    for page in set(page_to_tops) | set(page_to_bottoms):
        tops = page_to_tops.get(page, [0.0])
        bottoms = page_to_bottoms.get(page, [0.0])
        min_top = min(tops) if tops else 0.0
        max_bottom = max(bottoms) if bottoms else 0.0
        span = max(max_bottom - min_top, 1.0)
        stats[page] = {
            "min_top": float(min_top),
            "max_bottom": float(max_bottom),
            "span": float(span),
        }

    return stats


def _relative_page_position(
    element: dict[str, Any],
    page_stats: dict[int, dict[str, float]],
) -> tuple[float, float]:
    page = _safe_int(element.get("page"), default=1)
    bbox = _safe_bbox(element.get("bbox"))
    top = bbox[1]
    bottom = bbox[3]

    stats = page_stats.get(page) or {
        "min_top": 0.0,
        "max_bottom": max(bottom, 1.0),
        "span": 1.0,
    }
    min_top = stats["min_top"]
    max_bottom = stats["max_bottom"]
    span = max(stats["span"], 1.0)

    top_ratio = (top - min_top) / span
    bottom_ratio = (max_bottom - bottom) / span
    return top_ratio, bottom_ratio


# ============================================================================
# Internal helpers: single element classifier
# ============================================================================

def _classify_single_element(
    *,
    element: dict[str, Any],
    index: int,
    elements: list[dict[str, Any]],
    page_stats: dict[int, dict[str, float]],
    toc_ctx: _TocContext,
) -> ClassificationResult:
    """
    Классифицирует один элемент.

    Порядок приоритетов:
    1. Пустой текст → unknown_layout.
    2. Page artifact → page_artifact.
    3. TOC header → toc_header.
    4. TOC line scoring (local):
       - >= 0.78 → toc_line (или toc_false_positive если substantive).
       - 0.52–0.78 → possible_toc (или toc_false_positive).
    5. Signature block → signature_block.
    6. Requisites block → requisites_block.
    7. Table content → table_content.
    8. List item → list_item.
    9. Heading candidate → heading_candidate.
    10. Unknown layout.
    11. Default body_text.
    """
    text = _normalize_text(str(element.get("text") or ""))
    raw_type = str(element.get("type") or "").strip().lower() or None
    top_ratio, bottom_ratio = _relative_page_position(element, page_stats)
    page = _safe_int(element.get("page"), default=1)

    # 1. Пустой текст
    if not text:
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.55,
            reasons=[ClassificationReason(
                "empty_text", 0.55, "Empty or whitespace-only text"
            )],
            raw_type=raw_type,
        )

    reasons: list[ClassificationReason] = []

    # 2. Page artifact
    if _looks_like_page_artifact(text=text, top_ratio=top_ratio, bottom_ratio=bottom_ratio):
        reasons.append(ClassificationReason(
            "page_artifact_pattern",
            0.97,
            "Looks like page number/header/footer artifact near page edge",
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_PAGE_ARTIFACT,
            confidence=0.97,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 3. TOC header
    if _is_toc_header(text):
        toc_ctx.header_seen = True
        toc_ctx.header_page = page
        reasons.append(ClassificationReason(
            "toc_header", 0.98, "Explicit TOC header detected"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TOC_HEADER,
            confidence=0.98,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 4. TOC line scoring с contextual boost
    toc_score, toc_score_reasons = _toc_line_score(text)

    prev_text = (
        _normalize_text(str(elements[index - 1].get("text") or ""))
        if index > 0 else ""
    )
    next_text = (
        _normalize_text(str(elements[index + 1].get("text") or ""))
        if index + 1 < len(elements) else ""
    )

    contextual_boost = 0.0

    # Boost если рядом TOC header на той же или следующей странице
    if (
        toc_ctx.header_seen
        and toc_ctx.header_page is not None
        and page in {toc_ctx.header_page, toc_ctx.header_page + 1}
    ):
        contextual_boost += 0.06

    # Boost если соседи — сильные TOC lines
    if _is_toc_header(prev_text) or _is_toc_line(prev_text) or _is_toc_line(next_text):
        contextual_boost += 0.06

    toc_score = min(1.0, toc_score + contextual_boost)

    # Сильный TOC signal
    if toc_score >= 0.78:
        toc_ctx.recent_strong_toc_indexes.append(index)
        toc_ctx.recent_strong_toc_indexes[:] = toc_ctx.recent_strong_toc_indexes[-8:]

        for reason_code in toc_score_reasons:
            reasons.append(ClassificationReason(
                f"toc_signal:{reason_code}", toc_score, "Strong TOC line signal"
            ))
        if contextual_boost > 0:
            reasons.append(ClassificationReason(
                "toc_contextual_boost",
                contextual_boost,
                "Nearby TOC header or strong TOC line increased confidence",
            ))

        # Локальный false positive override — по природе текста, не по guard.
        # Guard FP override будет применён позже через annotate_elements_with_guard().
        if _looks_like_toc_false_positive(text):
            reasons.append(ClassificationReason(
                "toc_false_positive_local",
                0.86,
                "Line has substantive/body-like signals despite high TOC score",
            ))
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_FALSE_POSITIVE,
                confidence=0.86,
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "toc_semantic_role": "toc_false_positive",
                    "toc_score": round(toc_score, 3),
                },
            )

        # toc_line — semantic label, не policy decision.
        # Pipeline решит что с ним делать на основе guard verdict.
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TOC_LINE,
            confidence=round(toc_score, 3),
            reasons=reasons,
            raw_type=raw_type,
            metadata={
                "toc_semantic_role": "toc_line",
                "toc_score": round(toc_score, 3),
            },
        )

    # Средний TOC signal
    if 0.52 <= toc_score < 0.78:
        for reason_code in toc_score_reasons:
            reasons.append(ClassificationReason(
                f"possible_toc_signal:{reason_code}",
                toc_score,
                "Weak or partial TOC signal",
            ))
        if contextual_boost > 0:
            reasons.append(ClassificationReason(
                "possible_toc_contextual_boost",
                contextual_boost,
                "Nearby TOC context slightly increased confidence",
            ))

        if _looks_like_toc_false_positive(text):
            reasons.append(ClassificationReason(
                "possible_toc_false_positive_local",
                0.80,
                "Weak TOC signal overridden by substantive/body-like features",
            ))
            return ClassificationResult(
                element_type=ELEMENT_TYPE_TOC_FALSE_POSITIVE,
                confidence=0.80,
                reasons=reasons,
                raw_type=raw_type,
                metadata={
                    "toc_semantic_role": "toc_false_positive",
                    "toc_score": round(toc_score, 3),
                },
            )

        return ClassificationResult(
            element_type=ELEMENT_TYPE_POSSIBLE_TOC,
            confidence=round(toc_score, 3),
            reasons=reasons,
            raw_type=raw_type,
            metadata={
                "toc_semantic_role": "possible_toc",
                "toc_score": round(toc_score, 3),
            },
        )

    # 5. Signature block
    if _looks_like_signature_block(text):
        reasons.append(ClassificationReason(
            "signature_keywords", 0.94, "Contains signature/seal/representative markers"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_SIGNATURE_BLOCK,
            confidence=0.94,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 6. Requisites block
    if _looks_like_requisites_block(text):
        reasons.append(ClassificationReason(
            "requisites_keywords", 0.93, "Contains requisites/banking/address identifiers"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_REQUISITES_BLOCK,
            confidence=0.93,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 7. Table content
    if _looks_like_table_content(text):
        reasons.append(ClassificationReason(
            "table_structure", 0.83, "Looks like row-like or delimiter-heavy table content"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_TABLE_CONTENT,
            confidence=0.83,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 8. List item
    if raw_type == "listitem" or _looks_like_list_item(text):
        conf = 0.9 if raw_type == "listitem" else 0.82
        reasons.append(ClassificationReason(
            "list_item_pattern", conf, "Extractor or regex indicates list item"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_LIST_ITEM,
            confidence=conf,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 9. Heading candidate
    heading_conf = _heading_candidate_confidence(text=text, raw_type=raw_type)
    if heading_conf >= 0.75:
        reasons.append(ClassificationReason(
            "heading_candidate",
            heading_conf,
            "Heading-like numbering, uppercase, or upstream heading label",
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_HEADING_CANDIDATE,
            confidence=heading_conf,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 10. Unknown layout
    if _looks_like_unknown_layout(text):
        reasons.append(ClassificationReason(
            "unknown_layout_noise", 0.72, "Noise-heavy or layout-broken line"
        ))
        return ClassificationResult(
            element_type=ELEMENT_TYPE_UNKNOWN_LAYOUT,
            confidence=0.72,
            reasons=reasons,
            raw_type=raw_type,
        )

    # 11. Default body text
    conf = 0.8 if raw_type == "text" else 0.7
    reasons.append(ClassificationReason(
        "default_body_text", conf, "Falls back to ordinary body text"
    ))
    return ClassificationResult(
        element_type=ELEMENT_TYPE_BODY_TEXT,
        confidence=conf,
        reasons=reasons,
        raw_type=raw_type,
    )


# ============================================================================
# Semantic element type resolver
# ============================================================================

def _compute_semantic_element_type(
    *,
    text: str,
    element_type: str,
    raw_type: str | None,
) -> str:
    """
    Определяет уточнённый semantic_element_type для элемента.

    Это второй уровень типизации поверх базового element_type.
    Используется downstream в heading_scoring и heading_builder.

    Правила приоритетов:
    1. TOC-related типы → оставляем как есть (не semantic heading)
    2. page_artifact / unknown_layout → body_text как fallback
    3. signature_block → signature_block
    4. requisites_block → signature_block (негативный для heading)
    5. table_content / list_item → list_item
    6. appendix heading → appendix_heading
    7. definition item → definition_item
    8. heading candidate:
       - если есть numeric uid level 1 → section_heading
       - если есть numeric uid level >= 2 → subsection_heading
       - иначе → section_heading как default
    9. body_text → body_text
    10. fallback → body_text
    """
    normalized_et = element_type.lower().strip()

    # TOC-related — не даём им semantic heading type
    if normalized_et in {
        "toc_header",
        "toc_line",
        "possible_toc",
        "toc_false_positive",
        "page_artifact",
        "unknown_layout",
    }:
        return SEMANTIC_TYPE_BODY_TEXT

    # Signature / requisites → негативные для heading pipeline
    if normalized_et in {"signature_block", "requisites_block"}:
        return SEMANTIC_TYPE_SIGNATURE_BLOCK

    # Table / list
    if normalized_et in {"table_content", "list_item"}:
        return SEMANTIC_TYPE_LIST_ITEM

    # Body text — явно назначен
    if normalized_et == "body_text":
        return SEMANTIC_TYPE_BODY_TEXT

    # Для heading candidate, enumerated clause, definition item —
    # применяем legal-specific детекторы

    # Приоритет 1: Appendix heading
    if looks_like_appendix_heading(text):
        return SEMANTIC_TYPE_APPENDIX_HEADING

    # Приоритет 2: Definition item
    if looks_like_definition_item(text):
        return SEMANTIC_TYPE_DEFINITION_ITEM

    # Приоритет 3: Signature / requisites по тексту
    if looks_like_signature_heading(text) or looks_like_requisites_heading(text):
        return SEMANTIC_TYPE_SIGNATURE_BLOCK

    # Приоритет 4: Heading candidate — различаем section vs subsection по uid depth
    if normalized_et in {
        "heading_candidate",
        "section_heading",
        "subsection_heading",
        "appendix_heading",
        "enumerated_clause",
    }:
        # Пробуем распарсить uid из текста
        parsed = parse_raw_heading(text)
        if parsed is not None:
            raw_uid, _ = parsed
            if raw_uid:
                depth = numeric_uid_depth(raw_uid)
                if depth == 1:
                    return SEMANTIC_TYPE_SECTION_HEADING
                elif depth >= 2:
                    return SEMANTIC_TYPE_SUBSECTION_HEADING

        # Если uid не распарсился — для heading candidate ставим section_heading
        return SEMANTIC_TYPE_SECTION_HEADING

    # Fallback
    return SEMANTIC_TYPE_BODY_TEXT


def _compute_heading_confidence_from_classification(
    element_type: str,
    classification_confidence: float,
    semantic_type: str,
) -> float:
    """
    Вычисляет heading_confidence на основе element_type и semantic_type.

    Это не финальный scoring — только первичная оценка classifier-а.
    Финальный score даёт heading_scoring.py.

    Диапазон: 0.0–1.0
    """
    normalized_et = element_type.lower().strip()

    # TOC / artifact / body — не heading
    if normalized_et in {
        "toc_header", "toc_line", "possible_toc", "toc_false_positive",
        "page_artifact", "unknown_layout", "body_text",
        "signature_block", "requisites_block", "table_content",
    }:
        return 0.0

    # Appendix — слабый heading signal
    if semantic_type == SEMANTIC_TYPE_APPENDIX_HEADING:
        return round(min(classification_confidence, 0.75), 3)

    # Definition item — не section heading
    if semantic_type == SEMANTIC_TYPE_DEFINITION_ITEM:
        return 0.0

    # Signature / requisites
    if semantic_type == SEMANTIC_TYPE_SIGNATURE_BLOCK:
        return 0.0

    # List item — очень слабый heading signal
    if normalized_et == "list_item":
        return round(min(classification_confidence * 0.5, 0.45), 3)

    # Section / subsection heading
    if semantic_type in {SEMANTIC_TYPE_SECTION_HEADING, SEMANTIC_TYPE_SUBSECTION_HEADING}:
        return round(min(classification_confidence, 0.95), 3)

    # Fallback
    return round(min(classification_confidence * 0.6, 0.60), 3)


# ============================================================================
# Pattern helpers
# ============================================================================

def _normalize_text(text: str) -> str:
    text = text.replace("\u00A0", " ")
    text = text.replace("ё", "е").replace("Ё", "Е")
    text = NORMALIZE_NUM_SIGN_RE.sub("№ ", text)
    text = PUNCT_SPACES_RE.sub(r"\1 ", text)
    text = WHITESPACE_RE.sub(" ", text)
    return text.strip()


def _normalize_for_match(text: str) -> str:
    return _normalize_text(text).lower()


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _safe_bbox(bbox: Any) -> list[float]:
    if not isinstance(bbox, (list, tuple)):
        return [0.0, 0.0, 0.0, 0.0]
    values = list(bbox[:4])
    while len(values) < 4:
        values.append(0.0)
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v))
        except Exception:
            out.append(0.0)
    return out


def _is_toc_header(text: str) -> bool:
    normalized = _normalize_for_match(text)
    return any(re.fullmatch(pattern, normalized) for pattern in TOC_HEADER_PATTERNS)


def _toc_line_score(text: str) -> tuple[float, list[str]]:
    """
    Локальный scoring TOC-похожести строки.

    Возвращает score 0.0–1.0 и список reasons для explainability.

    Логика строгая:
    - сильный сигнал = page number в конце + dot leaders / heading-like uid;
    - длинные substantive lines штрафуются;
    - body-like punctuation штрафуется.

    Это LOCAL scoring. Authoritative guard применяется позже в pipeline.
    """
    normalized = _normalize_text(text)
    normalized_lc = normalized.lower()

    if not normalized:
        return 0.0, ["empty"]

    reasons: list[str] = []
    score = 0.0

    has_trailing_page = bool(re.search(r"\b\d{1,4}\s*$", normalized))
    has_dot_leader = bool(DOT_LEADER_RE.search(normalized))
    has_uid_heading = bool(UID_HEADING_RE.match(normalized))
    has_root_heading = bool(ROOT_HEADING_NO_DOT_RE.match(normalized))
    words = normalized.split()
    word_count = len(words)

    if has_trailing_page:
        score += 0.34
        reasons.append("trailing_page_number")

    if has_dot_leader and has_trailing_page:
        score += 0.38
        reasons.append("dot_leader_with_page")

    if has_uid_heading and has_trailing_page:
        score += 0.22
        reasons.append("uid_heading_with_page")

    if has_root_heading and has_trailing_page:
        score += 0.16
        reasons.append("root_heading_with_page")

    if (
        any(normalized_lc.startswith(prefix) for prefix in TOC_LINE_UID_PREFIX)
        and has_trailing_page
    ):
        score += 0.10
        reasons.append("toc_uid_prefix_with_page")

    if word_count <= 14:
        score += 0.08
        reasons.append("short_line")
    elif word_count >= 20:
        score -= 0.22
        reasons.append("too_long_for_toc")

    if len(normalized) >= 160:
        score -= 0.25
        reasons.append("line_too_long")

    if ":" in normalized and not has_dot_leader:
        score -= 0.08
        reasons.append("colon_without_dot_leader")

    if normalized.endswith((".", ";")):
        score -= 0.10
        reasons.append("body_like_terminal_punctuation")

    lower_hits = sum(1 for w in words[1:] if w and w[0].islower())
    if word_count >= 8 and lower_hits >= max(3, word_count // 2):
        score -= 0.14
        reasons.append("body_like_lowercase_flow")

    if has_trailing_page and not has_dot_leader and not has_uid_heading and word_count >= 10:
        score -= 0.18
        reasons.append("weak_page_tail_only")

    score = max(0.0, min(score, 1.0))
    return score, reasons


def _is_toc_line(text: str) -> bool:
    score, _ = _toc_line_score(text)
    return score >= 0.78


def _looks_like_toc_false_positive(text: str) -> bool:
    """
    Локальный детектор false positive TOC-кандидатов.

    Это LOCAL filter по природе текста — до guard.
    Использует только структурные признаки строки.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return False

    words = normalized.split()
    word_count = len(words)

    if word_count >= 18:
        return True

    if ":" in normalized and not DOT_LEADER_RE.search(normalized):
        return True

    if normalized.endswith((".", ";")) and word_count >= 8:
        return True

    if re.search(r"[«\"'].+[»\"']", normalized) and word_count >= 6:
        return True

    return False


def _looks_like_signature_block(text: str) -> bool:
    normalized = _normalize_for_match(text)

    if any(keyword in normalized for keyword in SIGNATURE_KEYWORDS_RU):
        return True
    if "________________" in text or "________" in text:
        return True
    if re.search(r"/\s*подпись\s*/", normalized):
        return True
    if re.search(r"\bм\.?\s*п\.?\b", normalized):
        return True

    return False


def _looks_like_requisites_block(text: str) -> bool:
    normalized = _normalize_for_match(text)

    keyword_hits = sum(1 for kw in REQUISITES_KEYWORDS_RU if kw in normalized)
    if keyword_hits >= 2:
        return True

    colon_count = text.count(":")
    if colon_count >= 2 and keyword_hits >= 1:
        return True

    if re.search(r"\b(инн|кпп|огрн|бик|iban|swift)\b", normalized):
        return True

    return False


def _looks_like_page_artifact(text: str, top_ratio: float, bottom_ratio: float) -> bool:
    normalized = _normalize_for_match(text)

    if any(re.fullmatch(pattern, normalized) for pattern in PAGE_ARTIFACT_PATTERNS):
        return top_ratio <= 0.08 or bottom_ratio <= 0.08

    if len(normalized) <= 25 and (top_ratio <= 0.04 or bottom_ratio <= 0.04):
        if re.search(r"\b(договор|приложение|акт|страница|page)\b", normalized):
            return True

    return False


def _looks_like_table_content(text: str) -> bool:
    normalized = _normalize_text(text)

    if "|" in normalized and normalized.count("|") >= 2:
        return True
    if "\t" in text:
        return True
    if normalized.count(";") >= 3:
        return True

    tokens = normalized.split()
    numeric_tokens = sum(1 for t in tokens if re.fullmatch(r"[\d\.,/%()-]+", t))
    if len(tokens) >= 5 and numeric_tokens >= 3:
        return True

    return False


def _looks_like_list_item(text: str) -> bool:
    normalized = _normalize_text(text)
    return bool(LIST_ITEM_RE.match(normalized) or ROMAN_LIST_ITEM_RE.match(normalized))


def _heading_candidate_confidence(*, text: str, raw_type: str | None) -> float:
    normalized = _normalize_text(text)
    score = 0.0

    if raw_type == "heading":
        score += 0.45
    if UID_HEADING_RE.match(normalized):
        score += 0.35
    if ROOT_HEADING_NO_DOT_RE.match(normalized) and not _looks_like_list_item(normalized):
        score += 0.28
    if len(normalized) <= 80 and normalized.isupper() and len(normalized) >= 3:
        score += 0.18
    if any(keyword in _normalize_for_match(normalized) for keyword in BOUNDARY_KEYWORDS_RU):
        score += 0.08

    if _looks_like_signature_block(normalized) or _looks_like_requisites_block(normalized):
        score -= 0.35
    if _looks_like_list_item(normalized):
        score -= 0.30

    toc_score, _ = _toc_line_score(normalized)
    if toc_score >= 0.78:
        score -= 0.40
    elif toc_score >= 0.52:
        score -= 0.14

    return max(0.0, min(score, 0.99))


def _looks_like_unknown_layout(text: str) -> bool:
    normalized = _normalize_text(text)
    if not normalized:
        return True

    weird_ratio = sum(
        1 for ch in normalized
        if not (ch.isalnum() or ch.isspace() or ch in ".,:;!?()/-№\"'")
    ) / max(len(normalized), 1)
    if weird_ratio >= 0.25:
        return True

    if len(normalized) >= 12:
        alnum = sum(1 for ch in normalized if ch.isalnum())
        if alnum / len(normalized) < 0.35:
            return True

    return False


# ============================================================================
# Logging
# ============================================================================

def _log_classification_summary(
    *,
    document_id: str | None,
    classified: list[dict[str, Any]],
    toc_ctx: _TocContext,
    toc_fp_count: int = 0,
) -> None:
    counts: dict[str, int] = {}
    semantic_counts: dict[str, int] = {}

    for el in classified:
        et = str(el.get("element_type") or ELEMENT_TYPE_UNKNOWN_LAYOUT)
        counts[et] = counts.get(et, 0) + 1

        # Считаем также semantic_element_type для diagnostics
        meta = el.get("metadata") or {}
        sem = str(meta.get("semantic_element_type") or "unknown")
        semantic_counts[sem] = semantic_counts.get(sem, 0) + 1

    toc_detected = bool(toc_ctx.toc_block and toc_ctx.toc_block.detected)
    toc_entries = len(toc_ctx.parsed_toc.entries) if toc_ctx.parsed_toc else 0

    logger.info(
        "STRUCTURE element classification completed",
        extra={
            "document_id": document_id,
            "elements_count": len(classified),
            "counts": counts,
            "semantic_counts": semantic_counts,
            "toc_detected": toc_detected,
            "toc_entries_parsed": toc_entries,
            "toc_source_indexes_count": len(toc_ctx.toc_source_indexes),
            "toc_header_count": counts.get(ELEMENT_TYPE_TOC_HEADER, 0),
            "toc_line_count": counts.get(ELEMENT_TYPE_TOC_LINE, 0),
            "possible_toc_count": counts.get(ELEMENT_TYPE_POSSIBLE_TOC, 0),
            "toc_false_positive_local_count": toc_fp_count,
            "semantic_section_heading_count": semantic_counts.get(SEMANTIC_TYPE_SECTION_HEADING, 0),
            "semantic_subsection_heading_count": semantic_counts.get(SEMANTIC_TYPE_SUBSECTION_HEADING, 0),
            "semantic_definition_item_count": semantic_counts.get(SEMANTIC_TYPE_DEFINITION_ITEM, 0),
            "semantic_appendix_heading_count": semantic_counts.get(SEMANTIC_TYPE_APPENDIX_HEADING, 0),
            "note": "authoritative_guard_applied_later_in_pipeline",
        },
    )


    
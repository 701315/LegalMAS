# src/services/structure/pipeline.py

"""
Структурный пайплайн: elements -> ClauseTree / FileStructureResult.

Целевая архитектура:
1. Валидация входа
2. Очистка невалидных элементов
3. Обязательная сегментация файла
4. Scope propagation и проверка segment metadata contract
5. TOC-детекция / TOC-исключение из body (временный v1.5 режим)
6. Heading candidates (parse + scoring + optional llm refinement)
7. Coverage + structural quality
8. Hierarchy + crossrefs
9. Quality gates + degraded fallback
10. Сборка ClauseTree / FileGraph

Важно:
- structured TOC flow не обязан быть идеально точным, чтобы быть полезным;
- stale или noisy TOC entries считаются diagnostics signal, а не fatal error;
- legacy TOC cutoff может сохраняться как rollback-safe fallback,
  но не должен быть основным Sprint 2 путём.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.crossrefs import extract_references
from services.structure.file_graph_builder import build_file_graph
from services.structure.heading_builder import build_heading_candidates
from services.structure.heading_patterns import normalize_spaces
from services.structure.hierarchy_builder import HeadingCandidate, build_clause_hierarchy
from services.structure.models import (
    ClauseNode,
    ClauseTree,
    FileStructureResult,
    SegmentDocument,
    ParseQualityDiagnostics,
    TOCDiagnostics,
    PARSE_QUALITY_OK,
    PARSE_QUALITY_WEAK,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_TYPE_CONTRACT,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    embed_parse_quality_diagnostics,
    embed_toc_diagnostics,
    make_effective_uid,
    make_segment_id,
)
from services.structure.element_classifier import (
    annotate_elements_with_guard,
    classify_elements,
)
from services.structure.segmenter import segment_elements
from services.structure.toc_analysis import TOCAnalysisBundle, analyze_toc_with_guard
from services.structure.toc_guard import (
    TOC_GUARD_RELIABLE,
)

logger = get_logger(__name__)

_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")

_REQUIRED_ELEMENT_FIELDS = (
    "scope",
    "segment_id",
    "segment_type",
    "segment_order",
    "element_type",
)


# ── Утилиты ──────────────────────────────────────────────────────────────────


def _log_timing(label: str, start: float, **extra: Any) -> None:
    elapsed = time.perf_counter() - start
    logger.info(
        f"STRUCTURE timing: {label}",
        extra={"elapsed_sec": round(elapsed, 4), **extra},
    )


def _stable_element_id(element: dict[str, Any], fallback_index: int) -> str:
    """
    Стабильный element_id.

    Если у элемента уже есть element_id — используем его.
    Иначе строим детерминированный fallback по странице, bbox и началу текста.
    """
    element_id = str(element.get("element_id") or "").strip()
    if element_id:
        return element_id

    page = element.get("page", 1)
    bbox = element.get("bbox") or [0, 0, 0, 0]
    text = normalize_spaces(element.get("text", ""))
    x0 = bbox[0] if len(bbox) > 0 else 0
    top = bbox[1] if len(bbox) > 1 else 0

    return f"fallback:{page}:{x0}:{top}:{fallback_index}:{text[:32]}"


def _clean_elements(document_id: str, elements: list[dict] | None) -> list[dict]:
    """
    Оставляет только dict-элементы.
    """
    if elements is None or not isinstance(elements, list):
        logger.error(
            "STRUCTURE invalid elements input",
            extra={
                "document_id": document_id,
                "elements_is_none": elements is None,
                "elements_type": None if elements is None else type(elements).__name__,
            },
        )
        return []

    clean: list[dict] = []
    for i, el in enumerate(elements):
        if isinstance(el, dict):
            clean.append(el)
        else:
            logger.warning(
                "STRUCTURE non_dict_element_skipped",
                extra={
                    "document_id": document_id,
                    "element_index": i,
                    "element_type": type(el).__name__,
                },
            )
    return clean


def _pages_for_elements(elements: list[dict]) -> tuple[int, int]:
    """
    Возвращает page_start, page_end для списка элементов.
    """
    pages = [el.get("page", 1) for el in elements if isinstance(el.get("page"), int)]
    if not pages:
        return 1, 1
    return min(pages), max(pages)


def _segment_slice_is_valid(seg: SegmentDocument, elements_count: int) -> bool:
    """
    Базовая защита от битых диапазонов segment.element_start/element_end.
    """
    return 0 <= seg.element_start <= seg.element_end <= elements_count


def _ensure_element_segment_metadata(
    *,
    elements: list[dict],
    segment: SegmentDocument,
) -> list[dict]:
    """
    Гарантирует, что каждый element сегмента имеет обязательные scope/segment metadata.

    Если segmenter уже всё проставил — просто нормализуем.
    Если нет — аккуратно заполняем из SegmentDocument.

    Важно:
    - НЕ делаем optimistic default element_type="heading_candidate";
    - безопасный fallback для отсутствующей классификации — body_text.
    """
    prepared: list[dict] = []
    filled_scope_count = 0
    filled_segment_id_count = 0
    filled_element_type_count = 0

    for el in elements:
        normalized = dict(el)

        if not normalized.get("segment_id"):
            filled_segment_id_count += 1
        normalized["segment_id"] = normalized.get("segment_id") or segment.segment_id

        normalized["segment_type"] = normalized.get("segment_type") or segment.segment_type

        normalized["segment_order"] = (
            normalized.get("segment_order")
            if normalized.get("segment_order") is not None
            else segment.segment_order
        )

        if not normalized.get("scope"):
            filled_scope_count += 1
        normalized["scope"] = normalized.get("scope") or segment.scope_name

        if not normalized.get("element_type"):
            filled_element_type_count += 1
            normalized["element_type"] = "body_text"

        prepared.append(normalized)

    if filled_scope_count or filled_segment_id_count or filled_element_type_count:
        logger.warning(
            "STRUCTURE element_metadata_normalization_fallback",
            extra={
                "segment_id": segment.segment_id,
                "segment_scope": segment.scope_name,
                "elements_count": len(elements),
                "filled_scope_count": filled_scope_count,
                "filled_segment_id_count": filled_segment_id_count,
                "filled_element_type_count": filled_element_type_count,
            },
        )

    return prepared


def _validate_element_contract(
    *,
    document_id: str,
    segment_id: str | None,
    elements: list[dict],
) -> tuple[bool, list[dict[str, Any]]]:
    """
    Проверка обязательного контракта элементов перед heading_builder.
    """
    violations: list[dict[str, Any]] = []

    for idx, el in enumerate(elements):
        missing = [field for field in _REQUIRED_ELEMENT_FIELDS if el.get(field) is None]
        if missing:
            violations.append(
                {
                    "elem_i": idx,
                    "page": el.get("page"),
                    "missing_fields": missing,
                    "text_sample": normalize_spaces(str(el.get("text") or ""))[:120],
                }
            )

    if violations:
        logger.error(
            "STRUCTURE element_contract_validation_failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "violations_count": len(violations),
                "violations_preview": violations[:10],
            },
        )
        return False, violations

    return True, []


def _is_numeric_uid(uid: str) -> bool:
    return bool(_NUMERIC_UID_RE.fullmatch(str(uid or "").strip()))


def _summarize_headings(headings: list[HeadingCandidate]) -> dict[str, Any]:
    """
    Лёгкая quality summary по уже принятым headings.

    Не перескориваем headings заново.
    """
    total = len(headings)
    if not total:
        return {
            "total": 0,
            "numeric_count": 0,
            "numeric_ratio": 0.0,
            "empty_title_count": 0,
            "scope_distribution": {},
        }

    numeric_count = 0
    empty_title_count = 0
    scope_distribution: dict[str, int] = {}

    for h in headings:
        raw_uid = str(getattr(h, "raw_uid", None) or h.uid or "").strip()
        title = str(h.title or "").strip()
        scope = str(getattr(h, "scope", None) or "unknown").strip() or "unknown"

        scope_distribution[scope] = scope_distribution.get(scope, 0) + 1

        if _is_numeric_uid(raw_uid):
            numeric_count += 1
        if not title:
            empty_title_count += 1

    return {
        "total": total,
        "numeric_count": numeric_count,
        "numeric_ratio": numeric_count / total,
        "empty_title_count": empty_title_count,
        "scope_distribution": scope_distribution,
    }


def _summarize_element_types(elements: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Лёгкая сводка по element_type после secondary classification.
    """
    counts: dict[str, int] = {}

    for el in elements:
        element_type = str(el.get("element_type") or "unknown").strip() or "unknown"
        counts[element_type] = counts.get(element_type, 0) + 1

    total = len(elements)
    toc_total = (
        counts.get("toc_header", 0)
        + counts.get("toc_line", 0)
        + counts.get("possible_toc", 0)
        + counts.get("toc_false_positive", 0)
    )

    return {
        "total": total,
        "counts": counts,
        "heading_candidates": counts.get("heading_candidate", 0),
        "body_text": counts.get("body_text", 0),
        "list_items": counts.get("list_item", 0),
        "toc_header": counts.get("toc_header", 0),
        "toc_line": counts.get("toc_line", 0),
        "possible_toc": counts.get("possible_toc", 0),
        "toc_false_positive": counts.get("toc_false_positive", 0),
        "toc_total": toc_total,
        "signature_blocks": counts.get("signature_block", 0),
        "requisites_blocks": counts.get("requisites_block", 0),
        "page_artifacts": counts.get("page_artifact", 0),
        "unknown_layout": counts.get("unknown_layout", 0),
    }


# ── TOC-детекция ─────────────────────────────────────────────────────────────

def _compute_suppressed_indexes(
    *,
    elements: list[dict[str, Any]],
    analysis: TOCAnalysisBundle,
) -> set[int]:
    """
    Вычисляет set индексов элементов, которые можно suppressed при reliable_toc.

    Suppression — только semantic, только в пределах TOC block:
    - suppression разрешён только при guard.decision == reliable_toc;
    - удаляются только toc_header и toc_line elements;
    - toc_false_positive НЕ удаляются никогда;
    - possible_toc НЕ удаляются;
    - body за пределами TOC block не трогается.

    Индексы segment-local (относительно переданного elements).
    """
    if not analysis.guard.suppress_body_elements:
        return set()

    if analysis.guard.decision != TOC_GUARD_RELIABLE:
        return set()

    # Собираем element indexes из parsed TOC entries —
    # только те, которые НЕ помечены как false positive guard-ом.
    entry_element_indexes: set[int] = set()
    for entry in analysis.parsed_toc.entries:
        for idx in (entry.source_element_indexes or []):
            if isinstance(idx, int) and idx >= 0:
                if idx not in analysis.guard.false_positive_indexes:
                    entry_element_indexes.add(idx)

    # Добавляем TOC header элементы из detected block
    if analysis.toc_block.start_index is not None:
        start = analysis.toc_block.start_index
        end = min(analysis.toc_block.end_index, len(elements))
        for idx in range(start, end):
            if elements[idx].get("element_type") == "toc_header":
                entry_element_indexes.add(idx)

    # Финальный фильтр: suppressed только toc_header и toc_line
    # — не possible_toc, не toc_false_positive, не body
    suppressible = {
        idx
        for idx in entry_element_indexes
        if elements[idx].get("element_type") in {"toc_header", "toc_line"}
    }

    return suppressible


def _resolve_parser_status(analysis: TOCAnalysisBundle) -> str:
    """
    Определяет parser_status для TOCDiagnostics.

    OK  — если TOC был reliable и suppression применён.
    WEAK — если TOC обнаружен, но reliability недостаточна.
    OK  — если TOC не обнаружен (нет сигнала → нет проблемы).
    """
    if analysis.guard.suppress_body_elements:
        return PARSE_QUALITY_OK
    if analysis.reliability.confidence_band in {"partial", "low"}:
        return PARSE_QUALITY_WEAK
    return PARSE_QUALITY_OK


def _build_toc_diagnostics(
    *,
    analysis: TOCAnalysisBundle,
    suppressed_indexes: set[int],
    body_recovered_count: int,
    guard_fp_count: int,
) -> TOCDiagnostics:
    """
    Строит TOCDiagnostics из authoritative TOCAnalysisBundle.

    Всё берётся из analysis — нет дублирующих расчётов.
    """
    return TOCDiagnostics(
        detected=analysis.toc_block.detected,
        block_start_index=analysis.toc_block.start_index,
        block_end_index=analysis.toc_block.end_index,
        detection_reason=analysis.toc_block.reason,
        parsed_entries_total=analysis.alignment.entries_total,
        parsed_entries_with_page_hint=int(
            analysis.parsed_toc.parser_diagnostics.get("entries_with_page_hint", 0)
        ),
        parsed_multiline_entries=int(
            analysis.parsed_toc.parser_diagnostics.get("multiline_entries", 0)
        ),
        exact_matches=analysis.alignment.exact_matches,
        fuzzy_matches=analysis.alignment.fuzzy_matches,
        no_matches=analysis.alignment.no_matches,
        stale_entries=analysis.alignment.stale_entries,
        toc_alignment_score=analysis.alignment.toc_alignment_score,
        toc_partial_reliability=analysis.reliability.partial_reliability,
        toc_confidence_band=analysis.reliability.confidence_band,
        toc_guard_applied=True,
        toc_body_suppression_allowed=analysis.guard.suppress_body_elements,
        toc_false_positive_count=guard_fp_count,
        body_recovered_from_toc=body_recovered_count,
        toc_skipped_elements=len(suppressed_indexes),
        parser_status=_resolve_parser_status(analysis),
        parser_reasons=list(analysis.reliability.reasons),
        extra={
            "index_space": "segment_local",
            "guard_decision": analysis.guard.decision,
            "guard_quality": analysis.guard.toc_quality,
            "guard_reliability": analysis.guard.toc_reliability,
            "false_positive_element_count": len(analysis.guard.false_positive_indexes),
            "recoverable_element_count": len(analysis.guard.recoverable_indexes),
        },
    )



# ── Coverage и quality ───────────────────────────────────────────────────────


def _calculate_node_coverage(
    *,
    nodes: dict[str, ClauseNode],
    elements: list[dict],
) -> float:
    """
    Доля элементов body, реально покрытых own_element_ids собранной структуры.
    """
    if not elements:
        return 0.0

    all_ids: set[str] = set()
    covered_ids: set[str] = set()

    for idx, el in enumerate(elements):
        all_ids.add(_stable_element_id(el, idx))

    for node in nodes.values():
        covered_ids.update(node.own_element_ids or [])

    if not all_ids:
        return 0.0

    return len(all_ids & covered_ids) / len(all_ids)


def _confidence_and_mode(
    coverage: float,
    *,
    layout_degraded: bool = False,
    headings_count: int = 0,
    numeric_ratio: float = 1.0,
    empty_title_count: int = 0,
    structure_degraded: bool = False,
) -> tuple[str, bool]:
    """
    Возвращает structural_confidence и degraded flag.
    """
    threshold = settings.STRUCTURE_MIN_CLAUSE_COVERAGE

    if layout_degraded:
        threshold *= 0.7

    if structure_degraded:
        return STRUCTURE_CONFIDENCE_LOW, True

    if headings_count == 0:
        return STRUCTURE_CONFIDENCE_FAILED, True

    if headings_count < 3:
        return STRUCTURE_CONFIDENCE_LOW, True

    if numeric_ratio < 0.3:
        return STRUCTURE_CONFIDENCE_LOW, True

    if empty_title_count >= max(2, headings_count // 2):
        return STRUCTURE_CONFIDENCE_LOW, True

    if coverage < threshold:
        return STRUCTURE_CONFIDENCE_LOW, True

    if coverage < 0.80:
        return STRUCTURE_CONFIDENCE_MEDIUM, False

    return STRUCTURE_CONFIDENCE_HIGH, False


# ── Degraded fallback ─────────────────────────────────────────────────────────


def _degraded_tree(
    document_id: str,
    elements: list[dict],
    coverage: float = 0.0,
    *,
    structure_confidence: str = STRUCTURE_CONFIDENCE_LOW,
    diagnostics: dict[str, Any] | None = None,
    scope_name: str = "main_contract",
    segment_id: str | None = None,
    segment_type: str | None = None,
    segment_title: str | None = None,
    segment_page_range: tuple[int, int] | None = None,
    segment_order: int | None = None,
    is_primary_segment: bool = False,
) -> ClauseTree:
    """
    Строит технический ClauseTree из равномерных чанков по токенам.

    Используется когда структуру документа восстановить не удалось
    или quality gates запрещают доверять section boundaries.
    """
    chunks: list[ClauseNode] = []
    current_ids: list[str] = []
    current_text_parts: list[str] = []
    current_tokens = 0
    chunk_idx = 1
    max_tokens = settings.STRUCTURE_DEGRADED_CHUNK_TOKENS
    current_start_page: int | None = None
    last_page: int = elements[0].get("page", 1) if elements else 1

    logger.info(
        "STRUCTURE degraded_tree_start",
        extra={
            "document_id": document_id,
            "elements_count": len(elements),
            "coverage": round(coverage, 3),
            "max_tokens_per_chunk": max_tokens,
            "structure_confidence": structure_confidence,
            "scope_name": scope_name,
            "segment_id": segment_id,
        },
    )

    def _flush_chunk() -> None:
        nonlocal chunk_idx, current_ids, current_text_parts, current_tokens, current_start_page

        start_page = current_start_page or last_page
        end_page = last_page
        own_text = " ".join(current_text_parts) if current_text_parts else None

        raw_uid = str(chunk_idx)
        effective_uid = make_effective_uid(scope_name, raw_uid)

        chunks.append(
            ClauseNode(
                effective_uid=effective_uid,
                raw_uid=raw_uid,
                scope=scope_name,
                title=f"Chunk {chunk_idx}",
                level=1,
                node_kind="leaf",
                own_element_ids=list(current_ids),
                subtree_element_ids=list(current_ids),
                own_text=own_text,
                subtree_text=own_text,
                start_page=start_page,
                end_page=end_page,
                children=[],
                range_end_reason="segment_end",
                diagnostics={"degraded_chunk": True},
            )
        )

        logger.debug(
            "STRUCTURE degraded_chunk_built",
            extra={
                "document_id": document_id,
                "raw_uid": raw_uid,
                "effective_uid": effective_uid,
                "element_ids_count": len(current_ids),
                "start_page": start_page,
                "end_page": end_page,
                "tokens": current_tokens,
                "scope_name": scope_name,
            },
        )

        chunk_idx += 1
        current_ids = []
        current_text_parts = []
        current_tokens = 0
        current_start_page = None

    for idx, el in enumerate(elements):
        text = el.get("text", "")
        tokens = len(str(text or "").split())
        page = el.get("page", 1)

        if current_tokens + tokens > max_tokens and current_ids:
            _flush_chunk()

        current_ids.append(_stable_element_id(el, idx))
        if str(text or "").strip():
            current_text_parts.append(str(text).strip())
        current_tokens += tokens
        if current_start_page is None:
            current_start_page = page
        last_page = page

    if current_ids:
        _flush_chunk()

    logger.info(
        "STRUCTURE degraded_tree_completed",
        extra={
            "document_id": document_id,
            "chunks": len(chunks),
            "coverage": round(coverage, 3),
            "structure_confidence": structure_confidence,
            "scope_name": scope_name,
            "segment_id": segment_id,
        },
    )

    diagnostics = dict(diagnostics or {})
    diagnostics.setdefault("quality_gates", {})
    diagnostics["quality_gates"].update(
        {
            "section_chunking_allowed": False,
            "technical_fallback_only": True,
            "structure_confidence": structure_confidence,
        }
    )

    return ClauseTree(
        document_id=document_id,
        root=chunks,
        references_index=[],
        structure_confidence=structure_confidence,
        degraded=True,
        nodes_index={node.effective_uid: node for node in chunks},
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="3.0",
    )


# ── Внутреннее ядро: один сегмент → ClauseTree ───────────────────────────────


def _build_single_segment_tree(
    document_id: str,
    elements: list[dict],
    *,
    segment_id: str | None = None,
    segment_type: str | None = None,
    segment_title: str | None = None,
    segment_page_range: tuple[int, int] | None = None,
    segment_order: int | None = None,
    scope_name: str | None = None,
    is_primary_segment: bool = False,
    log_prefix: str = "STRUCTURE",
) -> ClauseTree:
    """
    Строит ClauseTree для одного логического сегмента.

    Порядок операций:
    1. Ранние проверки (contract, layout degraded).
    2. Первый проход headings — без TOC match index.
    3. Authoritative TOC analysis с guard (analyze_toc_with_guard).
    4. Annotate elements с guard verdict (annotate_elements_with_guard).
    5. Semantic suppression TOC elements при reliable_toc.
    6. Второй проход headings — с TOC match index.
    7. Иерархия, coverage, diagnostics, ClauseTree.

    Все TOC indexes — segment-local (относительно elements этого сегмента).
    """
    build_started = time.perf_counter()
    normalized_scope_name = str(scope_name or "main_contract").strip() or "main_contract"

    # ── Начальные stats до любых изменений ───────────────────────────────────

    missing_element_ids = sum(
        1 for el in elements if not str(el.get("element_id") or "").strip()
    )
    element_type_summary = _summarize_element_types(elements)

    layout_degraded = False
    layout_degraded_reason: str | None = None
    for el in elements:
        lf = (el.get("language_filter") or {}) if isinstance(el, dict) else {}
        degraded_flag = lf.get("degraded")
        if degraded_flag is not None:
            layout_degraded = bool(degraded_flag)
            layout_degraded_reason = lf.get("degraded_reason")
            break

    # ── Contract validation ───────────────────────────────────────────────────

    contract_valid, contract_violations = _validate_element_contract(
        document_id=document_id,
        segment_id=segment_id,
        elements=elements,
    )

    # Начальное состояние diagnostics — будет дополняться по мере работы
    diagnostics: dict[str, Any] = {
        "toc": {
            "detected": False,
            "toc_skipped_elements": 0,
            "mode": "structured_toc_guarded_v4",
            "guard_decision": "reject_toc",
            "toc_body_suppression_allowed": False,
            "body_recovered_from_toc": 0,
            "toc_guard_applied": False,
        },
        "layout": {
            "degraded": layout_degraded,
            "degraded_reason": layout_degraded_reason,
            "missing_element_ids": missing_element_ids,
        },
        "classification": {
            "segment_elements_total": element_type_summary["total"],
            "segment_counts": element_type_summary["counts"],
        },
        "contract": {
            "valid": contract_valid,
            "violations_count": len(contract_violations),
            "violations_preview": contract_violations[:10],
        },
    }

    if not contract_valid:
        result = _degraded_tree(
            document_id=document_id,
            elements=elements,
            coverage=0.0,
            structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
            diagnostics={**diagnostics, "degraded_reason": "element_contract_validation_failed"},
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )
        _log_timing(
            f"{log_prefix} build_total", build_started,
            document_id=document_id, segment_id=segment_id,
            degraded=True, confidence=STRUCTURE_CONFIDENCE_FAILED,
        )
        return result

    # ── Шаг 1: первый проход headings (без TOC match index) ───────────────────

    t_h1 = time.perf_counter()
    headings_pre = build_heading_candidates(
        elements,
        document_id=document_id,
        toc_match_index=None,
    )
    _log_timing(
        f"{log_prefix} headings_pass_1", t_h1,
        document_id=document_id, segment_id=segment_id,
        headings_found=len(headings_pre),
    )

    if not headings_pre:
        fallback_confidence = (
            STRUCTURE_CONFIDENCE_FAILED if len(elements) < 3
            else STRUCTURE_CONFIDENCE_LOW
        )
        result = _degraded_tree(
            document_id=document_id,
            elements=elements,
            coverage=0.0,
            structure_confidence=fallback_confidence,
            diagnostics={**diagnostics, "degraded_reason": "no_headings_detected"},
            scope_name=normalized_scope_name,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            is_primary_segment=is_primary_segment,
        )
        _log_timing(
            f"{log_prefix} build_total", build_started,
            document_id=document_id, segment_id=segment_id,
            degraded=True, confidence=fallback_confidence,
        )
        return result

    # ── Шаг 2: authoritative TOC analysis с guard ─────────────────────────────
    # Вызываем ПОСЛЕ headings_pre — чтобы attach_toc_matches мог работать.
    # Все indexes в guard — segment-local.

    t_toc = time.perf_counter()
    analysis = analyze_toc_with_guard(
        elements,
        headings_pre,
        document_id=document_id,
    )
    _log_timing(
        f"{log_prefix} toc_analysis", t_toc,
        document_id=document_id, segment_id=segment_id,
        toc_detected=analysis.detected,
        guard_decision=analysis.guard.decision,
        suppress_body=analysis.suppress_body_elements,
        false_positive_count=len(analysis.guard.false_positive_indexes),
        recoverable_count=len(analysis.guard.recoverable_indexes),
    )

    # ── Шаг 3: annotate elements с guard verdict ──────────────────────────────
    # annotate_elements_with_guard проставляет guard metadata
    # и переклассифицирует false positive elements.
    # Работает на segment-local elements — indexes совпадают с guard verdict.

    annotated_elements, body_recovered_count, guard_fp_count = annotate_elements_with_guard(
        elements,
        analysis.guard,
    )

    # ── Шаг 4: semantic suppression при reliable_toc ──────────────────────────
    # При partial_toc и reject_toc — suppression не делается,
    # все элементы остаются в body.

    suppressed_indexes = _compute_suppressed_indexes(
        elements=annotated_elements,
        analysis=analysis,
    )

    if suppressed_indexes:
        body_elements = [
            el for idx, el in enumerate(annotated_elements)
            if idx not in suppressed_indexes
        ]
        logger.info(
            f"{log_prefix} toc_suppression_applied",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "suppressed_count": len(suppressed_indexes),
                "body_elements_after": len(body_elements),
            },
        )
    else:
        body_elements = annotated_elements

    # ── Шаг 5: второй проход headings с TOC match index ──────────────────────

    t_h2 = time.perf_counter()
    headings = build_heading_candidates(
        body_elements,
        document_id=document_id,
        toc_match_index=analysis.toc_match_index,
    )
    _log_timing(
        f"{log_prefix} headings_pass_2", t_h2,
        document_id=document_id, segment_id=segment_id,
        headings_found=len(headings),
        suppressed_elements=len(suppressed_indexes),
    )

    # ── Обновляем diagnostics после TOC analysis ──────────────────────────────

    toc_diag_dict = analysis.to_diagnostics_dict()
    toc_diag_dict["toc_skipped_elements"] = len(suppressed_indexes)
    toc_diag_dict["body_recovered_from_toc"] = body_recovered_count
    toc_diag_dict["toc_false_positive_count"] = guard_fp_count
    diagnostics["toc"].update(toc_diag_dict)

    body_type_summary = _summarize_element_types(body_elements)
    diagnostics["classification"]["body_elements_total"] = body_type_summary["total"]
    diagnostics["classification"]["body_counts"] = body_type_summary["counts"]

    # ── Строим typed TOCDiagnostics для embed ─────────────────────────────────

    toc_diag_obj = _build_toc_diagnostics(
        analysis=analysis,
        suppressed_indexes=suppressed_indexes,
        body_recovered_count=body_recovered_count,
        guard_fp_count=guard_fp_count,
    )

    parse_quality_toc_status = (
        PARSE_QUALITY_OK if analysis.guard.suppress_body_elements
        else PARSE_QUALITY_WEAK if analysis.reliability.confidence_band in {"partial", "low"}
        else PARSE_QUALITY_OK
    )
    parse_quality_reasons = list(analysis.reliability.reasons)
    if suppressed_indexes:
        parse_quality_reasons.append("toc_suppression_applied")
    elif analysis.detected:
        parse_quality_reasons.append("toc_detected_kept_as_soft_signal")

    parse_quality_obj = ParseQualityDiagnostics(
        overall_status=PARSE_QUALITY_OK,
        toc_status=parse_quality_toc_status,
        heading_status=PARSE_QUALITY_OK,
        hierarchy_status=PARSE_QUALITY_OK,
        reasons=parse_quality_reasons,
        toc_diagnostics=toc_diag_obj,
    )

    diagnostics = embed_toc_diagnostics(diagnostics, toc_diag_obj)
    diagnostics = embed_parse_quality_diagnostics(diagnostics, parse_quality_obj)

    # ── Шаг 6: hierarchy, coverage, quality gates ─────────────────────────────

    heading_summary = _summarize_headings(headings)

    logger.info(
        f"{log_prefix} pre_hierarchy_diagnostics",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
            "total_elements": len(elements),
            "body_elements": len(body_elements),
            "headings_found": len(headings),
            "toc_detected": analysis.detected,
            "guard_decision": analysis.guard.decision,
            "toc_skipped_elements": len(suppressed_indexes),
            "body_recovered_from_toc": body_recovered_count,
            "toc_false_positive_count": guard_fp_count,
            "toc_alignment_score": round(analysis.alignment.toc_alignment_score, 4),
            "partial_reliability": round(analysis.reliability.partial_reliability, 4),
            "numeric_headings_ratio": round(heading_summary["numeric_ratio"], 3),
            "layout_degraded": layout_degraded,
        },
    )

    t_tree = time.perf_counter()
    root_nodes, nodes, element_to_effective_uid, structure_degraded = build_clause_hierarchy(
        headings=headings,
        elements=body_elements,
        document_id=document_id,
        stable_element_id_resolver=_stable_element_id,
    )

    references = extract_references(
        elements=body_elements,
        element_to_effective_uid=element_to_effective_uid,
        nodes=nodes,
        document_id=document_id,
        stable_element_id_resolver=_stable_element_id,
    )

    _log_timing(
        f"{log_prefix} tree_build", t_tree,
        document_id=document_id, segment_id=segment_id,
        root_nodes=len(root_nodes), references=len(references),
    )

    coverage = _calculate_node_coverage(nodes=nodes, elements=body_elements)

    confidence, degraded = _confidence_and_mode(
        coverage,
        layout_degraded=layout_degraded,
        headings_count=heading_summary["total"],
        numeric_ratio=heading_summary["numeric_ratio"],
        empty_title_count=heading_summary["empty_title_count"],
        structure_degraded=structure_degraded,
    )

    section_chunking_allowed = (
        confidence in {STRUCTURE_CONFIDENCE_HIGH, STRUCTURE_CONFIDENCE_MEDIUM}
        and not structure_degraded
    )

    diagnostics["headings"] = {
        "headings_found": len(headings),
        "numeric_count": heading_summary["numeric_count"],
        "numeric_ratio": round(heading_summary["numeric_ratio"], 3),
        "empty_title_count": heading_summary["empty_title_count"],
        "scope_distribution": heading_summary["scope_distribution"],
        "coverage": round(coverage, 3),
    }
    diagnostics["hierarchy"] = {
        "root_nodes_count": len(root_nodes),
        "nodes_count": len(nodes),
        "references_count": len(references),
        "structure_degraded": structure_degraded,
    }
    diagnostics["quality_gates"] = {
        "section_chunking_allowed": section_chunking_allowed,
        "technical_fallback_only": not section_chunking_allowed,
        "structure_confidence": confidence,
        "structure_degraded": structure_degraded,
    }

    has_partial_structure = bool(root_nodes) and bool(nodes)

    # ── Degraded fallback если quality gates не пройдены ──────────────────────

    if degraded and confidence in {STRUCTURE_CONFIDENCE_LOW, STRUCTURE_CONFIDENCE_FAILED}:
        if not has_partial_structure:
            degraded_reason = (
                "hierarchy_degraded" if structure_degraded
                else "low_heading_quality_or_coverage"
            )
            logger.info(
                f"{log_prefix} degraded_no_recoverable_structure",
                extra={
                    "document_id": document_id, "segment_id": segment_id,
                    "coverage": round(coverage, 3),
                    "headings_count": heading_summary["total"],
                    "degraded_reason": degraded_reason,
                },
            )
            result = _degraded_tree(
                document_id=document_id,
                elements=body_elements,
                coverage=coverage,
                structure_confidence=confidence,
                diagnostics={**diagnostics, "degraded_reason": degraded_reason},
                scope_name=normalized_scope_name,
                segment_id=segment_id,
                segment_type=segment_type,
                segment_title=segment_title,
                segment_page_range=segment_page_range,
                segment_order=segment_order,
                is_primary_segment=is_primary_segment,
            )
            _log_timing(
                f"{log_prefix} build_total", build_started,
                document_id=document_id, segment_id=segment_id,
                degraded=True, confidence=confidence,
            )
            return result

        # Есть частичная структура — не деградируем полностью
        diagnostics["quality_gates"].update({
            "recoverable_hierarchy": True,
            "technical_fallback_only": False,
            "section_chunking_allowed": True,
            "total_downgrade_prevented": True,
        })
        logger.warning(
            f"{log_prefix} total_downgrade_prevented",
            extra={
                "document_id": document_id, "segment_id": segment_id,
                "coverage": round(coverage, 3),
                "root_nodes_count": len(root_nodes),
                "nodes_count": len(nodes),
            },
        )

    # ── Сборка ClauseTree ─────────────────────────────────────────────────────

    result = ClauseTree(
        document_id=document_id,
        root=root_nodes,
        references_index=references,
        structure_confidence=confidence,
        degraded=bool(structure_degraded),
        nodes_index=nodes,
        structure_diagnostics=diagnostics,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=normalized_scope_name,
        is_primary_segment=is_primary_segment,
        schema_version="3.0",
    )

    _log_timing(
        f"{log_prefix} build_total", build_started,
        document_id=document_id, segment_id=segment_id,
        degraded=bool(structure_degraded), confidence=confidence,
    )
    return result




# ── Legacy wrapper ───────────────────────────────────────────────────────────


def build_structure(
    document_id: str,
    elements: list[dict] | None,
) -> ClauseTree:
    """
    Legacy-compatible вход.
    """
    result = build_file_structure(
        document_id=document_id,
        elements=elements,
        document_version_id=None,
    )
    return result.primary_tree


# ── Segmentation helpers ─────────────────────────────────────────────────────


def _make_single_segment_list(
    *,
    document_id: str,
    document_version_id: str | None,
    elements: list[dict],
) -> list[SegmentDocument]:
    """
    Возвращает список из одного SegmentDocument,
    который покрывает весь файл.
    """
    page_start, page_end = _pages_for_elements(elements)

    single_segment = SegmentDocument(
        segment_id=make_segment_id(document_id, segment_order=0),
        document_id=document_id,
        document_version_id=document_version_id,
        segment_order=0,
        segment_type=SEGMENT_TYPE_CONTRACT,
        segment_title=None,
        page_start=page_start,
        page_end=page_end,
        element_start=0,
        element_end=len(elements),
        confidence=SEGMENT_CONFIDENCE_HIGH,
        is_primary=True,
        segmentation_confidence_score=1.0,
        segmentation_reasons=["single_segment_pipeline_fallback"],
    )
    return [single_segment]


def _segment_document(
    *,
    document_id: str,
    document_version_id: str | None,
    elements: list[dict],
) -> list[SegmentDocument]:
    """
    Всегда пытается выполнить сегментацию.
    """
    try:
        segments = segment_elements(document_id=document_id, elements=elements)
    except Exception as e:
        logger.exception(
            "STRUCTURE segmentation_failed_fallback_to_single_segment",
            extra={
                "document_id": document_id,
                "elements_count": len(elements),
                "error": str(e),
            },
        )
        return _make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    if not segments:
        logger.warning(
            "STRUCTURE segmentation_returned_empty_fallback_to_single_segment",
            extra={"document_id": document_id},
        )
        return _make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    valid_segments = [
        seg for seg in segments
        if _segment_slice_is_valid(seg, len(elements))
    ]

    if len(valid_segments) != len(segments):
        logger.warning(
            "STRUCTURE segmentation_invalid_ranges_fallback_to_single_segment",
            extra={
                "document_id": document_id,
                "segments_count": len(segments),
                "valid_segments_count": len(valid_segments),
            },
        )
        return _make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=elements,
        )

    for seg in valid_segments:
        seg.document_version_id = document_version_id

    return valid_segments


# ── Canonical entrypoint ─────────────────────────────────────────────────────


def build_file_structure(
    document_id: str,
    elements: list[dict] | None,
    *,
    document_version_id: str | None = None,
) -> FileStructureResult:
    """
    Каноническая точка входа для scope-aware file structure.
    """
    if not document_id:
        logger.warning("STRUCTURE build_file_structure: empty document_id, using placeholder")
        document_id = "<unknown>"

    clean_elements = _clean_elements(document_id, elements)

    if not clean_elements:
        single_segment = _make_single_segment_list(
            document_id=document_id,
            document_version_id=document_version_id,
            elements=[],
        )

        seg = single_segment[0]
        primary_tree = _build_single_segment_tree(
            document_id=document_id,
            elements=[],
            segment_id=seg.segment_id,
            segment_type=seg.segment_type,
            segment_title=seg.segment_title,
            segment_page_range=(seg.page_start, seg.page_end),
            segment_order=seg.segment_order,
            scope_name=seg.scope_name,
            is_primary_segment=True,
            log_prefix="STRUCTURE[seg=0]",
        )
        segment_trees = [primary_tree]
        file_graph = build_file_graph(
            document_id=document_id,
            document_version_id=document_version_id,
            segments=single_segment,
            segment_trees=segment_trees,
        )
        return FileStructureResult(
            primary_tree=primary_tree,
            segment_trees=segment_trees,
            file_graph=file_graph,
        )

    t_classify = time.perf_counter()
    classified_elements = classify_elements(clean_elements, document_id=document_id)
    classification_summary = _summarize_element_types(classified_elements)
    _log_timing(
        "STRUCTURE element_classification",
        t_classify,
        document_id=document_id,
        elements_count=len(classified_elements),
        heading_candidates=classification_summary["heading_candidates"],
        body_text=classification_summary["body_text"],
        list_items=classification_summary["list_items"],
        toc_total=classification_summary["toc_total"],
        toc_header=classification_summary["toc_header"],
        toc_line=classification_summary["toc_line"],
        possible_toc=classification_summary["possible_toc"],
        toc_false_positive=classification_summary["toc_false_positive"],
        signature_blocks=classification_summary["signature_blocks"],
        requisites_blocks=classification_summary["requisites_blocks"],
        page_artifacts=classification_summary["page_artifacts"],
        unknown_layout=classification_summary["unknown_layout"],
    )

    t_seg = time.perf_counter()
    segments = _segment_document(
        document_id=document_id,
        document_version_id=document_version_id,
        elements=classified_elements,
    )

    _log_timing(
        "STRUCTURE segmentation",
        t_seg,
        document_id=document_id,
        segments_count=len(segments),
    )

    segment_trees: list[ClauseTree] = []

    for seg in segments:
        slice_ = classified_elements[seg.element_start:seg.element_end]
        prepared_slice = _ensure_element_segment_metadata(
            elements=slice_,
            segment=seg,
        )

        contract_valid, contract_violations = _validate_element_contract(
            document_id=document_id,
            segment_id=seg.segment_id,
            elements=prepared_slice,
        )

        if not contract_valid:
            logger.error(
                "STRUCTURE pipeline_level_element_contract_failed",
                extra={
                    "document_id": document_id,
                    "segment_id": seg.segment_id,
                    "segment_order": seg.segment_order,
                    "segment_type": seg.segment_type,
                    "scope_name": seg.scope_name,
                    "violations_count": len(contract_violations),
                    "violations_preview": contract_violations[:10],
                },
            )

            tree = _degraded_tree(
                document_id=document_id,
                elements=prepared_slice,
                coverage=0.0,
                structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
                diagnostics={
                    "degraded_reason": "pipeline_element_contract_failed",
                    "contract": {
                        "valid": False,
                        "violations_count": len(contract_violations),
                        "violations_preview": contract_violations[:10],
                    },
                    "quality_gates": {
                        "section_chunking_allowed": False,
                        "technical_fallback_only": True,
                        "structure_confidence": STRUCTURE_CONFIDENCE_FAILED,
                    },
                },
                scope_name=seg.scope_name,
                segment_id=seg.segment_id,
                segment_type=seg.segment_type,
                segment_title=seg.segment_title,
                segment_page_range=(seg.page_start, seg.page_end),
                segment_order=seg.segment_order,
                is_primary_segment=seg.is_primary,
            )
            segment_trees.append(tree)
            continue

        tree = _build_single_segment_tree(
            document_id=document_id,
            elements=prepared_slice,
            segment_id=seg.segment_id,
            segment_type=seg.segment_type,
            segment_title=seg.segment_title,
            segment_page_range=(seg.page_start, seg.page_end),
            segment_order=seg.segment_order,
            scope_name=seg.scope_name,
            is_primary_segment=seg.is_primary,
            log_prefix=f"STRUCTURE[seg={seg.segment_order}]",
        )
        segment_trees.append(tree)

    file_graph = build_file_graph(
        document_id=document_id,
        document_version_id=document_version_id,
        segments=segments,
        segment_trees=segment_trees,
    )

    if file_graph.primary_segment_id:
        primary_tree = next(
            (t for t in segment_trees if t.segment_id == file_graph.primary_segment_id),
            segment_trees[0],
        )
    else:
        primary_tree = segment_trees[0]

    logger.info(
        "STRUCTURE build_file_structure completed",
        extra={
            "document_id": document_id,
            "document_version_id": document_version_id,
            "segments_count": len(segments),
            "segment_types": [s.segment_type for s in segments],
            "segment_scopes": [s.scope_name for s in segments],
            "primary_segment_id": file_graph.primary_segment_id,
            "degraded": file_graph.degraded,
            "structural_confidence": file_graph.structural_confidence,
        },
    )

    return FileStructureResult(
        primary_tree=primary_tree,
        segment_trees=segment_trees,
        file_graph=file_graph,
    )


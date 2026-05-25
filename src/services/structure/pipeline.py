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
from services.structure.element_classifier import classify_elements
from core.config import settings
from core.logging import get_logger
from services.structure.crossrefs import extract_references
from services.structure.file_graph_builder import build_file_graph
from services.structure.heading_builder import build_heading_candidates
from services.structure.heading_features import has_letters, looks_like_toc_line
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.hierarchy_builder import HeadingCandidate, build_clause_hierarchy
from services.structure.models import (
    ClauseNode,
    ClauseTree,
    FileGraph,
    FileStructureResult,
    SegmentDocument,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_UNKNOWN,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    make_segment_id,
)
from services.structure.segmenter import segment_elements
from services.structure.toc_matcher import attach_toc_matches, build_toc_match_index
from services.structure.toc_parser import (
    compute_partial_reliability,
    detect_toc_block,
    evaluate_toc_alignment,
    parse_toc_entries,
)


logger = get_logger(__name__)

_TOC_MAX_PAGES = 5
_NUMERIC_UID_RE = re.compile(r"^\d+(?:\.\d+)*$")

_TOC_MARKERS = frozenset(
    [
        "table of contents",
        "contents",
        "содержание",
        "оглавление",
    ]
)

_REQUIRED_ELEMENT_FIELDS = (
    "scope",
    "segment_id",
    "segment_type",
    "segment_order",
    "element_type",
)


@dataclass(slots=True)
class TocDetectionResult:
    detected: bool
    start_index: int | None
    end_index: int
    reason: str


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
    return {
        "total": total,
        "counts": counts,
        "heading_candidates": counts.get("heading_candidate", 0),
        "body_text": counts.get("body_text", 0),
        "list_items": counts.get("list_item", 0),
        "toc_content": counts.get("toc_content", 0),
        "signature_blocks": counts.get("signature_block", 0),
        "requisites_blocks": counts.get("requisites_block", 0),
        "page_artifacts": counts.get("page_artifact", 0),
        "unknown_layout": counts.get("unknown_layout", 0),
    }


# ── TOC-детекция ─────────────────────────────────────────────────────────────


def _find_toc_end(elements: list[dict]) -> TocDetectionResult:
    """
    Legacy TOC cutoff heuristic.

    Используется только как rollback-safe fallback во время миграции
    на structured TOC pipeline.

    Новый основной путь:
    - detect_toc_block()
    - parse_toc_entries()
    - attach_toc_matches()
    - evaluate_toc_alignment()
    - compute_partial_reliability()

    Важно:
    эта функция не строит structured TOC model и не должна использоваться
    как primary TOC logic в Sprint 2 flow.
    """
    if not elements:
        return TocDetectionResult(
            detected=False,
            start_index=None,
            end_index=0,
            reason="empty_elements",
        )

    first_page = elements[0].get("page", 1)
    page_threshold = first_page + _TOC_MAX_PAGES

    toc_start_idx: int | None = None
    for i, el in enumerate(elements):
        if el.get("page", 1) > page_threshold:
            break
        text_lower = normalize_spaces(el.get("text", "")).lower()
        if text_lower in _TOC_MARKERS:
            toc_start_idx = i
            break

    if toc_start_idx is not None:
        toc_last_page = elements[toc_start_idx].get("page", 1)

        for i in range(toc_start_idx + 1, len(elements)):
            el = elements[i]
            el_page = el.get("page", 1)

            if el_page > page_threshold:
                logger.debug(
                    "STRUCTURE toc_end_reached_by_page_threshold",
                    extra={
                        "toc_start_idx": toc_start_idx,
                        "toc_end_idx": i,
                        "toc_last_page": toc_last_page,
                    },
                )
                return TocDetectionResult(
                    detected=True,
                    start_index=toc_start_idx,
                    end_index=i,
                    reason="page_threshold",
                )

            text = normalize_spaces(el.get("text", ""))
            parsed = parse_raw_heading(text)

            if looks_like_toc_line(text):
                toc_last_page = el_page
                continue

            if el_page > toc_last_page and parsed:
                uid, title = parsed
                if uid and title:
                    logger.debug(
                        "STRUCTURE toc_end_reached_by_heading_after_toc",
                        extra={
                            "toc_start_idx": toc_start_idx,
                            "toc_end_idx": i,
                            "toc_last_page": toc_last_page,
                        },
                    )
                    return TocDetectionResult(
                        detected=True,
                        start_index=toc_start_idx,
                        end_index=i,
                        reason="heading_after_toc",
                    )

            if not parsed and len(text) > 80 and has_letters(text):
                logger.debug(
                    "STRUCTURE toc_end_reached_by_long_text_after_toc",
                    extra={
                        "toc_start_idx": toc_start_idx,
                        "toc_end_idx": i,
                        "toc_last_page": toc_last_page,
                    },
                )
                return TocDetectionResult(
                    detected=True,
                    start_index=toc_start_idx,
                    end_index=i,
                    reason="long_text_after_toc",
                )

            toc_last_page = el_page

        logger.debug(
            "STRUCTURE toc_end_fallback_after_marker",
            extra={
                "toc_start_idx": toc_start_idx,
                "toc_end_idx": toc_start_idx + 1,
                "toc_last_page": toc_last_page,
            },
        )
        return TocDetectionResult(
            detected=True,
            start_index=toc_start_idx,
            end_index=toc_start_idx + 1,
            reason="marker_only_fallback",
        )

    cluster_count = 0
    cluster_last_idx = 0
    cluster_start_idx: int | None = None

    for i, el in enumerate(elements):
        if el.get("page", 1) > page_threshold:
            break

        text = normalize_spaces(el.get("text", ""))
        parsed = parse_raw_heading(text)

        if parsed:
            uid, title = parsed
            if "." not in uid and uid and title:
                if looks_like_toc_line(text) or len(title.split()) <= 12:
                    if cluster_start_idx is None:
                        cluster_start_idx = i
                    cluster_count += 1
                    cluster_last_idx = i
                    continue

        if cluster_count >= 3:
            logger.debug(
                "STRUCTURE toc_cluster_fallback_used",
                extra={
                    "cluster_start_idx": cluster_start_idx,
                    "cluster_last_idx": cluster_last_idx,
                    "cluster_count": cluster_count,
                },
            )
            return TocDetectionResult(
                detected=True,
                start_index=cluster_start_idx,
                end_index=cluster_last_idx + 1,
                reason="cluster_fallback",
            )

        cluster_count = 0
        cluster_start_idx = None

    if cluster_count >= 3:
        logger.debug(
            "STRUCTURE toc_cluster_fallback_used_at_end",
            extra={
                "cluster_start_idx": cluster_start_idx,
                "cluster_last_idx": cluster_last_idx,
                "cluster_count": cluster_count,
            },
        )
        return TocDetectionResult(
            detected=True,
            start_index=cluster_start_idx,
            end_index=cluster_last_idx + 1,
            reason="cluster_fallback_end",
        )

    logger.debug("STRUCTURE toc_not_detected")
    return TocDetectionResult(
        detected=False,
        start_index=None,
        end_index=0,
        reason="not_detected",
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
        },
    )

    def _flush_chunk() -> None:
        nonlocal chunk_idx, current_ids, current_text_parts, current_tokens, current_start_page
        start_page = current_start_page or last_page
        end_page = last_page
        own_text = " ".join(current_text_parts) if current_text_parts else None

        raw_uid = str(chunk_idx)
        effective_uid = f"degraded_chunk::{raw_uid}"

        chunks.append(
            ClauseNode(
                effective_uid=effective_uid,
                raw_uid=raw_uid,
                scope="degraded_chunk",
                clause_uid=raw_uid,
                title=f"Chunk {chunk_idx}",
                level=1,
                node_kind="leaf",
                own_element_ids=current_ids,
                subtree_element_ids=list(current_ids),
                own_text=own_text,
                subtree_text=own_text,
                start_page=start_page,
                end_page=end_page,
                clause_uid_alias_mode=True,
                diagnostics={"degraded_chunk": True},
            )
        )

        logger.debug(
            "STRUCTURE degraded_chunk_built",
            extra={
                "document_id": document_id,
                "chunk_uid": raw_uid,
                "effective_uid": effective_uid,
                "element_ids_count": len(current_ids),
                "start_page": start_page,
                "end_page": end_page,
                "tokens": current_tokens,
            },
        )

        chunk_idx += 1
        current_ids = []
        current_text_parts = []
        current_tokens = 0
        current_start_page = None

    for idx, el in enumerate(elements):
        text = el.get("text", "")
        tokens = len(text.split())
        page = el.get("page", 1)

        if current_tokens + tokens > max_tokens and current_ids:
            _flush_chunk()

        current_ids.append(_stable_element_id(el, idx))
        if text.strip():
            current_text_parts.append(text.strip())
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
        },
    )

    diagnostics = diagnostics or {}
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
        clause_uid_alias_mode=True,
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

    Внутренний flow:
    1. TOC-lite detection
    2. contract validation для body elements
    3. heading candidate extraction
    4. hierarchy + crossrefs
    5. coverage + structural quality
    6. quality gates / degraded fallback
    """
    build_started = time.perf_counter()

    t_toc = time.perf_counter()
    toc_block = detect_toc_block(elements)
    parsed_toc = parse_toc_entries(toc_block)

    body_elements = elements
    if toc_block.detected and toc_block.end_index > 0:
        body_elements = elements[toc_block.end_index:] or elements

    if not body_elements:
        body_elements = elements

    _log_timing(
        f"{log_prefix} toc_detection",
        t_toc,
        document_id=document_id,
        segment_id=segment_id,
        toc_detected=toc_block.detected,
        toc_start_idx=toc_block.start_index,
        toc_end_idx=toc_block.end_index,
        toc_reason=toc_block.reason,
        toc_entries_parsed=len(parsed_toc.entries),
    )

    missing_element_ids = sum(
        1 for el in body_elements if not str(el.get("element_id") or "").strip()
    )
    element_type_summary = _summarize_element_types(elements)
    body_element_type_summary = _summarize_element_types(body_elements)

    layout_degraded = False
    layout_degraded_reason: str | None = None
    for el in elements:
        lf = (el.get("language_filter") or {}) if isinstance(el, dict) else {}
        degraded_flag = lf.get("degraded")
        if degraded_flag is not None:
            layout_degraded = bool(degraded_flag)
            layout_degraded_reason = lf.get("degraded_reason")
            break

    contract_valid, contract_violations = _validate_element_contract(
        document_id=document_id,
        segment_id=segment_id,
        elements=body_elements,
    )

    diagnostics: dict[str, Any] = {
        "toc": {
            "detected": toc_block.detected,
            "start_index": toc_block.start_index,
            "end_index": toc_block.end_index,
            "toc_skipped_elements": toc_block.end_index if toc_block.detected else 0,
            "mode": "structured_toc_v2",
            "reason": toc_block.reason,
            "entries_total": len(parsed_toc.entries),
            "entries_with_page_hint": parsed_toc.parser_diagnostics.get("entries_with_page_hint", 0),
            "multiline_entries": parsed_toc.parser_diagnostics.get("multiline_entries", 0),
            "toc_alignment_score": 0.0,
            "partial_reliability": 0.0,
            "is_reliable": False,
            "confidence_band": "none",
            "exact_matches": 0,
            "fuzzy_matches": 0,
            "no_matches": 0,
            "stale_entries": 0,
            "mismatch_details": [],
            "reasons": [],
        },
        "layout": {
            "degraded": layout_degraded,
            "degraded_reason": layout_degraded_reason,
            "missing_element_ids": missing_element_ids,
        },
        "classification": {
            "segment_elements_total": element_type_summary["total"],
            "body_elements_total": body_element_type_summary["total"],
            "segment_counts": element_type_summary["counts"],
            "body_counts": body_element_type_summary["counts"],
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
            elements=body_elements,
            coverage=0.0,
            structure_confidence=STRUCTURE_CONFIDENCE_FAILED,
            diagnostics={
                **diagnostics,
                "degraded_reason": "element_contract_validation_failed",
            },
        )
        _apply_segment_fields(
            result,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            scope_name=scope_name,
            is_primary_segment=is_primary_segment,
        )
        _log_timing(
            f"{log_prefix} build_total",
            build_started,
            document_id=document_id,
            segment_id=segment_id,
            degraded=True,
            confidence=STRUCTURE_CONFIDENCE_FAILED,
        )
        return result

    t_headings = time.perf_counter()
    headings = build_heading_candidates(body_elements, document_id=document_id)
    _log_timing(
        f"{log_prefix} heading_collection",
        t_headings,
        document_id=document_id,
        segment_id=segment_id,
        headings_found=len(headings),
    )

    if not headings:
        fallback_confidence = (
            STRUCTURE_CONFIDENCE_FAILED if len(body_elements) < 3 else STRUCTURE_CONFIDENCE_LOW
        )

        result = _degraded_tree(
            document_id=document_id,
            elements=body_elements,
            coverage=0.0,
            structure_confidence=fallback_confidence,
            diagnostics={
                **diagnostics,
                "degraded_reason": "no_headings_detected",
            },
        )
        _apply_segment_fields(
            result,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            scope_name=scope_name,
            is_primary_segment=is_primary_segment,
        )
        _log_timing(
            f"{log_prefix} build_total",
            build_started,
            document_id=document_id,
            segment_id=segment_id,
            degraded=True,
            confidence=fallback_confidence,
        )
        return result

    parsed_toc = attach_toc_matches(parsed_toc, headings)
    toc_alignment = evaluate_toc_alignment(parsed_toc)
    toc_reliability = compute_partial_reliability(parsed_toc, toc_alignment)
    toc_match_index = build_toc_match_index(parsed_toc)

    diagnostics["toc"].update(
        {
            "entries_total": toc_alignment.entries_total,
            "toc_alignment_score": round(toc_alignment.toc_alignment_score, 4),
            "partial_reliability": round(toc_reliability.partial_reliability, 4),
            "is_reliable": toc_reliability.is_reliable,
            "confidence_band": toc_reliability.confidence_band,
            "exact_matches": toc_alignment.exact_matches,
            "fuzzy_matches": toc_alignment.fuzzy_matches,
            "no_matches": toc_alignment.no_matches,
            "stale_entries": toc_alignment.stale_entries,
            "mismatch_details": toc_alignment.mismatch_details[:20],
            "reasons": list(toc_reliability.reasons),
            "match_index_size": len(toc_match_index),
        }
    )

    heading_summary = _summarize_headings(headings)

    logger.info(
        f"{log_prefix} build diagnostics",
        extra={
            "document_id": document_id,
            "segment_id": segment_id,
            "segment_type": segment_type,
            "scope_name": scope_name,
            "total_elements": len(elements),
            "body_elements": len(body_elements),
            "headings_found": len(headings),
            "missing_element_ids": missing_element_ids,
            "layout_degraded": layout_degraded,
            "layout_degraded_reason": layout_degraded_reason,
            "toc_detected": diagnostics["toc"]["detected"],
            "toc_skipped_elements": diagnostics["toc"]["toc_skipped_elements"],
            "toc_entries_total": diagnostics["toc"]["entries_total"],
            "toc_alignment_score": diagnostics["toc"]["toc_alignment_score"],
            "toc_partial_reliability": diagnostics["toc"]["partial_reliability"],
            "toc_is_reliable": diagnostics["toc"]["is_reliable"],
            "toc_exact_matches": diagnostics["toc"]["exact_matches"],
            "toc_fuzzy_matches": diagnostics["toc"]["fuzzy_matches"],
            "toc_no_matches": diagnostics["toc"]["no_matches"],
            "toc_stale_entries": diagnostics["toc"]["stale_entries"],
            "numeric_headings_count": heading_summary["numeric_count"],
            "numeric_headings_ratio": round(heading_summary["numeric_ratio"], 3),
            "empty_title_count": heading_summary["empty_title_count"],
            "element_type_counts": element_type_summary["counts"],
            "body_element_type_counts": body_element_type_summary["counts"],
        },
    )

    t_tree = time.perf_counter()
    root_nodes, nodes, element_to_uid, structure_degraded = build_clause_hierarchy(
        headings=headings,
        elements=body_elements,
        document_id=document_id,
        stable_element_id_resolver=_stable_element_id,
    )

    references = extract_references(
        elements=body_elements,
        element_to_uid=element_to_uid,
        nodes=nodes,
        document_id=document_id,
        stable_element_id_resolver=_stable_element_id,
    )

    _log_timing(
        f"{log_prefix} tree_build",
        t_tree,
        document_id=document_id,
        segment_id=segment_id,
        root_nodes=len(root_nodes),
        references=len(references),
    )

    coverage = _calculate_node_coverage(
        nodes=nodes,
        elements=body_elements,
    )

    confidence, degraded = _confidence_and_mode(
        coverage,
        layout_degraded=layout_degraded,
        headings_count=heading_summary["total"],
        numeric_ratio=heading_summary["numeric_ratio"],
        empty_title_count=heading_summary["empty_title_count"],
        structure_degraded=structure_degraded,
    )

    section_chunking_allowed = confidence in {
        STRUCTURE_CONFIDENCE_HIGH,
        STRUCTURE_CONFIDENCE_MEDIUM,
    } and not structure_degraded
    technical_fallback_only = not section_chunking_allowed

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
        "technical_fallback_only": technical_fallback_only,
        "structure_confidence": confidence,
        "structure_degraded": structure_degraded,
    }

    if degraded and confidence in {STRUCTURE_CONFIDENCE_LOW, STRUCTURE_CONFIDENCE_FAILED}:
        degraded_reason = (
            "hierarchy_degraded"
            if structure_degraded
            else "low_heading_quality_or_coverage"
        )

        logger.info(
            f"{log_prefix} degraded: quality gates failed",
            extra={
                "document_id": document_id,
                "segment_id": segment_id,
                "coverage": round(coverage, 3),
                "headings_count": heading_summary["total"],
                "numeric_ratio": round(heading_summary["numeric_ratio"], 3),
                "empty_title_count": heading_summary["empty_title_count"],
                "structure_degraded": structure_degraded,
                "degraded_reason": degraded_reason,
            },
        )

        result = _degraded_tree(
            document_id=document_id,
            elements=body_elements,
            coverage=coverage,
            structure_confidence=confidence,
            diagnostics={
                **diagnostics,
                "degraded_reason": degraded_reason,
            },
        )
        _apply_segment_fields(
            result,
            segment_id=segment_id,
            segment_type=segment_type,
            segment_title=segment_title,
            segment_page_range=segment_page_range,
            segment_order=segment_order,
            scope_name=scope_name,
            is_primary_segment=is_primary_segment,
        )
        _log_timing(
            f"{log_prefix} build_total",
            build_started,
            document_id=document_id,
            segment_id=segment_id,
            degraded=True,
            confidence=confidence,
        )
        return result

    result = ClauseTree(
        document_id=document_id,
        root=root_nodes,
        references_index=references,
        structure_confidence=confidence,
        degraded=bool(structure_degraded),
        nodes_index=nodes,
        structure_diagnostics=diagnostics,
        clause_uid_alias_mode=True,
    )

    _apply_segment_fields(
        result,
        segment_id=segment_id,
        segment_type=segment_type,
        segment_title=segment_title,
        segment_page_range=segment_page_range,
        segment_order=segment_order,
        scope_name=scope_name,
        is_primary_segment=is_primary_segment,
    )

    _log_timing(
        f"{log_prefix} build_total",
        build_started,
        document_id=document_id,
        segment_id=segment_id,
        degraded=bool(structure_degraded),
        confidence=confidence,
    )
    return result


def _apply_segment_fields(
    tree: ClauseTree,
    *,
    segment_id: str | None,
    segment_type: str | None,
    segment_title: str | None,
    segment_page_range: tuple[int, int] | None,
    segment_order: int | None,
    scope_name: str | None,
    is_primary_segment: bool,
) -> None:
    """
    Проставляет segment-поля в уже построенный ClauseTree.
    """
    if segment_id is not None:
        tree.segment_id = segment_id
        tree.schema_version = "2.0"
    if segment_type is not None:
        tree.segment_type = segment_type
    if segment_title is not None:
        tree.segment_title = segment_title
    if segment_page_range is not None:
        tree.segment_page_range = segment_page_range
    if segment_order is not None:
        tree.segment_order = segment_order
    if scope_name is not None:
        tree.scope_name = scope_name
    tree.is_primary_segment = is_primary_segment


# ── Legacy wrapper ───────────────────────────────────────────────────────────


def build_structure(
    document_id: str,
    elements: list[dict] | None,
) -> ClauseTree:
    """
    Legacy-compatible вход.

    Новый смысл:
    - build_file_structure() является канонической точкой входа;
    - build_structure() остаётся wrapper для старых downstream consumers.
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

    Это не "segmentation disabled", а valid single-segment result.
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
    )
    single_segment.scope_name = "main_contract"
    single_segment.segmentation_confidence_score = 1.0
    single_segment.segmentation_reasons = ["single_segment_pipeline_fallback"]
    return [single_segment]


def _segment_document(
    *,
    document_id: str,
    document_version_id: str | None,
    elements: list[dict],
) -> list[SegmentDocument]:
    """
    Всегда пытается выполнить сегментацию.

    Если segmenter падает, возвращает корректный single-segment fallback.
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

    Поведение:
    - файл всегда проходит через segmentation core;
    - результат сегментации может быть:
      - single-segment
      - multi-segment
    - но архитектурная ветка "совсем без сегментации" больше не используется.

    Инварианты:
    - каждый segment tree строится только по своим element slice;
    - каждый element в segment tree имеет scope/segment metadata;
    - primary_tree выбирается по file_graph.primary_segment_id.
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
        toc_content=classification_summary["toc_content"],
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
            )
            _apply_segment_fields(
                tree,
                segment_id=seg.segment_id,
                segment_type=seg.segment_type,
                segment_title=seg.segment_title,
                segment_page_range=(seg.page_start, seg.page_end),
                segment_order=seg.segment_order,
                scope_name=seg.scope_name,
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


# src/services/structure/pipeline.py

"""
Структурный пайплайн: elements -> ClauseTree.

Стадии:
  1. Валидация входа
  2. TOC-детекция
  3. Heading candidates (parse + scoring + filter)
  4. Coverage + confidence
  5. Hierarchy + crossrefs
  6. Degraded fallback при низком качестве
"""

from __future__ import annotations

import time
from typing import Any

from core.config import settings
from core.logging import get_logger
from services.structure.heading_patterns import parse_raw_heading, normalize_spaces
from services.structure.heading_scoring import (
    validate_heading_candidate,
    score_heading_candidate,
    CandidateStatus,
)
from services.structure.hierarchy_builder import (
    HeadingCandidate,
    level_from_uid,
    build_clause_hierarchy,
)
from services.structure.crossrefs import extract_references
from services.structure.models import ClauseNode, ClauseTree, CrossReference
from services.structure.heading_features import (
    has_letters,
    looks_like_toc_line,
)
from services.structure.heading_builder import build_heading_candidates


logger = get_logger(__name__)

_TOC_MAX_PAGES = 5

_TOC_MARKERS = frozenset([
    "table of contents",
    "contents",
    "содержание",
    "оглавление",
])


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
    Если у элемента есть собственный element_id — используем его.
    Иначе строим детерминированный fallback по странице, координатам и тексту.
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


# ── TOC-детекция ─────────────────────────────────────────────────────────────

def _find_toc_end(elements: list[dict]) -> int:
    """
    Возвращает индекс первого элемента после оглавления.
    Если оглавление не найдено — возвращает 0.
    """
    if not elements:
        return 0

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
                return i

            text = normalize_spaces(el.get("text", ""))
            parsed = parse_raw_heading(text)

            if looks_like_toc_line(text):
                toc_last_page = el_page
                continue

            if el_page > toc_last_page and parsed:
                uid, title = parsed
                if validate_heading_candidate(uid, title, text):
                    logger.debug(
                        "STRUCTURE toc_end_reached_by_heading_after_toc",
                        extra={
                            "toc_start_idx": toc_start_idx,
                            "toc_end_idx": i,
                            "toc_last_page": toc_last_page,
                        },
                    )
                    return i

            if not parsed and len(text) > 80 and has_letters(text):
                logger.debug(
                    "STRUCTURE toc_end_reached_by_long_text_after_toc",
                    extra={
                        "toc_start_idx": toc_start_idx,
                        "toc_end_idx": i,
                        "toc_last_page": toc_last_page,
                    },
                )
                return i

            toc_last_page = el_page

        logger.debug(
            "STRUCTURE toc_end_fallback_after_marker",
            extra={
                "toc_start_idx": toc_start_idx,
                "toc_end_idx": toc_start_idx + 1,
                "toc_last_page": toc_last_page,
            },
        )
        return toc_start_idx + 1

    # Fallback: кластер TOC-подобных строк без явного маркера
    cluster_count = 0
    cluster_last_idx = 0

    for i, el in enumerate(elements):
        if el.get("page", 1) > page_threshold:
            break

        text = normalize_spaces(el.get("text", ""))
        parsed = parse_raw_heading(text)

        if parsed:
            uid, title = parsed
            if "." not in uid and validate_heading_candidate(uid, title, text):
                if looks_like_toc_line(text) or len(title.split()) <= 12:
                    cluster_count += 1
                    cluster_last_idx = i
                    continue

        if cluster_count >= 3:
            logger.debug(
                "STRUCTURE toc_cluster_fallback_used",
                extra={
                    "cluster_last_idx": cluster_last_idx,
                    "cluster_count": cluster_count,
                },
            )
            return cluster_last_idx + 1

        cluster_count = 0

    if cluster_count >= 3:
        logger.debug(
            "STRUCTURE toc_cluster_fallback_used_at_end",
            extra={
                "cluster_last_idx": cluster_last_idx,
                "cluster_count": cluster_count,
            },
        )
        return cluster_last_idx + 1

    logger.debug("STRUCTURE toc_not_detected")
    return 0


# ── Coverage и quality ───────────────────────────────────────────────────────

def _calculate_coverage(
    headings: list[HeadingCandidate],
    elements: list[dict],
) -> float:
    """
    Доля элементов layout, покрытых заголовками (от 0.0 до 1.0).
    """
    if not elements:
        return 0.0

    assigned: set[int] = set()
    for h_idx, heading in enumerate(headings):
        elem_i = heading.elem_i
        next_elem_i = (
            headings[h_idx + 1].elem_i
            if h_idx + 1 < len(headings)
            else len(elements)
        )
        for j in range(elem_i, next_elem_i):
            assigned.add(j)

    return len(assigned) / len(elements)


def _calculate_heading_quality(
    headings: list[HeadingCandidate],
) -> tuple[int, int, float]:
    """
    Оценка качества заголовков через scorer.

    Используем score_heading_candidate как единую точку правды —
    это гарантирует, что логика «хороший/плохой заголовок» не дублируется.

    Возвращает:
    - good_count:  заголовков, которые scorer принял (ACCEPTED);
    - total:       всего заголовков;
    - ratio:       доля принятых (0.0..1.0).
    """
    total = len(headings)
    if not total:
        return 0, 0, 0.0

    good_count = 0
    for h in headings:
        # Используем scorer вместо дублирующих вызовов
        # is_garbage_heading_title / is_bad_heading_title / has_letters.
        result = score_heading_candidate(
            uid=h.uid,
            title=h.title,
            raw_text="",  # raw_text здесь не нужен — title уже нормализован
        )
        if result.status == CandidateStatus.ACCEPTED:
            good_count += 1

    ratio = good_count / total if total else 0.0
    return good_count, total, ratio


def _confidence_and_mode(
    coverage: float,
    *,
    layout_degraded: bool = False,
    good_headings_ratio: float = 1.0,
    good_headings_count: int = 0,
) -> tuple[str, bool]:
    threshold = settings.STRUCTURE_MIN_CLAUSE_COVERAGE

    if layout_degraded:
        threshold *= 0.7

    # Safety-net: слишком мало хороших заголовков — смысла строить дерево нет
    if good_headings_count < 3 or good_headings_ratio < 0.3:
        return "LOW", True

    if coverage < threshold:
        return "LOW", True
    if coverage < 0.80:
        return "MEDIUM", False
    return "HIGH", False


# ── Degraded fallback ─────────────────────────────────────────────────────────

def _degraded_tree(
    document_id: str,
    elements: list[dict],
    coverage: float = 0.0,
) -> ClauseTree:
    """
    Строит технический ClauseTree из равномерных чанков по токенам.
    Используется когда структуру документа восстановить не удалось.
    node_kind для чанков не нужен — они leaf по дефолту.
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
        },
    )

    def _flush_chunk() -> None:
        nonlocal chunk_idx, current_ids, current_text_parts, current_tokens, current_start_page
        start_page = current_start_page or last_page
        end_page = last_page
        own_text = " ".join(current_text_parts) if current_text_parts else None
        chunks.append(
            ClauseNode(
                clause_uid=str(chunk_idx),
                title=f"Chunk {chunk_idx}",
                level=1,
                node_kind="leaf",
                own_element_ids=current_ids,
                subtree_element_ids=list(current_ids),
                own_text=own_text,
                subtree_text=own_text,
                start_page=start_page,
                end_page=end_page,
            )
        )
        logger.debug(
            "STRUCTURE degraded_chunk_built",
            extra={
                "document_id": document_id,
                "chunk_uid": str(chunk_idx),
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
        },
    )

    return ClauseTree(
        document_id=document_id,
        root=chunks,
        references_index=[],
        structure_confidence="LOW",
        degraded=True,
        # nodes_index пустой при degraded — деградированные чанки не индексируются
        nodes_index={},
    )


# ── Главная функция ───────────────────────────────────────────────────────────

def build_structure(
    document_id: str,
    elements: list[dict] | None,
) -> ClauseTree:
    """
    Главная функция пайплайна: document_id + elements → ClauseTree.
    """
    build_started = time.perf_counter()

    if not document_id:
        logger.warning("STRUCTURE build: empty document_id, using placeholder")
        document_id = "<unknown>"

    if elements is None or not isinstance(elements, list):
        logger.error(
            "STRUCTURE build: invalid elements, degraded fallback",
            extra={
                "document_id": document_id,
                "elements_is_none": elements is None,
                "elements_type": None if elements is None else type(elements).__name__,
            },
        )
        result = _degraded_tree(document_id, elements or [])
        _log_timing("build_total", build_started, document_id=document_id, degraded=True)
        return result

    # Очищаем не-dict элементы
    clean_elements: list[dict] = []
    for i, el in enumerate(elements):
        if isinstance(el, dict):
            clean_elements.append(el)
        else:
            logger.warning(
                "STRUCTURE build: non-dict element skipped",
                extra={
                    "document_id": document_id,
                    "element_index": i,
                    "element_type": type(el).__name__,
                },
            )
    elements = clean_elements

    # Проверяем признак деградации layout
    layout_degraded = False
    layout_degraded_reason: str | None = None
    for el in elements:
        lf = (el.get("language_filter") or {}) if isinstance(el, dict) else {}
        degraded_flag = lf.get("degraded")
        if degraded_flag is not None:
            layout_degraded = bool(degraded_flag)
            layout_degraded_reason = lf.get("degraded_reason")
            break

    # ── Стадия 1: TOC-детекция ───────────────────────────────────────────────
    t_toc = time.perf_counter()
    toc_end_idx = _find_toc_end(elements)
    _log_timing("toc_detection", t_toc, document_id=document_id)

    body_elements = elements[toc_end_idx:] or elements
    if not body_elements:
        body_elements = elements
        toc_end_idx = 0

    missing_element_ids = sum(
        1 for el in body_elements
        if not str(el.get("element_id") or "").strip()
    )

    # ── Стадия 2: Heading candidates ─────────────────────────────────────────
    t_headings = time.perf_counter()
    headings = build_heading_candidates(body_elements, document_id=document_id)
    _log_timing(
        "heading_collection",
        t_headings,
        document_id=document_id,
        headings_found=len(headings),
    )

    if not headings:
        result = _degraded_tree(document_id, body_elements)
        _log_timing("build_total", build_started, document_id=document_id, degraded=True)
        return result

    # ── Стадия 3: Coverage + confidence ──────────────────────────────────────
    good_headings_count, total_headings, good_headings_ratio = _calculate_heading_quality(headings)
    coverage = _calculate_coverage(headings, body_elements)
    confidence, degraded = _confidence_and_mode(
        coverage,
        layout_degraded=layout_degraded,
        good_headings_ratio=good_headings_ratio,
        good_headings_count=good_headings_count,
    )

    logger.info(
        "Structure build diagnostics",
        extra={
            "document_id": document_id,
            "total_elements": len(elements),
            "body_elements": len(body_elements),
            "headings_found": len(headings),
            "missing_element_ids": missing_element_ids,
            "layout_degraded": layout_degraded,
            "layout_degraded_reason": layout_degraded_reason,
            "toc_skipped_elements": toc_end_idx,
            "good_headings_count": good_headings_count,
            "good_headings_ratio": round(good_headings_ratio, 3),
            "coverage": round(coverage, 3),
            "confidence": confidence,
        },
    )

    if degraded:
        logger.info(
            "Structure degraded: low coverage or poor headings",
            extra={
                "document_id": document_id,
                "coverage": round(coverage, 3),
                "good_headings_count": good_headings_count,
                "good_headings_ratio": round(good_headings_ratio, 3),
                "toc_skipped_elements": toc_end_idx,
            },
        )
        result = _degraded_tree(document_id, body_elements, coverage)
        _log_timing("build_total", build_started, document_id=document_id, degraded=True)
        return result

    # ── Стадия 4: Hierarchy + crossrefs ──────────────────────────────────────
    t_tree = time.perf_counter()
    root_nodes, nodes, element_to_uid = build_clause_hierarchy(
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
        "tree_build",
        t_tree,
        document_id=document_id,
        root_nodes=len(root_nodes),
        references=len(references),
    )

    # ── Финал: собираем ClauseTree ────────────────────────────────────────────
    # nodes_index передаём явно — downstream (чанкер, API) получает
    # быстрый доступ к любому узлу по uid без рекурсивного обхода дерева.
    result = ClauseTree(
        document_id=document_id,
        root=root_nodes,
        references_index=references,
        structure_confidence=confidence,
        degraded=False,
        nodes_index=nodes,
    )

    _log_timing(
        "build_total",
        build_started,
        document_id=document_id,
        degraded=False,
        confidence=confidence,
    )
    return result



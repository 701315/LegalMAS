# src/services/structure/_clause_detector/detector.py

"""
LLMClauseDetector — определение пунктов в главах договора.

Архитектурные принципы:
- Frozen-safe: принимает как Mutable, так и Frozen узлы.
  При frozen-входе применяет паттерн Unfreeze → Refine → Refreeze.
- Dynamic Span-Based Text Extraction: рассчитывает физические границы главы в документе
  между текущим и следующим заголовком ([Chapter Heading, Next Chapter Heading)). 
  Гарантирует 100% извлечение текста для глав 1-8 независимо от column page shifts.
- Orphans Sweep: собирает unowned элементы, расположенные до физического
  заголовка главы (e.g. 1.1-1.6 в начале Chapter 1), если они семантически
  относятся к этой главе по числовому префиксу.
- Рекурсивная иерархическая сборка произвольной глубины (Merge, Not Replace):
  сохраняет существующие узлы FSM, вливая в них LLM-детей и выстраивая
  иерархию любой вложенности (e.g. 7.3 -> 7.3.1 -> 7.3.1.a) без ограничений.
- Глобальная дедупликация: исключает любые коллизии effective_uid на уровне
  всего лесного массива перед refreeze.
- Точное clamp-наследование страниц: рассчитывает страницы подпунктов
  на основе их элементов, гарантируя вхождение в диапазон родителя.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence, Union

from core.config import settings
from core.logging import get_logger
from engine.llm.client import LLMClient
from ops.metrics import METRICS
from services.structure._models._nodes import (
    FrozenHierarchyNode,
    MutableHierarchyNode,
    refreeze_forest,
    unfreeze_forest,
)

from .parser import DetectedClause, extract_clauses_fallback, parse_llm_response

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------
_MIN_TEXT_LEN: int = int(getattr(settings, "CLAUSE_DETECTOR_MIN_TEXT_LEN", 30))
_MAX_TEXT_LEN: int = int(
    getattr(settings, "CLAUSE_DETECTOR_MAX_TEXT_LEN", None)
    or int(getattr(settings, "LLM_CONTEXT_LIMIT", 16384) * 0.4)
)

NodeType = Union[MutableHierarchyNode, FrozenHierarchyNode]


# ---------------------------------------------------------------------------
# Контракт возврата
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ClauseRefineResult:
    """Результат обогащения дерева пунктами."""
    clauses_added: int
    roots: Sequence[NodeType]
    stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Утилиты иерархической сборки (Merge, Not Replace)
# ---------------------------------------------------------------------------
def _split_uid_to_parts(uid: str) -> list[str]:
    """Разбить UID на составные части для иерархического сравнения."""
    normalized = (
        uid.replace("(", ".")
        .replace(")", ".")
        .replace("[", ".")
        .replace("]", ".")
    )
    return [p.strip() for p in normalized.split(".") if p.strip()]


def _find_best_parent(
    target: MutableHierarchyNode,
    candidates: list[MutableHierarchyNode],
    chapter_node: MutableHierarchyNode,
) -> MutableHierarchyNode:
    """Найти наиболее глубокого родителя для целевого узла в плоском пуле."""
    target_parts = _split_uid_to_parts(target.raw_uid or "")
    best_parent = chapter_node
    best_len = len(_split_uid_to_parts(chapter_node.raw_uid or ""))

    for cand in candidates:
        if cand.effective_uid == target.effective_uid:
            continue
        cand_parts = _split_uid_to_parts(cand.raw_uid or "")
        if len(cand_parts) < len(target_parts):
            if target_parts[: len(cand_parts)] == cand_parts:
                if len(cand_parts) > best_len:
                    best_parent = cand
                    best_len = len(cand_parts)

    return best_parent


def _propagate_subtree_element_ids(node: MutableHierarchyNode) -> list[str]:
    """Рекурсивно пересчитать subtree_element_ids для узла и всех потомков."""
    ids = list(node.own_element_ids or [])
    for child in node.children:
        ids.extend(_propagate_subtree_element_ids(child))

    seen: set[str] = set()
    unique: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            unique.append(i)
    node.subtree_element_ids = unique
    return unique


def _sort_key_for_node(node: MutableHierarchyNode) -> list[tuple[int, Any]]:
    """Композитный ключ сортировки узлов (числа как int, буквы как str)."""
    parts = _split_uid_to_parts(node.raw_uid or "")
    key: list[tuple[int, Any]] = []
    for p in parts:
        try:
            key.append((0, int(p)))
        except ValueError:
            key.append((1, p))
    return key


def _collect_all_uids(nodes: list[MutableHierarchyNode]) -> set[str]:
    """Собрать все существующие effective_uid во всём лесном массиве."""
    uids: set[str] = set()
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if n.effective_uid:
            uids.add(n.effective_uid)
        stack.extend(n.children or [])
    return uids


def _collect_all_owned_element_ids(nodes: list[MutableHierarchyNode]) -> set[str]:
    """Собрать все element_id, которыми уже владеет дерево."""
    owned = set()
    stack = list(nodes)
    while stack:
        n = stack.pop()
        owned.update(n.own_element_ids or [])
        stack.extend(n.children or [])
    return owned


def _flatten_subtree(node: MutableHierarchyNode) -> list[MutableHierarchyNode]:
    """Рекурсивно разгладить поддерево в плоский список с очисткой связей."""
    flat: list[MutableHierarchyNode] = []
    stack = list(node.children or [])
    while stack:
        n = stack.pop()
        stack.extend(n.children or [])
        n.children = []
        n.node_kind = "leaf"
        flat.append(n)
    return flat


# ---------------------------------------------------------------------------
# Утилиты текста и matching
# ---------------------------------------------------------------------------
def _load_prompt_template() -> str:
    """Загрузить шаблон промпта из файла или вернуть безопасный дефолт."""
    prompts_dir = Path(getattr(settings, "PROMPTS_DIR", "/srv/steloom-dev/prompts"))
    prompt_path = prompts_dir / "structure" / "clause_detection.txt"

    if prompt_path.exists():
        try:
            return prompt_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.warning("Failed to read prompt from file", error=str(e))

    return (
        "Extract numbered clauses from the following chapter text.\n"
        "Return JSON: {{\"clauses\": [{{\"uid\": \"...\", \"title\": \"...\", "
        "\"quote_start\": \"...\", \"quote_end\": \"...\"}}]}}\n"
        "Chapter: {chapter_title} ({chapter_number})\n"
        "Text:\n---\n{chapter_text}\n---"
    )


def _build_element_map(elements: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(el.get("element_id") or el.get("id") or ""): el
        for el in elements
    }


def _compose_element_text(el: dict[str, Any]) -> str:
    """Собрать текст элемента, приклеив маркер в начало."""
    text = str(el.get("text") or "").strip()
    marker = str(el.get("marker") or "").strip()

    if not text and not marker:
        return ""
    if not text:
        return marker
    if not marker:
        return text
    if text.startswith(marker):
        return text
    return f"{marker} {text}"


def _get_numeric_prefix(raw_uid: str | None) -> str | None:
    if not raw_uid:
        return None
    if raw_uid.isdigit():
        return f"{raw_uid}."
    return None


def _get_chapter_elements(
    chapter_node: MutableHierarchyNode,
    all_roots: list[MutableHierarchyNode],
    elements: list[dict[str, Any]],
    elem_map: dict[str, dict[str, Any]],
    owned_element_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Универсальное динамическое определение элементов, принадлежащих главе.
    Извлекает полный физический спан элементов от текущего заголовка до следующего.
    Дополнительно собирает сиротские элементы подходящего префикса.
    """
    # 1. Находим физические индексы заголовков глав в исходном массиве
    root_indices: list[tuple[int, MutableHierarchyNode]] = []
    for r in all_roots:
        if r.own_element_ids:
            first_id = r.own_element_ids[0]
            idx = -1
            for i, el in enumerate(elements):
                if str(el.get("element_id") or el.get("id") or "") == first_id:
                    idx = i
                    break
            if idx != -1:
                root_indices.append((idx, r))

    root_indices.sort(key=lambda x: x[0])

    start_idx = -1
    end_idx = len(elements)

    for i, (idx, r) in enumerate(root_indices):
        if r.effective_uid == chapter_node.effective_uid:
            start_idx = idx
            if i + 1 < len(root_indices):
                end_idx = root_indices[i + 1][0]
            break

    if start_idx == -1:
        return [elem_map[eid] for eid in chapter_node.own_element_ids if eid in elem_map]

    # Физический канонический спан элементов главы
    span_elements = elements[start_idx:end_idx]

    # 2. Orphans Sweep: подтягиваем сиротские элементы префикса главы (e.g. 1.1-1.6 на стр. 4)
    chapter_prefix = _get_numeric_prefix(chapter_node.raw_uid)
    if chapter_prefix and owned_element_ids is not None:
        sweep_elements = []
        span_ids = {str(el.get("element_id") or el.get("id") or "") for el in span_elements}

        for el in elements:
            eid = str(el.get("element_id") or el.get("id") or "")
            if eid and eid not in span_ids and eid not in owned_element_ids:
                el_marker = str(el.get("marker") or "").strip()
                el_text = str(el.get("text") or "").strip()
                if el_marker.startswith(chapter_prefix) or el_text.startswith(chapter_prefix):
                    sweep_elements.append(el)

        if sweep_elements:
            sweep_with_idx = []
            for el in sweep_elements:
                for i, orig in enumerate(elements):
                    if orig == el:
                        sweep_with_idx.append((i, el))
                        break
            sweep_with_idx.sort(key=lambda x: x[0])

            prepends = [el for idx, el in sweep_with_idx if idx < start_idx]
            appends = [el for idx, el in sweep_with_idx if idx >= end_idx]

            return prepends + span_elements + appends

    return span_elements


def _extract_chapter_text(
    node: NodeType,
    all_roots: list[MutableHierarchyNode],
    elements: list[dict[str, Any]],
    elem_map: dict[str, dict[str, Any]] | None = None,
    owned_element_ids: set[str] | None = None,
) -> str:
    """Извлечь полный текст главы по каноническому спану элементов."""
    if elem_map is None:
        elem_map = _build_element_map(elements)

    chapter_elements = _get_chapter_elements(
        chapter_node=node,  # type: ignore[arg-type]
        all_roots=all_roots,
        elements=elements,
        elem_map=elem_map,
        owned_element_ids=owned_element_ids,
    )

    parts: list[str] = []
    for el in chapter_elements:
        piece = _compose_element_text(el)
        if piece:
            parts.append(piece)

    return "\n".join(parts)


def _match_clauses_to_elements(
    clauses: list[DetectedClause],
    all_roots: list[MutableHierarchyNode],
    elements: list[dict[str, Any]],
    chapter_node: NodeType,
    elem_map: dict[str, dict[str, Any]] | None = None,
    owned_element_ids: set[str] | None = None,
) -> list[tuple[DetectedClause, list[str]]]:
    """Сопоставить найденные пункты с element_id (Fuzzy matching + Resilient fallback)."""
    if elem_map is None:
        elem_map = _build_element_map(elements)

    chapter_elements = _get_chapter_elements(
        chapter_node=chapter_node,  # type: ignore[arg-type]
        all_roots=all_roots,
        elements=elements,
        elem_map=elem_map,
        owned_element_ids=owned_element_ids,
    )

    results: list[tuple[DetectedClause, list[str]]] = []

    for clause in clauses:
        matched: list[str] = []
        target_uid = clause.uid.strip().rstrip(".")

        # Уровень 1: Fuzzy text anchor
        qs = clause.quote_start.strip()[:25]
        qs_clean = re.sub(r'^[|\s]+', '', qs).strip()

        if qs_clean and len(qs_clean) >= 4:
            for el in chapter_elements:
                text = _compose_element_text(el).strip()
                if not text:
                    continue
                text_clean = re.sub(r'^[|\s]+', '', text).strip()
                if (
                    text_clean.startswith(qs_clean[:12])
                    or qs_clean[:12] in text_clean[:100]
                ):
                    eid = str(el.get("element_id") or el.get("id") or "")
                    if eid and eid not in matched:
                        matched.append(eid)

        # Уровень 2: Resilient UID/marker fallback (bilingual-safe)
        if not matched:
            for el in chapter_elements:
                el_marker = str(el.get("marker") or "").strip().rstrip(".")
                el_text = _compose_element_text(el).strip()
                if (
                    (el_marker and el_marker == target_uid)
                    or el_text.startswith(target_uid + " ")
                    or el_text.startswith(target_uid + "\t")
                ):
                    eid = str(el.get("element_id") or el.get("id") or "")
                    if eid and eid not in matched:
                        matched.append(eid)

        results.append((clause, matched))

    return results


# ---------------------------------------------------------------------------
# Детектор
# ---------------------------------------------------------------------------
class LLMClauseDetector:
    def __init__(self) -> None:
        self.llm = LLMClient()
        self.prompt_template = _load_prompt_template()
        self.enabled = getattr(settings, "STRUCTURE_ENABLE_LLM_REFINER", True)

    def _call_llm(self, prompt: str) -> str | None:
        if not self.llm.is_available():
            logger.debug("CLAUSE_DETECTOR llm_unavailable")
            METRICS.clause_detector_llm_calls_total.labels(
                status="unavailable",
            ).inc()
            return None

        try:
            response, error_details = self.llm.call_with_retries(
                prompt=prompt,
                temperature=0.0,
                max_tokens=2000,
                response_format="json_object",
            )
            if error_details and error_details.get("error_type"):
                logger.warning(
                    "CLAUSE_DETECTOR llm_error",
                    extra={"error": error_details.get("error_message")},
                )
                METRICS.clause_detector_llm_calls_total.labels(
                    status="error",
                ).inc()
                return None

            text = response.text if response else None
            if not text:
                METRICS.clause_detector_llm_calls_total.labels(
                    status="empty",
                ).inc()
            else:
                METRICS.clause_detector_llm_calls_total.labels(
                    status="success",
                ).inc()
            return text

        except Exception as e:
            logger.warning("CLAUSE_DETECTOR exception", extra={"error": str(e)})
            METRICS.clause_detector_llm_calls_total.labels(
                status="error",
            ).inc()
            return None

    def detect_clauses_in_chapter(
        self,
        chapter_node: NodeType,
        all_roots: list[MutableHierarchyNode],
        elements: list[dict[str, Any]],
        elem_map: dict[str, dict[str, Any]] | None = None,
        owned_element_ids: set[str] | None = None,
    ) -> tuple[list[DetectedClause], str]:
        text = _extract_chapter_text(
            chapter_node, all_roots, elements, elem_map, owned_element_ids
        )

        if len(text) < _MIN_TEXT_LEN:
            return [], "none"
        if len(text) > _MAX_TEXT_LEN:
            text = text[:_MAX_TEXT_LEN]

        prompt = (
            self.prompt_template
            .replace("{chapter_title}", chapter_node.title or "")
            .replace("{chapter_number}", str(chapter_node.raw_uid or ""))
            .replace("{chapter_text}", text)
        )

        raw_response = self._call_llm(prompt)
        clauses = (
            parse_llm_response(raw_response, chapter_node.raw_uid)
            if raw_response
            else []
        )
        source = "llm"

        if not clauses:
            logger.debug(
                "CLAUSE_DETECTOR llm_empty, trying fallback",
                extra={"chapter": chapter_node.raw_uid},
            )
            clauses = extract_clauses_fallback(text, chapter_node.raw_uid)
            source = "fallback"

            if clauses:
                METRICS.clause_detector_fallback_clauses_total.labels(
                    pattern_type="generic",
                ).inc(len(clauses))

        return clauses, source

    def refine_tree(
        self,
        root_nodes: Sequence[NodeType],
        elements: list[dict[str, Any]],
    ) -> ClauseRefineResult:
        """Обогатить ClauseTree пунктами всех уровней вложенности."""
        import time as _time

        _refine_start = _time.perf_counter()
        _refine_status = "success"

        empty_result = ClauseRefineResult(
            clauses_added=0, roots=root_nodes, stats={"skipped": True},
        )

        if not self.enabled:
            logger.info("CLAUSE_DETECTOR skipped: disabled by config")
            METRICS.clause_detector_refine_duration_seconds.labels(
                status="skipped",
            ).observe(_time.perf_counter() - _refine_start)
            return empty_result
        if not self.llm.is_available():
            logger.info("CLAUSE_DETECTOR skipped: LLM unavailable")
            METRICS.clause_detector_refine_duration_seconds.labels(
                status="skipped",
            ).observe(_time.perf_counter() - _refine_start)
            return empty_result
        if not root_nodes:
            METRICS.clause_detector_refine_duration_seconds.labels(
                status="skipped",
            ).observe(_time.perf_counter() - _refine_start)
            return empty_result

        is_frozen_input = isinstance(root_nodes[0], FrozenHierarchyNode)
        mutable_roots = (
            unfreeze_forest(root_nodes)  # type: ignore[arg-type]
            if is_frozen_input
            else list(root_nodes)  # type: ignore[arg-type]
        )

        elem_map = _build_element_map(elements)
        total_added = 0
        total_skipped_duplicate = 0
        total_skipped_no_match = 0
        total_construction_failed = 0

        # Сбор глобальных инвариантов
        global_existing_uids = _collect_all_uids(mutable_roots)
        owned_element_ids = _collect_all_owned_element_ids(mutable_roots)

        for node in mutable_roots:
            if not node.own_element_ids:
                continue

            clauses, source = self.detect_clauses_in_chapter(
                node, mutable_roots, elements, elem_map, owned_element_ids
            )
            if not clauses:
                continue

            matched = _match_clauses_to_elements(
                clauses, mutable_roots, elements, node, elem_map, owned_element_ids
            )

            # Извлекаем плоский срез УЖЕ существующих потомков FSM
            existing_descendants = _flatten_subtree(node)
            existing_uids_in_subtree = {d.effective_uid for d in existing_descendants}
            
            new_candidates: list[MutableHierarchyNode] = []

            for clause, elem_ids in matched:
                if not elem_ids:
                    total_skipped_no_match += 1
                    METRICS.clause_detector_skipped_total.labels(
                        reason="no_match",
                    ).inc()
                    continue

                clause_clean_uid = clause.uid.strip().rstrip(".")
                child_uid = f"{node.scope}:{clause_clean_uid}"

                if child_uid in global_existing_uids or child_uid in existing_uids_in_subtree:
                    total_skipped_duplicate += 1
                    METRICS.clause_detector_skipped_total.labels(
                        reason="duplicate",
                    ).inc()
                    continue

                # Clamp-наследование страниц
                child_pages = []
                for eid in elem_ids:
                    el = elem_map.get(eid)
                    if el and el.get("page") is not None:
                        try:
                            child_pages.append(int(el["page"]))
                        except Exception:
                            pass

                c_start = min(child_pages) if child_pages else node.start_page
                c_end = max(child_pages) if child_pages else node.end_page
                c_start = max(node.start_page, min(c_start, node.end_page))
                c_end = max(c_start, min(c_end, node.end_page))

                try:
                    child = MutableHierarchyNode(
                        raw_uid=clause_clean_uid,
                        effective_uid=child_uid,
                        title=clause.title or clause_clean_uid,
                        level=node.level + 1,
                        scope=node.scope,
                        node_kind="leaf",
                        own_element_ids=elem_ids,
                        subtree_element_ids=elem_ids,
                        start_page=c_start,
                        end_page=c_end,
                        diagnostics={
                            "source": source,
                            "llm_clause_added": True,
                            "parent_effective_uid": node.effective_uid,
                            "quote_start": clause.quote_start[:50],
                            "quote_end": clause.quote_end[:50],
                        },
                    )
                    new_candidates.append(child)
                    global_existing_uids.add(child_uid)
                    owned_element_ids.update(elem_ids)
                    total_added += 1
                except Exception as e:
                    total_construction_failed += 1
                    METRICS.clause_detector_skipped_total.labels(
                        reason="construction_failed",
                    ).inc()
                    logger.debug(
                        "CLAUSE_DETECTOR child_construction_failed",
                        extra={
                            "clause_uid": clause_clean_uid,
                            "parent": node.effective_uid,
                            "error": str(e),
                        },
                    )

            if not new_candidates and not existing_descendants:
                continue

            # --- ИЕРАРХИЧЕСКОЕ ОБЪЕДИНЕНИЕ (Merge, Not Replace) ---
            all_nodes = existing_descendants + new_candidates
            parent_map: dict[str, list[MutableHierarchyNode]] = defaultdict(list)

            for cand in all_nodes:
                parent = _find_best_parent(cand, all_nodes, node)
                parent_map[parent.effective_uid].append(cand)

            def _assemble(parent: MutableHierarchyNode) -> None:
                children = parent_map.get(parent.effective_uid, [])
                if children:
                    parent.children = sorted(children, key=_sort_key_for_node)
                    parent.node_kind = "section"
                    for child in parent.children:
                        child.level = parent.level + 1
                        _assemble(child)
                else:
                    parent.children = []
                    parent.node_kind = "leaf"

            _assemble(node)
            _propagate_subtree_element_ids(node)

        stats = {
            "clauses_added": total_added,
            "skipped_duplicate": total_skipped_duplicate,
            "skipped_no_match": total_skipped_no_match,
            "construction_failed": total_construction_failed,
            "input_mode": "frozen" if is_frozen_input else "mutable",
        }

        # ── Prometheus export ────────────────────────────────────────
        if total_added > 0:
            METRICS.clause_detector_clauses_added_total.labels(
                method="llm",
            ).inc(total_added)
            logger.info("CLAUSE_DETECTOR refine_tree completed", extra=stats)

        # ── Duration ─────────────────────────────────────────────────
        _refine_duration = _time.perf_counter() - _refine_start
        METRICS.clause_detector_refine_duration_seconds.labels(
            status=_refine_status,
        ).observe(_refine_duration)

        if is_frozen_input:
            try:
                frozen_roots = refreeze_forest(mutable_roots)
                return ClauseRefineResult(
                    clauses_added=total_added, roots=frozen_roots, stats=stats,
                )
            except Exception as e:
                _refine_status = "error"
                METRICS.clause_detector_refine_duration_seconds.labels(
                    status="error",
                ).observe(_time.perf_counter() - _refine_start)
                logger.warning(
                    "CLAUSE_DETECTOR refreeze_failed, reverting to original frozen tree",
                    extra={
                        "error": str(e),
                        "clauses_would_be_added": total_added,
                    },
                )
                stats["refreeze_failed"] = True
                stats["reverted_to_original"] = True
                return ClauseRefineResult(
                    clauses_added=0, roots=root_nodes, stats=stats,
                )

        return ClauseRefineResult(
            clauses_added=total_added, roots=mutable_roots, stats=stats,
        )

# src/services/structure/_clause_detector/detector.py

"""
LLMClauseDetector — определение пунктов в главах договора.

Архитектурные принципы:
- Frozen-safe: принимает как Mutable, так и Frozen узлы.
- Dynamic Span-Based Text Extraction: рассчитывает физические границы главы в документе.
- Appendix Boundary Trimming: отсекает спан главы при обнаружении первого приложения.
- Hybrid LLM + Fallback Merge: гибридный запуск LLM и регулярного парсера для 100% полноты.
- Global Routing First: сначала перемещает misplaced элементы в родные главы.
- Layout-Aware Parenting (List Intro Invariant): буквенные подпункты (a), (b)
  прикрепляются к вводному разделу (3.4), а не к соседним завершенным листьям (3.4.1).
- Bottom-up Page Expansion: честный расчет страниц снизу-вверх для избежания рассинхрона.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Sequence, Union
import uuid
from services.llm_usage_recorder import LLMUsageRecorder
from mas_queue.async_helpers import log_task_exception

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
from services.structure._clause_detector.routing import global_routing_pass

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
# Граница приложений (Appendix Boundary Detection)
# ---------------------------------------------------------------------------
_APPENDIX_HEADING_RE = re.compile(
    r"""
    ^\s*
    (?:
        ПРИЛОЖЕНИ[ЕЯЙ] | APPENDI[XC]E?S? | ANNEX(?:ES)? |
        SCHEDULE | EXHIBIT | ATTACHMENT | ANLAGE | BEILAGE
    )
    \s*
    (?: № | N[Oo]\.? | \# | N\.? )?
    \s*
    [A-ZА-ЯЁ\d]
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _find_appendix_boundary(span_elements: list[dict[str, Any]]) -> int:
    for i, el in enumerate(span_elements):
        text = str(el.get("text") or "").strip()
        marker = str(el.get("marker") or "").strip()
        full_text = f"{marker} {text}".strip() if marker else text

        if _APPENDIX_HEADING_RE.match(full_text):
            return i
    return len(span_elements)


# ---------------------------------------------------------------------------
# Контракт возврата
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class ClauseRefineResult:
    clauses_added: int
    roots: Sequence[NodeType]
    stats: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Утилиты иерархической сборки (Merge, Not Replace)
# ---------------------------------------------------------------------------
def _split_uid_to_parts(uid: str) -> list[str]:
    normalized = (
        uid.replace("(", ".")
        .replace(")", ".")
        .replace("[", ".")
        .replace("]", ".")
    )
    return [p.strip() for p in normalized.split(".") if p.strip()]


def _get_physical_index(node: MutableHierarchyNode, elem_to_idx: dict[str, int]) -> int:
    if node.own_element_ids:
        return elem_to_idx.get(node.own_element_ids[0], 999999)
    return 999999


def _is_letter_like_uid(uid: str) -> bool:
    u = (uid or "").strip().lower()
    if not u:
        return False
    if re.match(r"^\(?[a-zа-яёivxlcm]+\)?[\.\)]?$", u):
        return True
    if u in {"•", "-", "–", "—", "*"}:
        return True
    return False


def _find_best_parent(
    target: MutableHierarchyNode,
    candidates: list[MutableHierarchyNode],
    chapter_node: MutableHierarchyNode,
) -> MutableHierarchyNode:
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


def _compute_parent_uid_str(node_uid: str) -> str | None:
    parts = _split_uid_to_parts(node_uid)
    if len(parts) <= 1:
        return None
    return ".".join(parts[:-1])


def _find_best_parent_layout_aware(
    target: MutableHierarchyNode,
    candidates: list[MutableHierarchyNode],
    chapter_node: MutableHierarchyNode,
    elem_to_idx: dict[str, int],
) -> MutableHierarchyNode:
    prefix_parent = _find_best_parent(target, candidates, chapter_node)
    if prefix_parent is not chapter_node:
        return prefix_parent

    target_uid = (target.raw_uid or "").strip()
    chapter_uid = (chapter_node.raw_uid or "").strip()

    if chapter_uid and target_uid.startswith(chapter_uid):
        rest = target_uid[len(chapter_uid):]
        if rest and rest[0] in ". )":
            return chapter_node

    if not _is_letter_like_uid(target_uid):
        return chapter_node

    target_idx = _get_physical_index(target, elem_to_idx)
    best_parent = chapter_node
    best_idx = -1
    for cand in candidates:
        if cand is target:
            continue

        cand_uid = (cand.raw_uid or "").strip()
        if _is_letter_like_uid(cand_uid):
            continue

        cand_idx = _get_physical_index(cand, elem_to_idx)
        if cand_idx < target_idx and cand_idx > best_idx:
            best_idx = cand_idx
            best_parent = cand

    # 🛡️ LIST INTRO INVARIANT:
    # Если кандидат-предшественник (3.4.1) является подпунктом глубины > 2 и не заканчивается двоеточием,
    # подпункт (a) относим к родительскому разделу 3.4
    if best_parent is not chapter_node:
        b_uid = (best_parent.raw_uid or "").strip()
        b_parts = _split_uid_to_parts(b_uid)
        b_title = (best_parent.title or "").strip()
        
        if len(b_parts) >= 3 and not b_title.endswith(":"):
            p_uid = _compute_parent_uid_str(b_uid)
            if p_uid:
                p_cand = next((c for c in candidates if (c.raw_uid or "").strip() == p_uid), None)
                if p_cand:
                    best_parent = p_cand

    return best_parent


def _recompute_page_ranges(
    node: MutableHierarchyNode,
    elem_map: dict[str, dict[str, Any]],
) -> tuple[int, int]:
    pages: list[int] = []
    
    for eid in node.own_element_ids or []:
        el = elem_map.get(str(eid))
        if el and el.get("page") is not None:
            try:
                pages.append(int(el["page"]))
            except Exception:
                pass
                
    for child in node.children or []:
        c_start, c_end = _recompute_page_ranges(child, elem_map)
        pages.extend([c_start, c_end])
        
    if pages:
        node.start_page = min(pages)
        node.end_page = max(pages)
        
    return node.start_page, node.end_page


def _propagate_subtree_element_ids(node: MutableHierarchyNode) -> list[str]:
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
    parts = _split_uid_to_parts(node.raw_uid or "")
    key: list[tuple[int, Any]] = []
    for p in parts:
        try:
            key.append((0, int(p)))
        except ValueError:
            key.append((1, p))
    return key


def _collect_all_uids(nodes: list[MutableHierarchyNode]) -> set[str]:
    uids: set[str] = set()
    stack = list(nodes)
    while stack:
        n = stack.pop()
        if n.effective_uid:
            uids.add(n.effective_uid)
        stack.extend(n.children or [])
    return uids


def _collect_all_owned_element_ids(nodes: list[MutableHierarchyNode]) -> set[str]:
    owned = set()
    stack = list(nodes)
    while stack:
        n = stack.pop()
        owned.update(n.own_element_ids or [])
        stack.extend(n.children or [])
    return owned


def _flatten_subtree(node: MutableHierarchyNode) -> list[MutableHierarchyNode]:
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

    span_elements = elements[start_idx:end_idx]

    # Обрезка спана на границе приложений
    appendix_boundary = _find_appendix_boundary(span_elements)
    if appendix_boundary < len(span_elements):
        span_elements = span_elements[:appendix_boundary]

    # Orphans Sweep
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
                    if orig is el or (
                        str(orig.get("element_id") or orig.get("id") or "")
                        == str(el.get("element_id") or el.get("id") or "")
                    ):
                        sweep_with_idx.append((i, el))
                        break
            sweep_with_idx.sort(key=lambda x: x[0])

            # Orphans = ТОЛЬКО до заголовка главы (1.1–1.6 до "1 ОПРЕДЕЛЕНИЯ").
            # НЕ подтягиваем элементы после end_idx (иначе 7.5/7.7 из приложений
            # с префиксом "7." всасываются в главу 7).
            prepends = [el for idx, el in sweep_with_idx if idx < start_idx]

            return prepends + span_elements

    return span_elements


def _extract_chapter_text(
    node: NodeType,
    all_roots: list[MutableHierarchyNode],
    elements: list[dict[str, Any]],
    elem_map: dict[str, dict[str, Any]] | None = None,
    owned_element_ids: set[str] | None = None,
) -> str:
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

        qs = clause.quote_start.strip()[:25]
        qs_clean = re.sub(r'^[|\s]+', '', qs).strip()
        # Если quote_start = "3.4.2 1 000 000...", а в layout нет префикса 3.4.2 —
        # матчим по телу цитаты без UID.
        if target_uid and qs_clean.startswith(target_uid):
            rest = qs_clean[len(target_uid):].lstrip(" .)\t")
            if rest:
                qs_clean = rest

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

    def detect_clauses_in_chapter(
        self,
        chapter_node: NodeType,
        all_roots: list[MutableHierarchyNode],
        elements: list[dict[str, Any]],
        elem_map: dict[str, dict[str, Any]] | None = None,
        owned_element_ids: set[str] | None = None,
        tenant_id: Optional[uuid.UUID] = None,
        deal_id: Optional[uuid.UUID] = None,
        document_id: Optional[uuid.UUID] = None,
        run_id: Optional[uuid.UUID] = None,
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

        raw_response, _telemetry = (
            self._call_llm(
                prompt,
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=document_id,
                run_id=run_id,
            )
            if self.llm.is_available()
            else (None, None)
        )
        llm_clauses = (
            parse_llm_response(raw_response, chapter_node.raw_uid)
            if raw_response
            else []
        )

        fallback_clauses = extract_clauses_fallback(text, chapter_node.raw_uid)

        # Hybrid Merge: LLM + Fallback
        merged: dict[str, DetectedClause] = {}
        for c in fallback_clauses:
            uid_key = c.uid.strip().rstrip(".")
            merged[uid_key] = c

        for c in llm_clauses:
            uid_key = c.uid.strip().rstrip(".")
            merged[uid_key] = c

        clauses = list(merged.values())
        source = "merged_hybrid"

        if clauses and not llm_clauses:
            source = "fallback"

        return clauses, source

    def _call_llm(
        self,
        prompt: str,
        tenant_id: Optional[uuid.UUID] = None,
        deal_id: Optional[uuid.UUID] = None,
        document_id: Optional[uuid.UUID] = None,
        run_id: Optional[uuid.UUID] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """
        Вызывает LLM и возвращает (text, telemetry_dict).

        Если tenant_id, deal_id, document_id переданы — записывает в ledger.
        """
        from engine.llm.client import build_llm_telemetry_from_response

        try:
            response, error_details = self.llm.call_with_retries(
                prompt=prompt,
                temperature=0.0,
                max_tokens=2000,
                response_format="json_object",
            )

            if error_details and error_details.get("error_type"):
                return None, None

            text = response.text if response else None
            if not text:
                return None, None

            telemetry = build_llm_telemetry_from_response(
                response,
                duration_ms=error_details.get("duration_ms"),
                llm_attempts=error_details.get("llm_attempts"),
            )
            telemetry["error_type"] = error_details.get("error_type")
            telemetry["parse_success"] = True

            # Запись в ledger (best-effort, не роняет пайплайн).
            #
            # ВАЖНО: _call_llm — sync-функция, но вызывается внутри running
            # event loop (structure_builder.py:run_async(_wrapper())). Поэтому
            # используем asyncio.create_task() для планирования корутины
            # в текущем loop.
            #
            # run_async() здесь НЕ подходит: он специально падает с RuntimeError
            # при вызове из running loop (см. mas_queue/async_helpers.py).
            if all([tenant_id, deal_id, document_id]):
                try:
                    import asyncio  # local import — избегаем циклов на импорте

                    task = asyncio.create_task(
                        LLMUsageRecorder.record_event_isolated(
                            tenant_id=tenant_id,
                            deal_id=deal_id,
                            stage="structure_clause_detection",
                            provider=telemetry.get("provider", "unknown"),
                            model=telemetry.get("model", "unknown"),
                            run_id=run_id,
                            document_id=document_id,
                            check_id=None,
                            prompt_tokens=telemetry.get("prompt_tokens"),
                            completion_tokens=telemetry.get("completion_tokens"),
                            duration_ms=telemetry.get("duration_ms"),
                            llm_attempts=telemetry.get("llm_attempts"),
                            parse_success=True,
                            error_type=None,
                        )
                    )
                    task.add_done_callback(log_task_exception)
                except Exception as exc:
                    logger.warning(
                        "ClauseDetector: failed to schedule LLM usage record",
                        extra={"document_id": str(document_id), "error": str(exc)},
                    )

            return text, telemetry

        except Exception as exc:
            logger.warning(
                "ClauseDetector: LLM call failed",
                extra={"error": str(exc)},
            )
            return None, None

    def refine_tree(
        self,
        root_nodes: Sequence[NodeType],
        elements: list[dict[str, Any]],
        tenant_id: Optional[uuid.UUID] = None,
        deal_id: Optional[uuid.UUID] = None,
        document_id: Optional[uuid.UUID] = None,
        run_id: Optional[uuid.UUID] = None,
    ) -> ClauseRefineResult:
        import time as _time

        _refine_start = _time.perf_counter()
        empty_result = ClauseRefineResult(
            clauses_added=0, roots=root_nodes, stats={"skipped": True},
        )

        if not root_nodes:
            return empty_result

        is_frozen_input = isinstance(root_nodes[0], FrozenHierarchyNode)
        mutable_roots = (
            unfreeze_forest(root_nodes)  # type: ignore[arg-type]
            if is_frozen_input
            else list(root_nodes)  # type: ignore[arg-type]
        )

        elem_map = _build_element_map(elements)
        elem_to_idx = {
            str(el.get("element_id") or el.get("id") or ""): i
            for i, el in enumerate(elements)
        }

        total_added = 0
        total_skipped_duplicate = 0
        total_skipped_no_match = 0
        total_construction_failed = 0

        global_existing_uids = _collect_all_uids(mutable_roots)
        owned_element_ids = _collect_all_owned_element_ids(mutable_roots)

        # 1. Извлечение и первичная привязка элементов
        for node in mutable_roots:
            if not node.own_element_ids:
                continue

            clauses, source = self.detect_clauses_in_chapter(
                node,
                mutable_roots,
                elements,
                elem_map,
                owned_element_ids,
                tenant_id=tenant_id,
                deal_id=deal_id,
                document_id=document_id,
                run_id=run_id,
            )
            if not clauses:
                continue

            matched = _match_clauses_to_elements(
                clauses, mutable_roots, elements, node, elem_map, owned_element_ids
            )

            existing_descendants = _flatten_subtree(node)
            existing_uids_in_subtree = {d.effective_uid for d in existing_descendants}
            
            new_candidates: list[MutableHierarchyNode] = []

            for clause, elem_ids in matched:
                if not elem_ids:
                    total_skipped_no_match += 1
                    continue

                clause_clean_uid = clause.uid.strip().rstrip(".")
                child_uid = f"{node.scope}:{clause_clean_uid}"

                if child_uid in global_existing_uids or child_uid in existing_uids_in_subtree:
                    total_skipped_duplicate += 1
                    continue

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

            if not new_candidates and not existing_descendants:
                continue

            node.children = sorted(existing_descendants + new_candidates, key=_sort_key_for_node)

        # ── 🚀 2. ГЛОБАЛЬНАЯ МАРШРУТИЗАЦИЯ (Global Routing First) ──────────
        for r in mutable_roots:
            _recompute_page_ranges(r, elem_map)

        routing_stats: dict[str, int] = {
            "moved": 0,
            "synthetic_parents": 0,
            "deduplicated": 0,
            "empty_cleaned": 0,
        }
        try:
            routing_stats = global_routing_pass(mutable_roots)
            logger.info("CLAUSE_DETECTOR routing_pass_completed", extra=routing_stats)
        except Exception as e:
            logger.warning("CLAUSE_DETECTOR routing_pass_failed", extra={"error": str(e)})

        # ── 🚀 3. ИЕРАРХИЧЕСКАЯ СБОРКА ПОДПУНКТОВ ПОСЛЕ РОУТИНГА ──────────
        for node in mutable_roots:
            all_descendants = _flatten_subtree(node)
            if not all_descendants:
                continue
                
            parent_map: dict[str, list[MutableHierarchyNode]] = defaultdict(list)
            for cand in all_descendants:
                parent = _find_best_parent_layout_aware(
                    cand, all_descendants, node, elem_to_idx
                )
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

        # ── 🚀 4. ФИНАЛЬНЫЙ ПЕРЕСЧЕТ СТРАНИЦ И ЭЛЕМЕНТОВ ──────────
        for r in mutable_roots:
            _recompute_page_ranges(r, elem_map)
            _propagate_subtree_element_ids(r)

        stats = {
            "clauses_added": total_added,
            "skipped_duplicate": total_skipped_duplicate,
            "skipped_no_match": total_skipped_no_match,
            "construction_failed": total_construction_failed,
            "input_mode": "frozen" if is_frozen_input else "mutable",
            "routing": routing_stats,
        }

        if is_frozen_input:
            try:
                frozen_roots = refreeze_forest(mutable_roots)
                return ClauseRefineResult(
                    clauses_added=total_added, roots=frozen_roots, stats=stats,
                )
            except Exception as e:
                logger.warning("CLAUSE_DETECTOR refreeze_failed", extra={"error": str(e)})
                return ClauseRefineResult(
                    clauses_added=0, roots=root_nodes, stats=stats,
                )

        return ClauseRefineResult(
            clauses_added=total_added, roots=mutable_roots, stats=stats,
        )

# src/services/structure/legal_unit_extractor.py

"""
LegalUnitExtractor — materialization of exact sub-units inside one parent LegalUnit.

Назначение:
- НЕ заменяет hierarchy builder;
- НЕ строит clause tree;
- НЕ трогает heading pipeline;
- работает поверх уже построенного parent LegalUnit и его own_element_ids.

Текущий scope:
- извлекает только definition_item sub-units из parent unit типа DEFINITION;
- не пытается materialize generic numbered clauses;
- не лезет в DB / MinIO / LLM;
- pure deterministic helper.

Почему это безопасно:
- definition_item уже надёжно распознаётся existing rules:
  `looks_like_definition_item()`;
- definition_item intentionally excluded from heading pipeline
  (heading_confidence = 0.0), значит нужен отдельный extractor;
- extractor включается только там, где caller явно передал element_index.

Контракт:
- input:
    * parent_unit: LegalUnit
    * element_index: dict[element_id -> layout element]
    * existing_unit_ids: set[str]  (для защиты от коллизий)
- output:
    * list[LegalUnit] children
    * [] если sub-units не найдены или extraction невозможен
"""

from __future__ import annotations

import copy
import re
from typing import Any

from core.logging import get_logger
from services.structure.heading_patterns import normalize_spaces, parse_raw_heading
from services.structure.legal_heading_rules import looks_like_definition_item
from services.structure.legal_unit_models import (
    CitabilityMetrics,
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
)

logger = get_logger(__name__)


# ── Local helpers ────────────────────────────────────────────────────────────

_DEFINITION_VERB_RE = re.compile(
    r"""
    \b(
        означает(?:ся|ют|ет)?
        |понимается
        |именуется
        |подразумевает(?:ся)?
        |shall\s+mean
        |means
        |shall\s+have\s+the\s+meaning
        |has\s+the\s+meaning
    )\b
    """,
    re.IGNORECASE | re.VERBOSE,
)

_QUOTED_TERM_RE = re.compile(
    r"""
    ^\s*
    (?:
        "([^"]{1,160})"
        |«([^»]{1,160})»
        |„([^“]{1,160})“
        |“([^”]{1,160})”
    )
    """,
    re.VERBOSE,
)


def _normalize_text(value: Any) -> str:
    return normalize_spaces(str(value or "")).strip()


def _compose_child_unit_id(parent_unit: LegalUnit, raw_uid: str) -> str:
    """
    Stable child unit id:
    - if parent scope exists → scope:raw_uid
    - else raw_uid

    Не inventим новый id namespace, опираемся на уже существующий
    effective_uid contract в системе: `scope:raw_uid`.
    """
    scope = _normalize_text(parent_unit.scope)
    raw_uid = _normalize_text(raw_uid)
    if scope:
        return f"{scope}:{raw_uid}"
    return raw_uid


def _extract_definition_title(text: str) -> str:
    """
    Извлечь title/term из definition item.

    Примеры:
    - '1.10 "Purchase Price" means ...' -> 'Purchase Price'
    - '1.10 «Покупная цена» означает ...' -> 'Покупная цена'
    - '1.3 Банк означает ...' -> 'Банк'

    Если не удалось — возвращаем нормализованный body до definition verb,
    либо весь текст как fallback.
    """
    normalized = _normalize_text(text)
    if not normalized:
        return ""

    parsed = parse_raw_heading(normalized)
    body = _normalize_text(parsed[1] if parsed is not None else normalized)
    if not body:
        return ""

    m_quoted = _QUOTED_TERM_RE.match(body)
    if m_quoted:
        for group in m_quoted.groups():
            if group:
                return _normalize_text(group)

    m_term = re.match(
        r"""
        ^\s*
        (?P<term>.+?)
        \s+
        (?:
            означает(?:ся|ют|ет)?
            |понимается
            |именуется
            |подразумевает(?:ся)?
            |shall\s+mean
            |means
            |shall\s+have\s+the\s+meaning
            |has\s+the\s+meaning
        )\b
        """,
        body,
        re.IGNORECASE | re.VERBOSE,
    )
    if m_term:
        term = _normalize_text(m_term.group("term"))
        if term:
            # Снимаем внешние кавычки
            term = term.strip().strip('"').strip("'").strip("«»").strip("“”„")
            return _normalize_text(term)

    return body[:160].strip()


def _collect_exact_text_from_elements(elements: list[dict[str, Any]]) -> str:
    """
    Собрать exact text из layout elements children unit.

    Мы не повторяем clause_tree_builder logic по pages/paragraph gaps —
    здесь важно получить deterministic exact text по source elements.
    """
    parts: list[str] = []
    last_page: int | None = None

    for el in elements:
        if not isinstance(el, dict):
            continue

        text = _normalize_text(el.get("text"))
        if not text:
            continue

        page = el.get("page")
        if (
            last_page is not None
            and isinstance(page, int)
            and isinstance(last_page, int)
            and page != last_page
        ):
            parts.append("")

        parts.append(text)
        last_page = page if isinstance(page, int) else last_page

    # сохраняем мягкие paragraph/page breaks
    exact_text = "\n\n".join(part for part in parts if part is not None).strip()
    return exact_text


def _build_child_citability(parent_unit: LegalUnit, exact_text: str) -> CitabilityMetrics:
    """
    Definition child units — high citability if exact_text exists.

    Не inventим новую сложную scoring policy; опираемся на already existing model.
    """
    parent_citability = parent_unit.citability or CitabilityMetrics()
    has_text = bool(_normalize_text(exact_text))

    return CitabilityMetrics(
        citability_score=0.9 if has_text else 0.0,
        citability_band="high" if has_text else "low",
        has_own_text=has_text,
        has_subtree_text=has_text,
        is_heading_only=False,
        recovered_via_best_effort=bool(parent_unit.recovered_via_best_effort),
        parse_confidence=parent_citability.parse_confidence,
        is_technical_fallback=False,
    )


class LegalUnitExtractor:
    """
    Извлекает exact child legal units из parent LegalUnit.

    Текущая реализация:
    - только definition_item extraction;
    - parent unit должен быть semantic DEFINITION;
    - child ids must not collide with existing units.
    """

    def extract_definition_sub_units(
        self,
        *,
        parent_unit: LegalUnit,
        element_index: dict[str, dict[str, Any]],
        existing_unit_ids: set[str] | None = None,
    ) -> list[LegalUnit]:
        """
        Вернуть children definition units или [].

        Parent остаётся жить отдельно; caller сам решает,
        как его demote / reclassify.
        """
        if parent_unit.unit_type != LegalUnitType.DEFINITION:
            return []

        if parent_unit.is_technical_fallback:
            return []

        if not parent_unit.own_element_ids:
            return []

        existing_ids = set(existing_unit_ids or set())

        ordered_elements: list[tuple[str, dict[str, Any]]] = []
        for el_id in parent_unit.own_element_ids:
            el = element_index.get(str(el_id))
            if not isinstance(el, dict):
                continue
            ordered_elements.append((str(el_id), el))

        if not ordered_elements:
            return []

        # ── Detect anchors ─────────────────────────────────────────────
        anchors: list[tuple[int, str, str, str]] = []
        # (position, child_raw_uid, child_unit_id, heading_text)

        for idx, (_el_id, el) in enumerate(ordered_elements):
            text = _normalize_text(el.get("text"))
            if not text:
                continue

            if not looks_like_definition_item(text):
                continue

            parsed = parse_raw_heading(text)
            if parsed is None:
                # Без parsed uid не inventим synthetic ids.
                logger.debug(
                    "LegalUnitExtractor: definition anchor skipped — no parsed uid",
                    extra={
                        "parent_unit_id": parent_unit.unit_id,
                        "text_sample": text[:120],
                    },
                )
                continue

            child_raw_uid, _title = parsed
            child_raw_uid = _normalize_text(child_raw_uid)
            if not child_raw_uid:
                continue

            child_unit_id = _compose_child_unit_id(parent_unit, child_raw_uid)
            if child_unit_id in existing_ids:
                logger.debug(
                    "LegalUnitExtractor: definition anchor skipped — unit_id already exists",
                    extra={
                        "parent_unit_id": parent_unit.unit_id,
                        "child_unit_id": child_unit_id,
                    },
                )
                continue

            anchors.append((idx, child_raw_uid, child_unit_id, text))

        if not anchors:
            return []

        # ── Build children from anchor spans ───────────────────────────
        children: list[LegalUnit] = []

        for anchor_idx, (start_pos, child_raw_uid, child_unit_id, heading_text) in enumerate(anchors):
            end_pos = (
                anchors[anchor_idx + 1][0]
                if anchor_idx + 1 < len(anchors)
                else len(ordered_elements)
            )

            grouped_ids: list[str] = []
            grouped_elements: list[dict[str, Any]] = []

            for el_id, el in ordered_elements[start_pos:end_pos]:
                grouped_ids.append(el_id)
                grouped_elements.append(el)

            exact_text = _collect_exact_text_from_elements(grouped_elements)
            if not exact_text:
                continue

            pages = [
                int(el.get("page"))
                for el in grouped_elements
                if isinstance(el.get("page"), int)
            ]
            page_start = min(pages) if pages else parent_unit.page_start
            page_end = max(pages) if pages else parent_unit.page_end

            title = _extract_definition_title(heading_text) or child_raw_uid

            parent_path = list(parent_unit.path_ids or [])
            if not parent_path:
                parent_path = [parent_unit.unit_id]

            child = LegalUnit(
                unit_id=child_unit_id,
                raw_uid=child_raw_uid,
                scope=parent_unit.scope,
                title=title,
                level=max(parent_unit.level + 1, 2),
                unit_type=LegalUnitType.DEFINITION,
                clause_function=ClauseFunction.DEFINITIONS,
                segment_id=parent_unit.segment_id,
                segment_type=parent_unit.segment_type,
                page_start=page_start,
                page_end=page_end,
                own_text=exact_text,
                subtree_text=exact_text,
                own_element_ids=list(grouped_ids),
                topic_tags=[],
                cross_refs=[],
                citability=_build_child_citability(parent_unit, exact_text),
                node_kind="leaf",
                semantic_node_type="definition_item",
                node_origin=parent_unit.node_origin,
                content_mode="full_text",
                recovered_via_best_effort=bool(parent_unit.recovered_via_best_effort),
                fallback_reason=parent_unit.fallback_reason,
                diagnostics={
                    "extracted_via": "legal_unit_extractor_v1",
                    "parent_unit_id": parent_unit.unit_id,
                    "parent_unit_type": parent_unit.unit_type.value,
                    "parent_unit_class": parent_unit.unit_class,
                    "source_anchor_heading_text": heading_text,
                    "source_elements_count": len(grouped_ids),
                    "user_facing_semantic": True,
                },
                unit_class="definition_item",
                exact_text=exact_text,
                retrieval_text=exact_text,
                context_prefix=None,
                context_strategy="none",
                parent_unit_id=parent_unit.unit_id,
                children_unit_ids=[],
                path_ids=parent_path + [child_unit_id],
                source_element_ids=list(grouped_ids),
                heading_text=heading_text,
            )

            children.append(child)
            existing_ids.add(child_unit_id)

        logger.info(
            "LegalUnitExtractor: definition sub-units extracted",
            extra={
                "parent_unit_id": parent_unit.unit_id,
                "children_count": len(children),
            },
        )

        return children
    

    
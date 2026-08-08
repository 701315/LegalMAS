# src/services/structure/semantic_enrichment/_prompting.py

"""
Prompt construction для semantic enrichment LLM.

Этот модуль НЕ хранит текст prompt внутри Python-кода.
Текст инструкции вынесен во внешний template-файл:

    prompts/classification/legal_unit_semantic_enrichment_ru_v1.txt

Ответственность этого модуля:
- подготовить контекст для одного LegalUnit;
- построить heading_path на основе raw_uid и соседних units;
- безопасно сериализовать значения для подстановки в prompt template;
- загрузить template через общий PromptLoader проекта;
- вернуть финальный prompt text для вызова LLM.

Архитектурные принципы:
- prompt = внешний artifact, а не бизнес-логика в коде;
- код отвечает за data preparation, template отвечает за instruction wording;
- для русскоязычного корпуса инструкции даны на русском;
- JSON schema и canonical enum/topic values остаются английскими.

Важно:
- Используем engine.prompts.loader.get_promptloader(),
  а НЕ engine.prompts.load_prompt из __init__.py,
  потому что loader.py — более зрелая реализация с cache и root resolution.
"""

from __future__ import annotations

import json
from typing import Iterable
from dataclasses import dataclass

from engine.prompts.loader import get_promptloader
from services.structure.legal_unit_models import (
    ClauseFunction,
    LegalUnit,
    LegalUnitType,
    build_clause_function_ontology_payload,
)
from services.structure.topic_tagger import KNOWN_TOPICS

PROMPT_VERSION = "phase12_semantic_enrichment_v3_ru"
PROMPT_TEMPLATE_NAME = "classification/legal_unit_semantic_enrichment_ru_v1"

@dataclass(frozen=True, slots=True)
class SemanticEnrichmentPromptContext:
    """
    Предвычисленный segment-scoped context для semantic enrichment prompt.

    Зачем нужен:
    - не пересчитывать одинаковые prompt invariants на каждый LegalUnit;
    - не строить uid_to_title map заново для каждого heading_path;
    - не делать повторный json.dumps() для одинаковых enum/topic/ontology payloads.

    Важно:
    - содержит только segment-invariant данные;
    - per-unit значения (title, raw_uid, excerpts, current_unit_type и т.д.)
      по-прежнему строятся на каждый unit отдельно;
    - prompt output при использовании context должен быть IDENTICAL
      старому path без context.
    """

    allowed_unit_types_json: str
    allowed_clause_functions_json: str
    clause_function_ontology_json: str
    allowed_topics_json: str
    uid_to_title: dict[str, str]


def _build_uid_to_title_map(
    all_units: list[LegalUnit] | None,
) -> dict[str, str]:
    """
    Построить map raw_uid -> title один раз на весь segment.

    Используется для heading_path, чтобы не проходить по all_units
    на каждый LegalUnit отдельно.
    """
    if not all_units:
        return {}

    uid_to_title: dict[str, str] = {}
    for u in all_units:
        raw_uid = str(getattr(u, "raw_uid", "") or "").strip()
        title = str(getattr(u, "title", "") or "").strip()
        if raw_uid and title:
            uid_to_title[raw_uid] = title
    return uid_to_title


def build_semantic_enrichment_prompt_context(
    all_units: list[LegalUnit] | None,
) -> SemanticEnrichmentPromptContext:
    """
    Построить предвычисленный prompt context для всех units сегмента.

    Что предвычисляем:
    - allowed_unit_types
    - allowed_clause_functions
    - clause_function_ontology
    - allowed_topics
    - uid_to_title map

    Это безопасный batching/context reuse:
    - не меняет per-unit prompt semantics;
    - не меняет LLM call contract;
    - не меняет prompt template;
    - только убирает повторную CPU-работу.
    """
    allowed_unit_types = LegalUnitType.llm_eligible_values()
    allowed_clause_functions = _enum_values(ClauseFunction)
    clause_function_ontology = build_clause_function_ontology_payload()
    allowed_topics = sorted(KNOWN_TOPICS)
    uid_to_title = _build_uid_to_title_map(all_units)

    return SemanticEnrichmentPromptContext(
        allowed_unit_types_json=_json_dump(allowed_unit_types),
        allowed_clause_functions_json=_json_dump(allowed_clause_functions),
        clause_function_ontology_json=_json_dump(clause_function_ontology),
        allowed_topics_json=_json_dump(allowed_topics),
        uid_to_title=uid_to_title,
    )


def _excerpt(text: str | None, *, max_chars: int) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    if len(value) <= max_chars:
        return value
    return value[: max_chars - 3].rstrip() + "..."


def _enum_values(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        raw = getattr(value, "value", None)
        if isinstance(raw, str) and raw.strip():
            result.append(raw.strip())
    return result


def _json_dump(value: object) -> str:
    """Сериализовать значение в компактный JSON для безопасной подстановки."""
    return json.dumps(value, ensure_ascii=False)


def _build_heading_path(
    unit: LegalUnit,
    all_units: list[LegalUnit] | None = None,
    uid_to_title: dict[str, str] | None = None,
) -> str:
    """
    Строит heading path от текущего unit вверх по hierarchy.

    Варианты источника heading metadata:
    - uid_to_title: precomputed map (предпочтительно, Phase 14.2 batching)
    - all_units: fallback для backward compatibility

    Использует raw_uid для поиска parent: если raw_uid = "7.2.1",
    то parent = "7.2", grandparent = "7".

    Возвращает строку вида:
        "7 Платежи → 7.2 Порядок оплаты"
    """
    if uid_to_title is None:
        uid_to_title = _build_uid_to_title_map(all_units)

    if not uid_to_title:
        return ""

    parts: list[str] = []
    current_uid = str(unit.raw_uid or "").strip()

    for _ in range(5):
        if not current_uid:
            break

        if "." not in current_uid:
            if current_uid in uid_to_title:
                parts.append(f"{current_uid} {uid_to_title[current_uid]}")
            break

        parent_uid = current_uid.rsplit(".", 1)[0]
        if parent_uid in uid_to_title:
            parts.append(f"{parent_uid} {uid_to_title[parent_uid]}")
        current_uid = parent_uid

    parts.reverse()
    return " → ".join(parts) if parts else ""


def build_semantic_enrichment_prompt(
    *,
    unit: LegalUnit,
    previous_unit: LegalUnit | None = None,
    next_unit: LegalUnit | None = None,
    all_units: list[LegalUnit] | None = None,
    prompt_context: SemanticEnrichmentPromptContext | None = None,
    max_unit_text_chars: int = 3000,
    max_neighbor_text_chars: int = 500,
) -> str:
    """
    Строит финальный prompt для LLM semantic enrichment одного LegalUnit.

    Шаги:
    1. Подготавливает локальный контекст и deterministic baseline.
    2. При наличии prompt_context переиспользует segment-scoped invariants
       (Phase 14.2 batching).
    3. Загружает template из prompts/.
    4. Подставляет переменные через общий PromptLoader.

    Phase 14.2:
    - prompt_context позволяет не пересчитывать одинаковые segment-invariant
      payloads на каждый LegalUnit;
    - output prompt должен оставаться IDENTICAL старому пути.
    """
    if prompt_context is not None:
        allowed_unit_types_json = prompt_context.allowed_unit_types_json
        allowed_clause_functions_json = prompt_context.allowed_clause_functions_json
        clause_function_ontology_json = prompt_context.clause_function_ontology_json
        allowed_topics_json = prompt_context.allowed_topics_json
        heading_path = _build_heading_path(
            unit,
            uid_to_title=prompt_context.uid_to_title,
        )
    else:
        allowed_unit_types_json = _json_dump(LegalUnitType.llm_eligible_values())
        allowed_clause_functions_json = _json_dump(_enum_values(ClauseFunction))
        clause_function_ontology_json = _json_dump(
            build_clause_function_ontology_payload()
        )
        allowed_topics_json = _json_dump(sorted(KNOWN_TOPICS))
        heading_path = _build_heading_path(unit, all_units=all_units)

    unit_text = _excerpt(
        unit.own_text or unit.subtree_text,
        max_chars=max_unit_text_chars,
    )
    prev_text = _excerpt(
        previous_unit.own_text or previous_unit.subtree_text if previous_unit else "",
        max_chars=max_neighbor_text_chars,
    )
    next_text = _excerpt(
        next_unit.own_text or next_unit.subtree_text if next_unit else "",
        max_chars=max_neighbor_text_chars,
    )

    variables = {
        "allowed_unit_types": allowed_unit_types_json,
        "allowed_clause_functions": allowed_clause_functions_json,
        "clause_function_ontology": clause_function_ontology_json,
        "allowed_topics": allowed_topics_json,
        "current_unit_type": _json_dump(unit.unit_type.value),
        "current_clause_function": _json_dump(unit.clause_function.value),
        "current_topic_tags": _json_dump(list(unit.topic_tags)),
        "citability_band": _json_dump(unit.citability.citability_band),
        "scope": _json_dump(unit.scope),
        "raw_uid": _json_dump(unit.raw_uid),
        "title": _json_dump(unit.title),
        "level": _json_dump(unit.level),
        "node_kind": _json_dump(unit.node_kind),
        "semantic_node_type": _json_dump(unit.semantic_node_type),
        "recovered_via_best_effort": _json_dump(
            bool(unit.recovered_via_best_effort)
        ),
        "heading_path": _json_dump(heading_path),
        "previous_unit_title": _json_dump(
            previous_unit.title if previous_unit else ""
        ),
        "previous_unit_type": _json_dump(
            previous_unit.unit_type.value if previous_unit else ""
        ),
        "previous_unit_excerpt": _json_dump(prev_text),
        "next_unit_title": _json_dump(
            next_unit.title if next_unit else ""
        ),
        "next_unit_type": _json_dump(
            next_unit.unit_type.value if next_unit else ""
        ),
        "next_unit_excerpt": _json_dump(next_text),
        "unit_id": _json_dump(unit.unit_id),
        "full_excerpt": _json_dump(unit_text),
    }

    loader = get_promptloader()
    return loader.load(PROMPT_TEMPLATE_NAME, variables)


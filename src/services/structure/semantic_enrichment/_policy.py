# src/services/semantic_enrichment/_policy.py

"""
Conservative merge-policy для semantic enrichment.

Этот модуль решает главный вопрос Phase 12 / 12.1:
"Как безопасно объединить deterministic baseline и LLM proposal?"

Принципы policy:
1. Deterministic layer — база. LLM может дополнять, но не молча заменять.
2. Missing fields (UNKNOWN) можно заполнять при достаточной уверенности.
3. Topic tags можно расширять add-only (не удалять rule-based теги).
4. Override существующего unit_type / clause_function по умолчанию запрещён.
5. Если LLM не предложила ничего значимого — status = REJECTED или NO_CHANGE.
6. Все решения policy документируются в diagnostics для аудита.
7. Evidence quotes проверяются на grounding:
   если цитаты не находятся в тексте clause, доверие к proposal понижается.

Tiered approach:
- Tier A (fill missing):      confidence >= min_confidence_fill_missing
- Tier B (add topics):        confidence >= min_confidence_add_topics
- Tier C (override existing): confidence >= min_confidence_override_existing
                              AND policy.allow_override_existing_type = True

Безопасность:
- Topic tags фильтруются через KNOWN_TOPICS taxonomy.
- Неизвестные topics отклоняются и логируются.
- Clause function может автоматически выводиться из unit_type
  через deterministic default mapping.
- Evidence grounding проверяется только по exact substring matching
  внутри текста текущего unit.
"""

from __future__ import annotations

import re
from typing import Any

from services.structure.legal_unit_models import ClauseFunction, LegalUnit, LegalUnitType
from services.structure.semantic_enrichment._types import (
    LLMEnrichmentProposal,
    LegalUnitEnrichment,
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
)
from services.structure.topic_tagger import KNOWN_TOPICS

_DEFAULT_TYPE_TO_FUNCTION: dict[LegalUnitType, ClauseFunction] = {
    LegalUnitType.DEFINITION: ClauseFunction.DEFINITIONS,
    LegalUnitType.WARRANTY: ClauseFunction.REPRESENTATIONS,
    LegalUnitType.GOVERNING_LAW: ClauseFunction.BOILERPLATE,
    LegalUnitType.JURISDICTION: ClauseFunction.BOILERPLATE,
    LegalUnitType.NOTICE: ClauseFunction.BOILERPLATE,
    LegalUnitType.APPENDIX_REFERENCE: ClauseFunction.BOILERPLATE,
    LegalUnitType.DISPUTE_RESOLUTION: ClauseFunction.BOILERPLATE,
    LegalUnitType.GENERAL_PROVISION: ClauseFunction.BOILERPLATE,

    LegalUnitType.OBLIGATION: ClauseFunction.OBLIGATIONS,
    LegalUnitType.PAYMENT_TERM: ClauseFunction.OBLIGATIONS,
    LegalUnitType.CONFIDENTIALITY: ClauseFunction.OBLIGATIONS,

    LegalUnitType.INDEMNIFICATION: ClauseFunction.REMEDIES,
    LegalUnitType.TERMINATION_PROVISION: ClauseFunction.PROCEDURES,
    LegalUnitType.LIABILITY_PROVISION: ClauseFunction.LIMITATIONS,

    LegalUnitType.STRUCTURAL_ANCHOR: ClauseFunction.UNKNOWN,
    LegalUnitType.TECHNICAL_FRAGMENT: ClauseFunction.UNKNOWN,
}


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _get_unit_text(unit: LegalUnit) -> str:
    return _normalize_text(unit.own_text or unit.subtree_text or "")


def _normalize_topic_name(value: Any) -> str:
    text = _normalize_text(value).lower()
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9_ ]+", "_", text)
    text = re.sub(r"\s+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def _normalize_topics(
    topics: list[str],
    *,
    max_topics: int,
) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for raw_topic in topics:
        normalized = _normalize_topic_name(raw_topic)
        if not normalized:
            continue
        if normalized not in KNOWN_TOPICS:
            rejected.append(normalized)
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        accepted.append(normalized)

    accepted = accepted[:max_topics]
    rejected = sorted(set(rejected))
    return accepted, rejected


def _default_clause_function_for_type(unit_type: LegalUnitType) -> ClauseFunction:
    return _DEFAULT_TYPE_TO_FUNCTION.get(unit_type, ClauseFunction.UNKNOWN)


def _verify_evidence_grounding(
    evidence_quotes: list[str],
    unit_text: str,
) -> tuple[list[str], list[str], float]:
    """
    Проверяет что evidence quotes реально присутствуют в тексте unit.

    Возвращает:
    - grounded_quotes: цитаты найденные в тексте
    - ungrounded_quotes: цитаты НЕ найденные в тексте
    - grounding_ratio: доля подтверждённых цитат [0.0..1.0]
    """
    if not evidence_quotes:
        return [], [], 0.0

    normalized_text = unit_text.lower().strip()
    grounded: list[str] = []
    ungrounded: list[str] = []

    for quote in evidence_quotes:
        normalized_quote = quote.lower().strip()
        if not normalized_quote:
            continue
        if normalized_quote in normalized_text:
            grounded.append(quote)
        else:
            ungrounded.append(quote)

    total = len(grounded) + len(ungrounded)
    ratio = len(grounded) / total if total > 0 else 0.0

    return grounded, ungrounded, round(ratio, 3)


def _base_enrichment(
    unit: LegalUnit,
    *,
    status: SemanticEnrichmentStatus,
    decision_reason: str,
    policy_version: str,
    llm_proposal: LLMEnrichmentProposal | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> LegalUnitEnrichment:
    merged_diagnostics = {
        "policy_version": policy_version,
        **dict(diagnostics or {}),
    }

    return LegalUnitEnrichment(
        unit_id=unit.unit_id,
        status=status,
        base_unit_type=unit.unit_type,
        base_clause_function=unit.clause_function,
        base_topic_tags=list(unit.topic_tags),
        effective_unit_type=unit.unit_type,
        effective_clause_function=unit.clause_function,
        effective_topic_tags=list(unit.topic_tags),
        applied_fields=[],
        llm_proposal=llm_proposal,
        decision_reason=decision_reason,
        diagnostics=merged_diagnostics,
    )


# ---------------------------------------------------------------------------
# Deterministic source detection for already-classified skip
# ---------------------------------------------------------------------------

_DETERMINISTIC_SOURCES = frozenset({
    "title_pattern",
    "keyword_match",
    "rule_based",
    "default_mapping",
})

# Типы юнитов которые НЕ eligible для topic completion.
#
# Denylist вместо allowlist: исключаем только структурные артефакты парсинга,
# а не перечисляем разрешённые семантические типы.
#
# Логика:
# - STRUCTURAL_ANCHOR: heading-only узел без собственного текста
#   → нет смысла enriching topics, нет содержания для inference
# - TECHNICAL_FRAGMENT: технический fallback fragment
#   → не является юридической клаузой
# - UNKNOWN: тип ещё не определён
#   → сначала нужно определить тип, потом enriching topics
#
# Все остальные типы (DEFINITION, GOVERNING_LAW, JURISDICTION,
# GENERAL_PROVISION, APPENDIX_REFERENCE и т.д.) могут получать
# topic completion если у них пустые topics и достаточно длинный текст.
# Это универсально для всего поддерживаемого contract registry.
_TOPIC_COMPLETION_INELIGIBLE_TYPES = frozenset({
    LegalUnitType.STRUCTURAL_ANCHOR,
    LegalUnitType.TECHNICAL_FRAGMENT,
    LegalUnitType.UNKNOWN,
})

def _is_deterministic_source(unit: LegalUnit) -> bool:
    """
    Check if unit_type was assigned by a deterministic (non-LLM) classifier.

    Looks at unit.diagnostics["unit_type_source"].
    If the source is in the known deterministic set, returns True.
    If diagnostics are missing or source is unknown/LLM-based, returns False.
    """
    diagnostics = getattr(unit, "diagnostics", None) or {}
    source = diagnostics.get("unit_type_source", "")
    return source in _DETERMINISTIC_SOURCES

def _is_topic_completion_candidate(
    unit: LegalUnit,
    *,
    policy: "SemanticEnrichmentPolicy",
) -> bool:
    """
    Проверяет, нужна ли topic completion для deterministic unit.

    Topic completion path — это когда:
    - structural classification уже сделана deterministically;
    - но topic_tags пустые;
    - тип юнита НЕ входит в denylist неeligible types;
    - текст достаточно длинный для meaningful topic inference;
    - policy разрешает этот path.

    Использует denylist вместо allowlist:
    - запрещаем только структурные артефакты (STRUCTURAL_ANCHOR,
      TECHNICAL_FRAGMENT, UNKNOWN);
    - все остальные содержательные contract clause types могут
      получать topic completion если topics пустые.
    - универсально для всего supported contract registry.

    Возвращает True если unit должен пройти enrichment
    только ради topics, даже если type/function уже известны.
    """
    if not policy.allow_topic_completion_for_deterministic_units:
        return False

    if not _is_deterministic_source(unit):
        return False

    # Denylist: только структурные артефакты не eligible
    if unit.unit_type in _TOPIC_COMPLETION_INELIGIBLE_TYPES:
        return False

    if unit.topic_tags:
        # Topics уже есть — completion не нужна.
        return False

    text = _get_unit_text(unit)
    if len(text) < policy.min_text_chars_topic_completion:
        return False

    return True


def _is_unit_semantically_complete(
    unit: LegalUnit,
    *,
    policy: "SemanticEnrichmentPolicy",
) -> bool:
    """
    Проверяет, является ли unit семантически достаточным для пропуска enrichment.

    Unit semantically complete если:
    - structural classification завершена deterministically;
    - semantic gap отсутствует:
        * topics уже заполнены;
        * или тип не является topic-enrichable;
        * или policy не разрешает topic completion.

    Это основной predicate для нового skip reason
    'already_semantically_complete'.
    Заменяет старый грубый 'already_classified_by_rules'.
    """
    type_known = (
        unit.unit_type is not None
        and unit.unit_type != LegalUnitType.UNKNOWN
    )

    if not type_known:
        return False

    if not _is_deterministic_source(unit):
        return False

    function_known = (
        unit.clause_function is not None
        and unit.clause_function != ClauseFunction.UNKNOWN
    )

    if not function_known:
        derived = _default_clause_function_for_type(unit.unit_type)
        function_known = derived != ClauseFunction.UNKNOWN

    if not function_known:
        return False

    # Structural completeness есть. Проверяем semantic completeness.
    if _is_topic_completion_candidate(unit, policy=policy):
        # Есть semantic gap — topics пусты и тип enrichable.
        # Unit НЕ является semantically complete.
        return False

    return True

def is_unit_eligible_for_enrichment(
    unit: LegalUnit,
    *,
    policy: SemanticEnrichmentPolicy,
) -> tuple[bool, str | None]:
    """
    Проверяет, стоит ли отправлять LegalUnit в LLM enrichment.

    E1.2 — Tighter eligibility с возвратом semantic value.

    Eligibility logic:
    1. Жёсткие structural skip:
       - missing_unit_id, technical_fallback, heading_only, text_too_short.

    2. Type/function unknown → eligible (стандартный случай).

    3. Deterministic structurally complete units (type + function known):
       - Если topic completion candidate:
         topics пустые + enrichable type + текст достаточно длинный
         → eligible (topic completion path).
       - Если semantically complete:
         topics уже заполнены или тип не enrichable
         → skip as 'already_semantically_complete'.

    4. Non-deterministic source → eligible (type может быть переосмыслен LLM).

    Ключевое изменение от старой логики:
    - Убран грубый 'already_classified_by_rules'.
    - Введена semantic completeness как настоящий skip criterion.
    - Deterministic units с known type/function, но пустыми topics
      теперь могут проходить enrichment для topic completion.
    """
    if not unit.unit_id:
        return False, "missing_unit_id"

    unit_is_technical_fallback = bool(getattr(unit, "is_technical_fallback", False))
    if policy.skip_technical_fallback_units and unit_is_technical_fallback:
        return False, "technical_fallback"

    unit_is_heading_only = bool(getattr(unit, "is_heading_only", False))
    if policy.skip_heading_only_units and unit_is_heading_only:
        return False, "heading_only"

    text = _get_unit_text(unit)
    if len(text) < policy.min_text_chars:
        return False, "text_too_short"

    # E1.2: Semantic completeness check.
    if policy.skip_semantically_complete_units:
        if _is_unit_semantically_complete(unit, policy=policy):
            return False, "already_semantically_complete"

    return True, None


def explain_unit_enrichment_eligibility(
    unit: LegalUnit,
    *,
    policy: SemanticEnrichmentPolicy,
) -> str:
    """
    Объяснить, почему unit eligible или skipped для enrichment.

    Используется только для observability/telemetry:
    - не влияет на само решение policy;
    - помогает понять, какие классы unit'ов реально жгут LLM budget.

    Формат:
    - для skipped unit возвращает "skip:<reason>"
    - для eligible unit возвращает одну из reason-категорий:
        * type_unknown
        * type_known_non_deterministic_source
        * function_unknown_but_derivable
        * function_unknown_no_default_mapping
        * eligible_other
    """
    eligible, skip_reason = is_unit_eligible_for_enrichment(unit, policy=policy)
    if not eligible:
        return f"skip:{skip_reason or 'unknown'}"

    type_known = (
        unit.unit_type is not None
        and unit.unit_type != LegalUnitType.UNKNOWN
    )
    function_known = (
        unit.clause_function is not None
        and unit.clause_function != ClauseFunction.UNKNOWN
    )
    source_deterministic = _is_deterministic_source(unit)

    if not type_known:
        return "type_unknown"

    if type_known and not source_deterministic:
        return "type_known_non_deterministic_source"

    if type_known and not function_known:
        derived = _default_clause_function_for_type(unit.unit_type)
        if derived != ClauseFunction.UNKNOWN:
            return "function_unknown_but_derivable"
        return "function_unknown_no_default_mapping"

    # type + function known + deterministic source.
    # Check if eligible via topic completion path.
    if _is_topic_completion_candidate(unit, policy=policy):
        return "topic_completion_needed"

    return "eligible_other"


def build_skipped_enrichment(
    unit: LegalUnit,
    *,
    policy: SemanticEnrichmentPolicy,
    reason: str,
    diagnostics: dict[str, Any] | None = None,
) -> LegalUnitEnrichment:
    return _base_enrichment(
        unit,
        status=SemanticEnrichmentStatus.SKIPPED,
        decision_reason=reason,
        policy_version=policy.policy_version,
        diagnostics=diagnostics,
    )


def build_failed_enrichment(
    unit: LegalUnit,
    *,
    policy: SemanticEnrichmentPolicy,
    reason: str,
    llm_proposal: LLMEnrichmentProposal | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> LegalUnitEnrichment:
    return _base_enrichment(
        unit,
        status=SemanticEnrichmentStatus.FAILED,
        decision_reason=reason,
        policy_version=policy.policy_version,
        llm_proposal=llm_proposal,
        diagnostics=diagnostics,
    )


def apply_enrichment_policy(
    unit: LegalUnit,
    *,
    proposal: LLMEnrichmentProposal,
    policy: SemanticEnrichmentPolicy,
) -> LegalUnitEnrichment:
    """
    Применяет conservative merge-policy к LLM proposal.

    Правила:
    - missing fields можно заполнять при достаточной уверенности;
    - topic_tags можно расширять add-only;
    - override существующего unit_type / clause_function по умолчанию запрещён;
    - evidence grounding понижает effective confidence если цитаты
      не подтверждаются текстом;
    - если policy не приняла ни одно изменение, enrichment становится REJECTED
      или NO_CHANGE.
    """
    base_unit_type = unit.unit_type
    base_clause_function = unit.clause_function
    base_topics = list(unit.topic_tags)

    effective_unit_type = base_unit_type
    effective_clause_function = base_clause_function
    effective_topics = list(base_topics)

    applied_fields: list[str] = []
    notes: list[str] = []

    confidence = round(max(0.0, min(1.0, float(proposal.confidence or 0.0))), 3)

    suggested_unit_type = proposal.suggested_unit_type
    suggested_clause_function = proposal.suggested_clause_function

    normalized_topics, rejected_topics = _normalize_topics(
        proposal.suggested_topics,
        max_topics=policy.max_topics_from_llm,
    )

    # ── Evidence grounding ────────────────────────────────────────────────
    unit_text = _get_unit_text(unit)
    evidence_quotes = list(proposal.evidence_quotes or [])

    grounded_quotes, ungrounded_quotes, grounding_ratio = _verify_evidence_grounding(
        evidence_quotes,
        unit_text,
    )

    if evidence_quotes and grounding_ratio < 0.5:
        confidence = round(confidence * 0.7, 3)
        notes.append("low_evidence_grounding")

    has_meaningful_suggestion = False

    if suggested_unit_type is not None and suggested_unit_type != LegalUnitType.UNKNOWN:
        has_meaningful_suggestion = True

        if base_unit_type == LegalUnitType.UNKNOWN:
            # unit_type использует отдельный, более строгий порог.
            # unit_type — semantic identity юнита, влияет на routing
            # в retrieval и checks pipeline. Ошибка здесь системная.
            if confidence >= policy.min_confidence_fill_unit_type:
                effective_unit_type = suggested_unit_type
                applied_fields.append("unit_type")
            else:
                notes.append("unit_type_below_fill_unit_type_threshold")
        elif base_unit_type != suggested_unit_type:
            if (
                policy.allow_override_existing_type
                and confidence >= policy.min_confidence_override_existing
            ):
                effective_unit_type = suggested_unit_type
                applied_fields.append("unit_type_override")
            else:
                notes.append("unit_type_override_rejected")

    if suggested_clause_function is not None and suggested_clause_function != ClauseFunction.UNKNOWN:
        has_meaningful_suggestion = True

        if base_clause_function == ClauseFunction.UNKNOWN:
            if confidence >= policy.min_confidence_fill_missing:
                effective_clause_function = suggested_clause_function
                applied_fields.append("clause_function")
            else:
                notes.append("clause_function_below_fill_threshold")
        elif base_clause_function != suggested_clause_function:
            if (
                policy.allow_override_existing_clause_function
                and confidence >= policy.min_confidence_override_existing
            ):
                effective_clause_function = suggested_clause_function
                applied_fields.append("clause_function_override")
            else:
                notes.append("clause_function_override_rejected")

    if normalized_topics:
        has_meaningful_suggestion = True

        if confidence >= policy.min_confidence_add_topics:
            if not base_topics:
                effective_topics = list(normalized_topics)
                applied_fields.append("topic_tags")
            elif policy.allow_add_topics_to_existing:
                additions = sorted(
                    topic for topic in normalized_topics
                    if topic not in set(base_topics)
                )
                if additions:
                    effective_topics = list(base_topics) + additions
                    applied_fields.append("topic_tags")
            else:
                notes.append("topic_addition_disabled")
        else:
            notes.append("topics_below_add_threshold")

    if rejected_topics:
        notes.append("some_topics_rejected_by_taxonomy")

    # Если unit_type уже применился, а clause_function всё ещё UNKNOWN,
    # можно безопасно вывести default mapping.
    if (
        effective_clause_function == ClauseFunction.UNKNOWN
        and effective_unit_type != LegalUnitType.UNKNOWN
    ):
        derived_function = _default_clause_function_for_type(effective_unit_type)
        if derived_function != ClauseFunction.UNKNOWN:
            effective_clause_function = derived_function
            if (
                "clause_function" not in applied_fields
                and "clause_function_override" not in applied_fields
            ):
                applied_fields.append("clause_function")

    diagnostics = {
        "policy_version": policy.policy_version,
        "llm_confidence": confidence,
        "normalized_topics": list(normalized_topics),
        "rejected_topics": list(rejected_topics),
        "notes": list(notes),
        "reasoning_excerpt": _normalize_text(proposal.reasoning)[: policy.max_reasoning_chars],
        "evidence_quotes": list(evidence_quotes),
        "grounded_evidence_quotes": list(grounded_quotes),
        "ungrounded_evidence_quotes": list(ungrounded_quotes),
        "evidence_grounding_ratio": grounding_ratio,
    }

    if applied_fields:
        return LegalUnitEnrichment(
            unit_id=unit.unit_id,
            status=SemanticEnrichmentStatus.APPLIED,
            base_unit_type=base_unit_type,
            base_clause_function=base_clause_function,
            base_topic_tags=list(base_topics),
            effective_unit_type=effective_unit_type,
            effective_clause_function=effective_clause_function,
            effective_topic_tags=list(effective_topics),
            applied_fields=list(dict.fromkeys(applied_fields)),
            llm_proposal=proposal,
            decision_reason="fields_applied",
            diagnostics=diagnostics,
        )

    if not has_meaningful_suggestion:
        return LegalUnitEnrichment(
            unit_id=unit.unit_id,
            status=SemanticEnrichmentStatus.REJECTED,
            base_unit_type=base_unit_type,
            base_clause_function=base_clause_function,
            base_topic_tags=list(base_topics),
            effective_unit_type=base_unit_type,
            effective_clause_function=base_clause_function,
            effective_topic_tags=list(base_topics),
            applied_fields=[],
            llm_proposal=proposal,
            decision_reason="empty_or_unknown_proposal",
            diagnostics=diagnostics,
        )

    proposal_matches_base = (
        (suggested_unit_type is None or suggested_unit_type == base_unit_type)
        and (
            suggested_clause_function is None
            or suggested_clause_function == base_clause_function
        )
        and (not normalized_topics or set(normalized_topics).issubset(set(base_topics)))
    )

    if proposal_matches_base:
        return LegalUnitEnrichment(
            unit_id=unit.unit_id,
            status=SemanticEnrichmentStatus.NO_CHANGE,
            base_unit_type=base_unit_type,
            base_clause_function=base_clause_function,
            base_topic_tags=list(base_topics),
            effective_unit_type=base_unit_type,
            effective_clause_function=base_clause_function,
            effective_topic_tags=list(base_topics),
            applied_fields=[],
            llm_proposal=proposal,
            decision_reason="proposal_matches_base",
            diagnostics=diagnostics,
        )

    return LegalUnitEnrichment(
        unit_id=unit.unit_id,
        status=SemanticEnrichmentStatus.REJECTED,
        base_unit_type=base_unit_type,
        base_clause_function=base_clause_function,
        base_topic_tags=list(base_topics),
        effective_unit_type=base_unit_type,
        effective_clause_function=base_clause_function,
        effective_topic_tags=list(base_topics),
        applied_fields=[],
        llm_proposal=proposal,
        decision_reason="policy_rejected",
        diagnostics=diagnostics,
    )

def make_policy_from_settings() -> SemanticEnrichmentPolicy:
    """
    Создаёт SemanticEnrichmentPolicy из runtime settings.

    Позволяет настраивать поведение enrichment без правки кода:
    - SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL_UNIT_TYPE
    - SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL
    - SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_TOPICS
    - SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_OVERRIDE
    - SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_TYPE
    - SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_FUNCTION
    - SEMANTIC_ENRICHMENT_ALLOW_ADD_TOPICS
    - SEMANTIC_ENRICHMENT_MAX_TOPICS_FROM_LLM
    - SEMANTIC_ENRICHMENT_MIN_TEXT_CHARS
    """
    try:
        from core.config import settings

        return SemanticEnrichmentPolicy(
            min_confidence_fill_unit_type=float(
                getattr(
                    settings,
                    "SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL_UNIT_TYPE",
                    0.80,
                )
            ),
            min_confidence_fill_missing=float(
                getattr(settings, "SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_FILL", 0.72)
            ),
            min_confidence_add_topics=float(
                getattr(settings, "SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_TOPICS", 0.72)
            ),
            min_confidence_override_existing=float(
                getattr(settings, "SEMANTIC_ENRICHMENT_MIN_CONFIDENCE_OVERRIDE", 0.92)
            ),
            allow_override_existing_type=bool(
                getattr(settings, "SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_TYPE", False)
            ),
            allow_override_existing_clause_function=bool(
                getattr(settings, "SEMANTIC_ENRICHMENT_ALLOW_OVERRIDE_FUNCTION", False)
            ),
            allow_add_topics_to_existing=bool(
                getattr(settings, "SEMANTIC_ENRICHMENT_ALLOW_ADD_TOPICS", True)
            ),
            max_topics_from_llm=int(
                getattr(settings, "SEMANTIC_ENRICHMENT_MAX_TOPICS_FROM_LLM", 8)
            ),
            min_text_chars=int(
                getattr(settings, "SEMANTIC_ENRICHMENT_MIN_TEXT_CHARS", 40)
            ),
            skip_semantically_complete_units=bool(
                getattr(settings, "SEMANTIC_ENRICHMENT_SKIP_SEMANTICALLY_COMPLETE", True)
            ),
            allow_topic_completion_for_deterministic_units=bool(
                getattr(settings, "SEMANTIC_ENRICHMENT_ALLOW_TOPIC_COMPLETION", True)
            ),
            min_text_chars_topic_completion=int(
                getattr(
                    settings,
                    "SEMANTIC_ENRICHMENT_MIN_TEXT_CHARS_TOPIC_COMPLETION",
                    80,
                )
            ),
        )
    except Exception:
        return SemanticEnrichmentPolicy()
    
    

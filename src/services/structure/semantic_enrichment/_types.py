# src/services/semantic_enrichment/_types.py

"""
Data contracts для semantic enrichment pipeline.

Этот файл — canonical source of truth для всех типов Phase 12 / 12.1.
Он не зависит от LLM, HTTP, prompt templates или downstream consumers.

Основные модели:

SemanticEnrichmentStatus — статус обогащения для одного LegalUnit:
    APPLIED    — LLM предложила, policy одобрила, поля обновлены.
    NO_CHANGE  — LLM предложила то же что и baseline.
    REJECTED   — LLM предложила, но policy отклонила (низкая уверенность,
                 override запрещён, плохой grounding, или topics вне taxonomy).
    SKIPPED    — Unit не отправлялся в LLM (technical fallback, heading only,
                 короткий текст).
    FAILED     — Ошибка LLM (timeout, невалидный JSON, сетевая ошибка).

SemanticEnrichmentPolicy — конфигурация merge-policy:
    Определяет пороги уверенности, разрешения на override,
    максимум topics от LLM и другие параметры.

LLMEnrichmentProposal — нормализованное предложение от LLM:
    Ещё не финальное решение, а только proposal для policy layer.
    Содержит semantic labels, topics, confidence, reasoning
    и evidence quotes (цитаты из текста clause).

LegalUnitEnrichment — sidecar record для одного LegalUnit:
    Хранит base values, LLM proposal и effective values после policy.

LegalUnitsEnrichmentResult — segment-level sidecar artifact:
    Хранится рядом с LegalUnitsSnapshot, не заменяет его.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from services.structure.legal_unit_models import (
    ClauseFunction,
    LegalUnitType,
    normalize_clause_function_label,
)


class SemanticEnrichmentStatus(str, Enum):
    """
    Статус enrichment для одного LegalUnit.
    """

    APPLIED = "applied"
    NO_CHANGE = "no_change"
    REJECTED = "rejected"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SemanticEnrichmentPolicy:
    """
    Политика применения LLM-enrichment поверх deterministic semantic layer.

    Принципы:
    - deterministic layer остаётся базой;
    - LLM может заполнять пустоты;
    - LLM может add-only расширять topic_tags;
    - override существующего rule-based типа по умолчанию запрещён.
    """

    policy_version: str = "phase12_v1"

    # eligibility
    skip_technical_fallback_units: bool = True
    skip_heading_only_units: bool = True
    skip_semantically_complete_units: bool = True
    allow_topic_completion_for_deterministic_units: bool = True
    min_text_chars: int = 40
    min_text_chars_topic_completion: int = 80

    # thresholds
    min_confidence_fill_missing: float = 0.72
    min_confidence_add_topics: float = 0.72
    min_confidence_override_existing: float = 0.92

    # behavior
    allow_override_existing_type: bool = False
    allow_override_existing_clause_function: bool = False
    allow_add_topics_to_existing: bool = True
    max_topics_from_llm: int = 8

    # prompt / diagnostics
    max_reasoning_chars: int = 400


@dataclass(slots=True)
class LLMEnrichmentProposal:
    """
    Нормализованное предложение от LLM для одного LegalUnit.

    Это ещё не "истина", а только proposal.
    Финальное решение принимает policy layer.

    evidence_quotes:
    - 1-3 короткие точные цитаты из текста clause,
      на которых основано решение модели.
    - Используются для grounding verification в policy layer.
    """

    suggested_unit_type: LegalUnitType | None = None
    suggested_clause_function: ClauseFunction | None = None
    suggested_topics: list[str] = field(default_factory=list)
    confidence: float = 0.0
    reasoning: str = ""
    evidence_quotes: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suggested_unit_type": (
                self.suggested_unit_type.value if self.suggested_unit_type is not None else None
            ),
            "suggested_clause_function": (
                self.suggested_clause_function.value
                if self.suggested_clause_function is not None
                else None
            ),
            "suggested_topics": list(self.suggested_topics),
            "confidence": round(max(0.0, min(1.0, float(self.confidence or 0.0))), 3),
            "reasoning": self.reasoning,
            "evidence_quotes": list(self.evidence_quotes),
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(slots=True)
class LegalUnitEnrichment:
    """
    Sidecar enrichment record для одного LegalUnit.

    Хранит:
    - deterministic base values;
    - LLM proposal;
    - approved/effective values после policy.
    """

    unit_id: str
    status: SemanticEnrichmentStatus

    base_unit_type: LegalUnitType
    base_clause_function: ClauseFunction
    base_topic_tags: list[str] = field(default_factory=list)

    effective_unit_type: LegalUnitType = LegalUnitType.UNKNOWN
    effective_clause_function: ClauseFunction = ClauseFunction.UNKNOWN
    effective_topic_tags: list[str] = field(default_factory=list)

    applied_fields: list[str] = field(default_factory=list)
    llm_proposal: LLMEnrichmentProposal | None = None
    decision_reason: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "status": self.status.value,
            "base": {
                "unit_type": self.base_unit_type.value,
                "clause_function": self.base_clause_function.value,
                "topic_tags": list(self.base_topic_tags),
            },
            "effective": {
                "unit_type": self.effective_unit_type.value,
                "clause_function": self.effective_clause_function.value,
                "topic_tags": list(self.effective_topic_tags),
            },
            "applied_fields": list(self.applied_fields),
            "llm_proposal": self.llm_proposal.to_dict() if self.llm_proposal is not None else None,
            "decision_reason": self.decision_reason,
            "diagnostics": dict(self.diagnostics),
        }


@dataclass(slots=True)
class LegalUnitsEnrichmentResult:
    """
    Segment-level sidecar artifact для semantic enrichment.

    Важно:
    - НЕ заменяет LegalUnitsSnapshot;
    - хранится рядом с ним;
    - downstream может строить "effective projection" на основе этого sidecar.
    """

    document_id: str
    document_version_id: str
    segment_id: str
    segment_type: str
    segment_order: int
    is_primary_segment: bool

    schema_version: str = "1"
    policy_version: str = "phase12_v1"
    prompt_version: str = "phase12_semantic_enrichment_v3_ru"
    llm_provider: str | None = None
    llm_model: str | None = None

    enrichments: list[LegalUnitEnrichment] = field(default_factory=list)
    build_warnings: list[str] = field(default_factory=list)

    @property
    def by_unit_id(self) -> dict[str, LegalUnitEnrichment]:
        index: dict[str, LegalUnitEnrichment] = {}
        for enrichment in self.enrichments:
            if enrichment.unit_id and enrichment.unit_id not in index:
                index[enrichment.unit_id] = enrichment
        return index

    @property
    def status_counts(self) -> dict[str, int]:
        counts = Counter(enrichment.status.value for enrichment in self.enrichments)
        return dict(sorted(counts.items()))

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "policy_version": self.policy_version,
            "prompt_version": self.prompt_version,
            "document_id": self.document_id,
            "document_version_id": self.document_version_id,
            "segment": {
                "segment_id": self.segment_id,
                "segment_type": self.segment_type,
                "segment_order": self.segment_order,
                "is_primary_segment": self.is_primary_segment,
            },
            "llm": {
                "provider": self.llm_provider,
                "model": self.llm_model,
            },
            "stats": {
                "total_units": len(self.enrichments),
                "status_counts": self.status_counts,
                "build_warnings": list(self.build_warnings),
            },
            "enrichments": [enrichment.to_dict() for enrichment in self.enrichments],
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LegalUnitsEnrichmentResult":
        """
        Восстановить LegalUnitsEnrichmentResult из сериализованного dict.

        Используется в Phase 12.1.6 для загрузки enrichment sidecar из MinIO.
        Неизвестные поля игнорируются (forward-compatible).
        """
        segment = data.get("segment") or {}
        llm = data.get("llm") or {}
        stats = data.get("stats") or {}

        enrichments_raw = data.get("enrichments") or []
        enrichments = []
        for raw in enrichments_raw:
            if not isinstance(raw, dict):
                continue
            try:
                enrichments.append(_legal_unit_enrichment_from_dict(raw))
            except Exception:
                continue

        return cls(
            document_id=str(data.get("document_id") or ""),
            document_version_id=str(data.get("document_version_id") or ""),
            segment_id=str(segment.get("segment_id") or ""),
            segment_type=str(segment.get("segment_type") or "unknown"),
            segment_order=int(segment.get("segment_order") or 0),
            is_primary_segment=bool(segment.get("is_primary_segment", False)),
            schema_version=str(data.get("schema_version") or "1"),
            policy_version=str(data.get("policy_version") or "phase12_v1"),
            prompt_version=str(data.get("prompt_version") or ""),
            llm_provider=llm.get("provider"),
            llm_model=llm.get("model"),
            enrichments=enrichments,
            build_warnings=list(stats.get("build_warnings") or []),
        )

def _legal_unit_enrichment_from_dict(raw: dict[str, Any]) -> "LegalUnitEnrichment":
    """
    Вспомогательная функция для десериализации LegalUnitEnrichment из dict.

    Вынесена за пределы класса чтобы не нарушать frozen/slots контракт.
    """
    status_str = str(raw.get("status") or "skipped").lower()
    try:
        status = SemanticEnrichmentStatus(status_str)
    except ValueError:
        status = SemanticEnrichmentStatus.SKIPPED

    base = raw.get("base") or {}
    effective = raw.get("effective") or {}

    def _parse_unit_type(val: Any) -> LegalUnitType:
        try:
            return LegalUnitType(str(val or "unknown").lower())
        except ValueError:
            return LegalUnitType.UNKNOWN

    def _parse_clause_function(val: Any) -> ClauseFunction:
        normalized = normalize_clause_function_label(val)
        return normalized or ClauseFunction.UNKNOWN

    # Восстанавливаем LLM proposal если есть
    proposal_raw = raw.get("llm_proposal")
    llm_proposal = None
    if isinstance(proposal_raw, dict):
        llm_proposal = LLMEnrichmentProposal(
            suggested_unit_type=_parse_unit_type(proposal_raw.get("suggested_unit_type"))
            if proposal_raw.get("suggested_unit_type") is not None
            else None,
            suggested_clause_function=_parse_clause_function(
                proposal_raw.get("suggested_clause_function")
            )
            if proposal_raw.get("suggested_clause_function") is not None
            else None,
            suggested_topics=list(proposal_raw.get("suggested_topics") or []),
            confidence=float(proposal_raw.get("confidence") or 0.0),
            reasoning=str(proposal_raw.get("reasoning") or ""),
            evidence_quotes=list(proposal_raw.get("evidence_quotes") or []),
            diagnostics=dict(proposal_raw.get("diagnostics") or {}),
        )

    return LegalUnitEnrichment(
        unit_id=str(raw.get("unit_id") or ""),
        status=status,
        base_unit_type=_parse_unit_type(base.get("unit_type")),
        base_clause_function=_parse_clause_function(base.get("clause_function")),
        base_topic_tags=list(base.get("topic_tags") or []),
        effective_unit_type=_parse_unit_type(effective.get("unit_type")),
        effective_clause_function=_parse_clause_function(effective.get("clause_function")),
        effective_topic_tags=list(effective.get("topic_tags") or []),
        applied_fields=list(raw.get("applied_fields") or []),
        llm_proposal=llm_proposal,
        decision_reason=raw.get("decision_reason"),
        diagnostics=dict(raw.get("diagnostics") or {}),
    )

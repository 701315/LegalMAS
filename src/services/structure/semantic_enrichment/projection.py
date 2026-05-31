# src/services/structure/semantic_enrichment/projection.py

"""
Projection — построение effective enriched LegalUnit для downstream.

Этот модуль берёт:
- deterministic LegalUnitsSnapshot (baseline от LegalUnitBuilder);
- sidecar LegalUnitsEnrichmentResult (от LLM enricher);

и возвращает список LegalUnit, где approved enrichments
аккуратно применены поверх baseline.

Принципы:
- Deterministic snapshot НЕ мутируется.
- Для каждого unit создаётся shallow copy с обновлёнными полями.
- Только enrichments со статусом APPLIED изменяют поля.
- Все остальные статусы (SKIPPED, FAILED, REJECTED, NO_CHANGE)
  оставляют unit без изменений.
- Diagnostic metadata записывается в unit.diagnostics["llm_enrichment"].

Использование:
    snapshot = LegalUnitBuilder().build_from_clause_tree(...)
    enrichment = enrich_legal_units(snapshot)
    effective_units = project_enriched_units(snapshot, enrichment)
    bundle = EvidenceBundleBuilder().build(effective_units, profile)

EvidenceBundleBuilder не знает про LLM — он просто получает
более качественные topic_tags и unit_type.
"""

from __future__ import annotations

import copy
from typing import Any

from services.structure.legal_unit_models import LegalUnit, LegalUnitsSnapshot
from services.structure.semantic_enrichment._types import (
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentStatus,
)


def _build_enrichment_diagnostic(enrichment: LegalUnitEnrichment) -> dict[str, Any]:
    """Строит diagnostic блок для записи в unit.diagnostics."""
    diag: dict[str, Any] = {
        "enrichment_status": enrichment.status.value,
        "enrichment_applied_fields": list(enrichment.applied_fields),
    }

    if enrichment.llm_proposal is not None:
        diag["llm_confidence"] = enrichment.llm_proposal.confidence
        diag["llm_reasoning_excerpt"] = enrichment.llm_proposal.reasoning[:200]

    if enrichment.decision_reason:
        diag["enrichment_decision_reason"] = enrichment.decision_reason

    return diag


def project_single_unit(
    unit: LegalUnit,
    enrichment: LegalUnitEnrichment | None,
) -> LegalUnit:
    """
    Проецирует enrichment на один LegalUnit.

    Возвращает shallow copy unit-а с применёнными approved полями.
    Оригинальный unit НЕ мутируется.
    """
    projected = copy.copy(unit)

    projected.topic_tags = list(unit.topic_tags)
    projected.own_element_ids = list(unit.own_element_ids)
    projected.cross_refs = list(unit.cross_refs)
    projected.diagnostics = dict(unit.diagnostics)

    if enrichment is None:
        return projected

    projected.diagnostics["llm_enrichment"] = _build_enrichment_diagnostic(enrichment)

    if enrichment.status != SemanticEnrichmentStatus.APPLIED:
        return projected

    if "unit_type" in enrichment.applied_fields or "unit_type_override" in enrichment.applied_fields:
        projected.unit_type = enrichment.effective_unit_type

    if (
        "clause_function" in enrichment.applied_fields
        or "clause_function_override" in enrichment.applied_fields
    ):
        projected.clause_function = enrichment.effective_clause_function

    if "topic_tags" in enrichment.applied_fields:
        projected.topic_tags = list(enrichment.effective_topic_tags)

    return projected


def project_enriched_units(
    snapshot: LegalUnitsSnapshot,
    enrichment_result: LegalUnitsEnrichmentResult | None,
) -> list[LegalUnit]:
    """
    Строит effective enriched список LegalUnit для downstream.

    Если enrichment_result is None — возвращает копии оригинальных units
    без каких-либо изменений.
    """
    if enrichment_result is None:
        return [project_single_unit(unit, None) for unit in snapshot.units]

    enrichment_index = enrichment_result.by_unit_id

    result: list[LegalUnit] = []
    for unit in snapshot.units:
        enrichment = enrichment_index.get(unit.unit_id)
        projected = project_single_unit(unit, enrichment)
        result.append(projected)

    return result



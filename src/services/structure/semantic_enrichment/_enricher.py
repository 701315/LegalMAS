# src/services/structure/semantic_enrichment/_enricher.py

"""
Orchestrator для semantic enrichment всех LegalUnit в snapshot.

Этот модуль — главный координатор Phase 12.
Он обходит все LegalUnit в LegalUnitsSnapshot,
для каждого eligible unit:
1. Проверяет eligibility через policy.
2. Строит prompt с контекстом соседей.
3. Вызывает LLM.
4. Валидирует ответ.
5. Применяет merge-policy.
6. Сохраняет результат в sidecar artifact.

Принципы:
- Per-unit enrichment (один prompt на один unit).
- Failure-isolated: ошибка на одном unit не ломает остальные.
- Stateless: можно безопасно запускать параллельно для разных сегментов.
- Deterministic baseline никогда не мутируется — результат в sidecar.

Вызывается как postbuild layer:
    snapshot = LegalUnitBuilder().build_from_clause_tree(...)
    enrichment_result = enrich_legal_units(snapshot, policy=policy)
    effective_units = project_enriched_units(snapshot, enrichment_result)
"""

from __future__ import annotations

from typing import Any

from core.logging import get_logger
from services.structure.legal_unit_models import LegalUnit, LegalUnitsSnapshot
from services.structure.semantic_enrichment._llm_client import (
    call_semantic_enrichment_llm,
    is_semantic_enrichment_llm_available,
)
from services.structure.semantic_enrichment._policy import (
    apply_enrichment_policy,
    build_failed_enrichment,
    build_skipped_enrichment,
    is_unit_eligible_for_enrichment,
)
from services.structure.semantic_enrichment._prompting import (
    PROMPT_VERSION,
    build_semantic_enrichment_prompt,
)
from services.structure.semantic_enrichment._types import (
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentPolicy,
    SemanticEnrichmentStatus,
)
from services.structure.semantic_enrichment._validator import parse_llm_enrichment_response

logger = get_logger(__name__)


def _get_neighbor(
    units: list[LegalUnit],
    index: int,
    offset: int,
) -> LegalUnit | None:
    target = index + offset
    if 0 <= target < len(units):
        return units[target]
    return None


def _resolve_llm_info() -> tuple[str | None, str | None]:
    """Достаёт provider и model из settings для записи в sidecar."""
    try:
        from core.config import settings

        provider = str(getattr(settings, "STRUCTURE_LLM_PROVIDER", "") or "").strip() or None
        model = str(getattr(settings, "STRUCTURE_LLM_MODEL", "") or "").strip() or None
        return provider, model
    except Exception:
        return None, None


def enrich_single_unit(
    *,
    unit: LegalUnit,
    previous_unit: LegalUnit | None,
    next_unit: LegalUnit | None,
    all_units: list[LegalUnit] | None = None,
    policy: SemanticEnrichmentPolicy,
    document_id: str,
) -> LegalUnitEnrichment:
    """
    Обогащает один LegalUnit через LLM.

    Шаги:
    1. Проверка eligibility.
    2. Построение prompt.
    3. Вызов LLM.
    4. Валидация response.
    5. Применение policy.

    При любой ошибке — возвращает FAILED/SKIPPED enrichment
    с сохранением deterministic baseline.
    """
    eligible, skip_reason = is_unit_eligible_for_enrichment(unit, policy=policy)

    if not eligible:
        return build_skipped_enrichment(
            unit,
            policy=policy,
            reason=skip_reason or "not_eligible",
        )

    try:
        prompt = build_semantic_enrichment_prompt(
            unit=unit,
            previous_unit=previous_unit,
            next_unit=next_unit,
            all_units=all_units,
        )
    except Exception as exc:
        logger.warning(
            "STRUCTURE semantic_enrichment_prompt_build_failed",
            extra={
                "document_id": document_id,
                "unit_id": unit.unit_id,
                "error": str(exc),
            },
        )
        return build_failed_enrichment(
            unit,
            policy=policy,
            reason=f"prompt_build_failed: {exc}",
        )

    try:
        raw_response = call_semantic_enrichment_llm(prompt=prompt)
    except Exception as exc:
        logger.warning(
            "STRUCTURE semantic_enrichment_llm_call_failed",
            extra={
                "document_id": document_id,
                "unit_id": unit.unit_id,
                "error": str(exc),
            },
        )
        return build_failed_enrichment(
            unit,
            policy=policy,
            reason=f"llm_call_failed: {exc}",
        )

    proposal = parse_llm_enrichment_response(
        raw_response,
        max_reasoning_chars=policy.max_reasoning_chars,
    )

    if proposal is None:
        logger.warning(
            "STRUCTURE semantic_enrichment_invalid_response",
            extra={
                "document_id": document_id,
                "unit_id": unit.unit_id,
                "raw_response_excerpt": raw_response[:200] if raw_response else "",
            },
        )
        return build_failed_enrichment(
            unit,
            policy=policy,
            reason="invalid_llm_response",
            diagnostics={"raw_response_excerpt": raw_response[:200] if raw_response else ""},
        )

    enrichment = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    logger.debug(
        "STRUCTURE semantic_enrichment_unit_processed",
        extra={
            "document_id": document_id,
            "unit_id": unit.unit_id,
            "status": enrichment.status.value,
            "applied_fields": enrichment.applied_fields,
            "llm_confidence": proposal.confidence,
        },
    )

    return enrichment


def enrich_legal_units(
    snapshot: LegalUnitsSnapshot,
    *,
    policy: SemanticEnrichmentPolicy | None = None,
) -> LegalUnitsEnrichmentResult:
    """
    Обогащает все LegalUnit в snapshot через LLM.

    Это главная entry-point функция Phase 12.

    Preflight Gate:
    - Если LLM недоступна — все units сразу получают SKIPPED
      с reason="llm_unavailable", без попыток вызова.
    - Это предотвращает N бесполезных попыток вызова LLM
      при некорректной конфигурации.

    Возвращает sidecar artifact (LegalUnitsEnrichmentResult),
    который не заменяет snapshot, а дополняет его.
    """
    if policy is None:
        policy = SemanticEnrichmentPolicy()

    llm_provider, llm_model = _resolve_llm_info()

    result = LegalUnitsEnrichmentResult(
        document_id=snapshot.document_id,
        document_version_id=snapshot.document_version_id,
        segment_id=snapshot.segment_id,
        segment_type=snapshot.segment_type,
        segment_order=snapshot.segment_order,
        is_primary_segment=snapshot.is_primary_segment,
        schema_version="1",
        policy_version=policy.policy_version,
        prompt_version=PROMPT_VERSION,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )

    units = snapshot.units
    if not units:
        return result

    # ── Preflight Gate ────────────────────────────────────────────────
    # Проверяем доступность LLM один раз перед обходом всех units.
    # Если LLM недоступна — пропускаем enrichment для всего сегмента.
    llm_available = is_semantic_enrichment_llm_available()

    if not llm_available:
        logger.warning(
            "STRUCTURE semantic_enrichment_llm_unavailable_skipping_segment",
            extra={
                "document_id": snapshot.document_id,
                "segment_id": snapshot.segment_id,
                "total_units": len(units),
            },
        )
        result.build_warnings.append("llm_unavailable_all_units_skipped")

        for unit in units:
            result.enrichments.append(
                build_skipped_enrichment(
                    unit,
                    policy=policy,
                    reason="llm_unavailable",
                )
            )
        return result
    # ── End Preflight Gate ────────────────────────────────────────────

    logger.info(
        "STRUCTURE semantic_enrichment_start",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "policy_version": policy.policy_version,
            "llm_model": llm_model,
        },
    )

    for index, unit in enumerate(units):
        previous_unit = _get_neighbor(units, index, -1)
        next_unit = _get_neighbor(units, index, +1)

        try:
            enrichment = enrich_single_unit(
                unit=unit,
                previous_unit=previous_unit,
                next_unit=next_unit,
                all_units=units,
                policy=policy,
                document_id=snapshot.document_id,
            )
        except Exception as exc:
            logger.error(
                "STRUCTURE semantic_enrichment_unexpected_error",
                extra={
                    "document_id": snapshot.document_id,
                    "unit_id": unit.unit_id,
                    "error": str(exc),
                },
            )
            enrichment = build_failed_enrichment(
                unit,
                policy=policy,
                reason=f"unexpected_error: {exc}",
            )

        result.enrichments.append(enrichment)

    status_counts = result.status_counts

    logger.info(
        "STRUCTURE semantic_enrichment_complete",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "status_counts": status_counts,
            "llm_model": llm_model,
        },
    )

    return result


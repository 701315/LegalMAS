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

Phase 13.1 — Telemetry:
- enrich_legal_units() принимает опциональный collector;
- если collector передан — emit EnrichmentCompletedEvent после обхода;
- failure-isolated: ошибка emit не ломает enrichment pipeline.

Phase 14.2 — Prompt Context Batching:
- prompt_context строится один раз на snapshot;
- segment-scoped invariants переиспользуются всеми units.

Phase 14.3.A — Safe LLM Response Cache:
- exact-match cache только для semantic enrichment;
- cache key document_version-scoped;
- ключ строится по full prompt + provider + model + document_version_id;
- в cache попадают только raw responses, прошедшие validator;
- invalid/garbage responses не кэшируются.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import TYPE_CHECKING

from core.logging import get_logger
from services.structure.legal_unit_models import LegalUnit, LegalUnitsSnapshot
from services.structure.semantic_enrichment._cache import (
    get_semantic_enrichment_response_cache,
)
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
    SemanticEnrichmentPromptContext,
    build_semantic_enrichment_prompt,
    build_semantic_enrichment_prompt_context,
)
from services.structure.semantic_enrichment._types import (
    LegalUnitEnrichment,
    LegalUnitsEnrichmentResult,
    SemanticEnrichmentPolicy,
)
from services.structure.semantic_enrichment._validator import (
    parse_llm_enrichment_response,
)

if TYPE_CHECKING:
    from services.telemetry._collector import TelemetryCollector

logger = get_logger(__name__)

# Cache fingerprint schema version. Меняется если меняем смысл cache key.
_RESPONSE_CACHE_SCHEMA_VERSION = "phase14_3_semantic_enrichment_response_cache_v1"

# Должно соответствовать semantic_enrichment/_llm_client.py
_RESPONSE_CACHE_TEMPERATURE = 0.0
_RESPONSE_CACHE_MAX_TOKENS = 512


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
    """
    Достаёт provider и model из settings для записи в sidecar.

    Важно:
    Этот helper сохраняет legacy contract sidecar metadata.
    Для cache fingerprint ниже используется отдельный helper,
    который читает общий semantic enrichment provider path.
    """
    try:
        from core.config import settings

        provider = (
            str(getattr(settings, "STRUCTURE_LLM_PROVIDER", "") or "").strip() or None
        )
        model = (
            str(getattr(settings, "STRUCTURE_LLM_MODEL", "") or "").strip() or None
        )
        return provider, model
    except Exception:
        return None, None


def _resolve_semantic_enrichment_cache_identity() -> tuple[str | None, str | None]:
    """
    Достаёт provider/model именно из общего LLM path semantic enrichment.

    Почему отдельный helper:
    - semantic enrichment использует settings.LLM_PROVIDER и соответствующий model path;
    - sidecar metadata исторически пишет STRUCTURE_LLM_*;
    - для cache key нужен именно фактический provider/model semantic enrichment path.
    """
    try:
        from core.config import settings

        provider = str(getattr(settings, "LLM_PROVIDER", "") or "").strip() or None
        model: str | None = None

        if provider == "llamacpp":
            model = str(getattr(settings, "LLM_LOCAL_MODEL_PATH", "") or "").strip() or None
        elif provider == "ollama":
            model = str(getattr(settings, "LLM_OLLAMA_MODEL", "") or "").strip() or None
        elif provider == "openai":
            model = str(getattr(settings, "LLM_OPENAI_MODEL", "") or "").strip() or None

        return provider, model
    except Exception:
        return None, None


def _is_semantic_enrichment_cache_enabled() -> bool:
    """Проверка feature flag кэша."""
    try:
        from core.config import settings

        return bool(getattr(settings, "SEMANTIC_ENRICHMENT_CACHE_ENABLED", False))
    except Exception:
        return False


def _build_semantic_enrichment_cache_key(
    *,
    prompt: str,
    document_version_id: str | None,
) -> str | None:
    """
    Построить exact-match cache key для semantic enrichment raw response.

    Безопасность:
    - key document_version-scoped;
    - raw legal text не используется как открытый key;
    - key = sha256(serialized fingerprint payload).

    Если document_version_id отсутствует — cache bypass.
    Это осознанно: не допускаем случайный глобальный cross-document reuse.
    """
    if not _is_semantic_enrichment_cache_enabled():
        return None

    scope_id = str(document_version_id or "").strip()
    if not scope_id:
        logger.debug(
            "STRUCTURE semantic_enrichment_cache_bypass_missing_document_version_id"
        )
        return None

    provider, model = _resolve_semantic_enrichment_cache_identity()

    payload = {
        "schema_version": _RESPONSE_CACHE_SCHEMA_VERSION,
        "document_version_id": scope_id,
        "provider": provider,
        "model": model,
        "temperature": _RESPONSE_CACHE_TEMPERATURE,
        "max_tokens": _RESPONSE_CACHE_MAX_TOKENS,
        "prompt": prompt,
    }

    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _get_cached_semantic_enrichment_response(
    cache_key: str | None,
) -> str | None:
    """
    Прочитать raw response из cache.

    Возвращает None если:
    - cache disabled,
    - cache_key отсутствует,
    - entry не найдена / протухла.
    """
    if not cache_key:
        return None

    cache = get_semantic_enrichment_response_cache()
    return cache.get(cache_key)


def _store_cached_semantic_enrichment_response(
    *,
    cache_key: str | None,
    raw_response: str,
) -> None:
    """
    Сохранить raw response в cache.

    Вызывается ТОЛЬКО после успешной validator-проверки proposal.
    Invalid/garbage responses не кэшируются.
    """
    if not cache_key or not raw_response:
        return
    if not _is_semantic_enrichment_cache_enabled():
        return

    try:
        from core.config import settings

        ttl_seconds = int(
            max(1, int(getattr(settings, "SEMANTIC_ENRICHMENT_CACHE_TTL_SECONDS", 86400)))
        )
        max_items = int(
            max(1, int(getattr(settings, "SEMANTIC_ENRICHMENT_CACHE_MAX_ITEMS", 10000)))
        )

        cache = get_semantic_enrichment_response_cache()
        cache.set(
            cache_key,
            raw_response,
            ttl_seconds=ttl_seconds,
            max_items=max_items,
        )
    except Exception as exc:
        logger.debug(
            "STRUCTURE semantic_enrichment_cache_store_failed_non_critical",
            error=str(exc),
        )


def _emit_enrichment_telemetry(
    collector: "TelemetryCollector",
    result: LegalUnitsEnrichmentResult,
    *,
    llm_unavailable: bool,
) -> None:
    """
    Phase 13.1: emit EnrichmentCompletedEvent в collector.

    Failure-isolated: любая ошибка логируется и игнорируется.
    """
    try:
        from services.telemetry._events import EnrichmentCompletedEvent

        status_counts = result.status_counts
        total_units = len(result.enrichments)
        applied = status_counts.get("applied", 0)

        collector.emit(
            EnrichmentCompletedEvent(
                document_id=result.document_id,
                segment_id=result.segment_id,
                total_units=total_units,
                applied_count=applied,
                rejected_count=status_counts.get("rejected", 0),
                skipped_count=status_counts.get("skipped", 0),
                failed_count=status_counts.get("failed", 0),
                applied_ratio=round(applied / total_units, 4) if total_units > 0 else 0.0,
                llm_provider=result.llm_provider,
                llm_model=result.llm_model,
                policy_version=result.policy_version,
                llm_unavailable=llm_unavailable,
            )
        )
    except Exception as exc:
        logger.warning(
            "TELEMETRY enrichment_emit_failed",
            document_id=result.document_id,
            error=str(exc),
        )


def enrich_single_unit(
    *,
    unit: LegalUnit,
    previous_unit: LegalUnit | None,
    next_unit: LegalUnit | None,
    all_units: list[LegalUnit] | None = None,
    prompt_context: SemanticEnrichmentPromptContext | None = None,
    policy: SemanticEnrichmentPolicy,
    document_id: str,
    document_version_id: str | None = None,
) -> LegalUnitEnrichment:
    """
    Обогащает один LegalUnit через LLM.

    Шаги:
    1. Проверка eligibility.
    2. Построение prompt.
    3. Exact cache lookup (document_version-scoped).
    4. Вызов LLM если cache miss.
    5. Валидация response.
    6. Сохранение raw response в cache только если validator успешен.
    7. Применение policy.
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
            prompt_context=prompt_context,
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

    cache_key = _build_semantic_enrichment_cache_key(
        prompt=prompt,
        document_version_id=document_version_id,
    )
    raw_response = _get_cached_semantic_enrichment_response(cache_key)
    cache_hit = raw_response is not None

    if raw_response is None:
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
    else:
        logger.debug(
            "STRUCTURE semantic_enrichment_cache_hit",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "unit_id": unit.unit_id,
            },
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
                "cache_hit": cache_hit,
            },
        )
        return build_failed_enrichment(
            unit,
            policy=policy,
            reason="invalid_llm_response",
            diagnostics={"raw_response_excerpt": raw_response[:200] if raw_response else ""},
        )

    # Сохраняем только validator-approved responses.
    if not cache_hit:
        _store_cached_semantic_enrichment_response(
            cache_key=cache_key,
            raw_response=raw_response,
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
            "cache_hit": cache_hit,
        },
    )

    return enrichment


def enrich_legal_units(
    snapshot: LegalUnitsSnapshot,
    *,
    policy: SemanticEnrichmentPolicy | None = None,
    collector: "TelemetryCollector | None" = None,
) -> LegalUnitsEnrichmentResult:
    """
    Обогащает все LegalUnit в snapshot через LLM.

    Phase 14.2:
    - строит prompt_context один раз на snapshot.

    Phase 14.3.A:
    - exact cache document_version-scoped;
    - reuse только внутри одного document_version.
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

        if collector is not None:
            _emit_enrichment_telemetry(
                collector=collector,
                result=result,
                llm_unavailable=True,
            )

        return result

    logger.info(
        "STRUCTURE semantic_enrichment_start",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "policy_version": policy.policy_version,
            "llm_model": llm_model,
            "cache_enabled": _is_semantic_enrichment_cache_enabled(),
        },
    )

    # Phase 14.2: строим один раз на snapshot
    prompt_context = build_semantic_enrichment_prompt_context(units)

    for index, unit in enumerate(units):
        previous_unit = _get_neighbor(units, index, -1)
        next_unit = _get_neighbor(units, index, +1)

        try:
            enrichment = enrich_single_unit(
                unit=unit,
                previous_unit=previous_unit,
                next_unit=next_unit,
                all_units=units,
                prompt_context=prompt_context,
                policy=policy,
                document_id=snapshot.document_id,
                document_version_id=snapshot.document_version_id,
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

    logger.info(
        "STRUCTURE semantic_enrichment_complete",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "status_counts": result.status_counts,
            "llm_model": llm_model,
        },
    )

    if collector is not None:
        _emit_enrichment_telemetry(
            collector=collector,
            result=result,
            llm_unavailable=False,
        )

    return result


async def enrich_single_unit_async(
    *,
    unit: LegalUnit,
    previous_unit: LegalUnit | None,
    next_unit: LegalUnit | None,
    all_units: list[LegalUnit] | None = None,
    prompt_context: SemanticEnrichmentPromptContext | None = None,
    policy: SemanticEnrichmentPolicy,
    document_id: str,
    document_version_id: str | None = None,
) -> LegalUnitEnrichment:
    """
    Async версия enrich_single_unit().

    Поведение идентично sync path:
    - exact cache lookup
    - async LLM call только на cache miss
    - cache store только после validator success
    """
    from services.structure.semantic_enrichment._llm_client import (
        call_semantic_enrichment_llm_async,
    )

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
            prompt_context=prompt_context,
        )
    except Exception as exc:
        logger.warning(
            "STRUCTURE semantic_enrichment_prompt_build_failed (async)",
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

    cache_key = _build_semantic_enrichment_cache_key(
        prompt=prompt,
        document_version_id=document_version_id,
    )
    raw_response = _get_cached_semantic_enrichment_response(cache_key)
    cache_hit = raw_response is not None

    if raw_response is None:
        try:
            raw_response = await call_semantic_enrichment_llm_async(prompt=prompt)
        except Exception as exc:
            logger.warning(
                "STRUCTURE semantic_enrichment_llm_call_failed (async)",
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
    else:
        logger.debug(
            "STRUCTURE semantic_enrichment_cache_hit (async)",
            extra={
                "document_id": document_id,
                "document_version_id": document_version_id,
                "unit_id": unit.unit_id,
            },
        )

    proposal = parse_llm_enrichment_response(
        raw_response,
        max_reasoning_chars=policy.max_reasoning_chars,
    )

    if proposal is None:
        logger.warning(
            "STRUCTURE semantic_enrichment_invalid_response (async)",
            extra={
                "document_id": document_id,
                "unit_id": unit.unit_id,
                "raw_response_excerpt": raw_response[:200] if raw_response else "",
                "cache_hit": cache_hit,
            },
        )
        return build_failed_enrichment(
            unit,
            policy=policy,
            reason="invalid_llm_response",
            diagnostics={
                "raw_response_excerpt": raw_response[:200] if raw_response else ""
            },
        )

    if not cache_hit:
        _store_cached_semantic_enrichment_response(
            cache_key=cache_key,
            raw_response=raw_response,
        )

    enrichment = apply_enrichment_policy(unit, proposal=proposal, policy=policy)

    logger.debug(
        "STRUCTURE semantic_enrichment_unit_processed (async)",
        extra={
            "document_id": document_id,
            "unit_id": unit.unit_id,
            "status": enrichment.status.value,
            "applied_fields": enrichment.applied_fields,
            "llm_confidence": proposal.confidence,
            "cache_hit": cache_hit,
        },
    )

    return enrichment


async def enrich_legal_units_async(
    snapshot: LegalUnitsSnapshot,
    *,
    policy: SemanticEnrichmentPolicy | None = None,
    collector: "TelemetryCollector | None" = None,
) -> LegalUnitsEnrichmentResult:
    """
    Async версия enrich_legal_units().

    Phase 14.2:
    - один prompt_context на весь snapshot.

    Phase 14.3.A:
    - exact cache document_version-scoped;
    - reuse только внутри одного document_version.
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

    llm_available = is_semantic_enrichment_llm_available()

    if not llm_available:
        logger.warning(
            "STRUCTURE semantic_enrichment_llm_unavailable_skipping_segment (async)",
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

        if collector is not None:
            _emit_enrichment_telemetry(
                collector=collector,
                result=result,
                llm_unavailable=True,
            )

        return result

    logger.info(
        "STRUCTURE semantic_enrichment_start (async)",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "policy_version": policy.policy_version,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "cache_enabled": _is_semantic_enrichment_cache_enabled(),
        },
    )

    prompt_context = build_semantic_enrichment_prompt_context(units)

    async def _process_unit(index: int, unit: LegalUnit) -> LegalUnitEnrichment:
        previous_unit = _get_neighbor(units, index, -1)
        next_unit_item = _get_neighbor(units, index, +1)
        try:
            return await enrich_single_unit_async(
                unit=unit,
                previous_unit=previous_unit,
                next_unit=next_unit_item,
                all_units=units,
                prompt_context=prompt_context,
                policy=policy,
                document_id=snapshot.document_id,
                document_version_id=snapshot.document_version_id,
            )
        except Exception as exc:
            logger.error(
                "STRUCTURE semantic_enrichment_unexpected_error (async gather)",
                extra={
                    "document_id": snapshot.document_id,
                    "unit_id": unit.unit_id,
                    "error": str(exc),
                },
            )
            return build_failed_enrichment(
                unit,
                policy=policy,
                reason=f"unexpected_error: {exc}",
            )

    tasks = [_process_unit(i, unit) for i, unit in enumerate(units)]
    enrichments: list[LegalUnitEnrichment] = list(await asyncio.gather(*tasks))
    result.enrichments.extend(enrichments)

    logger.info(
        "STRUCTURE semantic_enrichment_complete (async)",
        extra={
            "document_id": snapshot.document_id,
            "segment_id": snapshot.segment_id,
            "total_units": len(units),
            "status_counts": result.status_counts,
            "llm_model": llm_model,
        },
    )

    if collector is not None:
        _emit_enrichment_telemetry(
            collector=collector,
            result=result,
            llm_unavailable=False,
        )

    return result



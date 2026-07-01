# src/engine/checks/result_normalizer.py

"""
Нормализация результатов проверок: маппинг DTO от CheckExecutor
на поля CheckResult + сохранение в БД.

Ответственность этого модуля:
- привести "сырой" exec_result к полям, пригодным для persistence;
- нормализовать structured_data;
- выделить technical/diagnostic quality_flags;
- сохранить provenance (page/clause/segment/citation anchors);
- определить execution_status + error_details.

Важно:
- здесь НЕ формируется canonical display semantics для UI;
  это делает отдельный слой result_semantics.py;
- здесь НЕ должны жить user-facing поля вроде user_status / user_message;
  если они случайно попали в raw/quality_flags из legacy path,
  мы их очищаем.
"""

from __future__ import annotations

from typing import Any

from core.constants import CheckExecutionStatus
from core.logging import get_logger

logger = get_logger(__name__)

# Legacy UI explanation keys, которые больше НЕ являются canonical частью quality_flags.
# В Spec v2 эти данные переезжают в отдельные поля CheckResult:
#   review_status, review_message, needs_manual_review.
_LEGACY_UI_KEYS = frozenset({
    "user_status",
    "user_message",
    "needs_manual_review",
})


def normalize_check_result(
    exec_result: dict,
    check,
) -> dict[str, Any]:
    """
    Нормализовать DTO от CheckExecutor под поля CheckResult.

    Что делаем здесь:
    - приводим "сырой" результат чека к полям, которые можно сохранять в CheckResult;
    - вытаскиваем evidence / quality_flags / structured_data;
    - аккуратно сохраняем provenance по segment'ам.

    ВАЖНО:
    - здесь мы не решаем финальный execution_status;
      это делает resolve_execution_status();
    - здесь мы не строим display_text / review_message;
      это делает result_semantics.py.
    """
    reason = exec_result.get("reason")
    evidence = exec_result.get("evidence") or ""
    detector_method = exec_result.get("detector_method")
    raw = exec_result.get("raw") or {}

    # value_text — secondary raw summary / legacy helper.
    # В Spec v2 он НЕ является canonical UI text.
    # Сохраняем старую semantics:
    #   если reason есть — берём reason,
    #   иначе — укороченный evidence.
    value_text = reason or (evidence[:500] if evidence else None)

    # evidence_ref — полная строка evidence.
    evidence_ref = evidence or None

    quality_flags: dict[str, Any] = {}
    if isinstance(raw, dict):
        source = raw.get("source")
        if source:
            quality_flags["source"] = source

        rules_conf = raw.get("rules_confidence")
        if rules_conf is not None:
            quality_flags["rules_confidence"] = rules_conf

        llm_conf = raw.get("llm_confidence")
        if llm_conf is not None:
            quality_flags["llm_confidence"] = llm_conf

        llm_error_type = raw.get("llm_error_type")
        if llm_error_type:
            quality_flags["llm_error_type"] = llm_error_type

        llm_required = raw.get("llm_required")
        if llm_required is not None:
            quality_flags["llm_required"] = bool(llm_required)

        llm_degraded = raw.get("llm_degraded")
        if llm_degraded is not None:
            quality_flags["llm_degraded"] = bool(llm_degraded)

        rules_llm_decision = raw.get("rules_llm_decision")
        if rules_llm_decision:
            quality_flags["rules_llm_decision"] = rules_llm_decision

        # ── Semantic enrichment quality flags ─────────────────────────────────
        # Written when executor had semantic_context available.
        # Absent when enrichment was not loaded (old behaviour preserved).
        _sem_used = raw.get("semantic_enrichment_used")
        if _sem_used is not None:
            quality_flags["enrichment_used"] = bool(_sem_used)

        _sem_seg_type = raw.get("semantic_segment_type")
        if _sem_seg_type:
            quality_flags["enrichment_segment_type"] = _sem_seg_type

        _sem_clause_funcs = raw.get("semantic_clause_functions")
        if _sem_clause_funcs:
            quality_flags["enrichment_clause_functions"] = _sem_clause_funcs
            quality_flags["enrichment_clause_match"] = True

        # Сохраняем raw целиком.
        # Это допустимо, потому что поле quality_flags в модели — JSONB.
        quality_flags["raw"] = raw

    # Structured data
    structured_data = _normalize_structured_data(exec_result.get("structured_data"))

    # Red flags extraction
    if structured_data:
        _extract_red_flags(structured_data, quality_flags)

    detector_method = exec_result.get("detector_method")
    if detector_method == "extraction_only" and structured_data:
        provenance = exec_result.get("provenance") or {}
        has_primary_provenance = any(
            provenance.get(k) is not None
            for k in ("chunk_id", "clause_uid", "page", "segment_id")
        )
        if not has_primary_provenance:
            quality_flags["missing_provenance"] = True


    # Conditional check info
    conditional = getattr(check, "conditional", None) if check is not None else None
    if isinstance(conditional, dict):
        is_conditional = bool(conditional)
        trigger_name = conditional.get("trigger")
    else:
        is_conditional = bool(conditional)
        trigger_name = getattr(conditional, "trigger", None) if conditional is not None else None

    check_origin = getattr(check, "origin", None) if check is not None else None

    # Segment provenance
    provenance_info = _extract_provenance(exec_result)

    # ── Anchor / citation fields ──────────────────────────────────────────────
    # Эти поля заполняются когда детектор использует legal units + citation resolver.
    # Для старых детекторов поля будут None.
    anchor_uid = exec_result.get("anchor_uid") or exec_result.get("clause_uid")
    anchor_title = exec_result.get("anchor_title")
    quoted_text = exec_result.get("quoted_text")
    quote_start_char = exec_result.get("quote_start_char")
    quote_end_char = exec_result.get("quote_end_char")
    source_unit_id = exec_result.get("source_unit_id")

    # Citation diagnostics в quality_flags.
    if anchor_uid and isinstance(quality_flags, dict):
        quality_flags["citation_anchor_uid"] = anchor_uid
        if quoted_text:
            quality_flags["citation_has_quote"] = True
        if source_unit_id:
            quality_flags["citation_source_unit_id"] = source_unit_id

    # ── Spec v2 cleanup: legacy user-facing keys НЕ должны жить в quality_flags ──
    _cleanup_legacy_ui_keys(quality_flags)

    return {
        "value_text": value_text,
        "evidence_ref": evidence_ref,
        "detector_used": detector_method,
        "quality_flags": quality_flags or None,
        "structured_data": structured_data,
        "conditional_check_triggered": is_conditional,
        "trigger_name": trigger_name,
        "origin": check_origin,
        # ── Existing anchor fields (backward-compatible) ───────────────────────
        "page": exec_result.get("page"),
        "clause_uid": exec_result.get("clause_uid"),
        "element_id": exec_result.get("element_id"),
        "context_trace": _normalize_context_trace(exec_result.get("context_trace")),
        # ── Citation anchor fields ─────────────────────────────────────────────
        "anchor_uid": anchor_uid,
        "anchor_title": anchor_title,
        "quoted_text": quoted_text,
        "quote_start_char": quote_start_char,
        "quote_end_char": quote_end_char,
        "source_unit_id": source_unit_id,
        **provenance_info,
    }


def resolve_execution_status(exec_result: dict) -> tuple[str, dict[str, Any] | None]:
    """
    Определить execution_status и error_details по результату CheckExecutor.

    Возвращает:
    - execution_status: одно из значений CheckExecutionStatus (как строка)
      PENDING / RUNNING / SUCCESS / FAILED / TIMEOUT
      (на практике здесь используем только SUCCESS / FAILED / TIMEOUT);
    - error_details: dict или None.

    ВАЖНО:
    - Пока не вводим новые execution_status вроде FAILED_LLM / TECHNICAL_FAILURE,
      потому что остальной pipeline (финализация run, метрики, счётчики completed checks)
      пока явно ожидает SUCCESS / FAILED / TIMEOUT.
    - Если внедрить новые статусы прямо сейчас, можно сломать завершение Run.
    """
    raw = exec_result.get("raw") or {}

    # Берём признаки как из верхнего уровня exec_result, так и из raw.
    llm_error_type = exec_result.get("llm_error_type") or (
        raw.get("llm_error_type") if isinstance(raw, dict) else None
    )

    llm_required = bool(
        exec_result.get("llm_required")
        if exec_result.get("llm_required") is not None
        else (raw.get("llm_required") if isinstance(raw, dict) else False)
    )

    llm_degraded = bool(
        exec_result.get("llm_degraded")
        if exec_result.get("llm_degraded") is not None
        else (raw.get("llm_degraded") if isinstance(raw, dict) else False)
    )

    rules_llm_decision = exec_result.get("rules_llm_decision") or (
        raw.get("rules_llm_decision") if isinstance(raw, dict) else None
    )

    execution_status = CheckExecutionStatus.SUCCESS.value
    error_details: dict[str, Any] | None = None

    if llm_required and llm_error_type:
        llm_error_type_str = str(llm_error_type).lower()

        if "timeout" in llm_error_type_str:
            execution_status = CheckExecutionStatus.TIMEOUT.value
        else:
            execution_status = CheckExecutionStatus.FAILED.value

        error_details = {
            "type": "llm_error",
            "llm_error_type": llm_error_type,
            "llm_required": llm_required,
            "llm_degraded": llm_degraded,
            "rules_llm_decision": rules_llm_decision,
        }

    return execution_status, error_details


def _normalize_structured_data(
    structured_data_raw: Any,
) -> dict[str, Any] | None:
    """
    Нормализовать structured_data из exec_result.

    Ожидаем dict формата:
    {
        "field_name": {"value": ...}
    }

    Если значение пришло не в таком формате, заворачиваем его в {"value": ...}.
    """
    if not isinstance(structured_data_raw, dict):
        return None

    structured_data: dict[str, Any] = {}
    for field_name, field_val in structured_data_raw.items():
        if isinstance(field_val, dict) and "value" in field_val:
            structured_data[field_name] = field_val
        else:
            structured_data[field_name] = {"value": field_val}

    return structured_data or None


def _extract_red_flags(
    structured_data: dict[str, Any],
    quality_flags: dict,
) -> None:
    """
    Извлечь red_flags из structured_data и добавить в quality_flags.
    """
    rf_payload = structured_data.get("red_flags")
    red_from_struct: Any | None = None

    if rf_payload is not None:
        if isinstance(rf_payload, dict):
            red_from_struct = rf_payload.get("value")
        else:
            red_from_struct = rf_payload

    codes: list[str] = []
    if red_from_struct:
        if isinstance(red_from_struct, str):
            codes = [c.strip() for c in red_from_struct.split(",") if c and c.strip()]
        elif isinstance(red_from_struct, list):
            codes = [str(c).strip() for c in red_from_struct if str(c).strip()]
        else:
            codes = [str(red_from_struct).strip()]

    if codes:
        existing = quality_flags.get("red_flags")
        if isinstance(existing, list):
            existing.extend(codes)
        elif isinstance(existing, str):
            merged = [e.strip() for e in existing.split(",") if e and e.strip()] + codes
            quality_flags["red_flags"] = merged
        elif existing is None:
            quality_flags["red_flags"] = codes


def _cleanup_legacy_ui_keys(quality_flags: dict[str, Any]) -> None:
    """
    Удалить legacy UI explanation keys из quality_flags.

    Spec v2:
    - user_status        -> review_status
    - user_message       -> review_message
    - needs_manual_review -> отдельное bool поле needs_manual_review

    Если эти ключи случайно попали в quality_flags или quality_flags["raw"]
    из старого/legacy path, они НЕ должны сохраняться как canonical данные.
    """
    if not isinstance(quality_flags, dict):
        return

    for key in _LEGACY_UI_KEYS:
        quality_flags.pop(key, None)

    raw = quality_flags.get("raw")
    if isinstance(raw, dict):
        for key in _LEGACY_UI_KEYS:
            raw.pop(key, None)


def _normalize_context_trace(raw_trace: Any) -> list[dict[str, Any]]:
    """
    Нормализовать retrieval provenance trace к стабильному canonical schema.

    Canonical item schema:
    {
        "rank": int | None,
        "score": float | None,
        "score_breakdown": dict | None,
        "chunk_id": str | None,
        "chunk_index": int | None,
        "clause_uid": str | None,
        "element_id": str | None,
        "page": int | None,
        "segment_id": str | None,
        "segment_type": str | None,
        "segment_title": str | None,
        "segment_order": int | None,
        "is_primary_segment": bool | None,
    }

    Важно:
    - не храним полный текст чанков в context_trace;
    - context_trace остаётся compact forensic/debug provenance.
    - schema стабильна независимо от upstream producer.
    """
    if not isinstance(raw_trace, list):
        return []

    normalized: list[dict[str, Any]] = []

    for idx, item in enumerate(raw_trace):
        if not isinstance(item, dict):
            continue

        normalized.append(
            {
                "rank": item.get("rank", idx),
                "score": item.get("score"),
                "score_breakdown": item.get("score_breakdown"),
                "chunk_id": item.get("chunk_id"),
                "chunk_index": item.get("chunk_index"),
                "clause_uid": item.get("clause_uid"),
                "element_id": item.get("element_id"),
                "page": item.get("page"),
                "segment_id": item.get("segment_id"),
                "segment_type": item.get("segment_type"),
                "segment_title": item.get("segment_title"),
                "segment_order": item.get("segment_order"),
                "is_primary_segment": item.get("is_primary_segment"),
            }
        )

    return normalized


def _extract_provenance(exec_result: dict) -> dict[str, Any]:
    """
    Извлечь canonical provenance из exec_result.

    Contract:
    - primary source: exec_result["provenance"]
    - fallback: top-level fields (для безопасности в рамках одного rollout)
    """
    provenance = exec_result.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}

    page = provenance.get("page", exec_result.get("page"))
    clause_uid = provenance.get("clause_uid", exec_result.get("clause_uid"))
    element_id = provenance.get("element_id", exec_result.get("element_id"))
    bbox = provenance.get("bbox", exec_result.get("bbox"))

    segment_id = provenance.get("segment_id", exec_result.get("segment_id"))
    segment_type = provenance.get("segment_type", exec_result.get("segment_type"))
    segment_title = provenance.get("segment_title", exec_result.get("segment_title"))
    segment_order = provenance.get("segment_order", exec_result.get("segment_order"))
    is_primary_segment = provenance.get("is_primary_segment", exec_result.get("is_primary_segment"))
    chunk_id = provenance.get("chunk_id", exec_result.get("chunk_id"))
    chunk_index = provenance.get("chunk_index", exec_result.get("chunk_index"))

    return {
        "page": page,
        "clause_uid": clause_uid,
        "element_id": element_id,
        "bbox": bbox,
        "segment_id": segment_id,
        "segment_type": segment_type,
        "segment_title": segment_title,
        "segment_order": segment_order,
        "is_primary_segment": is_primary_segment,
        "chunk_id": chunk_id,
        "chunk_index": chunk_index,
    }




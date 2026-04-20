# src/engine/checks/result_normalizer.py

"""
Нормализация результатов проверок: маппинг DTO от CheckExecutor
на поля CheckResult + сохранение в БД.
"""

from __future__ import annotations

from typing import Any

from core.constants import CheckExecutionStatus
from core.logging import get_logger

logger = get_logger(__name__)


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
    - это делает resolve_execution_status().
    """
    reason = exec_result.get("reason")
    evidence = exec_result.get("evidence") or ""
    detector_method = exec_result.get("detector_method")
    raw = exec_result.get("raw") or {}

    # value_text — это короткое объяснение.
    # Если reason нет, берём укороченный evidence.
    value_text = reason or (evidence[:500] if evidence else None)

    # evidence_ref — сохраняем полную строку evidence.
    # После миграции на TEXT это безопасно.
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

        # Сохраняем raw целиком.
        # Это допустимо, потому что поле quality_flags в модели — JSONB.
        quality_flags["raw"] = raw

    # Structured data
    structured_data = _normalize_structured_data(exec_result.get("structured_data"))

    # Red flags extraction
    if structured_data:
        _extract_red_flags(structured_data, quality_flags)

    # Conditional check info
    conditional = getattr(check, "conditional", None) if check is not None else None
    if isinstance(conditional, dict):
        is_conditional = bool(conditional)
        trigger_name = conditional.get("trigger")
    else:
        is_conditional = bool(conditional)
        trigger_name = (
            getattr(conditional, "trigger", None)
            if conditional is not None
            else None
        )

    check_origin = getattr(check, "origin", None) if check is not None else None

    # Segment provenance
    segment_info = _extract_segment_provenance(exec_result)

    return {
        "value_text": value_text,
        "evidence_ref": evidence_ref,
        "detector_used": detector_method,
        "quality_flags": quality_flags or None,
        "structured_data": structured_data,
        "conditional_check_triggered": is_conditional,
        "trigger_name": trigger_name,
        "origin": check_origin,
        "page": exec_result.get("page"),
        "clause_uid": exec_result.get("clause_uid"),
        "element_id": exec_result.get("element_id"),
        "bbox": exec_result.get("bbox"),
        **segment_info,
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
    # Это важно, потому что в реальном пайплайне часть LLM-диагностики
    # часто оказывается именно в raw.
    llm_error_type = (
        exec_result.get("llm_error_type")
        or (raw.get("llm_error_type") if isinstance(raw, dict) else None)
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

    rules_llm_decision = (
        exec_result.get("rules_llm_decision")
        or (raw.get("rules_llm_decision") if isinstance(raw, dict) else None)
    )

    # По умолчанию считаем, что check отработал успешно.
    execution_status = CheckExecutionStatus.SUCCESS.value
    error_details: dict[str, Any] | None = None

    # Если LLM был обязателен и реально произошла ошибка,
    # то это уже не SUCCESS.
    if llm_required and llm_error_type:
        llm_error_type_str = str(llm_error_type).lower()

        if "timeout" in llm_error_type_str:
            execution_status = CheckExecutionStatus.TIMEOUT.value
        else:
            # В текущей архитектуре используем только те terminal-статусы,
            # которые уже понимают run counters и finalize_run_if_finished.
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


def _extract_segment_provenance(exec_result: dict) -> dict[str, Any]:
    """
    Извлечь segment-aware информацию из exec_result.
    """
    segment_id = None
    segment_type = None
    segment_title = None
    segment_order = None
    is_primary_segment = None

    raw_segment = None
    if isinstance(exec_result.get("raw"), dict):
        raw_segment = exec_result["raw"].get("segment_provenance")

    if isinstance(raw_segment, dict):
        segment_id = raw_segment.get("segment_id") or None
        segment_type = raw_segment.get("segment_type") or None
        segment_title = raw_segment.get("segment_title") or None

        try:
            if raw_segment.get("segment_order") is not None:
                segment_order = int(raw_segment.get("segment_order"))
        except (TypeError, ValueError):
            segment_order = None

        is_primary_segment = raw_segment.get("is_primary_segment")
        if isinstance(is_primary_segment, str):
            is_primary_segment = is_primary_segment.strip().lower() in (
                "1",
                "true",
                "yes",
            )

    return {
        "segment_id": segment_id,
        "segment_type": segment_type,
        "segment_title": segment_title,
        "segment_order": segment_order,
        "is_primary_segment": is_primary_segment,
    }




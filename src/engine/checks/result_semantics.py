# src/engine/checks/result_semantics.py

"""
Canonical result semantics builder.

Единственное место во всём пайплайне, где формируется user-facing
display text и review semantics для результата проверки.

Архитектурная роль:
- Вызывается из result_saver сразу после normalize + resolve_execution_status.
- Получает на вход check definition, exec_result и structured_data.
- Возвращает immutable ResultSemantics с canonical display/review полями.
- Эти поля записываются в CheckResult и далее только проецируются
  через aggregator → MatrixCellDTO → frontend без переинтерпретации.

Принципы:
- Детерминированная чистая логика, без обращений к БД и ORM.
- Универсальность: работает для любого языка, типа документа и ui_mode.
- Graceful degradation: при отсутствии structured_data, evidence или check
  всегда возвращает осмысленный fallback.
- Никаких document-specific или check-specific хаков.

Приоритеты формирования display_text:
1. Factual extraction (structured_data) — для ЛЮБОГО result, включая unclear.
2. Meaningful evidence text.
3. Domain-specific outcome text (по result + ui_mode).
4. None — frontend использует review_status как fallback label.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.constants import CheckExecutionStatus
from core.logging import get_logger

logger = get_logger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

_NOT_FOUND_VALUES = frozenset({
    "not_found",
    "notfound",
    "not_defined",
    "missing",
    "absent",
    "not present",
    "none",
    "null",
    "",
    "n/a",
    "—",
    "не найдено",
    "не определено",
    "отсутствует",
    "данные не определены",
})

_RESERVED_METADATA_FIELDS = frozenset({
    "reason",
    "evidence",
    "explanation",
    "notes",
})

_TECHNICAL_FAILURE_STATUSES = frozenset({
    CheckExecutionStatus.FAILED.value,
    CheckExecutionStatus.TIMEOUT.value,
    CheckExecutionStatus.COMPUTE_FAILED.value,
    CheckExecutionStatus.PERSIST_FAILED.value,
})

# Evidence text shorter than this is not meaningful enough for display.
_MIN_EVIDENCE_LENGTH = 20

# Max length of evidence snippet used as display_text fallback.
_MAX_EVIDENCE_DISPLAY_LENGTH = 200


# ─── Result dataclass ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ResultSemantics:
    """
    Immutable canonical semantics of a check result.

    display_text:         Primary human-facing factual text for DD Grid cell.
                          None means frontend should use review_status label.
    machine_reason_code:  Internal machine reason (diagnostics only).
    review_status:        Canonical review workflow status.
    review_message:       Advisory explanation for lawyer (drawer/details only).
    needs_manual_review:  Explicit boolean for workflow filtering.
    """

    display_text: str | None
    machine_reason_code: str | None
    review_status: str
    review_message: str | None
    needs_manual_review: bool


# ─── Public API ───────────────────────────────────────────────────────────────


def build_canonical_result_semantics(
    *,
    check: Any | None,
    check_name: str | None = None,
    exec_result: dict,
    execution_status: str,
    structured_data: dict[str, Any] | None,
) -> ResultSemantics:
    """
    Build canonical display and review semantics for a check result.

    This is the single source of truth for how a check result is presented
    to the user. All downstream layers (aggregator, DD Matrix, frontend)
    must use these fields without reinterpretation.

    Args:
        check:            CheckDefinition or None (for not-applicable / legacy).
        check_name:       Explicit check name fallback when check is None.
        exec_result:      Raw result dict from CheckExecutor.
        execution_status: Technical execution status (CheckExecutionStatus value).
        structured_data:  Normalized structured_data from result_normalizer.
    """
    # ── A. Normalize inputs ───────────────────────────────────────────────────

    exec_result = exec_result or {}
    if not isinstance(structured_data, dict):
        structured_data = None

    result = str(exec_result.get("result") or "").strip().lower()
    severity = str(exec_result.get("severity") or "").strip().lower()
    ui_mode = _extract_ui_mode(check)
    resolved_check_name = _resolve_check_name(check, check_name, exec_result)

    # ── B. Machine reason ─────────────────────────────────────────────────────

    machine_reason_code = _extract_machine_reason(exec_result)

    # ── C. Review status ──────────────────────────────────────────────────────

    review_status = _derive_review_status(
        result=result,
        exec_result=exec_result,
        execution_status=execution_status,
    )

    # ── D. Display text ───────────────────────────────────────────────────────

    display_text = _build_display_text(
        check=check,
        check_name=resolved_check_name,
        ui_mode=ui_mode,
        result=result,
        severity=severity,
        exec_result=exec_result,
        execution_status=execution_status,
        structured_data=structured_data,
    )

    # ── E. Needs manual review ────────────────────────────────────────────────

    needs_manual_review = _derive_needs_manual_review(
        result=result,
        severity=severity,
        execution_status=execution_status,
        structured_data=structured_data,
        exec_result=exec_result,
    )

    # ── F. Review message ─────────────────────────────────────────────────────

    review_message = _build_review_message(
        check=check,
        exec_result=exec_result,
        execution_status=execution_status,
        structured_data=structured_data,
        review_status=review_status,
    )

    return ResultSemantics(
        display_text=display_text,
        machine_reason_code=machine_reason_code,
        review_status=review_status,
        review_message=review_message,
        needs_manual_review=needs_manual_review,
    )


# ─── Input normalization helpers ──────────────────────────────────────────────


def _extract_ui_mode(check: Any | None) -> str | None:
    """Extract and normalize ui_mode from check definition."""
    if check is None:
        return None
    raw = getattr(check, "ui_mode", None)
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    return normalized if normalized else None


def _has_any_extraction(check: Any | None) -> bool:
    """Return True if check has extraction enabled."""
    if check is None:
        return False

    extraction = getattr(check, "extraction", None)
    if extraction is None:
        return False

    return bool(getattr(extraction, "enabled", False))


def _resolve_check_name(
    check: Any | None,
    explicit_name: str | None,
    exec_result: dict,
) -> str | None:
    """
    Resolve human-readable check name with fallback chain:
    1. Explicit check_name parameter.
    2. check.name from CheckDefinition.
    3. exec_result["check_name"] from executor.
    """
    if explicit_name and explicit_name.strip():
        return explicit_name.strip()

    if check is not None:
        attr_name = getattr(check, "name", None)
        if attr_name and str(attr_name).strip():
            return str(attr_name).strip()

    from_exec = exec_result.get("check_name")
    if from_exec and str(from_exec).strip():
        return str(from_exec).strip()

    return None


# ─── Machine reason ──────────────────────────────────────────────────────────


def _is_machine_code(reason: str | None) -> bool:
    """
    Determine if a reason string is a machine-internal code vs human text.

    Machine codes are snake_case lowercase tokens without spaces,
    e.g. "rules_confident_positive", "llm_timeout".
    """
    if not reason:
        return True
    r = reason.strip()
    if not r:
        return True
    return "_" in r and " " not in r and r == r.lower()


def _extract_machine_reason(exec_result: dict) -> str | None:
    """Extract machine reason code if the reason looks like an internal code."""
    reason = exec_result.get("reason")
    if not isinstance(reason, str):
        return None
    reason = reason.strip()
    if reason and _is_machine_code(reason):
        return reason
    return None


# ─── Structured data inspection ──────────────────────────────────────────────


def _is_not_found_value(value: Any) -> bool:
    """Check if a single extracted value represents 'not found'."""
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in _NOT_FOUND_VALUES


def _extract_scalar_value(field_payload: Any) -> Any:
    """
    Extract scalar value from structured_data field payload.

    Normalized structured_data stores fields as:
        {"field_name": {"value": actual_value, ...}}
    This helper unwraps the {"value": ...} envelope.
    """
    if isinstance(field_payload, dict) and "value" in field_payload:
        return field_payload["value"]
    return field_payload


def _has_factual_extraction(structured_data: dict[str, Any] | None) -> bool:
    """
    Return True if structured_data contains at least one meaningful
    factual extracted value.
    """
    return bool(_iter_factual_fields(structured_data))


def _iter_factual_fields(
    structured_data: dict[str, Any] | None,
) -> list[tuple[str, Any]]:
    """
    Return list of (field_name, scalar_value) for meaningful extracted fields.

    Skips:
    - reserved metadata fields (reason/evidence/explanation/notes),
    - None / empty / explicit not-found markers.

    Preserves dict iteration order (insertion order in Python 3.7+).
    """
    if not structured_data:
        return []

    result: list[tuple[str, Any]] = []
    for field_name, field_payload in structured_data.items():
        if field_name in _RESERVED_METADATA_FIELDS:
            continue

        value = _extract_scalar_value(field_payload)
        if not _is_not_found_value(value):
            result.append((field_name, value))

    return result


# ─── Field label / unit resolution ───────────────────────────────────────────


def _humanize_field_name(field_name: str) -> str:
    """
    Convert snake_case field name to human-readable label.

    Examples:
        governing_law       → Governing law
        termination_notice   → Termination notice
    """
    return field_name.replace("_", " ").strip().capitalize()


def _find_extraction_field_config(check: Any | None, field_name: str) -> Any | None:
    """
    Find ExtractionFieldConfig for a given field_name in check.extraction.fields.

    Returns None if check has no extraction config or field not found.
    """
    if check is None:
        return None

    extraction = getattr(check, "extraction", None)
    if extraction is None:
        return None

    fields = getattr(extraction, "fields", None)
    if not isinstance(fields, list):
        return None

    for field_cfg in fields:
        if getattr(field_cfg, "name", None) == field_name:
            return field_cfg

    return None


def _get_field_label(check: Any | None, field_name: str) -> str:
    """
    Get human-readable label for an extraction field.

    Priority:
    1. ExtractionFieldConfig.description (if non-empty).
    2. Humanized field_name as fallback.
    """
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        description = getattr(field_cfg, "description", None)
        if description and str(description).strip():
            return str(description).strip()

    return _humanize_field_name(field_name)


def _get_field_unit(check: Any | None, field_name: str) -> str | None:
    """Get unit for an extraction field (e.g. 'days', 'RUB')."""
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        unit = getattr(field_cfg, "unit", None)
        if unit and str(unit).strip():
            return str(unit).strip()
    return None


def _get_field_priority(check: Any | None, field_name: str) -> int:
    """
    Get display priority for an extraction field.

    Fields listed earlier in ExtractionConfig.fields get lower index (higher priority).
    Unknown fields get a high fallback index.
    """
    if check is None:
        return 10_000

    extraction = getattr(check, "extraction", None)
    if extraction is None:
        return 10_000

    fields = getattr(extraction, "fields", None)
    if not isinstance(fields, list):
        return 10_000

    for idx, field_cfg in enumerate(fields):
        if getattr(field_cfg, "name", None) == field_name:
            return idx

    return 10_000


def _select_primary_factual_field(
    check: Any | None,
    structured_data: dict[str, Any] | None,
) -> tuple[str, Any] | None:
    """
    Select the most important factual field for display_text.

    Priority:
    1. *_display fields
    2. *_details fields
    3. everything else

    Inside each group, extraction config field order remains canonical priority.
    Returns (field_name, scalar_value) or None.
    """
    factual = _iter_factual_fields(structured_data)
    if not factual:
        return None

    def field_priority(pair: tuple[str, Any]) -> tuple[int, int]:
        field_name = pair[0]
        if field_name.endswith("_display"):
            return (0, _get_field_priority(check, field_name))
        if field_name.endswith("_details"):
            return (1, _get_field_priority(check, field_name))
        return (2, _get_field_priority(check, field_name))

    factual.sort(key=field_priority)
    return factual[0]


# ─── Value formatting ────────────────────────────────────────────────────────


def _format_display_value(value: Any, unit: str | None = None) -> str:
    """
    Format an extracted value for human display.

    Handles booleans, None, and appends unit if present.
    No locale-specific formatting — kept universal.
    """
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "Да" if value else "Нет"

    text = str(value).strip()
    if not text:
        return "—"

    if unit and not text.lower().endswith(unit.lower()):
        text = f"{text} {unit}"

    return text


# ─── Evidence inspection ─────────────────────────────────────────────────────


def _extract_meaningful_evidence(exec_result: dict) -> str | None:
    """
    Extract meaningful evidence text from exec_result.

    Returns None if evidence is:
    - empty or too short,
    - a machine code,
    - a technical error token.
    """
    evidence = str(exec_result.get("evidence") or "").strip()
    if not evidence:
        return None

    if len(evidence) < _MIN_EVIDENCE_LENGTH:
        return None

    if _is_machine_code(evidence):
        return None

    lower = evidence.lower()
    if lower in {"error", "timeout", "none", "null", "n/a"}:
        return None

    return evidence


# ─── Not-applicable detection ────────────────────────────────────────────────


def _is_not_applicable(exec_result: dict) -> bool:
    """Detect if the check was marked as not applicable."""
    reason = str(exec_result.get("reason") or "").strip().lower()
    if reason == "check_not_applicable":
        return True

    raw = exec_result.get("raw")
    if isinstance(raw, dict):
        raw_error = str(raw.get("error") or "").strip().lower()
        if raw_error == "check_not_applicable_for_document":
            return True

    return False


# ─── Display text builder ────────────────────────────────────────────────────


def _build_factual_display_text(
    *,
    check: Any | None,
    ui_mode: str | None,
    structured_data: dict[str, Any] | None,
) -> str | None:
    """
    Build factual display text from structured_data based on ui_mode.

    Returns None if no factual extraction is available.
    """
    if not _has_factual_extraction(structured_data):
        return None

    # clause_presence with factual data → simple confirmation
    if ui_mode == "clause_presence":
        return "Положение обнаружено"

    is_field_extraction_mode = (
        ui_mode == "field_extraction"
        or (ui_mode is None and _has_any_extraction(check))
    )

    if is_field_extraction_mode:
        # Step 1: canonical direct UI field
        for field_name, field_payload in structured_data.items():
            if field_name in _RESERVED_METADATA_FIELDS:
                continue
            if not field_name.endswith("_display"):
                continue

            value = _extract_scalar_value(field_payload)
            if not _is_not_found_value(value):
                return str(value).strip()

        # Step 2: fallback to best factual field
        primary = _select_primary_factual_field(check, structured_data)
        if primary is None:
            return None

        field_name, raw_value = primary
        logger.debug(
            "result_semantics: field_extraction display_text fallback to primary factual field",
            extra={
                "field_name": field_name,
                "ui_mode": ui_mode,
            },
        )
        label = _get_field_label(check, field_name)
        unit = _get_field_unit(check, field_name)
        value_str = _format_display_value(raw_value, unit)
        return f"{label}: {value_str}"

    # Existing logic for non-field-extraction modes
    primary = _select_primary_factual_field(check, structured_data)
    if primary is None:
        return None

    field_name, raw_value = primary
    label = _get_field_label(check, field_name)
    unit = _get_field_unit(check, field_name)
    value_str = _format_display_value(raw_value, unit)

    return f"{label}: {value_str}"


def _build_display_text(
    *,
    check: Any | None,
    check_name: str | None,
    ui_mode: str | None,
    result: str,
    severity: str,
    exec_result: dict,
    execution_status: str,
    structured_data: dict[str, Any] | None,
) -> str | None:
    """
    Build canonical display_text following priority chain.

    Priority:
    1. Technical failure / not applicable → None
    2. Factual extraction (for ANY result including unclear)
    3. Meaningful evidence text
    4. Domain-specific outcome text
    5. None (frontend uses review_status label)
    """
    # ── Priority 0: technical failure ─────────────────────────────────────────
    if execution_status in _TECHNICAL_FAILURE_STATUSES:
        return None

    # ── Priority 0b: not applicable ───────────────────────────────────────────
    if _is_not_applicable(exec_result):
        return None

    # ── Priority 1: factual extraction ────────────────────────────────────────
    factual_text = _build_factual_display_text(
        check=check,
        ui_mode=ui_mode,
        structured_data=structured_data,
    )
    if factual_text is not None:
        return factual_text

    # ── Priority 2: meaningful evidence ───────────────────────────────────────
    evidence = _extract_meaningful_evidence(exec_result)
    if evidence is not None:
        if len(evidence) > _MAX_EVIDENCE_DISPLAY_LENGTH:
            return evidence[:_MAX_EVIDENCE_DISPLAY_LENGTH - 1] + "…"
        return evidence

    # ── Priority 3: domain-specific outcomes ──────────────────────────────────

    if result == "missing_required_clause":
        return "Обязательное положение отсутствует"

    if result == "pass":
        if ui_mode == "clause_presence":
            return "Положение обнаружено"
        return "Признаков риска не обнаружено"

    if result == "fail":
        if check_name:
            return f"Обнаружено несоответствие: {check_name}"
        return "Обнаружено несоответствие"

    # ── Priority 4: unclear / unknown → None ──────────────────────────────────
    return None


# ─── Review status ────────────────────────────────────────────────────────────


def _derive_review_status(
    *,
    result: str,
    exec_result: dict,
    execution_status: str,
) -> str:
    """
    Derive canonical review workflow status.

    Returns one of:
        technical_failure, not_applicable, clause_missing,
        issue_detected, no_issue_detected,
        manual_review_required, unclear
    """
    if execution_status in _TECHNICAL_FAILURE_STATUSES:
        return "technical_failure"

    if _is_not_applicable(exec_result):
        return "not_applicable"

    if result == "missing_required_clause":
        return "clause_missing"

    if result == "fail":
        return "issue_detected"

    if result == "pass":
        return "no_issue_detected"

    if result == "unclear":
        llm_error = exec_result.get("llm_error_type") or (
            exec_result.get("raw", {}).get("llm_error_type")
            if isinstance(exec_result.get("raw"), dict)
            else None
        )
        if llm_error:
            return "manual_review_required"
        return "unclear"

    # Unknown result value — conservative fallback
    logger.warning(
        "result_semantics: unexpected result value, defaulting review_status to unclear",
        extra={"result": result, "execution_status": execution_status},
    )
    return "unclear"


# ─── Needs manual review ─────────────────────────────────────────────────────


def _derive_needs_manual_review(
    *,
    result: str,
    severity: str,
    execution_status: str,
    structured_data: dict[str, Any] | None,
    exec_result: dict,
) -> bool:
    """
    Determine if the check result needs manual lawyer review.

    True when:
    - Technical failure.
    - Unclear result.
    - Fail with critical/high severity but no factual extraction and no evidence.
    """
    # Technical failure → always needs review
    if execution_status in _TECHNICAL_FAILURE_STATUSES:
        return True

    # Not applicable → no review needed
    if _is_not_applicable(exec_result):
        return False

    # Unclear → always needs review
    if result == "unclear":
        return True

    # Pass / missing_required_clause → no review needed
    if result in ("pass", "missing_required_clause"):
        return False

    # Fail → depends on whether we have supporting data
    if result == "fail":
        has_fact = _has_factual_extraction(structured_data)
        has_evidence = _extract_meaningful_evidence(exec_result) is not None

        if has_fact or has_evidence:
            return False

        # No supporting data: critical/high need manual review
        return severity in ("critical", "high")

    # Unknown result → conservative
    return True


# ─── Review message ───────────────────────────────────────────────────────────

# Deterministic fallback messages by review_status.
# Used when build_user_explanation doesn't produce a useful message.
_REVIEW_MESSAGE_FALLBACKS: dict[str, str] = {
    "technical_failure": (
        "Проверка не завершена из-за технического ограничения. "
        "Рекомендуется ручной просмотр соответствующего раздела."
    ),
    "not_applicable": (
        "Проверка не применима к данному документу."
    ),
    "clause_missing": (
        "Система проверила релевантные фрагменты договора "
        "и не обнаружила требуемое положение."
    ),
    "issue_detected": (
        "Обнаружено условие, требующее правовой оценки. "
        "Проверьте соответствующий фрагмент договора."
    ),
    "no_issue_detected": (
        "По данной проверке признаков риска не обнаружено."
    ),
    "manual_review_required": (
        "Проверка не завершена надёжно. "
        "Рекомендуется ручной просмотр."
    ),
    "unclear": (
        "Система не смогла сделать достаточно надёжный вывод. "
        "Рекомендуется ручной просмотр."
    ),
}


def _build_review_message(
    *,
    check: Any | None,
    exec_result: dict,
    execution_status: str,
    structured_data: dict[str, Any] | None,
    review_status: str,
) -> str | None:
    """
    Build advisory review message for lawyer.

    Uses build_user_explanation as internal helper, with deterministic
    fallback messages by review_status.
    """
    # Import here to avoid circular dependency issues at module level.
    # build_user_explanation is a stable internal helper.
    from engine.checks.ui_explanation import build_user_explanation

    try:
        explanation = build_user_explanation(
            check=check,
            exec_result=exec_result,
            execution_status=execution_status,
            structured_data=structured_data,
        )
        message = explanation.get("user_message")
        if message and str(message).strip():
            return str(message).strip()
    except Exception:
        logger.debug(
            "result_semantics: build_user_explanation failed, using fallback",
            exc_info=True,
        )

    return _REVIEW_MESSAGE_FALLBACKS.get(review_status)



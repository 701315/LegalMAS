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

from core.config import settings
from core.constants import CheckExecutionStatus
from core.logging import get_logger

from engine.checks.extraction_semantics import (
    NOT_FOUND_VALUES as _NOT_FOUND_VALUES,
    RESERVED_METADATA_FIELDS as _RESERVED_METADATA_FIELDS,
    extract_scalar_value as _extract_scalar_value_shared,
    is_machine_code_token as _is_machine_code_shared,
    is_not_found_scalar as _is_not_found_value_shared,
    iter_meaningful_fields as _iter_meaningful_fields_shared,
)


logger = get_logger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

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
# Max number of explicitly selected factual fields combined into compact DD Grid summary.
_MAX_FACT_FIELDS_IN_DISPLAY = 3

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
        ui_mode=ui_mode,
        check=check,
        structured_data=structured_data,
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
        check=check,
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
    """Shared machine-code detector."""
    return _is_machine_code_shared(reason)


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
    """Shared not-found semantic predicate."""
    return _is_not_found_value_shared(value)


def _is_field_fallback_value(
    check: Any | None,
    field_name: str,
    value: Any,
) -> bool:
    """
    Display-only: True, если value — один из fallback_texts этого поля.

    Источник fallback_texts — ExtractionFieldConfig.fallback_texts
    (автопарсинг description или явный YAML override).

    Не влияет на gate semantics — is_not_found_scalar остаётся главным
    предикатом для presence_signal / iter_meaningful_fields.
    """
    if check is None or not isinstance(value, str):
        return False
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is None:
        return False
    fallback_texts = getattr(field_cfg, "fallback_texts", None) or []
    if not fallback_texts:
        return False
    normalized = value.strip()
    return any(normalized == str(t).strip() for t in fallback_texts)


def _count_meaningful_fact_fields(
    check: Any | None,
    structured_data: dict[str, Any] | None,
) -> tuple[int, int]:
    """
    Подсчитать meaningful fact-поля и общее число fact-полей check'а.

    Returns:
        (meaningful_count, total_fact_count)
        meaningful_count ∈ [0, total_fact_count]
        total_fact_count = 0 для legacy checks без fact/summary полей.

    Учитываются presentation ∈ {fact, summary}, не в _RESERVED_METADATA_FIELDS.
    meaningful = value не not_found и не в field_cfg.fallback_texts.

    Универсально: не зависит от check_id, doc_type, языка.
    """
    if check is None:
        return 0, 0
    extraction = getattr(check, "extraction", None)
    if extraction is None:
        return 0, 0

    fact_fields = [
        f for f in (getattr(extraction, "fields", None) or [])
        if (
            (getattr(f, "presentation", "fact") or "").strip().lower()
            in {"fact", "summary"}
            and getattr(f, "name", None) not in _RESERVED_METADATA_FIELDS
        )
    ]
    total = len(fact_fields)
    if total == 0:
        return 0, 0

    meaningful = 0
    sd = structured_data or {}
    for f in fact_fields:
        field_name = getattr(f, "name", None)
        if not field_name or field_name not in sd:
            continue
        value = _extract_scalar_value(sd[field_name])
        if _is_not_found_value(value):
            continue
        if _is_field_fallback_value(check, field_name, value):
            continue
        meaningful += 1

    return meaningful, total



def _extract_scalar_value(field_payload: Any) -> Any:
    """Shared scalar extractor for normalized structured_data fields."""
    return _extract_scalar_value_shared(field_payload)


def _has_factual_extraction(
    structured_data: dict[str, Any] | None,
    check: Any | None = None,
) -> bool:
    """
    Return True if structured_data contains at least one meaningful
    extracted value eligible for primary display.

    Includes fact, summary, and high-confidence signal fields.
    Excludes diagnostic fields and low-confidence signal fields.
    See _iter_factual_fields() for detailed evaluation rules.
    """
    return bool(_iter_factual_fields(structured_data, check=check))


def _iter_factual_fields(
    structured_data: dict[str, Any] | None,
    check: Any | None = None,
) -> list[tuple[str, Any]]:
    """
    Return meaningful extracted fields eligible for primary display.

    Uses one canonical semantic rule-set shared with CheckExecutor:
    fact/summary + high-confidence signal fields are displayable;
    diagnostic and not-found values are excluded.
    """
    meaningful = _iter_meaningful_fields_shared(
        structured_data,
        presentation_resolver=lambda field_name: _get_field_presentation(check, field_name),
    )
    return [(field_name, value) for field_name, value, _payload, _presentation in meaningful]


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
    1. ExtractionFieldConfig.label  — explicit UI label from YAML (always wins).
    2. humanize(field_name)         — deterministic fallback.

    Note: ExtractionFieldConfig.description is an extraction instruction,
    never a UI label. It is intentionally excluded from this resolution.
    """
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        label = getattr(field_cfg, "label", None)
        if label and str(label).strip():
            return str(label).strip()

    return _humanize_field_name(field_name)


def _get_field_presentation(check: Any | None, field_name: str) -> str:
    """
    Get presentation role for an extraction field.

    Returns one of: summary, fact, signal, diagnostic.
    Default is 'fact' when not specified (backward compatible).
    """
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        presentation = getattr(field_cfg, "presentation", None)
        if presentation and str(presentation).strip():
            return str(presentation).strip()
    return "fact"

def _is_grid_display_presentation(check: Any | None, field_name: str) -> bool:
    """
    Return True only for extraction fields that are safe for human DD Grid display.

    Grid / display_text must never expose internal signal or diagnostic fields,
    even if they are accidentally marked with display_in_grid=True.
    """
    presentation = _get_field_presentation(check, field_name)
    return presentation in {"fact", "summary"}

def _get_field_unit(check: Any | None, field_name: str) -> str | None:
    """Get unit for an extraction field (e.g. 'days', 'RUB')."""
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        unit = getattr(field_cfg, "unit", None)
        if unit and str(unit).strip():
            return str(unit).strip()
    return None


def _get_allowed_value_label(
    check: Any | None,
    field_name: str,
    value: Any,
) -> str | None:
    """
    Resolve human-readable label for enum-like extracted values.

    If field.allowed_values uses AllowedValueSpec(value, label),
    return label. Otherwise return None.
    """
    if value is None:
        return None

    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is None:
        return None

    allowed_values = getattr(field_cfg, "allowed_values", None) or []
    value_norm = str(value).strip().lower()

    for candidate in allowed_values:
        candidate_value = getattr(candidate, "value", candidate)
        candidate_label = getattr(candidate, "label", None)

        if str(candidate_value).strip().lower() == value_norm:
            if candidate_label and str(candidate_label).strip():
                return str(candidate_label).strip()
            return str(candidate_value).strip()

    return None


def _get_field_display_in_grid(check: Any | None, field_name: str) -> bool:
    """
    Return True if field is explicitly marked for compact DD Grid display.

    This is a playbook-driven universal contract.
    No guessing by field names, no document-specific logic.
    """
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is None:
        return False
    return bool(getattr(field_cfg, "display_in_grid", False))


def _get_field_display_priority(check: Any | None, field_name: str) -> int:
    """
    Resolve explicit DD Grid display priority for a field.

    Lower value = earlier in compact summary.
    If not configured, fall back to extraction field declaration order.
    """
    field_cfg = _find_extraction_field_config(check, field_name)
    if field_cfg is not None:
        priority = getattr(field_cfg, "display_priority", None)
        if isinstance(priority, int):
            return priority
    return _get_field_priority(check, field_name)


def _iter_grid_factual_fields(
    structured_data: dict[str, Any] | None,
    check: Any | None = None,
) -> list[tuple[str, Any]]:
    """
    Return meaningful factual fields explicitly marked for DD Grid display.

    Rules:
    - Only fields with display_in_grid=True are included.
    - Only human-displayable fields are allowed:
      presentation in {"fact", "summary"}.
    - signal/diagnostic fields are never included in compact DD Grid summary,
      even if misconfigured with display_in_grid=True.
    """
    factual = _iter_factual_fields(structured_data, check=check)
    if not factual:
        return []

    return [
        (field_name, value)
        for field_name, value in factual
        if _get_field_display_in_grid(check, field_name)
        and _is_grid_display_presentation(check, field_name)
        and not _is_field_fallback_value(check, field_name, value)
    ]


def _build_compact_grid_factual_summary(
    check: Any | None,
    structured_data: dict[str, Any] | None,
) -> str | None:
    """
    Build compact DD Grid summary from explicitly selected factual fields.

    Universal rules:
    - Uses only playbook-selected factual fields (display_in_grid=True).
    - Orders them by display_priority, then by extraction field order.
    - Joins first N fields into one compact line separated by '; '.

    If no fields are explicitly selected for grid display, returns None.
    """
    factual = _iter_grid_factual_fields(structured_data, check=check)
    if not factual:
        return None

    factual.sort(
        key=lambda pair: (
            _get_field_display_priority(check, pair[0]),
            _get_field_priority(check, pair[0]),
        )
    )

    parts: list[str] = []
    for field_name, raw_value in factual[:_MAX_FACT_FIELDS_IN_DISPLAY]:
        label = _get_field_label(check, field_name)
        unit = _get_field_unit(check, field_name)
        value_str = _format_display_value(check, field_name, raw_value, unit)
        parts.append(f"{label}: {value_str}")

    if not parts:
        return None

    return "; ".join(parts)


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

    Only fields with presentation in {"fact", "summary"} are eligible.
    signal/diagnostic fields are never used as primary display text.

    Inside each group, extraction config field order remains canonical priority.
    Returns (field_name, scalar_value) or None.
    """
    factual = [
        (field_name, value)
        for field_name, value in _iter_factual_fields(structured_data, check=check)
        if _is_grid_display_presentation(check, field_name)
        and not _is_field_fallback_value(check, field_name, value)
    ]
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


def _format_display_value(
    check: Any | None,
    field_name: str,
    value: Any,
    unit: str | None = None,
) -> str:
    """
    Format extracted value for human display.

    Enhancements:
    - resolves localized enum labels from AllowedValueSpec when available;
    - preserves old behavior for plain strings and booleans;
    - appends unit if needed.
    """
    if value is None:
        return "—"

    if isinstance(value, bool):
        return "Да" if value else "Нет"

    enum_label = _get_allowed_value_label(check, field_name, value)
    text = enum_label or str(value).strip()

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
    Build factual display text from structured_data.

    Priority:
    1. Field with presentation='summary' — ready-made cell text.
    2. Explicit compact DD Grid summary from display_in_grid=True fields,
       sorted by display_priority (deterministic — order independent of jsonb).
    3. Legacy *_display convention — backward compat for checks
       without display_in_grid=True fields.
    4. Legacy primary fact field — formatted as 'Label: Value'.

    Все приоритеты применяют fallback-фильтр: значения из
    field_cfg.fallback_texts пропускаются (это «данных нет», не факт).

    Fields with presentation='signal' or 'diagnostic' are never used
    as primary display text.

    Returns None if no displayable extraction is available.
    """
    if not structured_data:
        return None

    # clause_presence with factual data → simple confirmation
    if ui_mode == "clause_presence":
        if _has_factual_extraction(structured_data, check):
            return "Положение обнаружено"
        return None

    # Priority 1: summary field — единый агрегат, объявленный как presentation: summary.
    for field_name, field_payload in structured_data.items():
        if field_name in _RESERVED_METADATA_FIELDS:
            continue
        if _get_field_presentation(check, field_name) != "summary":
            continue
        value = _extract_scalar_value(field_payload)
        if _is_field_fallback_value(check, field_name, value):
            continue
        if not _is_not_found_value(value):
            return str(value).strip()

    # Priority 2: explicit compact DD Grid summary from display_in_grid=True
    # fields, sorted by display_priority.
    #
    # Это основной путь для playbook-driven checks. Детерминирован: порядок
    # полей задаётся конфигурацией (display_priority), а не порядком ключей
    # в structured_data (jsonb не сохраняет порядок).
    compact_summary = _build_compact_grid_factual_summary(check, structured_data)
    if compact_summary is not None:
        logger.debug(
            "result_semantics: display_text built from compact grid factual summary",
            extra={"ui_mode": ui_mode},
        )
        # Счётчик раскрытия — только для compact summary.
        # Показываем долю раскрытых fact-полей при частичном раскрытии.
        # Для legacy paths (Priority 3/4) префикс не применяется —
        # счётчик относится только к конфигурированным display_in_grid полям.
        if check is not None:
            meaningful, total = _count_meaningful_fact_fields(check, structured_data)
            if 0 < meaningful < total:
                return f"[{meaningful}/{total}] {compact_summary}"
        return compact_summary

    # Priority 3: *_display convention — legacy path для checks БЕЗ
    # display_in_grid=True полей. Итерируем по порядку ключей в
    # structured_data (jsonb — порядок неопределён, но для legacy это
    # приемлемо: у таких checks обычно одно-два *_display поля).
    for field_name, field_payload in structured_data.items():
        if field_name in _RESERVED_METADATA_FIELDS:
            continue
        if not field_name.endswith("_display"):
            continue
        if _get_field_presentation(check, field_name) in ("signal", "diagnostic"):
            continue
        value = _extract_scalar_value(field_payload)
        if _is_field_fallback_value(check, field_name, value):
            continue
        if not _is_not_found_value(value):
            return str(value).strip()

    # Priority 4: single primary fact field fallback
    primary = _select_primary_factual_field(check, structured_data)
    if primary is None:
        return None

    field_name, raw_value = primary
    logger.debug(
        "result_semantics: display_text fallback to primary fact field",
        extra={"field_name": field_name, "ui_mode": ui_mode},
    )
    label = _get_field_label(check, field_name)
    unit = _get_field_unit(check, field_name)
    value_str = _format_display_value(check, field_name, raw_value, unit)
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
    ui_mode: str | None = None,
    check: Any | None = None,
    structured_data: dict[str, Any] | None = None,
) -> str:
    """
    Derive canonical review workflow status.

    Returns one of:
        technical_failure, not_applicable,
        clause_missing, clause_defined, clause_partially_defined,
        issue_detected, no_issue_detected,
        manual_review_required, unclear

    field_extraction + pass:
        все fact-поля meaningful → clause_defined
        часть meaningful, часть fallback → clause_partially_defined
        (total=0, legacy checks) → no_issue_detected (старое поведение)

    clause_presence + pass:
        clause_defined (тема раскрыта).

    Остальные ui_mode → прежнее поведение.
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
        if ui_mode == "field_extraction" and check is not None:
            meaningful, total = _count_meaningful_fact_fields(check, structured_data)
            if total == 0:
                # Legacy checks без fact-полей — старое поведение.
                return "no_issue_detected"
            if meaningful == total:
                return "clause_defined"
            if meaningful > 0:
                return "clause_partially_defined"
            # meaningful == 0 при pass — fail-safe, не должно происходить.
            return "clause_missing"
        if ui_mode == "clause_presence":
            return "clause_defined"
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
    check: Any | None = None,
) -> bool:
    """
    Determine if the check result needs manual lawyer review.

    True when:
    - Technical failure.
    - Unclear result.
    - Fail with low confidence (below severity-adjusted threshold).
    - Fail with critical/high severity but no factual extraction and no evidence.

    Confidence thresholds (from config):
    - CONFIDENCE_MANUAL_REVIEW_THRESHOLD_HIGH_SEVERITY (0.65) for critical/high
    - CONFIDENCE_MANUAL_REVIEW_THRESHOLD (0.55) for medium/low
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

    # Fail → depends on confidence and supporting data
    if result == "fail":
        # Confidence-based check: low confidence fail → needs review
        # regardless of whether we have evidence or structured_data.
        # This is the key addition for P0-3.
        confidence = float(exec_result.get("confidence", 1.0) or 0.0)
        if severity in ("critical", "high"):
            conf_threshold = float(
                getattr(settings, "CONFIDENCE_MANUAL_REVIEW_THRESHOLD_HIGH_SEVERITY", 0.65)
            )
        else:
            conf_threshold = float(
                getattr(settings, "CONFIDENCE_MANUAL_REVIEW_THRESHOLD", 0.55)
            )

        if confidence < conf_threshold:
            return True

        # High-confidence fail: check if we have supporting data
        has_fact = _has_factual_extraction(structured_data, check=check)
        has_evidence = _extract_meaningful_evidence(exec_result) is not None

        if has_fact or has_evidence:
            return False

        # High-confidence fail, no supporting data: critical/high need manual review
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

    For low-confidence fail results, prepends a confidence warning
    so the lawyer sees why manual review is recommended.
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
            base_message = str(message).strip()

            # Если fail с низкой уверенностью — добавляем предупреждение.
            # Это единственное место где confidence виден юристу в review message.
            result = str(exec_result.get("result") or "").strip().lower()
            if result == "fail" and explanation.get("needs_manual_review"):
                confidence = float(exec_result.get("confidence", 1.0) or 0.0)
                severity = str(exec_result.get("severity") or "").strip().lower()
                if severity in ("critical", "high"):
                    conf_threshold = float(
                        getattr(
                            settings,
                            "CONFIDENCE_MANUAL_REVIEW_THRESHOLD_HIGH_SEVERITY",
                            0.65,
                        )
                    )
                else:
                    conf_threshold = float(
                        getattr(settings, "CONFIDENCE_MANUAL_REVIEW_THRESHOLD", 0.55)
                    )

                if confidence < conf_threshold:
                    confidence_pct = int(round(confidence * 100))
                    base_message = (
                        f"Уверенность системы: {confidence_pct}% "
                        f"(рекомендуется ручная проверка). "
                        f"{base_message}"
                    )

            return base_message
    except Exception:
        logger.debug(
            "result_semantics: build_user_explanation failed, using fallback",
            exc_info=True,
        )

    return _REVIEW_MESSAGE_FALLBACKS.get(review_status)



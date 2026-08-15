from __future__ import annotations

from typing import Any, Callable


NOT_FOUND_VALUES = frozenset({
    "not_found",
    "notfound",
    "not_defined",
    "not_specified",
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

RESERVED_METADATA_FIELDS = frozenset({
    "reason",
    "evidence",
    "explanation",
    "notes",
})

SIGNAL_MEANINGFUL_CONFIDENCE_THRESHOLD = 0.5


def normalize_text_token(value: Any) -> str | None:
    """Normalize arbitrary scalar to a stripped non-empty string or None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def is_not_found_scalar(value: Any) -> bool:
    """
    Return True when value semantically means 'not found / not defined'.

    Rules:
    - None is treated as not found.
    - Only strings are checked against NOT_FOUND_VALUES.
    - Non-string non-null values are considered meaningful by default.
    """
    if value is None:
        return True

    if not isinstance(value, str):
        return False

    return value.strip().lower() in NOT_FOUND_VALUES


def extract_scalar_value(field_payload: Any) -> Any:
    """
    Extract scalar value from normalized structured_data field payload.

    Supports:
    - {"value": ...}
    - scalar
    """
    if isinstance(field_payload, dict) and "value" in field_payload:
        return field_payload["value"]
    return field_payload


def extract_field_confidence(field_payload: Any) -> float:
    """
    Safely extract confidence from field payload.
    Returns 0.0 for malformed or missing confidence.
    """
    if not isinstance(field_payload, dict):
        return 0.0

    raw_confidence = field_payload.get("confidence", 0.0)
    try:
        return float(raw_confidence)
    except (TypeError, ValueError):
        return 0.0


def is_machine_code_token(text: str | None) -> bool:
    """
    Heuristic: machine/internal reason code looks like snake_case lowercase token
    without spaces, e.g.:
    - field_extraction_skip_presence
    - rules_confident_positive
    """
    normalized = normalize_text_token(text)
    if not normalized:
        return True

    return "_" in normalized and " " not in normalized and normalized == normalized.lower()


def iter_meaningful_fields(
    structured_data: dict[str, Any] | None,
    *,
    presentation_resolver: Callable[[str], str],
    signal_confidence_threshold: float = SIGNAL_MEANINGFUL_CONFIDENCE_THRESHOLD,
) -> list[tuple[str, Any, dict[str, Any], str]]:
    """
    Return meaningful extraction fields using one canonical rule-set.

    Output tuple:
        (field_name, scalar_value, normalized_payload, presentation)

    Semantic rules:
    - reserved metadata fields are skipped;
    - diagnostic fields are skipped;
    - fact/summary fields are included if value is not not-found;
    - signal fields are included only if:
        * value is not not-found
        * confidence >= signal_confidence_threshold
    """
    if not isinstance(structured_data, dict) or not structured_data:
        return []

    result: list[tuple[str, Any, dict[str, Any], str]] = []

    for field_name, field_payload in structured_data.items():
        if field_name in RESERVED_METADATA_FIELDS:
            continue

        presentation = (presentation_resolver(field_name) or "fact").strip().lower()

        if presentation == "diagnostic":
            continue

        scalar_value = extract_scalar_value(field_payload)

        if is_not_found_scalar(scalar_value):
            continue

        normalized_payload = (
            field_payload if isinstance(field_payload, dict) else {"value": scalar_value}
        )

        if presentation == "signal":
            confidence = extract_field_confidence(normalized_payload)
            if confidence < signal_confidence_threshold:
                continue

        result.append((field_name, scalar_value, normalized_payload, presentation))

    return result



    
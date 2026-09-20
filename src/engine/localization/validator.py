"""
Post-translation validator for legal result presentations (Sprint 3.5).

Validates LLM output AFTER receiving response but BEFORE persisting to DB.
Detects:
1. Truncation (incomplete JSON)
2. Hallucination (extra keys in response)
3. Glossary compliance violations (wrong terminology)

Raises:
- PermanentError: for truncation, hallucination, schema violations
- GlossaryComplianceError: for terminology violations (retryable)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class GlossaryComplianceError(ValueError):
    """
    Raised when LLM output violates glossary terminology constraints.

    This is a retryable error — the translation should be retried with
    the same glossary, as the LLM may produce correct output on retry.
    """

    def __init__(
        self,
        message: str,
        *,
        source_term: str,
        expected_target: str,
        actual_target: str,
    ):
        super().__init__(message)
        self.source_term = source_term
        self.expected_target = expected_target
        self.actual_target = actual_target


@dataclass(frozen=True)
class ValidationResult:
    """Result of post-translation validation."""

    is_valid: bool
    errors: list[str]
    glossary_violations: list[GlossaryComplianceError]


def validate_translation_response(
    *,
    response_text: str,
    expected_keys: set[str],
    glossary_terms: dict[str, str] | None = None,
    source_text: str | None = None,
) -> ValidationResult:
    """
    Validate LLM translation response.

    Args:
        response_text: Raw LLM response text (before JSON parsing)
        expected_keys: Set of required JSON keys
        glossary_terms: Optional glossary for terminology compliance check
        source_text: Optional original source text for glossary term detection

    Returns:
        ValidationResult with is_valid flag and list of errors

    Raises:
        ValueError: For truncation or schema violations (PermanentError candidates)
    """
    errors: list[str] = []
    glossary_violations: list[GlossaryComplianceError] = []

    # ── 1. Truncation check (before JSON parse) ─────────────────────
    response_stripped = response_text.strip()
    if not response_stripped:
        raise ValueError("LLM response is empty")

    if not response_stripped.endswith("}"):
        raise ValueError(
            f"LLM response appears truncated: does not end with closing brace. "
            f"Last 50 chars: {response_stripped[-50:]!r}"
        )

    # ── 2. JSON parse and schema validation ─────────────────────────
    import json

    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")

    actual_keys = set(payload.keys())
    if actual_keys != expected_keys:
        missing = expected_keys - actual_keys
        extra = actual_keys - expected_keys
        error_parts = []
        if missing:
            error_parts.append(f"missing keys: {missing}")
        if extra:
            error_parts.append(f"extra keys (hallucination): {extra}")
        raise ValueError(f"LLM response schema violation: {', '.join(error_parts)}")

    # ── 3. Glossary compliance check (if glossary provided) ─────────
    if glossary_terms and source_text:
        violations = _check_glossary_compliance(
            payload=payload,
            glossary_terms=glossary_terms,
            source_text=source_text,
        )
        glossary_violations.extend(violations)

    is_valid = len(errors) == 0 and len(glossary_violations) == 0

    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        glossary_violations=glossary_violations,
    )


def _check_glossary_compliance(
    *,
    payload: dict[str, Any],
    glossary_terms: dict[str, str],
    source_text: str,
) -> list[GlossaryComplianceError]:
    """
    Check if translated fields use correct glossary terminology.

    Algorithm:
    1. For each glossary source_term, check if it appears in source_text
    2. If yes, verify that the corresponding target_term appears in translated fields
    3. If target_term is missing, flag as glossary violation

    Returns:
        List of GlossaryComplianceError for each violation found
    """
    violations: list[GlossaryComplianceError] = []

    # Collect all translated text values
    translated_texts: list[str] = []
    for key, value in payload.items():
        if isinstance(value, str) and value:
            translated_texts.append(value.lower())

    translated_combined = " ".join(translated_texts)
    source_lower = source_text.lower()

    for src_term, expected_tgt in glossary_terms.items():
        # Check if source term appears in original text
        if src_term.lower() in source_lower:
            # Verify expected translation appears in output
            if expected_tgt.lower() not in translated_combined:
                violations.append(
                    GlossaryComplianceError(
                        f"Glossary violation: '{src_term}' should be translated as "
                        f"'{expected_tgt}', but this term was not found in the output",
                        source_term=src_term,
                        expected_target=expected_tgt,
                        actual_target="(not found)",
                    )
                )

    return violations

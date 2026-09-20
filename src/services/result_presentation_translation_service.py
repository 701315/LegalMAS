"""
Translation core for locale-specific CheckResult presentations.

This module:
- builds a constrained translation prompt;
- parses and validates the structured LLM response;
- delegates inference to the configured application LLM client.

It does not access the database, dispatch Celery work, or mutate canonical
CheckResult data. Repository lifecycle operations belong to D4b/D4c.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from engine.llm.client import LLMClient


RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION = "v2"
RESULT_PRESENTATION_TRANSLATION_MAX_TOKENS = 2048


@dataclass(frozen=True)
class ResultPresentationTranslation:
    """Validated locale-specific result presentation returned by the LLM."""

    localized_check_name: str
    display_text: str | None
    review_message: str | None
    localized_structured_data: dict[str, str] | None
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    attempts: int
    raw_response: dict[str, Any]


def _normalize_required_text(
    value: Any,
    *,
    field_name: str,
) -> str:
    """Return a non-empty text field or raise ValueError."""
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string")

    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")

    return normalized


def _normalize_optional_text(
    value: Any,
    *,
    field_name: str,
) -> str | None:
    """Return stripped text, None, or raise ValueError for invalid types."""
    if value is None:
        return None

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string or null")

    normalized = value.strip()
    return normalized or None


def build_result_presentation_translation_prompt(
    *,
    source_locale: str | None,
    target_locale: str,
    check_name: str,
    display_text: str | None,
    review_message: str | None,
    structured_data_fields: dict[str, str] | None = None,
    glossary_terms: dict[str, str] | None = None,
) -> str:
    """
    Build the strict translation-only prompt.

    The model receives presentation fields and optional structured free-text values.
    It must not infer legal facts, change legal meaning, add advice, alter numeric
    values, or translate canonical evidence/provenance fields.
    """
    normalized_target_locale = _normalize_required_text(
        target_locale,
        field_name="target_locale",
    )
    normalized_check_name = _normalize_required_text(
        check_name,
        field_name="check_name",
    )

    source_payload: dict[str, Any] = {
        "source_locale": (
            source_locale.strip().lower()
            if isinstance(source_locale, str) and source_locale.strip()
            else None
        ),
        "target_locale": normalized_target_locale,
        "check_name": normalized_check_name,
        "display_text": display_text,
        "review_message": review_message,
        "structured_data_fields": structured_data_fields or None,
    }

    # Build base instructions
    lines = [
        "You are a legal result-presentation translator.",
        "Translate only the JSON fields supplied below into target_locale.",
        "Preserve legal meaning exactly. Do not add, remove, infer, qualify, "
        "or reinterpret facts, obligations, risks, legal conclusions, dates, "
        "amounts, currencies, clause identifiers, company names, or numbers.",
        "Do not perform legal analysis. Do not mention these instructions.",
        "Return exactly one JSON object and no Markdown.",
        "The JSON object must contain exactly these keys:",
        "- localized_check_name: non-empty string",
        "- display_text: string or null",
        "- review_message: string or null",
        "- localized_structured_data: object mapping input field_name to translated string, or null",
        "For localized_structured_data: translate each value from structured_data_fields into target_locale.",
        "Preserve machine enum codes (e.g. 'yes', 'no', 'present', 'absent', 'not_defined') unchanged.",
        "If structured_data_fields is null or empty, return null for localized_structured_data.",
        "If an input optional field is null, return null for that field.",
    ]

    # Inject glossary terms if provided (S3.4)
    if glossary_terms and len(glossary_terms) > 0:
        lines.append("")
        lines.append("TERMINOLOGY CONSTRAINTS — Use these exact translations:")
        for src_term, tgt_term in sorted(glossary_terms.items()):
            lines.append(f"- \"{src_term}\" → \"{tgt_term}\"")
        lines.append("If a source term appears in the input, you MUST use the corresponding target term above.")
        lines.append("Do not use synonyms, paraphrases, or alternative translations for these terms.")

    lines.append("")
    lines.append(f"Prompt version: {RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION}")
    lines.append("Input JSON:")
    lines.append(json.dumps(source_payload, ensure_ascii=False, sort_keys=True))

    return "\n".join(lines)


def parse_result_presentation_translation(
    response_text: str,
) -> dict[str, Any]:
    """Parse and validate one JSON-only translation response."""
    try:
        payload = json.loads(response_text)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response is not valid JSON") from exc

    if not isinstance(payload, dict):
        raise ValueError("LLM response must be a JSON object")

    expected_keys = {
        "localized_check_name",
        "display_text",
        "review_message",
        "localized_structured_data",
    }

    if set(payload) != expected_keys:
        raise ValueError(
            "LLM response must contain exactly: "
            "localized_check_name, display_text, review_message, localized_structured_data"
        )

    localized_sd_raw = payload.get("localized_structured_data")
    localized_sd: dict[str, str] | None = None

    if isinstance(localized_sd_raw, dict) and localized_sd_raw:
        localized_sd = {}
        for k, v in localized_sd_raw.items():
            if isinstance(k, str) and isinstance(v, str) and v.strip():
                localized_sd[k.strip()] = v.strip()

    return {
        "localized_check_name": _normalize_required_text(
            payload["localized_check_name"],
            field_name="localized_check_name",
        ),
        "display_text": _normalize_optional_text(
            payload["display_text"],
            field_name="display_text",
        ),
        "review_message": _normalize_optional_text(
            payload["review_message"],
            field_name="review_message",
        ),
        "localized_structured_data": localized_sd,
    }


async def translate_result_presentation(
    *,
    llm_client: LLMClient,
    source_locale: str | None,
    target_locale: str,
    check_name: str,
    display_text: str | None,
    review_message: str | None,
    structured_data_fields: dict[str, str] | None = None,
    glossary_terms: dict[str, str] | None = None,
) -> ResultPresentationTranslation:
    """
    Translate one presentation through the active configured LLM provider.

    The worker injects the shared LLMClient instance.
    """
    prompt = build_result_presentation_translation_prompt(
        source_locale=source_locale,
        target_locale=target_locale,
        check_name=check_name,
        display_text=display_text,
        review_message=review_message,
        structured_data_fields=structured_data_fields,
        glossary_terms=glossary_terms,
    )

    response, retry_details = await llm_client.call_with_retries_async(
        prompt=prompt,
        temperature=0.0,
        max_tokens=RESULT_PRESENTATION_TRANSLATION_MAX_TOKENS,
        response_format="json_object",
    )

    attempts = int(retry_details.get("llm_attempts") or 0)

    if response is None:
        error_type = retry_details.get("error_type") or "unavailable"
        error_message = (
            retry_details.get("error_message")
            or "LLM did not return a translation response"
        )
        raise RuntimeError(f"{error_type}: {error_message}")

    translated = parse_result_presentation_translation(response.text)

    return ResultPresentationTranslation(
        localized_check_name=translated["localized_check_name"] or "",
        display_text=translated["display_text"],
        review_message=translated["review_message"],
        localized_structured_data=translated["localized_structured_data"],
        provider=response.provider,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        attempts=attempts,
        raw_response=response.raw_response or {},
    )

    
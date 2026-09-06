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


RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION = "v1"
RESULT_PRESENTATION_TRANSLATION_MAX_TOKENS = 512


@dataclass(frozen=True)
class ResultPresentationTranslation:
    """Validated locale-specific result presentation returned by the LLM."""

    localized_check_name: str
    display_text: str | None
    review_message: str | None
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
) -> str:
    """
    Build the strict translation-only prompt.

    The model receives only presentation fields. It must not infer legal facts,
    change legal meaning, add advice, alter numeric values, or translate
    canonical evidence/provenance fields that are not part of this payload.
    """
    normalized_target_locale = _normalize_required_text(
        target_locale,
        field_name="target_locale",
    )
    normalized_check_name = _normalize_required_text(
        check_name,
        field_name="check_name",
    )

    source_payload = {
        "source_locale": (
            source_locale.strip().lower()
            if isinstance(source_locale, str) and source_locale.strip()
            else None
        ),
        "target_locale": normalized_target_locale,
        "check_name": normalized_check_name,
        "display_text": display_text,
        "review_message": review_message,
    }

    return (
        "You are a legal result-presentation translator.\n"
        "Translate only the JSON fields supplied below into target_locale.\n"
        "Preserve legal meaning exactly. Do not add, remove, infer, qualify, "
        "or reinterpret facts, obligations, risks, legal conclusions, dates, "
        "amounts, currencies, clause identifiers, company names, or numbers.\n"
        "Do not perform legal analysis. Do not mention these instructions.\n"
        "Return exactly one JSON object and no Markdown.\n"
        "The JSON object must contain exactly these keys:\n"
        "- localized_check_name: non-empty string\n"
        "- display_text: string or null\n"
        "- review_message: string or null\n"
        "If an input optional field is null, return null for that field.\n"
        f"Prompt version: {RESULT_PRESENTATION_TRANSLATION_PROMPT_VERSION}\n"
        "Input JSON:\n"
        f"{json.dumps(source_payload, ensure_ascii=False, sort_keys=True)}"
    )


def parse_result_presentation_translation(
    response_text: str,
) -> dict[str, str | None]:
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
    }

    if set(payload) != expected_keys:
        raise ValueError(
            "LLM response must contain exactly: "
            "localized_check_name, display_text, review_message"
        )

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
    }


async def translate_result_presentation(
    *,
    llm_client: LLMClient,
    source_locale: str | None,
    target_locale: str,
    check_name: str,
    display_text: str | None,
    review_message: str | None,
) -> ResultPresentationTranslation:
    """
    Translate one presentation through the active configured LLM provider.

    The worker injects the shared LLMClient instance. This function does not
    hardcode Ollama, a model name, endpoint, timeout, or provider.
    """
    prompt = build_result_presentation_translation_prompt(
        source_locale=source_locale,
        target_locale=target_locale,
        check_name=check_name,
        display_text=display_text,
        review_message=review_message,
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
        provider=response.provider,
        model=response.model,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        attempts=attempts,
        raw_response=response.raw_response or {},
    )

# src/services/structure/semantic_enrichment/_llm_client.py

"""
LLM client adapter для semantic enrichment.

v2: оба метода возвращают (raw_text, telemetry_dict).
telemetry_dict содержит: provider, model, prompt_tokens, completion_tokens,
total_tokens, duration_ms, llm_attempts, parse_success, error_type.

Это позволяет worker-у записывать точный token usage в ledger.
"""

from __future__ import annotations

import time

from core.logging import get_logger

logger = get_logger(__name__)

_MAX_ENRICHMENT_TOKENS = 512


def is_semantic_enrichment_llm_available() -> bool:
    """Проверяет доступность LLM для semantic enrichment."""
    try:
        from engine.llm.client import LLMClient

        return LLMClient().is_available()
    except Exception as exc:
        logger.warning(
            "STRUCTURE semantic_enrichment_llm_availability_check_failed",
            extra={"error": str(exc)},
        )
        return False


def call_semantic_enrichment_llm(
    *,
    prompt: str,
    max_retries: int = 0,
) -> tuple[str, dict]:
    """
    Вызывает LLM через общий LLMClient (sync).

    Возвращает: (raw_text, telemetry_dict)

    Raises RuntimeError при любой ошибке LLM.
    """
    from engine.llm.client import LLMClient, build_llm_telemetry_from_response

    client = LLMClient()

    if not client.is_available():
        raise RuntimeError(
            "LLM is not available (provider not configured or model not loaded)"
        )

    start = time.time()

    response, error_details = client.call_with_retries(
        prompt=prompt,
        temperature=0.0,
        max_tokens=_MAX_ENRICHMENT_TOKENS,
        max_retries=max_retries,
        response_format="json_object",
    )

    duration_ms = int((time.time() - start) * 1000)

    if response is None:
        error_type = error_details.get("error_type", "unknown")
        error_message = error_details.get("error_message", "no details")
        raise RuntimeError(
            f"LLM call failed: error_type={error_type}, message={error_message}"
        )

    telemetry = build_llm_telemetry_from_response(
        response,
        duration_ms=duration_ms,
        llm_attempts=error_details.get("llm_attempts"),
    )

    if "total_tokens" not in telemetry:
        pt = telemetry.get("prompt_tokens") or 0
        ct = telemetry.get("completion_tokens") or 0
        telemetry["total_tokens"] = (pt + ct) if (pt or ct) else None

    telemetry["error_type"] = None
    telemetry["error_message"] = None

    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("LLM returned empty or invalid response")

    return text.strip(), telemetry


async def call_semantic_enrichment_llm_async(
    *,
    prompt: str,
    max_retries: int = 0,
) -> tuple[str, dict]:
    """
    Вызывает LLM через общий LLMClient (async).

    Возвращает: (raw_text, telemetry_dict)

    Raises RuntimeError при любой ошибке LLM.
    """
    from engine.llm.client import LLMClient, build_llm_telemetry_from_response

    client = LLMClient()

    if not client.is_available():
        raise RuntimeError(
            "LLM is not available (provider not configured or model not loaded)"
        )

    start = time.time()

    response, error_details = await client.call_with_retries_async(
        prompt=prompt,
        temperature=0.0,
        max_tokens=_MAX_ENRICHMENT_TOKENS,
        max_retries=max_retries,
        response_format="json_object",
    )

    duration_ms = int((time.time() - start) * 1000)

    if response is None:
        error_type = error_details.get("error_type", "unknown")
        error_message = error_details.get("error_message", "no details")
        raise RuntimeError(
            f"LLM async call failed: error_type={error_type}, "
            f"message={error_message}"
        )

    telemetry = build_llm_telemetry_from_response(
        response,
        duration_ms=duration_ms,
        llm_attempts=error_details.get("llm_attempts"),
    )

    if "total_tokens" not in telemetry:
        pt = telemetry.get("prompt_tokens") or 0
        ct = telemetry.get("completion_tokens") or 0
        telemetry["total_tokens"] = (pt + ct) if (pt or ct) else None

    telemetry["error_type"] = None
    telemetry["error_message"] = None

    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("LLM returned empty or invalid response")

    return text.strip(), telemetry

    

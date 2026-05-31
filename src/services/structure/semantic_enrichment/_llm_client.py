# src/services/structure/semantic_enrichment/_llm_client.py

"""
LLM client adapter для semantic enrichment.

Этот модуль НЕ реализует свой HTTP-клиент.
Вместо этого он использует общий LLMClient проекта (engine.llm.client),
который уже поддерживает llamacpp, ollama и openai провайдеры,
а также retry logic, context limit management и is_available() check.

Ответственность этого модуля:
- предоставить простой интерфейс для enricher:
    call_semantic_enrichment_llm(prompt) -> raw_text
    is_semantic_enrichment_llm_available() -> bool
- адаптировать LLMResponse к raw string для нашего validator
- изолировать enricher от деталей LLMClient

Важно:
- LLMClient использует settings.LLM_PROVIDER, LLM_LOCAL_MODEL_PATH и т.д.
- Тот же самый LLMClient используется в LLMDetector и L4LLMClassifier.
- Не нужен отдельный STRUCTURE_LLM_PROVIDER — используем общий.
"""

from __future__ import annotations

from core.logging import get_logger

logger = get_logger(__name__)

_MAX_ENRICHMENT_TOKENS = 512


def is_semantic_enrichment_llm_available() -> bool:
    """
    Проверяет доступность LLM для semantic enrichment.

    Использует тот же LLMClient что и остальная система.
    Если LLM недоступна — enrichment будет тихо пропущен.
    """
    try:
        from engine.llm.client import LLMClient

        client = LLMClient()
        return client.is_available()
    except Exception as exc:
        logger.warning(
            "STRUCTURE semantic_enrichment_llm_availability_check_failed",
            extra={"error": str(exc)},
        )
        return False


def call_semantic_enrichment_llm(
    *,
    prompt: str,
    max_retries: int = 2,
) -> str:
    """
    Вызывает LLM через общий LLMClient проекта.

    Использует тот же провайдер (llamacpp/ollama/openai) что и
    LLMDetector и L4LLMClassifier.

    Возвращает raw string из response для последующего парсинга.
    """
    try:
        from engine.llm.client import LLMClient
    except ImportError as exc:
        raise RuntimeError(f"LLMClient not available: {exc}") from exc

    client = LLMClient()

    if not client.is_available():
        raise RuntimeError("LLM is not available (provider not configured or model not loaded)")

    response, error_details = client.call_with_retries(
        prompt=prompt,
        temperature=0.0,
        max_tokens=_MAX_ENRICHMENT_TOKENS,
        max_retries=max_retries,
    )

    if response is None:
        error_type = error_details.get("error_type", "unknown")
        error_message = error_details.get("error_message", "no details")
        raise RuntimeError(
            f"LLM call failed: error_type={error_type}, message={error_message}"
        )

    # Используем response.text — сырой ответ LLM.
    # LLMClient автоматически парсит JSON в response.found/evidence/confidence,
    # но для semantic enrichment нам нужен именно raw text:
    # наш parse_llm_enrichment_response() сам извлечёт нужные поля.
    text = getattr(response, "text", None)
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("LLM returned empty or invalid response")

    return text.strip()



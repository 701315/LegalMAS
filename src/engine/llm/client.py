# src/engine/llm/client.py

"""
LLM Client Abstraction.

Provides a unified interface for calling different LLM providers:
- OpenAI (GPT-4o-mini, etc.)
- Ollama (local models)
- (опционально) llama-cpp
- None (disabled, rules-only mode)

Each provider returns a standardized LLMResponse.
The client handles timeouts, retries, and error normalization.
"""

import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx

from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    """Standardized response from an LLM call."""

    text: str  # Raw response text
    found: bool | None = None  # Parsed: was the condition found?
    evidence: str = ""  # Parsed: evidence snippet from response
    clause: str = ""  # Parsed: clause reference
    confidence: float = 0.0  # Parsed: confidence (if LLM provides it)
    provider: str = ""  # Which provider was used
    model: str = ""  # Which model was used
    tokens_used: int = 0  # Approximate tokens consumed
    parse_success: bool = False  # Was the JSON response parsed successfully?
    raw_response: dict = field(default_factory=dict)


class LLMClient:
    """Unified LLM client supporting multiple providers."""

    def __init__(self) -> None:
        self.provider = settings.LLM_PROVIDER  # "none" | "openai" | "ollama" | "llamacpp"
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        # llamacpp модель можно лениво инициализировать, когда понадобится
        self._llama_model: Any = None

    def is_available(self) -> bool:
        """Check if any LLM provider is configured."""
        return self.provider in ("openai", "ollama", "llamacpp")

    def call(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> LLMResponse | None:
        """
        Call the configured LLM provider.

        Args:
            prompt: Complete prompt text.
            temperature: Override default temperature.
            max_tokens: Override default max tokens.

        Returns:
            LLMResponse or None if LLM is not available/failed.
        """
        if self.provider == "none" or not self.is_available():
            return None

        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS

        try:
            if self.provider == "openai":
                return self._call_openai(prompt, temp, tokens)
            elif self.provider == "ollama":
                return self._call_ollama(prompt, temp, tokens)
            elif self.provider == "llamacpp":
                return self._call_llamacpp(prompt, temp, tokens)
            else:
                logger.warning("Unknown LLM provider", provider=self.provider)
                return None
        except httpx.TimeoutException:
            logger.warning("LLM call timed out", provider=self.provider)
            raise TransientError(f"LLM timeout ({self.provider})")
        except httpx.ConnectError:
            logger.warning("LLM connection failed", provider=self.provider)
            raise TransientError(f"LLM connection failed ({self.provider})")
        except TransientError:
            # уже залогировано, пробрасываем дальше
            raise
        except PermanentError:
            # уже залогировано, пробрасываем дальше
            raise
        except Exception as e:
            logger.error("LLM call failed", provider=self.provider, error=str(e))
            return None

    # --- OpenAI-compatible provider ---

    def _call_openai(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call OpenAI-compatible API."""
        url = f"{settings.LLM_OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM_OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.LLM_OPENAI_MODEL,
            "messages": [
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=body, headers=headers)

        if response.status_code == 401:
            raise PermanentError("OpenAI invalid API key")
        if response.status_code == 429:
            raise TransientError("OpenAI rate limit exceeded")
        if response.status_code >= 500:
            raise TransientError(f"OpenAI server error: {response.status_code}")
        if response.status_code != 200:
            raise PermanentError(f"OpenAI error {response.status_code}: {response.text[:200]}")

        data = response.json()
        text = data["choices"][0]["message"]["content"]
        tokens_used = data.get("usage", {}).get("total_tokens", 0)

        result = LLMResponse(
            text=text,
            provider="openai",
            model=settings.LLM_OPENAI_MODEL,
            tokens_used=tokens_used,
            raw_response=data,
        )
        return _parse_llm_response(result)

    # --- Ollama local provider ---

    def _call_ollama(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call Ollama local API."""
        url = f"{settings.LLM_OLLAMA_BASE_URL}/api/generate"
        body = {
            "model": settings.LLM_OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json=body)

        if response.status_code == 404:
            raise PermanentError(
                f"Ollama model not found: {settings.LLM_OLLAMA_MODEL}. "
                f"Run `ollama pull {settings.LLM_OLLAMA_MODEL}`."
            )
        if response.status_code != 200:
            raise TransientError(f"Ollama error {response.status_code}: {response.text[:200]}")

        data = response.json()
        text = data.get("response", "")

        result = LLMResponse(
            text=text,
            provider="ollama",
            model=settings.LLM_OLLAMA_MODEL,
            raw_response=data,
        )
        return _parse_llm_response(result)

    # --- llama-cpp provider (optional, CPU/GPU local model) ---

    def _call_llamacpp(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Call local model via llama-cpp-python."""
        model_path = settings.LLM_LOCAL_MODEL_PATH
        if not model_path:
            raise PermanentError("LLM_LOCAL_MODEL_PATH is not set for llamacpp provider")

        # Нормализуем путь под Linux/Windows
        normalized = model_path.replace("\\", "/")
        if not os.path.exists(normalized):
            raise PermanentError(f"Model file does not exist: {normalized} (LLM_LOCAL_MODEL_PATH)")

        # Lazy-load модели
        if self._llama_model is None:
            try:
                from llamacpp import Llama  # type: ignore
            except ImportError as e:
                raise PermanentError(
                    "llama-cpp-python is not installed. " "Install it or switch LLM_PROVIDER."
                ) from e

            logger.info(
                "Loading local LLM model",
                path=normalized,
                context_length=settings.LLM_LOCAL_N_CTX,
                gpu_layers=settings.LLM_LOCAL_N_GPU_LAYERS,
            )
            self._llama_model = Llama(
                model_path=normalized,
                n_ctx=settings.LLM_LOCAL_N_CTX,
                n_gpu_layers=settings.LLM_LOCAL_N_GPU_LAYERS,
                verbose=False,
            )
            logger.info("Local LLM model loaded successfully", path=normalized)

        # Вызов модели
        output = self._llama_model(
            prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stop=["\n\n", "###", "-----"],
            echo=False,
        )

        text = output["choices"][0]["text"].strip()
        tokens_used = output.get("usage", {}).get("total_tokens", 0)

        result = LLMResponse(
            text=text,
            provider="llamacpp",
            model=model_path,
            tokens_used=tokens_used,
            raw_response=output,
        )
        return _parse_llm_response(result)


def _parse_llm_response(response: LLMResponse) -> LLMResponse:
    """
    Parse LLM response text to extract structured data.

    Expects JSON: {"found": true/false, "evidence": "...", "clause": "...", "confidence": 0.0-1.0}
    Falls back to text analysis if JSON parsing fails.
    """
    text = response.text.strip()

    # Try to extract JSON from response
    json_data = _extract_json(text)

    if json_data:
        response.found = json_data.get("found", None)
        response.evidence = str(json_data.get("evidence", "") or "")
        response.clause = str(json_data.get("clause", "") or "")
        response.confidence = float(json_data.get("confidence", 0.7))
        response.parse_success = True
    else:
        # Fallback: simple text analysis
        text_lower = text.lower()
        if any(w in text_lower for w in ["yes", "да", "found", "найден", "true"]):
            response.found = True
        elif any(w in text_lower for w in ["no", "нет", "not found", "не найден", "false"]):
            response.found = False
        else:
            response.found = None  # Uncertain

        response.evidence = text[:500]
        response.confidence = 0.5
        response.parse_success = False

    return response


def _extract_json(text: str) -> dict | None:
    """
    Extract JSON object from LLM response text.

    Handles:
    - Pure JSON: {"found": true}
    - JSON in markdown: ```json\n{"found": true}\n```
    - JSON embedded in text: Some text {"found": true} more text
    """
    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    import re

    # Try to find JSON in markdown code block
    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find JSON object anywhere in text (простая, но часто рабочая эвристика)
    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None

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
from typing import Any, Optional
import time

import httpx

from ops.metrics import METRICS
from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from engine.retrieval.tokenization import count_tokens  # для подсчёта prompt_tokens

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
        # llama-cpp модель можно лениво инициализировать, когда понадобится
        self._llama_model: Any = None
        self._llama_grammar_cache: dict[str, Any] = {}  # кэш грамматик

    # Максимальное количество попыток для повторов LLM-запроса.
    # Для непрофессионального программиста:
    # - 0 означает «ровно один вызов без ретраев»;
    # - 2 означает «до трёх вызовов: первая попытка + 2 повтора».
    _DEFAULT_MAX_RETRIES = getattr(settings, "LLM_MAX_RETRIES", 2)

    def is_available(self) -> bool:
        """Check if any LLM provider is configured."""
        return self.provider in ("openai", "ollama", "llamacpp")

    def _compute_token_budget(
        self,
        prompt: str,
        requested_max_tokens: int,
    ) -> tuple[int, dict]:
        """
        Посчитать эффективный max_tokens с учётом общего лимита модели.

        Инвариант:
            prompt_tokens + effective_max_tokens + safety_margin <= model_limit

        Термины:
        - prompt_tokens: токены входного prompt
        - reserved_output_tokens: максимум токенов, который можно отдать под ответ
        после вычета prompt и safety_margin
        - effective_max_tokens: фактически используемый max_tokens для вызова модели
        """
        model_limit = getattr(settings, "LLM_CONTEXT_LIMIT", None)
        safety_margin = int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 256))
        min_output_tokens = int(getattr(settings, "LLM_MIN_OUTPUT_TOKENS", 64))

        diagnostics: dict[str, Any] = {
            "model_limit": model_limit,
            "requested_max_tokens": int(requested_max_tokens),
            "effective_max_tokens": int(requested_max_tokens),
            "prompt_tokens": None,
            "reserved_output_tokens": None,
            "available_for_output": None,  # backward-compatible alias
            "safety_margin": safety_margin,
            "min_output_tokens": min_output_tokens,
            "budget_enforced": False,
            "output_budget_reduced": False,
        }

        # Если лимит не задан — ведём себя как раньше.
        if not isinstance(model_limit, int) or model_limit <= 0:
            return int(requested_max_tokens), diagnostics

        prompt_tokens = count_tokens(prompt)
        diagnostics["prompt_tokens"] = int(prompt_tokens)

        reserved_output_tokens = model_limit - prompt_tokens - safety_margin
        diagnostics["reserved_output_tokens"] = int(reserved_output_tokens)
        diagnostics["available_for_output"] = int(reserved_output_tokens)

        if reserved_output_tokens <= 0:
            logger.warning(
                "LLMClient: prompt exceeds model context window",
                provider=self.provider,
                model_limit=model_limit,
                prompt_tokens=prompt_tokens,
                requested_max_tokens=int(requested_max_tokens),
                reserved_output_tokens=int(reserved_output_tokens),
                safety_margin=safety_margin,
            )
            raise PermanentError("LLM prompt exceeds model context limit")

        if reserved_output_tokens < min_output_tokens:
            logger.warning(
                "LLMClient: insufficient output token budget",
                provider=self.provider,
                model_limit=model_limit,
                prompt_tokens=prompt_tokens,
                requested_max_tokens=int(requested_max_tokens),
                reserved_output_tokens=int(reserved_output_tokens),
                min_output_tokens=int(min_output_tokens),
                safety_margin=safety_margin,
            )
            raise PermanentError("LLM prompt leaves insufficient output token budget")

        effective_max_tokens = min(
            int(requested_max_tokens),
            int(reserved_output_tokens),
        )

        diagnostics["effective_max_tokens"] = int(effective_max_tokens)
        diagnostics["budget_enforced"] = True
        diagnostics["output_budget_reduced"] = (
            int(effective_max_tokens) < int(requested_max_tokens)
        )

        logger.info(
            "LLM token budget computed",
            provider=self.provider,
            model_limit=model_limit,
            prompt_tokens=int(prompt_tokens),
            requested_max_tokens=int(requested_max_tokens),
            reserved_output_tokens=int(reserved_output_tokens),
            effective_max_tokens=int(effective_max_tokens),
            safety_margin=int(safety_margin),
            min_output_tokens=int(min_output_tokens),
            output_budget_reduced=diagnostics["output_budget_reduced"],
        )

        return effective_max_tokens, diagnostics

    def call(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: Optional[str] = None,
    ) -> LLMResponse | None:
        """
        Call the configured LLM provider.

        grammar_path:
            Optional path to a GBNF grammar file (used for llama-cpp).
            For OpenAI/Ollama сейчас игнорируется (можно расширить позже).

        Returns:
            LLMResponse or None if LLM is not available/failed.
        """
        if self.provider == "none" or not self.is_available():
            return None

        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        requested_tokens = (
            max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        )

        # Жёсткий budget по токенам: prompt_tokens + max_tokens <= LLM_CONTEXT_LIMIT.
        # Если лимит не задан — tokens остаётся как раньше.
        try:
            tokens, budget_info = self._compute_token_budget(
                prompt=prompt,
                requested_max_tokens=int(requested_tokens),
            )
        except PermanentError:
            # Логируем отдельно и пробрасываем дальше.
            logger.warning(
                "LLM call aborted due to token budget violation",
                provider=self.provider,
                requested_max_tokens=int(requested_tokens),
            )
            raise

        logger.info(
            "LLM call",
            provider=self.provider,
            temperature=temp,
            max_tokens=tokens,
            prompt_preview=prompt[:200],
            grammar_enabled=bool(grammar_path),
            prompt_tokens=budget_info.get("prompt_tokens"),
            reserved_output_tokens=budget_info.get("reserved_output_tokens"),
            effective_max_tokens=budget_info.get("effective_max_tokens"),
            token_budget=budget_info,
        )

        start_time = time.time()
        error_type_for_metrics: str | None = None
        result: LLMResponse | None = None

        try:
            if self.provider == "openai":
                # Пока grammar_path игнорируем для openai
                result = self._call_openai(prompt, temp, tokens)
            elif self.provider == "ollama":
                # Пока grammar_path игнорируем для ollama
                result = self._call_ollama(prompt, temp, tokens)
            elif self.provider == "llamacpp":
                result = self._call_llamacpp(
                    prompt, temp, tokens, grammar_path=grammar_path
                )
            else:
                logger.warning("Unknown LLM provider", provider=self.provider)
                error_type_for_metrics = "unknown_provider"
                result = None
        except httpx.TimeoutException:
            logger.warning("LLM call timed out", provider=self.provider)
            error_type_for_metrics = "timeout"
            # пробрасываем как TransientError — дальше поймает LLMDetector
            raise TransientError(f"LLM timeout ({self.provider})")
        except httpx.ConnectError:
            logger.warning("LLM connection failed", provider=self.provider)
            error_type_for_metrics = "connect_error"
            raise TransientError(f"LLM connection failed ({self.provider})")
        except TransientError:
            error_type_for_metrics = "transient_error"
            # уже залогировано выше, пробрасываем дальше
            raise
        except PermanentError:
            error_type_for_metrics = "permanent_error"
            # уже залогировано выше, пробрасываем дальше
            raise
        except Exception as e:
            logger.error("LLM call failed", provider=self.provider, error=str(e))
            error_type_for_metrics = "unexpected_error"
            result = None
        finally:
            # Метрики LLM-вызова — считаем всегда, даже при исключениях.
            duration = time.time() - start_time
            try:
                METRICS.llm_request_duration_seconds.labels(
                    provider=self.provider
                ).observe(duration)
                METRICS.llm_requests_total.labels(
                    provider=self.provider,
                    error_type=error_type_for_metrics or "none",
                ).inc()
                if isinstance(result, LLMResponse):
                    METRICS.llm_tokens_total.labels(
                        provider=self.provider,
                    ).inc(result.tokens_used)
            except Exception:
                # Метрики не должны ломать бизнес-логику
                logger.exception("LLMClient: failed to update LLM metrics")

        return result

    def call_with_retries(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: Optional[str] = None,
        max_retries: int | None = None,
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызов LLM с повторами при временных ошибках.

        Для непрофессионального программиста:
        - сначала мы пробуем один обычный вызов LLM (через self.call);
        - если ловим временную ошибку (TransientError), пробуем ещё раз,
          пока не исчерпаем max_retries;
        - если ошибка постоянная (PermanentError) или неожиданная — не повторяем;
        - всегда возвращаем пару (response_or_none, errordetails_dict).

        errordetails содержит:
        - llm_attempts: сколько реальных попыток было сделано;
        - error_type: None, если всё ок; иначе строку ("transient_error", "permanent_error", ...);
        - error_message: текст ошибки (если была).
        """
        attempts = 0
        last_error_type: str | None = None
        last_error_message: str | None = None

        # Определяем, сколько раз максимум будем повторять
        retries = (
            max_retries
            if max_retries is not None
            else getattr(settings, "LLM_MAX_RETRIES", 2)
        )

        while True:
            try:
                attempts += 1
                response = self.call(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grammar_path=grammar_path,
                )

                # Если self.call вернул None (например, LLM_PROVIDER="none"),
                # считаем, что это не ошибка LLM, а просто отсутствие провайдера.
                if response is None:
                    return None, {
                        "llm_attempts": attempts,
                        "error_type": "unavailable",
                        "error_message": "LLM provider is not available",
                    }

                # Успешный ответ — выходим без ошибок.
                return response, {
                    "llm_attempts": attempts,
                    "error_type": None,
                    "error_message": None,
                }

            except TransientError as e:
                # Временная ошибка: можно попробовать ещё раз, если не исчерпали лимит.
                last_error_type = "transient_error"
                last_error_message = str(e)
                logger.warning(
                    "LLMClient transient error, will retry if attempts left",
                    provider=self.provider,
                    attempt=attempts,
                    max_retries=retries,
                    error=str(e),
                )
                if attempts > retries:
                    break
                # Переходим к следующей итерации цикла и пробуем ещё раз.
                continue

            except PermanentError as e:
                # Постоянная ошибка: повторять бессмысленно.
                last_error_type = "permanent_error"
                last_error_message = str(e)
                logger.warning(
                    "LLMClient permanent error, no retries",
                    provider=self.provider,
                    attempt=attempts,
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }

            except Exception as e:
                # Любая неожиданная ошибка: ведём себя консервативно, не повторяем.
                last_error_type = "unexpected_error"
                last_error_message = str(e)
                logger.error(
                    "LLMClient unexpected exception",
                    provider=self.provider,
                    attempt=attempts,
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }

        # Если сюда дошли — значит, были только временные ошибки и мы исчерпали retries.
        return None, {
            "llm_attempts": attempts,
            "error_type": last_error_type or "transient_error",
            "error_message": last_error_message,
        }

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
            raise PermanentError(
                f"OpenAI error {response.status_code}: {response.text[:200]}"
            )

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
            raise TransientError(
                f"Ollama error {response.status_code}: {response.text[:200]}"
            )

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
        grammar_path: Optional[str] = None,
    ) -> LLMResponse:
        """Call local model via llama-cpp-python."""
        model_path = settings.LLM_LOCAL_MODEL_PATH
        if not model_path:
            raise PermanentError("LLM_LOCAL_MODEL_PATH is not set for llamacpp provider")

        normalized = model_path.replace("\\", "/")
        if not os.path.exists(normalized):
            raise PermanentError(
                f"Model file does not exist: {normalized} (LLM_LOCAL_MODEL_PATH)"
            )

        # Lazy-load модели
        if self._llama_model is None:
            try:
                from llama_cpp import Llama  # только Llama здесь
            except ImportError as e:
                raise PermanentError(
                    "llama-cpp-python is not installed. "
                    "Install it or switch LLM_PROVIDER."
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

        # Импорт LlamaGrammar отдельно, вне if
        from llama_cpp import LlamaGrammar

        llama_kwargs: dict[str, Any] = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stop": ["\n\n", "###", "-----"],
            "echo": False,
        }

        if grammar_path:
            try:
                if grammar_path not in self._llama_grammar_cache:
                    with open(grammar_path, "r", encoding="utf-8") as f:
                        gbnf_text = f.read()
                    grammar_obj = LlamaGrammar.from_string(gbnf_text)
                    self._llama_grammar_cache[grammar_path] = grammar_obj
                else:
                    grammar_obj = self._llama_grammar_cache[grammar_path]

                llama_kwargs["grammar"] = grammar_obj
            except Exception as e:
                logger.warning(
                    "Failed to load/parse GBNF grammar, falling back without it",
                    path=grammar_path,
                    error=str(e),
                )

        output = self._llama_model(**llama_kwargs)

        text = output["choices"][0]["text"].strip()
        tokens_used = output.get("usage", {}).get("total_tokens", 0)

        logger.info(
            "LLM response",
            provider="llamacpp",
            tokens_used=tokens_used,
            text_preview=text[:200],
        )

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
        try:
            response.confidence = float(json_data.get("confidence", 0.7))
        except (TypeError, ValueError):
            response.confidence = 0.7
        response.parse_success = True
    else:
        # Fallback: simple text analysis
        text_lower = text.lower()
        if any(w in text_lower for w in ["yes", "да", "found", "найден", "true"]):
            response.found = True
        elif any(
            w in text_lower
            for w in ["no", "нет", "not found", "не найден", "false"]
        ):
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


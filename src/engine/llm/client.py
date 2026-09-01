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

import gc
import json
import os
import re
import time
import asyncio
import random

from dataclasses import dataclass, field
from typing import Any

import httpx

from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from engine.retrieval.tokenization import count_tokens
from ops.metrics import METRICS


# ── Tracing: импортируем лениво чтобы не ломать если OTEL выключен ───────────
try:
    from core.tracing import get_stage_tracer as _get_stage_tracer
    _TRACING_AVAILABLE = True
except ImportError:
    _TRACING_AVAILABLE = False

logger = get_logger(__name__)

# P8.5: Valid values for response_format parameter
_VALID_RESPONSE_FORMATS: frozenset[str | None] = frozenset({None, "json_object"})


# =============================================================================
# Backoff helpers
# =============================================================================

def _compute_backoff_delay(
    attempt: int,
    base: float,
    cap: float,
    jitter_range: float,
) -> float:
    """
    Вычислить задержку перед retry с экспоненциальным backoff и jitter.

    Формула: min(base * 2^(attempt-1), cap) + uniform(0, jitter_range)

    Аргументы:
        attempt:      номер попытки, начиная с 1.
                      attempt=1 → base * 1 (первый retry)
                      attempt=2 → base * 2
                      attempt=3 → base * 4 (но не более cap)
        base:         базовая задержка в секундах (LLM_RETRY_BASE_DELAY_SECONDS)
        cap:          максимальная задержка в секундах (LLM_RETRY_MAX_DELAY_SECONDS)
        jitter_range: диапазон случайного сдвига в секундах (LLM_RETRY_JITTER_SECONDS)

    Возвращает:
        Задержку в секундах (float >= 0).

    Свойства:
        - Pure function: детерминирована при фиксированном random seed.
        - Никогда не возвращает отрицательное значение.
        - cap защищает от бесконечного роста при большом attempt.
        - jitter разбрасывает retry N воркеров во времени (thundering herd protection).

    Пример для base=1.0, cap=30.0, jitter_range=1.0:
        attempt=1 → ~1.0-2.0s
        attempt=2 → ~2.0-3.0s
        attempt=3 → ~4.0-5.0s
        attempt=5 → ~16.0-17.0s
        attempt=6 → ~30.0-31.0s  (cap сработал)
    """
    if attempt < 1:
        attempt = 1
    if base < 0:
        base = 0.0
    if cap < 0:
        cap = 0.0
    if jitter_range < 0:
        jitter_range = 0.0

    exponential = min(base * (2 ** (attempt - 1)), cap)
    jitter = random.uniform(0.0, jitter_range)  # noqa: S311 — не криптографический контекст
    return exponential + jitter


# =============================================================================
# Helpers
# =============================================================================

def _safe_non_negative_int(value: Any) -> int | None:
    """Привести значение к неотрицательному int или вернуть None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _extract_prompt_tokens_from_raw_response(
    provider: str,
    raw_response: dict[str, Any] | None,
) -> int | None:
    """Извлечь prompt tokens из provider-specific raw response."""
    if not isinstance(raw_response, dict):
        return None

    if provider == "openai":
        usage = raw_response.get("usage") or {}
        if isinstance(usage, dict):
            return _safe_non_negative_int(usage.get("prompt_tokens"))

    if provider == "ollama":
        return _safe_non_negative_int(raw_response.get("prompt_eval_count"))

    if provider == "llamacpp":
        usage = raw_response.get("usage") or {}
        if isinstance(usage, dict):
            return _safe_non_negative_int(usage.get("prompt_tokens"))

    return None


def _extract_completion_tokens_from_raw_response(
    provider: str,
    raw_response: dict[str, Any] | None,
) -> int | None:
    """Извлечь completion tokens из provider-specific raw response."""
    if not isinstance(raw_response, dict):
        return None

    if provider == "openai":
        usage = raw_response.get("usage") or {}
        if isinstance(usage, dict):
            return _safe_non_negative_int(usage.get("completion_tokens"))

    if provider == "ollama":
        return _safe_non_negative_int(raw_response.get("eval_count"))

    if provider == "llamacpp":
        usage = raw_response.get("usage") or {}
        if isinstance(usage, dict):
            return _safe_non_negative_int(usage.get("completion_tokens"))

    return None


def build_llm_telemetry_from_response(
    response: "LLMResponse",
    *,
    duration_ms: int | None = None,
    llm_attempts: int | None = None,
) -> dict[str, Any]:
    """
    Построить normalized telemetry dict из LLMResponse.

    Единый внутренний контракт observability-метаданных.
    """
    provider = str(response.provider or "").strip()
    raw_response = response.raw_response if isinstance(response.raw_response, dict) else {}

    prompt_tokens = (
        response.prompt_tokens
        if response.prompt_tokens is not None
        else _extract_prompt_tokens_from_raw_response(provider, raw_response)
    )
    completion_tokens = (
        response.completion_tokens
        if response.completion_tokens is not None
        else _extract_completion_tokens_from_raw_response(provider, raw_response)
    )

    return {
        "provider": provider or None,
        "model": (str(response.model).strip() if response.model else None),
        "tokens_used": _safe_non_negative_int(response.tokens_used),
        "prompt_tokens": _safe_non_negative_int(prompt_tokens),
        "completion_tokens": _safe_non_negative_int(completion_tokens),
        "duration_ms": _safe_non_negative_int(duration_ms),
        "llm_attempts": _safe_non_negative_int(llm_attempts),
        "parse_success": (
            bool(response.parse_success)
            if response.parse_success is not None
            else None
        ),
    }


def _resolve_structured_output_strategy(
    provider: str,
    response_format: "str | None",
    grammar_path: "str | None",
) -> str:
    """
    Determine the actual structured output strategy for logging/diagnostics.

    Returns: "none" | "ollama_json_mode" | "llamacpp_gbnf" | "prompt_only"
    """
    if response_format != "json_object" and not grammar_path:
        return "none"
    if provider == "ollama" and response_format == "json_object":
        return "ollama_json_mode"
    if provider == "llamacpp" and grammar_path:
        return "llamacpp_gbnf"
    if response_format == "json_object":
        return "prompt_only"
    return "none"


class LLMContextLimitError(PermanentError):
    """
    Prompt + max_tokens превышают контекстное окно модели.

    Не требует retry — контекст не уменьшится сам по себе.
    HybridDetector выставляет llm_error_type='context_limit'.
    """


@dataclass
class LLMResponse:
    """Standardized response from an LLM call."""

    text: str
    found: bool | None = None
    evidence: str = ""
    clause: str = ""
    confidence: float = 0.0
    provider: str = ""
    model: str = ""
    tokens_used: int = 0
    parse_success: bool = False
    raw_response: dict = field(default_factory=dict)
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class LLMClient:
    """
    Unified LLM client supporting multiple providers.

    Singleton: каждый вызов LLMClient() возвращает один и тот же объект.
    Модель (llamacpp) загружается ровно один раз за время жизни процесса.
    """

    _instance: "LLMClient | None" = None

    def __new__(cls) -> "LLMClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if hasattr(self, "_initialized"):
            return
        self._initialized = True
        self.provider = settings.LLM_PROVIDER
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self._llama_model: Any = None
        self._llama_grammar_cache: dict[str, Any] = {}
        self._llamacpp_semaphore: asyncio.Semaphore | None = None
        self._llamacpp_inflight_futures: set[Any] = set()

    # -------------------------------------------------------------------------
    # ИСПРАВЛЕНО: используем settings.LLM_MAX_RETRIES (typed field),
    # а не getattr(settings, "LLM_MAX_RETRIES", 2) (phantom setting).
    # Теперь значение из .env корректно читается Pydantic-ом.
    # -------------------------------------------------------------------------
    @property
    def _default_max_retries(self) -> int:
        """
        Число retry по умолчанию из конфига.

        Property вместо class-level атрибута потому что:
        - LLMClient — singleton, создаётся при первом импорте;
        - settings может быть переопределён в тестах через monkeypatch;
        - class-level атрибут читается один раз при загрузке модуля.
        """
        return settings.LLM_MAX_RETRIES

    # =========================================================================
    # Tracing helpers
    # =========================================================================

    def _get_tracer(self):
        """Вернуть tracer или None."""
        if not _TRACING_AVAILABLE:
            return None
        try:
            return _get_stage_tracer()
        except Exception:
            return None

    def _enrich_llm_span(
        self,
        span,
        result: "LLMResponse | None",
        duration_ms: int,
        error_type: "str | None",
        exc: "Exception | None",
    ) -> None:
        """Обогатить span llm.call атрибутами после завершения вызова."""
        try:
            from opentelemetry.trace import StatusCode

            span.set_attribute("llm.success", error_type is None and result is not None)
            span.set_attribute("llm.duration_ms", duration_ms)

            if error_type is not None:
                span.set_attribute("llm.error_type", error_type)

            if isinstance(result, LLMResponse):
                span.set_attribute("llm.tokens_total", result.tokens_used)

                raw = result.raw_response or {}

                if self.provider == "ollama":
                    prompt_tokens = raw.get("prompt_eval_count")
                    completion_tokens = raw.get("eval_count")
                    if isinstance(prompt_tokens, int):
                        span.set_attribute("llm.prompt_tokens", prompt_tokens)
                    if isinstance(completion_tokens, int):
                        span.set_attribute("llm.completion_tokens", completion_tokens)

                elif self.provider == "openai":
                    usage = raw.get("usage", {}) or {}
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
                    if isinstance(prompt_tokens, int):
                        span.set_attribute("llm.prompt_tokens", prompt_tokens)
                    if isinstance(completion_tokens, int):
                        span.set_attribute("llm.completion_tokens", completion_tokens)

                elif self.provider == "llamacpp":
                    usage = raw.get("usage", {}) or {}
                    prompt_tokens = usage.get("prompt_tokens")
                    completion_tokens = usage.get("completion_tokens")
                    if isinstance(prompt_tokens, int):
                        span.set_attribute("llm.prompt_tokens", prompt_tokens)
                    if isinstance(completion_tokens, int):
                        span.set_attribute("llm.completion_tokens", completion_tokens)

            if exc is not None:
                span.record_exception(exc)
                span.set_status(StatusCode.ERROR, str(exc))
            elif error_type is not None:
                span.set_status(StatusCode.ERROR, error_type)
            else:
                span.set_status(StatusCode.OK)

        except Exception:
            pass

    def is_available(self) -> bool:
        """Check if any LLM provider is configured."""
        return self.provider in ("openai", "ollama", "llamacpp")

    def reset_local_runtime_state(self) -> None:
        """
        Сбросить process-local runtime state для llama-cpp.

        Безопасен только если нет активных in-flight llamacpp-вызовов.
        Для non-llamacpp provider ничего не делает.
        """
        if self.provider != "llamacpp":
            return

        active_inflight_calls = self._count_active_llamacpp_futures()
        if active_inflight_calls > 0:
            logger.warning(
                "LLMClient local runtime reset skipped: active llamacpp calls still in flight",
                provider=self.provider,
                pid=os.getpid(),
                active_inflight_calls=active_inflight_calls,
            )
            return

        old_model = self._llama_model
        old_grammar_cache_size = len(self._llama_grammar_cache)

        self._llama_model = None
        self._llama_grammar_cache.clear()

        if old_model is not None:
            close_fn = getattr(old_model, "close", None)
            if callable(close_fn):
                close_fn()

        del old_model
        gc.collect()

        logger.info(
            "LLMClient local runtime state reset",
            provider=self.provider,
            pid=os.getpid(),
            cleared_grammar_cache_entries=old_grammar_cache_size,
        )

    def reset_local_runtime_state_best_effort(self) -> None:
        """Best-effort обёртка над reset_local_runtime_state()."""
        try:
            self.reset_local_runtime_state()
        except Exception as exc:
            logger.warning(
                "LLMClient failed to reset local runtime state",
                provider=self.provider,
                pid=os.getpid(),
                error=str(exc),
            )

    def _compute_token_budget(
        self,
        prompt: str,
        requested_max_tokens: int,
    ) -> tuple[int, dict]:
        """
        Fail-fast check: влезает ли prompt + requested_max_tokens в окно модели.

        Выбрасывает LLMContextLimitError если не влезает.
        """
        model_limit = getattr(settings, "LLM_CONTEXT_LIMIT", None)
        safety_margin = int(getattr(settings, "LLM_SAFETY_MARGIN_TOKENS", 512))
        min_output_tokens = int(getattr(settings, "LLM_MIN_OUTPUT_TOKENS", 64))

        diagnostics = {
            "model_limit": model_limit,
            "requested_max_tokens": int(requested_max_tokens),
            "prompt_tokens": None,
            "effective_max_tokens": int(requested_max_tokens),
            "safety_margin": safety_margin,
        }

        if not isinstance(model_limit, int) or model_limit <= 0:
            return int(requested_max_tokens), diagnostics

        prompt_tokens = count_tokens(prompt)
        diagnostics["prompt_tokens"] = int(prompt_tokens)

        reserved_output_tokens = model_limit - prompt_tokens - safety_margin

        if reserved_output_tokens <= 0:
            raise LLMContextLimitError(
                f"Prompt exceeds model context (prompt={prompt_tokens}, "
                f"limit={model_limit}, margin={safety_margin})"
            )

        if reserved_output_tokens < min_output_tokens:
            raise LLMContextLimitError(
                f"Insufficient output budget (reserved={reserved_output_tokens}, "
                f"min_required={min_output_tokens})"
            )

        effective_max_tokens = min(int(requested_max_tokens), int(reserved_output_tokens))
        diagnostics["effective_max_tokens"] = int(effective_max_tokens)

        return effective_max_tokens, diagnostics

    def call(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse | None:
        """Call the configured LLM provider (sync, single attempt)."""
        if response_format not in _VALID_RESPONSE_FORMATS:
            raise PermanentError(
                f"Invalid response_format={response_format!r}. "
                f"Valid values: {set(_VALID_RESPONSE_FORMATS)}"
            )

        if self.provider == "none" or not self.is_available():
            return None

        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        requested_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS

        try:
            tokens, budget_info = self._compute_token_budget(
                prompt=prompt,
                requested_max_tokens=int(requested_tokens),
            )
        except LLMContextLimitError:
            logger.warning(
                "LLM call aborted: context limit exceeded",
                provider=self.provider,
                requested_max_tokens=int(requested_tokens),
            )
            raise
        except PermanentError:
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
            grammar_requested=bool(grammar_path),
            prompt_tokens=budget_info.get("prompt_tokens"),
            effective_max_tokens=budget_info.get("effective_max_tokens"),
            token_budget=budget_info,
        )

        _tracer = self._get_tracer()
        _llm_span_ctx = (
            _tracer.start_as_current_span(
                "llm.call",
                attributes={
                    "llm.provider": self.provider,
                    "llm.model": (
                        settings.LLM_OLLAMA_MODEL if self.provider == "ollama"
                        else settings.LLM_OPENAI_MODEL if self.provider == "openai"
                        else str(getattr(settings, "LLM_LOCAL_MODEL_PATH", "unknown"))
                    ),
                    "llm.temperature": float(temp),
                    "llm.max_tokens": int(tokens),
                },
            )
            if _tracer is not None
            else __import__("contextlib").nullcontext()
        )

        start_time = time.time()
        error_type_for_metrics: str | None = None
        result: LLMResponse | None = None
        _last_exc: Exception | None = None

        with _llm_span_ctx as _llm_span:
            try:
                if self.provider == "openai":
                    result = self._call_openai(prompt, temp, tokens)
                elif self.provider == "ollama":
                    result = self._call_ollama(
                        prompt, temp, tokens,
                        response_format=response_format,
                    )
                elif self.provider == "llamacpp":
                    result = self._call_llamacpp(prompt, temp, tokens, grammar_path=grammar_path)
                else:
                    logger.warning("Unknown LLM provider", provider=self.provider)
                    error_type_for_metrics = "unknown_provider"
                    result = None
            except httpx.TimeoutException as e:
                logger.warning("LLM call timed out", provider=self.provider)
                error_type_for_metrics = "timeout"
                _last_exc = e
                raise TransientError(f"LLM timeout ({self.provider})")
            except httpx.ConnectError as e:
                logger.warning("LLM connection failed", provider=self.provider)
                error_type_for_metrics = "connect_error"
                _last_exc = e
                raise TransientError(f"LLM connection failed ({self.provider})")
            except TransientError as e:
                error_type_for_metrics = "transient_error"
                _last_exc = e
                raise
            except PermanentError as e:
                error_type_for_metrics = "permanent_error"
                _last_exc = e
                raise
            except Exception as e:
                logger.error("LLM call failed", provider=self.provider, error=str(e))
                error_type_for_metrics = "unexpected_error"
                _last_exc = e
                result = None
            finally:
                duration = time.time() - start_time
                duration_ms = int(duration * 1000)

                if _llm_span is not None:
                    self._enrich_llm_span(
                        span=_llm_span,
                        result=result,
                        duration_ms=duration_ms,
                        error_type=error_type_for_metrics,
                        exc=_last_exc,
                    )

                try:
                    METRICS.llm_request_duration_seconds.labels(
                        provider=self.provider
                    ).observe(duration)
                    METRICS.llm_requests_total.labels(
                        provider=self.provider,
                        error_type=error_type_for_metrics or "none",
                    ).inc()
                    if error_type_for_metrics == "timeout":
                        METRICS.llm_timeout_total.labels(provider=self.provider).inc()
                    if isinstance(result, LLMResponse):
                        METRICS.llm_tokens_total.labels(
                            provider=self.provider,
                        ).inc(result.tokens_used)
                except Exception:
                    logger.exception("LLMClient: failed to update LLM metrics")

        return result

    def call_with_retries(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: str | None = None,
        max_retries: int | None = None,
        response_format: str | None = None,
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызов LLM с повторами при временных ошибках (sync).

        Порядок обработки исключений:
        - LLMContextLimitError → no retry (permanent, контекст не уменьшится)
        - PermanentError       → no retry
        - TransientError       → retry с exponential backoff + jitter
        - Exception            → no retry

        Возвращает:
            (response_or_none, error_details_dict)

        error_details содержит:
            llm_attempts:  число реальных попыток
            error_type:    None | 'context_limit' | 'permanent_error' |
                           'transient_error' | 'unexpected_error' | 'unavailable'
            error_message: текст ошибки (если была)

        Backoff (sync):
            Использует time.sleep() — корректно для Celery workers.
            НЕ вызывать из async-контекста (блокирует event loop).
            Для async используйте call_with_retries_async().
        """
        attempts = 0
        last_error_type: str | None = None
        last_error_message: str | None = None

        # ИСПРАВЛЕНО: используем settings.LLM_MAX_RETRIES (typed field),
        # а не getattr(settings, "LLM_MAX_RETRIES", 2) (phantom setting).
        retries = (
            max_retries if max_retries is not None else self._default_max_retries
        )

        while True:
            try:
                attempts += 1
                response = self.call(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grammar_path=grammar_path,
                    response_format=response_format,
                )

                if response is None:
                    return None, {
                        "llm_attempts": attempts,
                        "error_type": "unavailable",
                        "error_message": "LLM provider is not available",
                    }

                return response, {
                    "llm_attempts": attempts,
                    "error_type": None,
                    "error_message": None,
                }

            except LLMContextLimitError as e:
                # Контекстный лимит: retry бессмысленен.
                # Важно поймать ДО общего PermanentError.
                logger.warning(
                    "LLMClient context limit exceeded, no retries",
                    provider=self.provider,
                    attempt=attempts,
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": "context_limit",
                    "error_message": str(e),
                }

            except TransientError as e:
                last_error_type = "transient_error"
                last_error_message = str(e)

                if attempts > retries:
                    # Retries исчерпаны — выходим из цикла.
                    break

                # =============================================================
                # ИСПРАВЛЕНО: exponential backoff + jitter перед retry.
                #
                # Ранее: немедленный continue (нулевая пауза).
                # Теперь: задержка растёт экспоненциально с каждой попыткой,
                # ограничена LLM_RETRY_MAX_DELAY_SECONDS.
                # Jitter разбрасывает retry N воркеров во времени.
                #
                # time.sleep() корректен в sync Celery worker контексте.
                # Для async используется call_with_retries_async().
                # =============================================================
                delay = _compute_backoff_delay(
                    attempt=attempts,
                    base=settings.LLM_RETRY_BASE_DELAY_SECONDS,
                    cap=settings.LLM_RETRY_MAX_DELAY_SECONDS,
                    jitter_range=settings.LLM_RETRY_JITTER_SECONDS,
                )
                logger.warning(
                    "LLMClient transient error, retrying with backoff",
                    provider=self.provider,
                    attempt=attempts,
                    max_retries=retries,
                    delay_seconds=round(delay, 2),
                    error=str(e),
                )
                time.sleep(delay)

            except PermanentError as e:
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

        # Retries исчерпаны на transient ошибках.
        return None, {
            "llm_attempts": attempts,
            "error_type": last_error_type or "transient_error",
            "error_message": last_error_message,
        }

    # =========================================================================
    # Async API
    # =========================================================================

    def _get_llamacpp_semaphore(self) -> asyncio.Semaphore:
        """Semaphore(1) для сериализации вызовов llamacpp."""
        if self._llamacpp_semaphore is None:
            self._llamacpp_semaphore = asyncio.Semaphore(1)
        return self._llamacpp_semaphore

    def _register_llamacpp_inflight_future(self, future: Any) -> None:
        """Зарегистрировать in-flight future llamacpp-вызова."""
        self._llamacpp_inflight_futures.add(future)

        def _cleanup(done_future: Any) -> None:
            self._llamacpp_inflight_futures.discard(done_future)

        future.add_done_callback(_cleanup)

    def _count_active_llamacpp_futures(self) -> int:
        """Посчитать реально активные llamacpp futures."""
        return sum(
            1 for future in self._llamacpp_inflight_futures
            if not future.done()
        )

    async def _call_openai_async(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """Async OpenAI call через httpx.AsyncClient."""
        url = f"{settings.LLM_OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.LLM_OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        body = {
            "model": settings.LLM_OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=body, headers=headers)

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
        usage = data.get("usage", {}) or {}

        result = LLMResponse(
            text=text,
            provider="openai",
            model=settings.LLM_OPENAI_MODEL,
            tokens_used=tokens_used,
            raw_response=data,
            prompt_tokens=_safe_non_negative_int(usage.get("prompt_tokens")),
            completion_tokens=_safe_non_negative_int(usage.get("completion_tokens")),
        )
        return _parse_llm_response(result)

    async def _call_ollama_async(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Async Ollama call через httpx.AsyncClient."""
        url = f"{settings.LLM_OLLAMA_BASE_URL}/api/generate"
        body: dict = {
            "model": settings.LLM_OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": settings.LLM_CONTEXT_LIMIT,
            },
        }

        if response_format == "json_object":
            body["format"] = "json"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(url, json=body)

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

        _ollama_pt = _safe_non_negative_int(data.get("prompt_eval_count")) or 0
        _ollama_ct = _safe_non_negative_int(data.get("eval_count")) or 0

        result = LLMResponse(
            text=text,
            provider="ollama",
            model=settings.LLM_OLLAMA_MODEL,
            tokens_used=_ollama_pt + _ollama_ct,
            raw_response=data,
            prompt_tokens=_safe_non_negative_int(data.get("prompt_eval_count")),
            completion_tokens=_safe_non_negative_int(data.get("eval_count")),
        )
        return _parse_llm_response(result)

    async def _call_llamacpp_async(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        grammar_path: str | None = None,
    ) -> LLMResponse:
        """
        Async llamacpp через run_in_executor + Semaphore(1).

        asyncio.shield() предотвращает освобождение semaphore при отмене,
        пока native inference физически выполняется в thread pool.
        """
        sem = self._get_llamacpp_semaphore()
        loop = asyncio.get_running_loop()

        async with sem:
            future = loop.run_in_executor(
                None,
                lambda: self._call_llamacpp(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grammar_path=grammar_path,
                ),
            )
            self._register_llamacpp_inflight_future(future)

            try:
                return await asyncio.shield(future)
            except asyncio.CancelledError:
                logger.warning(
                    "LLM llamacpp async call cancelled; waiting for in-flight native inference to finish",
                    provider=self.provider,
                    pid=os.getpid(),
                )
                try:
                    await asyncio.shield(future)
                except Exception as exec_exc:
                    logger.warning(
                        "LLM llamacpp in-flight call finished with exception during cancellation drain",
                        provider=self.provider,
                        pid=os.getpid(),
                        error=str(exec_exc),
                    )
                raise

    async def call_async(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: str | None = None,
        response_format: str | None = None,
    ) -> LLMResponse | None:
        """Async версия call() — один вызов без retry."""
        if response_format not in _VALID_RESPONSE_FORMATS:
            raise PermanentError(
                f"Invalid response_format={response_format!r}. "
                f"Valid values: {set(_VALID_RESPONSE_FORMATS)}"
            )

        if self.provider == "none" or not self.is_available():
            return None

        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        requested_tokens = (
            max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        )

        try:
            tokens, budget_info = self._compute_token_budget(
                prompt=prompt,
                requested_max_tokens=int(requested_tokens),
            )
        except LLMContextLimitError:
            logger.warning(
                "LLM async call aborted: context limit exceeded",
                provider=self.provider,
                requested_max_tokens=int(requested_tokens),
            )
            raise
        except PermanentError:
            raise

        so_strategy = _resolve_structured_output_strategy(
            self.provider, response_format, grammar_path,
        )

        logger.info(
            "LLM async call",
            provider=self.provider,
            temperature=temp,
            max_tokens=tokens,
            prompt_preview=prompt[:200],
            grammar_requested=bool(grammar_path),
            response_format_requested=response_format,
            structured_output_strategy=so_strategy,
            prompt_tokens=budget_info.get("prompt_tokens"),
            effective_max_tokens=budget_info.get("effective_max_tokens"),
        )

        _tracer = self._get_tracer()
        _llm_span_ctx = (
            _tracer.start_as_current_span(
                "llm.call",
                attributes={
                    "llm.provider": self.provider,
                    "llm.model": (
                        settings.LLM_OLLAMA_MODEL if self.provider == "ollama"
                        else settings.LLM_OPENAI_MODEL if self.provider == "openai"
                        else str(getattr(settings, "LLM_LOCAL_MODEL_PATH", "unknown"))
                    ),
                    "llm.temperature": float(temp),
                    "llm.max_tokens": int(tokens),
                },
            )
            if _tracer is not None
            else __import__("contextlib").nullcontext()
        )

        start_time = time.time()
        error_type_for_metrics: str | None = None
        result: LLMResponse | None = None
        _last_exc: Exception | None = None

        with _llm_span_ctx as _llm_span:
            try:
                if self.provider == "openai":
                    result = await self._call_openai_async(prompt, temp, tokens)
                elif self.provider == "ollama":
                    result = await self._call_ollama_async(
                        prompt, temp, tokens,
                        response_format=response_format,
                    )
                elif self.provider == "llamacpp":
                    result = await self._call_llamacpp_async(
                        prompt, temp, tokens, grammar_path=grammar_path
                    )
                else:
                    logger.warning(
                        "Unknown LLM provider (async)", provider=self.provider
                    )
                    error_type_for_metrics = "unknown_provider"
                    result = None
            except httpx.TimeoutException as e:
                logger.warning("LLM async call timed out", provider=self.provider)
                error_type_for_metrics = "timeout"
                _last_exc = e
                raise TransientError(f"LLM timeout ({self.provider})")
            except httpx.ConnectError as e:
                logger.warning("LLM async connection failed", provider=self.provider)
                error_type_for_metrics = "connect_error"
                _last_exc = e
                raise TransientError(f"LLM connection failed ({self.provider})")
            except TransientError as e:
                error_type_for_metrics = "transient_error"
                _last_exc = e
                raise
            except PermanentError as e:
                error_type_for_metrics = "permanent_error"
                _last_exc = e
                raise
            except Exception as e:
                logger.error(
                    "LLM async call failed", provider=self.provider, error=str(e)
                )
                error_type_for_metrics = "unexpected_error"
                _last_exc = e
                result = None
            finally:
                duration = time.time() - start_time
                duration_ms = int(duration * 1000)

                if _llm_span is not None:
                    self._enrich_llm_span(
                        span=_llm_span,
                        result=result,
                        duration_ms=duration_ms,
                        error_type=error_type_for_metrics,
                        exc=_last_exc,
                    )

                try:
                    METRICS.llm_request_duration_seconds.labels(
                        provider=self.provider
                    ).observe(duration)
                    METRICS.llm_requests_total.labels(
                        provider=self.provider,
                        error_type=error_type_for_metrics or "none",
                    ).inc()
                    if error_type_for_metrics == "timeout":
                        METRICS.llm_timeout_total.labels(provider=self.provider).inc()
                    if isinstance(result, LLMResponse):
                        METRICS.llm_tokens_total.labels(
                            provider=self.provider,
                        ).inc(result.tokens_used)
                except Exception:
                    logger.exception(
                        "LLMClient: failed to update LLM metrics (async)"
                    )

        return result

    async def call_with_retries_async(
        self,
        prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
        grammar_path: str | None = None,
        max_retries: int | None = None,
        response_format: str | None = None,
    ) -> tuple[LLMResponse | None, dict]:
        """
        Async версия call_with_retries().

        Та же retry логика, но через await call_async().
        Backoff использует asyncio.sleep() — не блокирует event loop.

        Возвращает (response_or_none, error_details_dict).
        """
        attempts = 0
        last_error_type: str | None = None
        last_error_message: str | None = None

        # ИСПРАВЛЕНО: используем settings.LLM_MAX_RETRIES (typed field).
        retries = (
            max_retries if max_retries is not None else self._default_max_retries
        )

        while True:
            try:
                attempts += 1
                response = await self.call_async(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grammar_path=grammar_path,
                    response_format=response_format,
                )

                if response is None:
                    return None, {
                        "llm_attempts": attempts,
                        "error_type": "unavailable",
                        "error_message": "LLM provider is not available",
                    }

                return response, {
                    "llm_attempts": attempts,
                    "error_type": None,
                    "error_message": None,
                }

            except LLMContextLimitError as e:
                logger.warning(
                    "LLMClient async context limit exceeded, no retries",
                    provider=self.provider,
                    attempt=attempts,
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": "context_limit",
                    "error_message": str(e),
                }

            except TransientError as e:
                last_error_type = "transient_error"
                last_error_message = str(e)

                if attempts > retries:
                    break

                # =============================================================
                # ИСПРАВЛЕНО: exponential backoff + jitter перед async retry.
                #
                # Ранее: немедленный continue (нулевая пауза).
                # Теперь: asyncio.sleep() — не блокирует event loop,
                # освобождает для других coroutine во время ожидания.
                # =============================================================
                delay = _compute_backoff_delay(
                    attempt=attempts,
                    base=settings.LLM_RETRY_BASE_DELAY_SECONDS,
                    cap=settings.LLM_RETRY_MAX_DELAY_SECONDS,
                    jitter_range=settings.LLM_RETRY_JITTER_SECONDS,
                )
                logger.warning(
                    "LLMClient async transient error, retrying with backoff",
                    provider=self.provider,
                    attempt=attempts,
                    max_retries=retries,
                    delay_seconds=round(delay, 2),
                    error=str(e),
                )
                await asyncio.sleep(delay)

            except PermanentError as e:
                last_error_type = "permanent_error"
                last_error_message = str(e)
                logger.warning(
                    "LLMClient async permanent error, no retries",
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
                last_error_type = "unexpected_error"
                last_error_message = str(e)
                logger.error(
                    "LLMClient async unexpected exception",
                    provider=self.provider,
                    attempt=attempts,
                    error=str(e),
                )
                return None, {
                    "llm_attempts": attempts,
                    "error_type": last_error_type,
                    "error_message": last_error_message,
                }

        return None, {
            "llm_attempts": attempts,
            "error_type": last_error_type or "transient_error",
            "error_message": last_error_message,
        }

    # =========================================================================
    # Provider implementations (без изменений)
    # =========================================================================

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
            "messages": [{"role": "user", "content": prompt}],
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
        usage = data.get("usage", {}) or {}

        result = LLMResponse(
            text=text,
            provider="openai",
            model=settings.LLM_OPENAI_MODEL,
            tokens_used=tokens_used,
            raw_response=data,
            prompt_tokens=_safe_non_negative_int(usage.get("prompt_tokens")),
            completion_tokens=_safe_non_negative_int(usage.get("completion_tokens")),
        )
        return _parse_llm_response(result)

    def _call_ollama(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        response_format: str | None = None,
    ) -> LLMResponse:
        """Call Ollama local API."""
        url = f"{settings.LLM_OLLAMA_BASE_URL}/api/generate"
        body: dict = {
            "model": settings.LLM_OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": settings.LLM_CONTEXT_LIMIT,
            },
        }

        if response_format == "json_object":
            body["format"] = "json"

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

        _ollama_pt = _safe_non_negative_int(data.get("prompt_eval_count")) or 0
        _ollama_ct = _safe_non_negative_int(data.get("eval_count")) or 0

        result = LLMResponse(
            text=text,
            provider="ollama",
            model=settings.LLM_OLLAMA_MODEL,
            tokens_used=_ollama_pt + _ollama_ct,
            raw_response=data,
            prompt_tokens=_safe_non_negative_int(data.get("prompt_eval_count")),
            completion_tokens=_safe_non_negative_int(data.get("eval_count")),
        )
        return _parse_llm_response(result)

    def _call_llamacpp(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
        grammar_path: str | None = None,
    ) -> LLMResponse:
        """Call local model via llama-cpp-python."""
        model_path = settings.LLM_LOCAL_MODEL_PATH
        if not model_path:
            raise PermanentError("LLM_LOCAL_MODEL_PATH is not set for llamacpp provider")

        normalized = model_path.replace("\\", "/")
        if not os.path.exists(normalized):
            raise PermanentError(f"Model file does not exist: {normalized} (LLM_LOCAL_MODEL_PATH)")

        if self._llama_model is None:
            logger.info(
                "LLMClient: загрузка модели с диска (первый вызов в этом процессе)",
                extra={"pid": os.getpid()},
            )

            try:
                from llama_cpp import Llama
            except ImportError as e:
                raise PermanentError(
                    "llama-cpp-python is not installed. Install it or switch LLM_PROVIDER."
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
            logger.info(
                "LLMClient: модель загружена успешно",
                extra={"pid": os.getpid()},
            )

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
                    with open(grammar_path, encoding="utf-8") as f:
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
        usage = output.get("usage", {}) or {}

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
            prompt_tokens=_safe_non_negative_int(usage.get("prompt_tokens")),
            completion_tokens=_safe_non_negative_int(usage.get("completion_tokens")),
        )
        return _parse_llm_response(result)


# =============================================================================
# Response parsing (без изменений)
# =============================================================================

def _parse_llm_response(response: LLMResponse) -> LLMResponse:
    """
    Parse LLM response text to extract structured data.

    Expects JSON: {"found": bool, "evidence": str, "clause": str, "confidence": float}
    Falls back to text analysis if JSON parsing fails.
    """
    text = response.text.strip()
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
        text_lower = text.lower()
        if any(w in text_lower for w in ["yes", "да", "found", "найден", "true"]):
            response.found = True
        elif any(w in text_lower for w in ["no", "нет", "not found", "не найден", "false"]):
            response.found = False
        else:
            response.found = None

        response.evidence = text[:500]
        response.confidence = 0.5
        response.parse_success = False

    return response


def _extract_json(text: str) -> dict | None:
    """
    Extract JSON object from LLM response text.

    Handles: pure JSON, markdown code blocks, JSON embedded in text.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    brace_match = re.search(r"\{.*\}", text, re.DOTALL)
    if brace_match:
        candidate = brace_match.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None

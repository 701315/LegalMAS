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
import re
import time
import asyncio
import gc

from dataclasses import dataclass, field
from typing import Any

import httpx

from core.config import settings
from core.exceptions import PermanentError, TransientError
from core.logging import get_logger
from engine.retrieval.tokenization import count_tokens
from ops.metrics import METRICS

logger = get_logger(__name__)


class LLMContextLimitError(PermanentError):
    """
    Prompt + max_tokens превышают контекстное окно модели.

    Отличается от общего PermanentError тем, что:
    - не требует ретраев (контекст не уменьшится сам по себе);
    - вызывающий код (HybridDetector) выставляет llm_error_type='context_limit'
      и может корректно сформировать execution_status=FAILED.
    """


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
        self.provider = settings.LLM_PROVIDER  # "none" | "openai" | "ollama" | "llamacpp"
        self.timeout = settings.LLM_TIMEOUT_SECONDS
        self._llama_model: Any = None
        self._llama_grammar_cache: dict[str, Any] = {}
        self._llamacpp_semaphore: asyncio.Semaphore | None = None
        # Futures активных llamacpp-вызовов, запущенных через run_in_executor.
        # Нужны для безопасного reset: нельзя закрывать native runtime,
        # пока хотя бы один inference ещё физически выполняется.
        self._llamacpp_inflight_futures: set[Any] = set()


    # - 0 означает «ровно один вызов без ретраев»;
    # - 2 означает «до трёх вызовов: первая попытка + 2 повтора».
    _DEFAULT_MAX_RETRIES = getattr(settings, "LLM_MAX_RETRIES", 2)

    def is_available(self) -> bool:
        """Check if any LLM provider is configured."""
        return self.provider in ("openai", "ollama", "llamacpp")


    def reset_local_runtime_state(self) -> None:
        """
        Сбросить process-local runtime state для llama-cpp.

        Важно:
        - reset безопасен только если в процессе нет активных in-flight
          llamacpp-вызовов, запущенных через run_in_executor;
        - если такой вызов ещё работает, закрывать native runtime нельзя:
          это может привести к SIGSEGV.

        Что сбрасывается:
        - self._llama_model
        - self._llama_grammar_cache

        Для non-llamacpp provider метод ничего не делает.
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
        """
        Best-effort обёртка над reset_local_runtime_state().

        Никогда не бросает исключение наружу — cleanup не должен ломать
        основную задачу worker-а.
        """
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

        Вызывающий код (LLMDetector) отвечает за то, чтобы prompt был правильного размера.
        Этот метод только проверяет финальный инвариант и выбрасывает LLMContextLimitError.
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
    ) -> LLMResponse | None:
        """
        Call the configured LLM provider.

        grammar_path:
            Optional path to a GBNF grammar file (used for llama-cpp).
            For OpenAI/Ollama сейчас игнорируется (можно расширить позже).

        Returns:
            LLMResponse or None if LLM is not available/failed.

        Raises:
            LLMContextLimitError: если prompt превышает контекстное окно.
                                  Вызывающий код должен поймать это и выставить
                                  error_type='context_limit', не делать retry.
            TransientError: таймаут / сетевая ошибка — можно повторить.
            PermanentError: прочие постоянные ошибки — retry бессмысленен.
        """
        if self.provider == "none" or not self.is_available():
            return None

        temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        requested_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS

        # ── Жёсткий budget: останавливаем вызов до обращения к модели ──────
        # LLMContextLimitError — подкласс PermanentError, поэтому порядок важен:
        # сначала ловим специфичный, затем общий.
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
            raise  # пробрасываем как LLMContextLimitError, не теряем тип
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
                result = self._call_openai(prompt, temp, tokens)
            elif self.provider == "ollama":
                result = self._call_ollama(prompt, temp, tokens)
            elif self.provider == "llamacpp":
                result = self._call_llamacpp(prompt, temp, tokens, grammar_path=grammar_path)
            else:
                logger.warning("Unknown LLM provider", provider=self.provider)
                error_type_for_metrics = "unknown_provider"
                result = None
        except httpx.TimeoutException:
            logger.warning("LLM call timed out", provider=self.provider)
            error_type_for_metrics = "timeout"
            raise TransientError(f"LLM timeout ({self.provider})")
        except httpx.ConnectError:
            logger.warning("LLM connection failed", provider=self.provider)
            error_type_for_metrics = "connect_error"
            raise TransientError(f"LLM connection failed ({self.provider})")
        except TransientError:
            error_type_for_metrics = "transient_error"
            raise
        except PermanentError:
            error_type_for_metrics = "permanent_error"
            raise
        except Exception as e:
            logger.error("LLM call failed", provider=self.provider, error=str(e))
            error_type_for_metrics = "unexpected_error"
            result = None
        finally:
            duration = time.time() - start_time
            try:
                METRICS.llm_request_duration_seconds.labels(provider=self.provider).observe(
                    duration
                )
                METRICS.llm_requests_total.labels(
                    provider=self.provider,
                    error_type=error_type_for_metrics or "none",
                ).inc()
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
    ) -> tuple[LLMResponse | None, dict]:
        """
        Вызов LLM с повторами при временных ошибках.

        Порядок обработки исключений важен:
        - LLMContextLimitError (подкласс PermanentError) — ловим первым,
          возвращаем error_type='context_limit' без retry;
        - PermanentError — ловим вторым, возвращаем error_type='permanent_error';
        - TransientError — retry до max_retries;
        - Exception — не повторяем, возвращаем error_type='unexpected_error'.

        Возвращает:
            (response_or_none, error_details_dict)

        error_details содержит:
        - llm_attempts: сколько реальных попыток было сделано;
        - error_type: None | 'context_limit' | 'permanent_error' |
                      'transient_error' | 'unexpected_error' | 'unavailable';
        - error_message: текст ошибки (если была).
        """
        attempts = 0
        last_error_type: str | None = None
        last_error_message: str | None = None

        retries = (
            max_retries if max_retries is not None else getattr(settings, "LLM_MAX_RETRIES", 2)
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
                # ── Контекстный лимит: retry бессмысленен, промпт не изменится ──
                # Важно поймать ДО общего PermanentError, иначе тип потеряется.
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
                logger.warning(
                    "LLMClient transient error, will retry if attempts left",
                    provider=self.provider,
                    attempt=attempts,
                    max_retries=retries,
                    error=str(e),
                )
                if attempts > retries:
                    break
                continue

            except PermanentError as e:
                # Общие постоянные ошибки (не context_limit).
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

        # Исчерпали retries на transient ошибках.
        return None, {
            "llm_attempts": attempts,
            "error_type": last_error_type or "transient_error",
            "error_message": last_error_message,
        }


    # =========================================================================
    # Phase 14.1: Async API
    # Добавлено рядом со sync API. Sync методы сохранены без изменений.
    # llamacpp: не блокирует event loop через run_in_executor + Semaphore(1).
    # ollama/openai: реальный async I/O через httpx.AsyncClient.
    # =========================================================================

    def _get_llamacpp_semaphore(self) -> asyncio.Semaphore:
        """
        Semaphore(1) для сериализации вызовов llamacpp.

        llamacpp (_llama_model) не является thread-safe для
        параллельных инференсов. Semaphore(1) гарантирует что в любой
        момент времени через run_in_executor выполняется не более
        одного вызова модели.

        Создаётся лениво при первом async вызове — не в __init__,
        потому что event loop может ещё не существовать в момент
        создания LLMClient singleton.
        """
        if self._llamacpp_semaphore is None:
            self._llamacpp_semaphore = asyncio.Semaphore(1)
        return self._llamacpp_semaphore


    def _register_llamacpp_inflight_future(self, future: Any) -> None:
        """
        Зарегистрировать in-flight future llamacpp-вызова.

        Future удаляется из реестра автоматически после завершения.
        """
        self._llamacpp_inflight_futures.add(future)

        def _cleanup(done_future: Any) -> None:
            self._llamacpp_inflight_futures.discard(done_future)

        future.add_done_callback(_cleanup)

    def _count_active_llamacpp_futures(self) -> int:
        """
        Посчитать реально активные llamacpp futures.

        done()-futures не считаются активными.
        """
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
        """
        Async OpenAI call через httpx.AsyncClient.

        Идентична sync _call_openai() по логике,
        но не блокирует event loop во время сетевого I/O.
        """
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

        result = LLMResponse(
            text=text,
            provider="openai",
            model=settings.LLM_OPENAI_MODEL,
            tokens_used=tokens_used,
            raw_response=data,
        )
        return _parse_llm_response(result)

    async def _call_ollama_async(
        self,
        prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> LLMResponse:
        """
        Async Ollama call через httpx.AsyncClient.

        Идентична sync _call_ollama() по логике,
        но не блокирует event loop во время сетевого I/O.
        """
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

        result = LLMResponse(
            text=text,
            provider="ollama",
            model=settings.LLM_OLLAMA_MODEL,
            raw_response=data,
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

        Важная деталь:
        - native llamacpp-вызов нельзя безопасно "оборвать" через asyncio cancel;
        - поэтому при отмене outer coroutine мы не отпускаем semaphore сразу,
          а дожидаемся завершения in-flight executor future;
        - это предотвращает гонку, когда runtime закрывают или переиспользуют,
          пока native inference ещё физически работает в thread pool.
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
                    # Дожидаемся фактического завершения native inference,
                    # чтобы не освободить semaphore и не допустить unsafe reset.
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
    ) -> LLMResponse | None:
        """
        Async версия call().

        Provider routing:
        - llamacpp → _call_llamacpp_async() (run_in_executor + Semaphore)
        - ollama   → _call_ollama_async()   (httpx.AsyncClient)
        - openai   → _call_openai_async()   (httpx.AsyncClient)

        Raises:
            LLMContextLimitError: prompt превышает контекстное окно.
            TransientError: таймаут / сетевая ошибка.
            PermanentError: постоянные ошибки.
        """
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

        logger.info(
            "LLM async call",
            provider=self.provider,
            temperature=temp,
            max_tokens=tokens,
            prompt_preview=prompt[:200],
            grammar_enabled=bool(grammar_path),
            prompt_tokens=budget_info.get("prompt_tokens"),
            effective_max_tokens=budget_info.get("effective_max_tokens"),
        )

        start_time = time.time()
        error_type_for_metrics: str | None = None
        result: LLMResponse | None = None

        try:
            if self.provider == "openai":
                result = await self._call_openai_async(prompt, temp, tokens)
            elif self.provider == "ollama":
                result = await self._call_ollama_async(prompt, temp, tokens)
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
        except httpx.TimeoutException:
            logger.warning("LLM async call timed out", provider=self.provider)
            error_type_for_metrics = "timeout"
            raise TransientError(f"LLM timeout ({self.provider})")
        except httpx.ConnectError:
            logger.warning(
                "LLM async connection failed", provider=self.provider
            )
            error_type_for_metrics = "connect_error"
            raise TransientError(f"LLM connection failed ({self.provider})")
        except TransientError:
            error_type_for_metrics = "transient_error"
            raise
        except PermanentError:
            error_type_for_metrics = "permanent_error"
            raise
        except Exception as e:
            logger.error(
                "LLM async call failed", provider=self.provider, error=str(e)
            )
            error_type_for_metrics = "unexpected_error"
            result = None
        finally:
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
    ) -> tuple[LLMResponse | None, dict]:
        """
        Async версия call_with_retries().

        Та же retry логика (context_limit → no retry, transient → retry,
        permanent → no retry), но через await call_async().

        Возвращает (response_or_none, error_details_dict).
        error_details содержит: llm_attempts, error_type, error_message.
        """
        attempts = 0
        last_error_type: str | None = None
        last_error_message: str | None = None

        retries = (
            max_retries
            if max_retries is not None
            else getattr(settings, "LLM_MAX_RETRIES", 2)
        )

        while True:
            try:
                attempts += 1
                response = await self.call_async(
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    grammar_path=grammar_path,
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
                logger.warning(
                    "LLMClient async transient error, will retry if attempts left",
                    provider=self.provider,
                    attempt=attempts,
                    max_retries=retries,
                    error=str(e),
                )
                if attempts > retries:
                    break
                continue

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
                extra={"pid": __import__("os").getpid()},
            )

            try:
                from llama_cpp import Llama
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
            logger.info(
                "LLMClient: модель загружена успешно",
                extra={"pid": __import__("os").getpid()},
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

    Handles:
    - Pure JSON: {"found": true}
    - JSON in markdown: ```json\n{"found": true}\n```
    - JSON embedded in text: Some text {"found": true} more text
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

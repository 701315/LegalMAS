"""
Fallback Chain — tries multiple providers in order of preference.

Used by the Runner to handle LLM unavailability gracefully:
    1. Cloud LLM (via circuit breaker)
    2. Local LLM (via circuit breaker)
    3. Rules-only (deterministic, no CB)
    4. UNCLEAR result (last resort)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core.circuit_breaker import CBState, CircuitBreaker
from core.exceptions import CircuitOpenError
from core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class FallbackResult:
    """Result from the fallback chain."""

    value: Any  # The actual result
    provider_used: str  # Which provider produced this result
    fallback_used: bool = False  # Was a fallback used?
    providers_tried: list[str] = field(default_factory=list)
    providers_failed: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


@dataclass
class FallbackProvider:
    """A single provider in the fallback chain."""

    name: str  # Human-readable name
    func: Callable  # The function to call
    circuit_breaker: CircuitBreaker | None = None  # Optional CB protection


class FallbackChain:
    """
    Tries providers in order until one succeeds.

    Usage:
        chain = FallbackChain(
            providers=[
                FallbackProvider("cloud_llm", call_openai, CircuitBreaker("openai")),
                FallbackProvider("local_llm", call_local, CircuitBreaker("local")),
                FallbackProvider("rules", apply_rules),  # No CB for deterministic
            ],
            default_result={"result": "unclear"},
            default_flags=["needs_manual_review"],
        )

        result = chain.execute(prompt="Analyze this clause...")
    """

    def __init__(
        self,
        providers: list[FallbackProvider],
        default_result: Any = None,
        default_flags: list[str] | None = None,
    ):
        self.providers = providers
        self.default_result = default_result
        self.default_flags = default_flags or ["needs_manual_review"]

    def execute(self, *args, **kwargs) -> FallbackResult:
        """
        Try each provider in order. Return result from the first that succeeds.
        If all fail, return default_result with flags.
        """
        providers_tried = []
        providers_failed = []

        for provider in self.providers:
            providers_tried.append(provider.name)

            # Check circuit breaker state before even trying
            if provider.circuit_breaker and provider.circuit_breaker.state == CBState.OPEN:
                logger.debug(
                    "Skipping provider — circuit breaker OPEN",
                    provider=provider.name,
                )
                providers_failed.append(provider.name)
                continue

            try:
                if provider.circuit_breaker:
                    result = provider.circuit_breaker.execute(provider.func, *args, **kwargs)
                else:
                    result = provider.func(*args, **kwargs)

                is_fallback = len(providers_tried) > 1

                if is_fallback:
                    logger.info(
                        "Fallback provider succeeded",
                        provider=provider.name,
                        tried=providers_tried,
                        failed=providers_failed,
                    )

                return FallbackResult(
                    value=result,
                    provider_used=provider.name,
                    fallback_used=is_fallback,
                    providers_tried=providers_tried,
                    providers_failed=providers_failed,
                    flags=["llm_fallback_used"] if is_fallback else [],
                )

            except CircuitOpenError:
                logger.debug(
                    "Provider circuit opened during call",
                    provider=provider.name,
                )
                providers_failed.append(provider.name)
                continue

            except Exception as e:
                logger.warning(
                    "Provider failed",
                    provider=provider.name,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                providers_failed.append(provider.name)
                continue

        # All providers failed
        logger.error(
            "All providers failed — returning default",
            tried=providers_tried,
            failed=providers_failed,
        )

        return FallbackResult(
            value=self.default_result,
            provider_used="default",
            fallback_used=True,
            providers_tried=providers_tried,
            providers_failed=providers_failed,
            flags=self.default_flags,
        )

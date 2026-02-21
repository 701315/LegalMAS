"""
Unit tests for FallbackChain.
"""

import pytest
import redis

from src.core.circuit_breaker import CircuitBreaker
from src.core.config import settings
from src.core.fallback import FallbackChain, FallbackProvider


@pytest.fixture
def redis_client():
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield r
    for key in r.keys("cb:fb_test_*"):
        r.delete(key)


def make_provider(name, return_value=None, raise_error=None, cb=None):
    """Helper: create a provider that returns a value or raises an error."""

    def func(*args, **kwargs):
        if raise_error:
            raise raise_error
        return return_value

    return FallbackProvider(name=name, func=func, circuit_breaker=cb)


class TestFallbackChain:
    def test_first_provider_succeeds(self):
        """Should return result from first provider when it works."""
        chain = FallbackChain(
            providers=[
                make_provider("primary", return_value="primary_result"),
                make_provider("secondary", return_value="secondary_result"),
            ],
        )

        result = chain.execute()
        assert result.value == "primary_result"
        assert result.provider_used == "primary"
        assert result.fallback_used is False
        assert result.flags == []

    def test_first_fails_second_succeeds(self):
        """Should fall back to second provider when first fails."""
        chain = FallbackChain(
            providers=[
                make_provider("primary", raise_error=ValueError("primary down")),
                make_provider("secondary", return_value="fallback_result"),
            ],
        )

        result = chain.execute()
        assert result.value == "fallback_result"
        assert result.provider_used == "secondary"
        assert result.fallback_used is True
        assert "primary" in result.providers_failed
        assert "llm_fallback_used" in result.flags

    def test_all_fail_returns_default(self):
        """Should return default when all providers fail."""
        chain = FallbackChain(
            providers=[
                make_provider("p1", raise_error=ValueError("down")),
                make_provider("p2", raise_error=RuntimeError("also down")),
            ],
            default_result={"result": "unclear"},
            default_flags=["needs_manual_review"],
        )

        result = chain.execute()
        assert result.value == {"result": "unclear"}
        assert result.provider_used == "default"
        assert result.fallback_used is True
        assert "needs_manual_review" in result.flags
        assert result.providers_failed == ["p1", "p2"]

    def test_passes_args_to_provider(self):
        """Should pass positional and keyword arguments to provider."""

        def adder(a, b):
            return a + b

        chain = FallbackChain(
            providers=[
                FallbackProvider(name="adder", func=adder),
            ],
        )

        result = chain.execute(3, 5)
        assert result.value == 8

    def test_skips_open_circuit_breaker(self, redis_client):
        """Should skip provider whose circuit breaker is OPEN."""
        cb = CircuitBreaker(
            name="fb_test_open",
            failure_threshold=1,
            redis_client=redis_client,
        )
        cb.reset()

        # Open the circuit
        cb.record_failure(Exception("down"))

        chain = FallbackChain(
            providers=[
                make_provider("guarded", return_value="never_reached", cb=cb),
                make_provider("backup", return_value="backup_result"),
            ],
        )

        result = chain.execute()
        assert result.value == "backup_result"
        assert result.provider_used == "backup"
        assert result.fallback_used is True
        assert "guarded" in result.providers_failed

    def test_providers_tried_tracking(self):
        """Should track which providers were tried."""
        chain = FallbackChain(
            providers=[
                make_provider("a", raise_error=ValueError("fail")),
                make_provider("b", raise_error=ValueError("fail")),
                make_provider("c", return_value="success"),
            ],
        )

        result = chain.execute()
        assert result.providers_tried == ["a", "b", "c"]
        assert result.providers_failed == ["a", "b"]
        assert result.provider_used == "c"

    def test_empty_chain_returns_default(self):
        """Should return default immediately if chain is empty."""
        chain = FallbackChain(
            providers=[],
            default_result="nothing",
            default_flags=["empty_chain"],
        )

        result = chain.execute()
        assert result.value == "nothing"
        assert "empty_chain" in result.flags

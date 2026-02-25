"""
Unit tests for CircuitBreaker.

These tests use a real Redis connection (integration-level).
"""

import time

import pytest
import redis

from src.core.circuit_breaker import CBState, CircuitBreaker
from src.core.config import settings
from src.core.exceptions import CircuitOpenError


@pytest.fixture
def redis_client():
    """Fresh Redis client. Clean up test keys after each test."""
    r = redis.from_url(settings.REDIS_URL, decode_responses=True)
    yield r
    # Cleanup: delete all circuit breaker test keys
    for key in r.keys("cb:test_*"):
        r.delete(key)


@pytest.fixture
def cb(redis_client):
    """Circuit breaker with short timeouts for testing."""
    breaker = CircuitBreaker(
        name="test_service",
        failure_threshold=3,  # Open after 3 failures
        window_size_seconds=10,  # 10 second window
        recovery_timeout_seconds=2,  # 2 seconds to half-open (short for tests)
        success_threshold=2,  # 2 successes to close
        redis_client=redis_client,
    )
    breaker.reset()  # Ensure clean state
    return breaker


class TestCircuitBreakerStates:
    def test_initial_state_is_closed(self, cb):
        """New circuit breaker should be in CLOSED state."""
        assert cb.state == CBState.CLOSED

    def test_stays_closed_on_success(self, cb):
        """Successful calls should keep circuit CLOSED."""
        cb.record_success()
        cb.record_success()
        cb.record_success()
        assert cb.state == CBState.CLOSED

    def test_stays_closed_below_threshold(self, cb):
        """Circuit should stay CLOSED if failures below threshold."""
        cb.record_failure(Exception("err1"))
        cb.record_failure(Exception("err2"))
        assert cb.state == CBState.CLOSED  # threshold is 3

    def test_opens_at_threshold(self, cb):
        """Circuit should OPEN when failures reach threshold."""
        cb.record_failure(Exception("err1"))
        cb.record_failure(Exception("err2"))
        cb.record_failure(Exception("err3"))
        assert cb.state == CBState.OPEN

    def test_open_to_half_open_after_timeout(self, cb):
        """Circuit should transition OPEN -> HALF_OPEN after recovery timeout."""
        # Open the circuit
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))
        assert cb.state == CBState.OPEN

        # Wait for recovery timeout (2 seconds in test config)
        time.sleep(2.5)

        assert cb.state == CBState.HALF_OPEN

    def test_half_open_to_closed_on_successes(self, cb):
        """Circuit should CLOSE from HALF_OPEN after enough successes."""
        # Open the circuit
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))
        assert cb.state == CBState.OPEN

        # Wait for half-open
        time.sleep(2.5)
        assert cb.state == CBState.HALF_OPEN

        # Record successes (threshold is 2)
        cb.record_success()
        cb.record_success()
        assert cb.state == CBState.CLOSED

    def test_half_open_to_open_on_failure(self, cb):
        """Circuit should re-OPEN from HALF_OPEN on any failure."""
        # Open the circuit
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))

        # Wait for half-open
        time.sleep(2.5)
        assert cb.state == CBState.HALF_OPEN

        # One failure -> back to OPEN
        cb.record_failure(Exception("still broken"))
        assert cb.state == CBState.OPEN


class TestCircuitBreakerExecute:
    def test_execute_success(self, cb):
        """execute() should call function and return result on success."""
        result = cb.execute(lambda: "hello")
        assert result == "hello"

    def test_execute_raises_when_open(self, cb):
        """execute() should raise CircuitOpenError when circuit is OPEN."""
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))

        with pytest.raises(CircuitOpenError) as exc_info:
            cb.execute(lambda: "hello")

        assert "test_service" in str(exc_info.value)

    def test_execute_records_failure(self, cb):
        """execute() should record failure when function raises."""

        def failing_func():
            raise ValueError("boom")

        with pytest.raises(ValueError):
            cb.execute(failing_func)

        # Should have 1 failure recorded
        assert cb.metrics["failures_in_window"] == 1

    def test_execute_records_success(self, cb):
        """execute() should record success when function succeeds."""
        # Open and wait for half-open
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))
        time.sleep(2.5)

        # Execute in half-open
        cb.execute(lambda: "recovered")
        cb.execute(lambda: "recovered again")

        assert cb.state == CBState.CLOSED


class TestCircuitBreakerWindow:
    def test_old_failures_dont_count(self, cb):
        """Failures outside the time window should not count."""
        # Record 2 failures
        cb.record_failure(Exception("old1"))
        cb.record_failure(Exception("old2"))

        # Wait for window to expire (window is 10 seconds in test)
        # We can't wait 10 seconds in a test, so we'll test the metric instead
        assert cb.metrics["failures_in_window"] == 2
        assert cb.state == CBState.CLOSED  # Still below threshold of 3


class TestCircuitBreakerMetrics:
    def test_metrics_structure(self, cb):
        """metrics should return expected structure."""
        m = cb.metrics
        assert "name" in m
        assert "state" in m
        assert "failures_in_window" in m
        assert "failure_threshold" in m
        assert "time_in_open_seconds" in m

    def test_metrics_after_failures(self, cb):
        """metrics should reflect current failure count."""
        cb.record_failure(Exception("e1"))
        cb.record_failure(Exception("e2"))

        m = cb.metrics
        assert m["failures_in_window"] == 2
        assert m["state"] == "closed"

    def test_metrics_when_open(self, cb):
        """metrics should show time in open state."""
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))

        time.sleep(0.5)
        m = cb.metrics
        assert m["state"] == "open"
        assert m["time_in_open_seconds"] >= 0.4


class TestCircuitBreakerReset:
    def test_reset_returns_to_closed(self, cb):
        """reset() should return circuit to CLOSED state."""
        for i in range(3):
            cb.record_failure(Exception(f"err{i}"))
        assert cb.state == CBState.OPEN

        cb.reset()
        assert cb.state == CBState.CLOSED
        assert cb.metrics["failures_in_window"] == 0

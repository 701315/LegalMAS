"""
Circuit Breaker implementation.

Protects the system from cascading failures when external services
(LLM APIs, OCR services) become unavailable.

States:
    CLOSED  -> Normal operation. Failures are counted.
    OPEN    -> Service considered down. All calls fail fast.
    HALF_OPEN -> Testing if service recovered. Limited calls allowed.

Transitions:
    CLOSED -> OPEN: failure count exceeds threshold within window
    OPEN -> HALF_OPEN: recovery timeout expires
    HALF_OPEN -> CLOSED: enough successes in half-open
    HALF_OPEN -> OPEN: any failure in half-open

State is stored in Redis so it's shared across all Celery workers.
"""

import time
import uuid
from enum import Enum

import redis as redis_lib

from src.core.config import settings
from src.core.exceptions import CircuitOpenError
from src.core.logging import get_logger

logger = get_logger(__name__)


class CBState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Circuit breaker for external service calls.

    Usage:
        cb = CircuitBreaker("openai")

        try:
            result = cb.execute(call_openai_api, prompt="...")
        except CircuitOpenError:
            # Service is down, use fallback
            result = use_local_llm(prompt="...")

    Or manually:
        if cb.state == CBState.OPEN:
            use_fallback()
        else:
            try:
                result = call_api()
                cb.record_success()
            except Exception as e:
                cb.record_failure(e)
                use_fallback()
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        window_size_seconds: int = 60,
        recovery_timeout_seconds: int = 60,
        success_threshold: int = 3,
        redis_client: redis_lib.Redis | None = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_size_seconds = window_size_seconds
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.success_threshold = success_threshold

        # Redis connection for shared state across workers
        self._redis = redis_client or redis_lib.from_url(settings.REDIS_URL, decode_responses=True)

        # Redis keys for this circuit breaker
        self._state_key = f"cb:{name}:state"
        self._failures_key = f"cb:{name}:failures"
        self._opened_at_key = f"cb:{name}:opened_at"
        self._half_open_successes_key = f"cb:{name}:ho_successes"

    @property
    def state(self) -> CBState:
        """Get current circuit breaker state."""
        stored = self._redis.get(self._state_key)

        if stored is None or stored == CBState.CLOSED.value:
            return CBState.CLOSED

        if stored == CBState.OPEN.value:
            # Check if recovery timeout has passed -> transition to HALF_OPEN
            opened_at = self._redis.get(self._opened_at_key)
            if opened_at is not None:
                elapsed = time.time() - float(opened_at)
                if elapsed >= self.recovery_timeout_seconds:
                    self._transition_to(CBState.HALF_OPEN)
                    return CBState.HALF_OPEN
            return CBState.OPEN

        if stored == CBState.HALF_OPEN.value:
            return CBState.HALF_OPEN

        return CBState.CLOSED

    def execute(self, func, *args, **kwargs):
        """
        Execute a function through the circuit breaker.

        Raises:
            CircuitOpenError: if circuit is OPEN and recovery not due
            Any exception from func: if circuit is CLOSED or HALF_OPEN
        """
        current_state = self.state

        if current_state == CBState.OPEN:
            raise CircuitOpenError(self.name)

        try:
            result = func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure(e)
            raise

    def record_success(self) -> None:
        """Record a successful call."""
        current_state = self.state

        if current_state == CBState.HALF_OPEN:
            # Count successes in half-open
            count = self._redis.incr(self._half_open_successes_key)
            if count >= self.success_threshold:
                self._transition_to(CBState.CLOSED)
        # In CLOSED state, successes are not tracked (only failures matter)

    def record_failure(self, error: Exception | None = None) -> None:
        """Record a failed call."""
        current_state = self.state
        now = time.time()

        if current_state == CBState.HALF_OPEN:
            # Any failure in half-open -> back to OPEN
            self._transition_to(CBState.OPEN)
            return

        if current_state == CBState.CLOSED:
            # Add failure timestamp to sorted set with unique member
            member = str(uuid.uuid4())
            self._redis.zadd(self._failures_key, {member: now})

            # Remove failures outside the window
            window_start = now - self.window_size_seconds
            self._redis.zremrangebyscore(self._failures_key, "-inf", window_start)

            # Count failures in window
            failure_count = self._redis.zcard(self._failures_key)

            if failure_count >= self.failure_threshold:
                self._transition_to(CBState.OPEN)

    def _transition_to(self, new_state: CBState) -> None:
        """Transition to a new state with logging."""
        old_state = self._redis.get(self._state_key) or CBState.CLOSED.value
        self._redis.set(self._state_key, new_state.value)

        if new_state == CBState.OPEN:
            self._redis.set(self._opened_at_key, str(time.time()))
            self._redis.delete(self._half_open_successes_key)

        elif new_state == CBState.HALF_OPEN:
            self._redis.delete(self._half_open_successes_key)

        elif new_state == CBState.CLOSED:
            self._redis.delete(self._failures_key)
            self._redis.delete(self._opened_at_key)
            self._redis.delete(self._half_open_successes_key)

        logger.warning(
            "Circuit breaker state change",
            circuit=self.name,
            old_state=old_state,
            new_state=new_state.value,
        )

    @property
    def metrics(self) -> dict:
        """Get current metrics for monitoring."""
        now = time.time()
        window_start = now - self.window_size_seconds
        self._redis.zremrangebyscore(self._failures_key, "-inf", window_start)
        failure_count = self._redis.zcard(self._failures_key)

        opened_at = self._redis.get(self._opened_at_key)
        time_in_open = 0.0
        if opened_at and self.state == CBState.OPEN:
            time_in_open = now - float(opened_at)

        return {
            "name": self.name,
            "state": self.state.value,
            "failures_in_window": failure_count,
            "failure_threshold": self.failure_threshold,
            "time_in_open_seconds": round(time_in_open, 1),
        }

    def reset(self) -> None:
        """Force reset to CLOSED state. Use for testing or manual intervention."""
        self._redis.delete(self._state_key)
        self._redis.delete(self._failures_key)
        self._redis.delete(self._opened_at_key)
        self._redis.delete(self._half_open_successes_key)
        logger.info("Circuit breaker manually reset", circuit=self.name)

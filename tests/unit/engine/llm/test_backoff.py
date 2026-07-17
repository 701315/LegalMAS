"""
Tests for LLM retry backoff logic.

Покрывает:
- _compute_backoff_delay: математика, cap, jitter
- call_with_retries: sleep вызывается между попытками
- call_with_retries_async: asyncio.sleep вызывается между попытками
- граничные случаи: max_retries=0, PermanentError без sleep
"""

from __future__ import annotations

import asyncio
import random
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from core.exceptions import PermanentError, TransientError
from engine.llm.client import LLMClient, LLMResponse, _compute_backoff_delay


# =============================================================================
# _compute_backoff_delay — unit tests
# =============================================================================

class TestComputeBackoffDelay:
    """Тесты функции _compute_backoff_delay."""

    def test_first_attempt_equals_base(self) -> None:
        """attempt=1 → exponential=base*1=base, jitter=0 при seed."""
        random.seed(0)
        delay = _compute_backoff_delay(attempt=1, base=1.0, cap=30.0, jitter_range=0.0)
        assert delay == pytest.approx(1.0)

    def test_exponential_growth(self) -> None:
        """Задержка растёт как base * 2^(attempt-1)."""
        delays = [
            _compute_backoff_delay(attempt=i, base=1.0, cap=1000.0, jitter_range=0.0)
            for i in range(1, 6)
        ]
        # 1.0, 2.0, 4.0, 8.0, 16.0
        assert delays == pytest.approx([1.0, 2.0, 4.0, 8.0, 16.0])

    def test_cap_limits_growth(self) -> None:
        """Задержка не превышает cap."""
        for attempt in range(1, 20):
            delay = _compute_backoff_delay(
                attempt=attempt, base=1.0, cap=10.0, jitter_range=0.0
            )
            assert delay <= 10.0, f"attempt={attempt}: delay={delay} exceeds cap=10.0"

    def test_jitter_within_range(self) -> None:
        """Jitter всегда в диапазоне [0, jitter_range]."""
        for seed in range(50):
            random.seed(seed)
            delay = _compute_backoff_delay(
                attempt=1, base=1.0, cap=30.0, jitter_range=2.0
            )
            # exponential=1.0, jitter∈[0, 2.0] → delay∈[1.0, 3.0]
            assert 1.0 <= delay <= 3.0, f"seed={seed}: delay={delay} out of range"

    def test_zero_base_returns_only_jitter(self) -> None:
        """base=0 → только jitter."""
        random.seed(42)
        delay = _compute_backoff_delay(attempt=3, base=0.0, cap=30.0, jitter_range=1.0)
        assert 0.0 <= delay <= 1.0

    def test_zero_jitter_is_deterministic(self) -> None:
        """jitter_range=0 → детерминированный результат."""
        d1 = _compute_backoff_delay(attempt=2, base=2.0, cap=30.0, jitter_range=0.0)
        d2 = _compute_backoff_delay(attempt=2, base=2.0, cap=30.0, jitter_range=0.0)
        assert d1 == d2 == pytest.approx(4.0)

    def test_negative_inputs_clamped(self) -> None:
        """Отрицательные аргументы не вызывают исключение."""
        delay = _compute_backoff_delay(
            attempt=-1, base=-1.0, cap=-1.0, jitter_range=-1.0
        )
        assert delay >= 0.0

    def test_attempt_zero_treated_as_one(self) -> None:
        """attempt=0 обрабатывается как attempt=1."""
        d0 = _compute_backoff_delay(attempt=0, base=1.0, cap=30.0, jitter_range=0.0)
        d1 = _compute_backoff_delay(attempt=1, base=1.0, cap=30.0, jitter_range=0.0)
        assert d0 == d1


# =============================================================================
# call_with_retries — sync backoff
# =============================================================================

class TestCallWithRetriesBackoff:
    """Тесты что sync retry использует time.sleep с правильными задержками."""

    def _make_client(self) -> LLMClient:
        """Сбросить singleton и вернуть свежий клиент."""
        LLMClient._instance = None
        client = LLMClient()
        client.provider = "ollama"
        return client

    def test_sleep_called_between_retries(self) -> None:
        """time.sleep вызывается между retry при TransientError."""
        client = self._make_client()

        call_count = 0

        def _failing_call(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise TransientError("ollama unavailable")

        with (
            patch.object(client, "call", side_effect=_failing_call),
            patch("engine.llm.client.time.sleep") as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 2
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0  # детерминизм

            response, details = client.call_with_retries(prompt="test", max_retries=2)

        assert response is None
        assert details["error_type"] == "transient_error"
        assert details["llm_attempts"] == 3  # 1 первый + 2 retry

        # sleep вызван ровно 2 раза (после attempt 1 и attempt 2)
        assert mock_sleep.call_count == 2

        # Первый sleep: attempt=1, base=1.0, 2^0=1.0 → 1.0s
        # Второй sleep: attempt=2, base=1.0, 2^1=2.0 → 2.0s
        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args[0] == pytest.approx(1.0)
        assert sleep_args[1] == pytest.approx(2.0)

    def test_no_sleep_on_zero_retries(self) -> None:
        """max_retries=0 → одна попытка, sleep не вызывается."""
        client = self._make_client()

        with (
            patch.object(client, "call", side_effect=TransientError("fail")),
            patch("engine.llm.client.time.sleep") as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 0
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            response, details = client.call_with_retries(prompt="test", max_retries=0)

        assert response is None
        assert details["llm_attempts"] == 1
        mock_sleep.assert_not_called()

    def test_no_sleep_on_permanent_error(self) -> None:
        """PermanentError → немедленный возврат без sleep."""
        client = self._make_client()

        with (
            patch.object(client, "call", side_effect=PermanentError("bad input")),
            patch("engine.llm.client.time.sleep") as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 2
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            response, details = client.call_with_retries(prompt="test")

        assert details["error_type"] == "permanent_error"
        assert details["llm_attempts"] == 1
        mock_sleep.assert_not_called()

    def test_success_on_second_attempt_no_extra_sleep(self) -> None:
        """Успех на второй попытке → sleep только один раз."""
        client = self._make_client()

        attempt_count = 0
        mock_response = LLMResponse(text='{"found": true}', provider="ollama")

        def _flaky(*args, **kwargs):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise TransientError("first fail")
            return mock_response

        with (
            patch.object(client, "call", side_effect=_flaky),
            patch("engine.llm.client.time.sleep") as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 2
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            response, details = client.call_with_retries(prompt="test")

        assert response is mock_response
        assert details["llm_attempts"] == 2
        assert details["error_type"] is None
        assert mock_sleep.call_count == 1  # только после первого fail


# =============================================================================
# call_with_retries_async — async backoff
# =============================================================================

class TestCallWithRetriesAsyncBackoff:
    """Тесты что async retry использует asyncio.sleep с правильными задержками."""

    def _make_client(self) -> LLMClient:
        LLMClient._instance = None
        client = LLMClient()
        client.provider = "ollama"
        return client

    @pytest.mark.asyncio
    async def test_asyncio_sleep_called_between_retries(self) -> None:
        """asyncio.sleep вызывается между retry — не блокирует event loop."""
        client = self._make_client()

        with (
            patch.object(
                client, "call_async",
                side_effect=TransientError("ollama unavailable")
            ),
            patch("engine.llm.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 2
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=2
            )

        assert response is None
        assert details["error_type"] == "transient_error"
        assert details["llm_attempts"] == 3
        assert mock_sleep.call_count == 2

        sleep_args = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_args[0] == pytest.approx(1.0)
        assert sleep_args[1] == pytest.approx(2.0)

    @pytest.mark.asyncio
    async def test_no_asyncio_sleep_on_zero_retries(self) -> None:
        """max_retries=0 → одна попытка, asyncio.sleep не вызывается."""
        client = self._make_client()

        with (
            patch.object(
                client, "call_async",
                side_effect=TransientError("fail")
            ),
            patch("engine.llm.client.asyncio.sleep", new_callable=AsyncMock) as mock_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 0
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            response, details = await client.call_with_retries_async(
                prompt="test", max_retries=0
            )

        assert details["llm_attempts"] == 1
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_cap_applied_at_high_attempt(self) -> None:
        """При большом числе retry задержка ограничена cap."""
        client = self._make_client()

        sleep_calls: list[float] = []

        async def _mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        with (
            patch.object(
                client, "call_async",
                side_effect=TransientError("fail")
            ),
            patch("engine.llm.client.asyncio.sleep", side_effect=_mock_sleep),
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 10
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 5.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            await client.call_with_retries_async(prompt="test", max_retries=10)

        # Все задержки должны быть <= cap=5.0 (jitter=0)
        for i, delay in enumerate(sleep_calls):
            assert delay <= 5.0, f"attempt {i+1}: delay={delay} exceeds cap=5.0"

    @pytest.mark.asyncio
    async def test_time_sleep_not_called_in_async(self) -> None:
        """В async-версии НЕ должен вызываться time.sleep (блокирует event loop)."""
        client = self._make_client()

        with (
            patch.object(
                client, "call_async",
                side_effect=TransientError("fail")
            ),
            patch("engine.llm.client.asyncio.sleep", new_callable=AsyncMock),
            patch("engine.llm.client.time.sleep") as mock_sync_sleep,
            patch("engine.llm.client.settings") as mock_settings,
        ):
            mock_settings.LLM_MAX_RETRIES = 2
            mock_settings.LLM_RETRY_BASE_DELAY_SECONDS = 1.0
            mock_settings.LLM_RETRY_MAX_DELAY_SECONDS = 30.0
            mock_settings.LLM_RETRY_JITTER_SECONDS = 0.0

            await client.call_with_retries_async(prompt="test", max_retries=2)

        # Критически важно: time.sleep не должен вызываться в async-пути
        mock_sync_sleep.assert_not_called()


        
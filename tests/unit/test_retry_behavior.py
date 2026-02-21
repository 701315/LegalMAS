"""
Unit tests for MASBaseTask retry and DLQ logic.
No broker, no eager mode — pure logic testing via mocks.
"""

from unittest.mock import patch

import pytest
from celery.exceptions import Retry as CeleryRetry

from src.core.exceptions import PermanentError, TransientError
from tests.tasks_for_testing import permanent_fail_task, transient_fail_task


@pytest.fixture(autouse=True)
def reset_retries():
    """Сбрасываем retries после каждого теста."""
    yield
    transient_fail_task.request.update(retries=0)
    permanent_fail_task.request.update(retries=0)


class TestBackoff:
    def test_first_retry(self):
        assert transient_fail_task._calculate_backoff(0) == 10.0

    def test_second_retry(self):
        assert transient_fail_task._calculate_backoff(1) == 30.0

    def test_third_retry(self):
        assert transient_fail_task._calculate_backoff(2) == 90.0

    def test_cap_at_max(self):
        # 10 * 3**5 = 2430 → capped at 300
        assert transient_fail_task._calculate_backoff(5) == 300.0


class TestTransientRetry:
    def test_retry_called_on_transient_error(self):
        """__call__ вызывает self.retry() при TransientError."""
        with patch.object(transient_fail_task, "retry", side_effect=CeleryRetry()) as mock_retry:
            with pytest.raises(CeleryRetry):
                transient_fail_task(fail_until_retry=99)

            mock_retry.assert_called_once()

    def test_retry_countdown_is_correct(self):
        """Первый retry использует backoff=10 сек."""
        with patch.object(transient_fail_task, "retry", side_effect=CeleryRetry()) as mock_retry:
            with pytest.raises(CeleryRetry):
                transient_fail_task(fail_until_retry=99)

            assert mock_retry.call_args.kwargs["countdown"] == 10.0

    def test_exhausted_retries_go_to_dlq(self):
        """При retries == max_retries → DLQ, не retry."""
        transient_fail_task.request.update(retries=3)

        with patch.object(transient_fail_task, "_send_to_dlq") as mock_dlq:
            with pytest.raises(TransientError):
                transient_fail_task(fail_until_retry=99)

            mock_dlq.assert_called_once()
            assert mock_dlq.call_args.kwargs["failure_type"] == "transient"
            assert mock_dlq.call_args.kwargs["task_type"] == "test.transient_fail_task"

    def test_exhausted_retries_reason_in_details(self):
        """DLQ запись содержит reason=max_retries_exceeded."""
        transient_fail_task.request.update(retries=3)

        with patch.object(transient_fail_task, "_send_to_dlq") as mock_dlq:
            with pytest.raises(TransientError):
                transient_fail_task(fail_until_retry=99)

            error_details = mock_dlq.call_args.kwargs["error_details"]
            assert error_details["reason"] == "max_retries_exceeded"


class TestPermanentFailure:
    def test_permanent_error_not_retried(self):
        """
        PermanentError пробрасывается из __call__ напрямую — retry не вызывается.
        _send_to_dlq вызывается из on_failure Celery, не из __call__.
        Здесь проверяем именно __call__: retry должен быть NOT called.
        """
        with patch.object(permanent_fail_task, "retry") as mock_retry:
            with pytest.raises(PermanentError):
                permanent_fail_task()

            mock_retry.assert_not_called()

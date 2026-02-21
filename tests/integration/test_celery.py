"""
Integration tests for Celery + MASBaseTask.

These tests use eager mode (tasks execute in the same process)
to avoid needing a running Celery worker during tests.
"""

from unittest.mock import patch

import pytest
from celery.exceptions import Retry as CeleryRetry

from src.core.exceptions import PermanentError, TransientError
from src.queue.celery_app import celery_app
from tests.tasks_for_testing import (
    add_numbers,
    permanent_fail_task,
    success_task,
    transient_fail_task,
)


@pytest.fixture(autouse=True)
def celery_eager_mode():
    """
    Run Celery tasks eagerly (synchronously in the same process).
    countdown in eager mode is ignored by Celery — retries happen immediately.
    """
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
    )
    yield
    celery_app.conf.update(
        task_always_eager=False,
        task_eager_propagates=False,
    )


@pytest.fixture(autouse=True)
def mock_job_status_update():
    """
    Suppress DB calls to _update_job_status in all tests.
    Tasks under test have track_job=False, but this guards against
    accidental track_job=True tasks in future.
    """
    with patch("src.queue.base_task.run_async", return_value=None):
        yield


class TestCeleryBasics:
    def test_add_numbers(self):
        """Simple task should execute and return result."""
        result = add_numbers.delay(3, 7)
        assert result.get() == {"result": 10}

    def test_success_task(self):
        """Success task should return ok status."""
        result = success_task.delay(message="test_message")
        data = result.get()
        assert data["status"] == "ok"
        assert data["message"] == "test_message"

    def test_success_task_with_kwargs(self):
        """Task should accept keyword arguments."""
        result = success_task.apply(kwargs={"message": "kwargs_test"})
        data = result.get()
        assert data["message"] == "kwargs_test"


class TestRetryBehavior:
    def test_transient_error_initiates_retry(self):
        """
        __call__ должен вызвать self.retry() при TransientError.
        Проверяем что retry инициирован с правильным backoff (countdown=10).
        Полный retry-цикл тестируется только с реальным воркером.
        """
        with patch.object(transient_fail_task, "retry", side_effect=CeleryRetry()) as mock_retry:
            with pytest.raises(CeleryRetry):
                transient_fail_task(fail_until_retry=99)

            mock_retry.assert_called_once()
            call_kwargs = mock_retry.call_args.kwargs
            assert call_kwargs["countdown"] == 10.0  # 10 * (3**0)

    def test_transient_error_max_retries_sends_to_dlq(self):
        """
        Когда retries == max_retries задача идёт в DLQ без retry.
        """
        transient_fail_task.request.update(retries=3)
        try:
            with patch.object(transient_fail_task, "_send_to_dlq") as mock_dlq:
                with pytest.raises(TransientError):
                    transient_fail_task(fail_until_retry=99)

                mock_dlq.assert_called_once()
                assert mock_dlq.call_args.kwargs["failure_type"] == "transient"
        finally:
            transient_fail_task.request.update(retries=0)

    def test_backoff_progression(self):
        """
        Формула backoff: 10 * (3 ** retry_num), max 300.
        """
        assert transient_fail_task._calculate_backoff(0) == 10.0
        assert transient_fail_task._calculate_backoff(1) == 30.0
        assert transient_fail_task._calculate_backoff(2) == 90.0
        assert transient_fail_task._calculate_backoff(3) == 270.0


class TestPermanentFailure:
    def test_permanent_error_not_retried(self):
        """
        PermanentError goes straight to on_failure — no retry.
        With propagates=True the exception surfaces to the caller.
        """
        with pytest.raises(PermanentError):
            permanent_fail_task.delay()


class TestDLQIntegration:
    def test_permanent_error_sends_to_dlq(self):
        """
        PermanentError should trigger _send_to_dlq in on_failure.
        We mock _send_to_dlq to verify it's called without hitting DB.
        """
        celery_app.conf.update(task_eager_propagates=False)
        try:
            with patch.object(permanent_fail_task, "_send_to_dlq") as mock_dlq:
                result = permanent_fail_task.delay()

                assert result.failed()
                mock_dlq.assert_called_once()

                call_kwargs = mock_dlq.call_args.kwargs
                assert call_kwargs["failure_type"] == "permanent"
                assert call_kwargs["task_type"] == "test.permanent_fail_task"
        finally:
            celery_app.conf.update(task_eager_propagates=True)


class TestCeleryQueues:
    def test_task_queue_configuration(self):
        """Celery should have three queues configured."""
        queue_names = {q.name for q in celery_app.conf.task_queues}
        assert "high_priority" in queue_names
        assert "default" in queue_names
        assert "low_priority" in queue_names

    def test_default_queue(self):
        """Default queue should be 'default'."""
        assert celery_app.conf.task_default_queue == "default"


class TestCeleryConfig:
    def test_serializer_is_json(self):
        """Tasks should use JSON serialization."""
        assert celery_app.conf.task_serializer == "json"
        assert celery_app.conf.result_serializer == "json"
        assert "json" in celery_app.conf.accept_content

    def test_acks_late(self):
        """Tasks should be acknowledged after completion."""
        assert celery_app.conf.task_acks_late is True

    def test_prefetch_one(self):
        """Workers should prefetch only one task at a time."""
        assert celery_app.conf.worker_prefetch_multiplier == 1

"""
Pure-logic tests for typed check_result persistence error contract.

Не тянет ORM/Celery импорты.
Проверяет:
- typed exception contract;
- retryable semantics;
- worker-level failure action classification.
"""

from core.check_result_persist_errors import (
    CheckFailureAction,
    CheckResultPersistPermanentError,
    CheckResultPersistTransientError,
    decide_check_failure_action,
)


class TestCheckResultPersistErrorContract:
    def test_transient_error_is_retryable(self):
        exc = CheckResultPersistTransientError(
            "temporary database issue",
            sqlstate="40001",
        )

        assert exc.retryable is True
        assert exc.sqlstate == "40001"
        assert str(exc) == "temporary database issue"

    def test_permanent_error_is_not_retryable(self):
        exc = CheckResultPersistPermanentError(
            "value too long for column",
            sqlstate="22001",
        )

        assert exc.retryable is False
        assert exc.sqlstate == "22001"
        assert str(exc) == "value too long for column"

    def test_transient_error_maps_to_retry_action(self):
        exc = CheckResultPersistTransientError(
            "transient persist failure",
            sqlstate="40001",
        )

        assert decide_check_failure_action(exc) == CheckFailureAction.RETRY

    def test_permanent_error_maps_to_persist_failed_action(self):
        exc = CheckResultPersistPermanentError(
            "permanent persist failure",
            sqlstate="22001",
        )

        assert decide_check_failure_action(exc) == CheckFailureAction.PERSIST_FAILED

    def test_generic_exception_maps_to_compute_failed_action(self):
        exc = RuntimeError("executor crashed")

        assert decide_check_failure_action(exc) == CheckFailureAction.COMPUTE_FAILED


        
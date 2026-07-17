# src/core/check_result_persist_errors.py

"""
Typed exception contract for check_result persistence failures.

Зачем нужен этот модуль:
- persistence layer не должен кодировать retry-semantics в строку сообщения;
- worker не должен парсить retry/non-retryable поведение по тексту ошибки;
- межслойный контракт должен быть typed и machine-readable.
"""

from __future__ import annotations

from enum import StrEnum


class CheckFailureAction(StrEnum):
    RETRY = "retry"
    PERSIST_FAILED = "persist_failed"
    COMPUTE_FAILED = "compute_failed"


class CheckResultPersistError(RuntimeError):
    """
    Базовая ошибка сохранения check_result.

    Поля:
    - sqlstate: SQLSTATE от оригинальной DB-ошибки, если доступен
    - retryable: можно ли безопасно ретраить задачу
    """

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None,
        retryable: bool,
    ) -> None:
        super().__init__(message)
        self.sqlstate = sqlstate
        self.retryable = retryable


class CheckResultPersistTransientError(CheckResultPersistError):
    """
    Временная ошибка persistence.

    Ожидаемая реакция worker:
    - не маркировать compute failure;
    - ретраить Celery task.
    """

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None,
    ) -> None:
        super().__init__(
            message,
            sqlstate=sqlstate,
            retryable=True,
        )


class CheckResultPersistPermanentError(CheckResultPersistError):
    """
    Постоянная ошибка persistence.

    Ожидаемая реакция worker:
    - не ретраить;
    - best-effort материализовать sentinel row со статусом PERSIST_FAILED.
    """

    def __init__(
        self,
        message: str,
        *,
        sqlstate: str | None,
    ) -> None:
        super().__init__(
            message,
            sqlstate=sqlstate,
            retryable=False,
        )


def decide_check_failure_action(exc: BaseException) -> CheckFailureAction:
    """
    Преобразовать exception в worker-level action.

    Используется как чистый контрактный слой:
    - transient persist error -> retry
    - permanent persist error -> persist_failed
    - всё остальное -> compute_failed
    """
    if isinstance(exc, CheckResultPersistTransientError):
        return CheckFailureAction.RETRY

    if isinstance(exc, CheckResultPersistPermanentError):
        return CheckFailureAction.PERSIST_FAILED

    return CheckFailureAction.COMPUTE_FAILED



    
"""
Unit tests for result-presentation Celery worker adapter.

Проверяет:
- task registration и queue routing;
- проброс bounded outbox payload в ResultPresentationTranslationUseCase;
- envelope-safe игнорирование stage_execution_id,
  orchestration_strategy и произвольных extra kwargs;
- возврат use-case result envelope без изменения полей.

Тест не запускает реальный Celery worker, Redis, PostgreSQL или LLM.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from mas_queue.celery_app import celery_app
from workers.result_presentation_worker import (
    RESULT_PRESENTATION_TRANSLATION_TASK_NAME,
    process_pending_result_presentations,
)


RUN_ID = "11111111-1111-1111-1111-111111111111"
DEAL_ID = "22222222-2222-2222-2222-222222222222"
TENANT_ID = "33333333-3333-3333-3333-333333333333"


class FakeUnitOfWork:
    """Минимальный async context manager для worker adapter test."""

    def __init__(self, session: object) -> None:
        self.session = session

    async def __aenter__(self) -> "FakeUnitOfWork":
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        _ = exc_type, exc_value, traceback


def run_coroutine(coroutine):
    """Выполнить coroutine так же, как worker runtime helper."""

    return asyncio.run(coroutine)


def test_task_is_registered_on_heavy_llm_checks_queue() -> None:
    assert process_pending_result_presentations.name == (
        RESULT_PRESENTATION_TRANSLATION_TASK_NAME
    )

    route = celery_app.conf.task_routes[
        RESULT_PRESENTATION_TRANSLATION_TASK_NAME
    ]

    assert route == {
        "queue": "heavy_llm_checks",
        "routing_key": "heavy_llm_checks",
    }


def test_worker_delegates_outbox_payload_to_translation_use_case() -> None:
    fake_session = MagicMock()

    expected_result = {
        "status": "completed",
        "run_id": RUN_ID,
        "deal_id": DEAL_ID,
        "tenant_id": TENANT_ID,
        "locale": "en",
        "content_version": "v1",
        "claimed": 2,
        "ready": 2,
        "failed": 0,
        "stale": 0,
        "missing_result": 0,
    }

    with patch(
        "workers.result_presentation_worker.db_uow",
        return_value=FakeUnitOfWork(fake_session),
    ) as db_uow_mock, patch(
        "workers.result_presentation_worker."
        "ResultPresentationTranslationUseCase",
    ) as use_case_cls, patch(
        "workers.result_presentation_worker.run_async",
        side_effect=run_coroutine,
    ) as run_async_mock:
        use_case = MagicMock()
        use_case.execute = AsyncMock(return_value=expected_result)
        use_case_cls.return_value = use_case

        result = process_pending_result_presentations.run(
            run_id=RUN_ID,
            deal_id=DEAL_ID,
            tenant_id=TENANT_ID,
            locale="en",
            content_version="v1",
            batch_limit=5,
            stage_execution_id="stage-execution-id",
            orchestration_strategy="outbox",
            unexpected_envelope_value="safe-to-ignore",
        )

    assert result == expected_result

    db_uow_mock.assert_called_once_with()

    use_case_cls.assert_called_once_with(
        db=fake_session,
    )

    use_case.execute.assert_awaited_once_with(
        run_id=RUN_ID,
        deal_id=DEAL_ID,
        tenant_id=TENANT_ID,
        locale="en",
        content_version="v1",
        batch_limit=5,
    )

    run_async_mock.assert_called_once()

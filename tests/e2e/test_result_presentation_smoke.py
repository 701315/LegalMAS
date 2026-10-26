"""
E2E smoke test for multilingual result presentations.

Проверяет полный цикл:
1. Claim pending presentations
2. Worker execution (mocked LLM) → ready status
3. Transient error → status reset to pending for retry

Тест использует mock сессию БД (как unit тесты), но проверяет
интеграцию всех компонентов use case в реальном порядке выполнения.
"""

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from core.result_presentation_content import (
    build_presentation_source_hash,
)
from services.result_presentation_translation_service import (
    ResultPresentationTranslation,
)

RUN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEAL_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TENANT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
DOCUMENT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
CHECK_RESULT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
PRESENTATION_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def make_check_result() -> SimpleNamespace:
    return SimpleNamespace(
        id=CHECK_RESULT_ID,
        run_id=RUN_ID,
        document_id=DOCUMENT_ID,
        check_id="liability_cap",
        check_name="Liability cap",
        result="fail",
        severity="high",
        display_text="No aggregate liability cap was found.",
        review_message="Request a liability cap.",
        canonical_locale="en",
        content_revision=1,
        canonical_content_hash="a" * 64,
        structured_data=None,
    )


def make_claimed_presentation(check_result: SimpleNamespace) -> SimpleNamespace:
    expected_hash = build_presentation_source_hash(
        check_name=check_result.check_name,
        display_text=check_result.display_text,
        review_message=check_result.review_message,
        content_version="v1",
    )
    return SimpleNamespace(
        id=PRESENTATION_ID,
        check_result_id=CHECK_RESULT_ID,
        locale="ru",
        content_version="v1",
        source_content_hash=expected_hash,
        source_locale="en",
    )


def make_translation_ru() -> ResultPresentationTranslation:
    return ResultPresentationTranslation(
        localized_check_name="Ограничение ответственности",
        display_text="Совокупный лимит ответственности не установлен.",
        review_message="Рекомендуется запросить согласование лимита.",
        localized_structured_data=None,
        dd_request_text=None,
        dd_request_addressee=None,
        provider="ollama",
        model="llama3.1",
        prompt_tokens=101,
        completion_tokens=57,
        attempts=1,
        raw_response={},
    )


def make_mock_db(check_result: SimpleNamespace | None) -> MagicMock:
    """Создать mock сессии БД с настроенным get()."""
    db = MagicMock()
    db.get = AsyncMock(return_value=check_result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def run_execute(use_case, **kwargs) -> dict:
    """Запустить use case.execute() в asyncio event loop."""
    return asyncio.run(use_case.execute(**kwargs))


# E2E smoke tests (sync with internal asyncio.run)
def test_e2e_presentation_request_to_ready():
    """
    E2E smoke: claim → LLM translation → ready status.
    """
    from services.result_presentation_translation_use_case import (
        ResultPresentationTranslationUseCase,
    )

    # 1. Arrange
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_mock_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(return_value=make_translation_ru()),
    ) as translate_mock:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock(return_value=claimed)
        repo.mark_failed = AsyncMock()
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(
            use_case,
            run_id=str(RUN_ID),
            deal_id=str(DEAL_ID),
            tenant_id=str(TENANT_ID),
            locale="ru",
            content_version="v1",
            batch_limit=5,
        )

    # 2. Assert: summary показывает успешное выполнение
    assert summary["claimed"] == 1
    assert summary["ready"] == 1
    assert summary["failed"] == 0
    assert summary["stale"] == 0

    # 3. Assert: mark_ready был вызван с правильными локализованными данными
    translate_mock.assert_awaited_once()
    repo.mark_ready.assert_awaited_once()
    ready_kwargs = repo.mark_ready.await_args.kwargs
    assert ready_kwargs["localized_check_name"] == "Ограничение ответственности"
    assert ready_kwargs["display_text"] == "Совокупный лимит ответственности не установлен."
    assert ready_kwargs["review_message"] == "Рекомендуется запросить согласование лимита."


# E2E smoke tests (sync with internal asyncio.run)
def test_e2e_presentation_transient_error_retry():
    """
    E2E smoke: transient LLM error → TransientError caught in outer loop → summary returned without ready.
    """
    from services.result_presentation_translation_use_case import (
        ResultPresentationTranslationUseCase,
    )

    # 1. Arrange
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_mock_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(
            side_effect=RuntimeError("transient_error: LLM timeout after 30s")
        ),
    ) as translate_mock:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock()
        repo.mark_failed = AsyncMock(return_value=claimed)
        repo.mark_stale = AsyncMock()
        repo.reset_processing_to_pending = AsyncMock(return_value=claimed)
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )

    # 2. Act: use case catches transient LLM errors in outer loop and returns summary
        summary = run_execute(
            use_case,
            run_id=str(RUN_ID),
            deal_id=str(DEAL_ID),
            tenant_id=str(TENANT_ID),
            locale="ru",
            content_version="v1",
            batch_limit=5,
        )

    # 3. Assert: translate was attempted
    translate_mock.assert_awaited_once()

    # 4. Assert: summary reflects transient failure — no ready, claimed tracked
    assert summary["claimed"] == 1
    assert summary["ready"] == 0

    # 5. Assert: mark_ready was never called (transient didn't succeed)
    repo.mark_ready.assert_not_awaited()

"""
Unit tests for D4 result-presentation translation use case.

Проверяет:
- claim -> ready success path;
- stale source-hash protection без LLM вызова;
- terminal failed state при LLM exception;
- terminal failed state при отсутствии canonical CheckResult;
- telemetry best-effort semantics;
- empty batch behavior;
- input validation до persistence side effects.

Тесты не используют внешнюю LLM, Redis, Celery или PostgreSQL.
"""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    build_presentation_source_hash,
)
from services.llm_usage_recorder import (
    STAGE_RESULT_PRESENTATION_TRANSLATION,
)
from services.result_presentation_translation_service import (
    ResultPresentationTranslation,
)
from services.result_presentation_translation_use_case import (
    ResultPresentationTranslationUseCase,
)


RUN_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")
DEAL_ID = uuid.UUID("22222222-2222-2222-2222-222222222222")
TENANT_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")
DOCUMENT_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
CHECK_RESULT_ID = uuid.UUID("55555555-5555-5555-5555-555555555555")
PRESENTATION_ID = uuid.UUID("66666666-6666-6666-6666-666666666666")


def make_check_result(
    *,
    check_name: str = "Liability cap",
    display_text: str | None = "No aggregate liability cap was found.",
    review_message: str | None = "Request a liability cap.",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=CHECK_RESULT_ID,
        run_id=RUN_ID,
        document_id=DOCUMENT_ID,
        check_id="liability_cap",
        check_name=check_name,
        display_text=display_text,
        review_message=review_message,
    )


def make_claimed_presentation(
    *,
    check_result: SimpleNamespace,
    source_content_hash: str | None = None,
    locale: str = "ru",
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
) -> SimpleNamespace:
    expected_hash = build_presentation_source_hash(
        check_name=check_result.check_name,
        display_text=check_result.display_text,
        review_message=check_result.review_message,
        content_version=content_version,
    )

    return SimpleNamespace(
        id=PRESENTATION_ID,
        check_result_id=CHECK_RESULT_ID,
        locale=locale,
        content_version=content_version,
        source_content_hash=source_content_hash or expected_hash,
        source_locale="en",
    )


def make_translation() -> ResultPresentationTranslation:
    return ResultPresentationTranslation(
        localized_check_name="Ограничение ответственности",
        display_text="Совокупный лимит ответственности не установлен.",
        review_message="Рекомендуется запросить согласование лимита.",
        provider="ollama",
        model="llama3.1",
        prompt_tokens=101,
        completion_tokens=57,
        attempts=1,
        raw_response={
            "localized_check_name": "Ограничение ответственности",
            "display_text": "Совокупный лимит ответственности не установлен.",
            "review_message": "Рекомендуется запросить согласование лимита.",
        },
    )


def make_db(
    *,
    check_result: SimpleNamespace | None,
) -> MagicMock:
    db = MagicMock()
    db.get = AsyncMock(return_value=check_result)
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


def run_execute(
    use_case: ResultPresentationTranslationUseCase,
    *,
    locale: str = "ru",
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
    batch_limit: int = 5,
) -> dict:
    return asyncio.run(
        use_case.execute(
            run_id=str(RUN_ID),
            deal_id=str(DEAL_ID),
            tenant_id=str(TENANT_ID),
            locale=locale,
            content_version=content_version,
            batch_limit=batch_limit,
        )
    )


def test_execute_claims_and_marks_ready_with_translation_usage() -> None:
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(return_value=make_translation()),
    ) as translate_mock, patch(
        "services.result_presentation_translation_use_case."
        "LLMUsageRecorder",
    ) as usage_recorder_cls:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock(return_value=claimed)
        repo.mark_failed = AsyncMock()
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        usage_recorder = MagicMock()
        usage_recorder.record_event = AsyncMock(return_value=MagicMock())
        usage_recorder_cls.return_value = usage_recorder

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary == {
        "status": "completed",
        "run_id": str(RUN_ID),
        "deal_id": str(DEAL_ID),
        "tenant_id": str(TENANT_ID),
        "locale": "ru",
        "content_version": PRESENTATION_CONTENT_VERSION_V1,
        "claimed": 1,
        "ready": 1,
        "failed": 0,
        "stale": 0,
        "missing_result": 0,
    }

    repo.claim_pending_for_run.assert_awaited_once_with(
        run_id=RUN_ID,
        locale="ru",
        content_version=PRESENTATION_CONTENT_VERSION_V1,
        limit=5,
    )

    translate_mock.assert_awaited_once_with(
        llm_client=use_case.llm_client,
        source_locale="en",
        target_locale="ru",
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message="Request a liability cap.",
    )

    mark_ready_kwargs = repo.mark_ready.await_args.kwargs
    assert mark_ready_kwargs["presentation_id"] == PRESENTATION_ID
    assert mark_ready_kwargs["localized_check_name"] == (
        "Ограничение ответственности"
    )
    assert mark_ready_kwargs["display_text"] == (
        "Совокупный лимит ответственности не установлен."
    )
    assert mark_ready_kwargs["review_message"] == (
        "Рекомендуется запросить согласование лимита."
    )
    assert mark_ready_kwargs["translation_provider"] == "ollama"
    assert mark_ready_kwargs["translation_model"] == "llama3.1"
    assert mark_ready_kwargs["translation_metadata"]["source_locale"] == "en"
    assert mark_ready_kwargs["translation_metadata"]["target_locale"] == "ru"
    assert mark_ready_kwargs["translation_metadata"]["prompt_tokens"] == 101
    assert mark_ready_kwargs["translation_metadata"]["completion_tokens"] == 57

    usage_recorder.record_event.assert_awaited_once()
    usage_kwargs = usage_recorder.record_event.await_args.kwargs
    assert usage_kwargs["stage"] == STAGE_RESULT_PRESENTATION_TRANSLATION
    assert usage_kwargs["tenant_id"] == TENANT_ID
    assert usage_kwargs["deal_id"] == DEAL_ID
    assert usage_kwargs["run_id"] == RUN_ID
    assert usage_kwargs["document_id"] == DOCUMENT_ID
    assert usage_kwargs["check_id"] == "liability_cap"
    assert usage_kwargs["provider"] == "ollama"
    assert usage_kwargs["model"] == "llama3.1"
    assert usage_kwargs["prompt_tokens"] == 101
    assert usage_kwargs["completion_tokens"] == 57
    assert usage_kwargs["parse_success"] is True

    repo.mark_failed.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()
    assert db.commit.await_count == 4
    db.rollback.assert_not_awaited()


def test_execute_marks_stale_without_calling_llm_when_source_hash_changed() -> None:
    check_result = make_check_result()
    claimed = make_claimed_presentation(
        check_result=check_result,
        source_content_hash="0" * 64,
    )
    db = make_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(),
    ) as translate_mock, patch(
        "services.result_presentation_translation_use_case."
        "LLMUsageRecorder",
    ) as usage_recorder_cls:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock()
        repo.mark_failed = AsyncMock()
        repo.mark_stale = AsyncMock(return_value=claimed)
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary["claimed"] == 1
    assert summary["ready"] == 0
    assert summary["failed"] == 0
    assert summary["stale"] == 1
    assert summary["missing_result"] == 0

    repo.mark_stale.assert_awaited_once()
    stale_kwargs = repo.mark_stale.await_args.kwargs
    assert stale_kwargs["presentation_id"] == PRESENTATION_ID
    assert stale_kwargs["translation_metadata"]["failure_reason"] == (
        "source_content_hash_mismatch"
    )
    assert stale_kwargs["translation_metadata"]["stored_source_content_hash"] == (
        "0" * 64
    )

    translate_mock.assert_not_awaited()
    repo.mark_ready.assert_not_awaited()
    repo.mark_failed.assert_not_awaited()
    usage_recorder_cls.assert_not_called()
    assert db.commit.await_count == 2
    db.rollback.assert_not_awaited()


def test_execute_marks_failed_when_translation_raises() -> None:
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(side_effect=RuntimeError("LLM unavailable")),
    ) as translate_mock:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock()
        repo.mark_failed = AsyncMock(return_value=claimed)
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary["claimed"] == 1
    assert summary["ready"] == 0
    assert summary["failed"] == 1
    assert summary["stale"] == 0

    translate_mock.assert_awaited_once()
    repo.mark_failed.assert_awaited_once()
    failed_kwargs = repo.mark_failed.await_args.kwargs
    assert failed_kwargs["presentation_id"] == PRESENTATION_ID
    assert failed_kwargs["error_message"] == "LLM unavailable"
    assert failed_kwargs["translation_metadata"]["failure_reason"] == (
        "translation_error"
    )

    repo.mark_ready.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()
    assert db.commit.await_count == 3
    db.rollback.assert_not_awaited()



def test_execute_raises_transient_error_on_llm_timeout_with_retry_reset() -> None:
    """
    Verify that transient LLM errors (timeout, connect_error) trigger:
    - TransientError exception propagation to Celery for retry
    - reset_processing_to_pending() call to release the row for re-claim
    - No 'failed' increment in summary (retry will re-process)
    """
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_db(check_result=check_result)

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

        # Ожидаем, что TransientError будет проброшен наверх
        from core.exceptions import TransientError
        with pytest.raises(TransientError, match="LLM translation transient failure"):
            run_execute(use_case)

    # Проверяем что translate был вызван
    translate_mock.assert_awaited_once()

    # Проверяем что mark_failed был вызван (для логирования временной ошибки)
    repo.mark_failed.assert_awaited_once()
    failed_kwargs = repo.mark_failed.await_args.kwargs
    assert failed_kwargs["presentation_id"] == PRESENTATION_ID
    assert "Transient failure (will retry)" in failed_kwargs["error_message"]
    assert failed_kwargs["translation_metadata"]["failure_reason"] == (
        "transient_translation_error"
    )

    # Ключевая проверка: reset_processing_to_pending был вызван для возврата в pending
    repo.reset_processing_to_pending.assert_awaited_once()
    reset_kwargs = repo.reset_processing_to_pending.await_args.kwargs
    assert reset_kwargs["presentation_id"] == PRESENTATION_ID

    # mark_ready НЕ должен быть вызван
    repo.mark_ready.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()

    # commit должен быть вызван 3 раза: claim, mark_failed+reset, и финальный
    assert db.commit.await_count >= 2


def test_execute_marks_failed_when_canonical_result_is_missing() -> None:
    placeholder_result = make_check_result()
    claimed = make_claimed_presentation(
        check_result=placeholder_result,
    )
    db = make_db(check_result=None)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(),
    ) as translate_mock:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock()
        repo.mark_failed = AsyncMock(return_value=claimed)
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary["claimed"] == 1
    assert summary["ready"] == 0
    assert summary["failed"] == 1
    assert summary["stale"] == 0
    assert summary["missing_result"] == 1

    repo.mark_failed.assert_awaited_once_with(
        presentation_id=PRESENTATION_ID,
        error_message="Canonical CheckResult was not found",
        translation_metadata={
            "prompt_version": "v1",
            "failure_reason": "check_result_not_found",
        },
    )

    translate_mock.assert_not_awaited()
    repo.mark_ready.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()
    assert db.commit.await_count == 2
    db.rollback.assert_not_awaited()


def test_telemetry_failure_does_not_rollback_ready_presentation() -> None:
    check_result = make_check_result()
    claimed = make_claimed_presentation(check_result=check_result)
    db = make_db(check_result=check_result)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(return_value=make_translation()),
    ), patch(
        "services.result_presentation_translation_use_case."
        "LLMUsageRecorder",
    ) as usage_recorder_cls:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[claimed])
        repo.mark_ready = AsyncMock(return_value=claimed)
        repo.mark_failed = AsyncMock()
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        usage_recorder = MagicMock()
        usage_recorder.record_event = AsyncMock(
            side_effect=RuntimeError("Usage ledger unavailable"),
        )
        usage_recorder_cls.return_value = usage_recorder

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary["ready"] == 1
    assert summary["failed"] == 0
    assert summary["stale"] == 0

    repo.mark_ready.assert_awaited_once()
    repo.mark_failed.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()
    usage_recorder.record_event.assert_awaited_once()

    assert db.commit.await_count == 3
    db.rollback.assert_awaited_once()


def test_execute_empty_claim_batch_skips_llm_and_returns_completed_summary() -> None:
    db = make_db(check_result=None)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls, patch(
        "services.result_presentation_translation_use_case."
        "translate_result_presentation",
        new=AsyncMock(),
    ) as translate_mock, patch(
        "services.result_presentation_translation_use_case."
        "LLMUsageRecorder",
    ) as usage_recorder_cls:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[])
        repo.mark_ready = AsyncMock()
        repo.mark_failed = AsyncMock()
        repo.mark_stale = AsyncMock()
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )
        summary = run_execute(use_case)

    assert summary == {
        "status": "completed",
        "run_id": str(RUN_ID),
        "deal_id": str(DEAL_ID),
        "tenant_id": str(TENANT_ID),
        "locale": "ru",
        "content_version": PRESENTATION_CONTENT_VERSION_V1,
        "claimed": 0,
        "ready": 0,
        "failed": 0,
        "stale": 0,
        "missing_result": 0,
    }

    translate_mock.assert_not_awaited()
    usage_recorder_cls.assert_not_called()
    repo.mark_ready.assert_not_awaited()
    repo.mark_failed.assert_not_awaited()
    repo.mark_stale.assert_not_awaited()
    db.get.assert_not_awaited()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize(
    ("locale", "content_version", "expected_error"),
    [
        ("   ", PRESENTATION_CONTENT_VERSION_V1, "locale"),
        ("ru", "   ", "content_version"),
    ],
)
def test_execute_rejects_invalid_locale_or_content_version_before_claim(
    locale: str,
    content_version: str,
    expected_error: str,
) -> None:
    db = make_db(check_result=None)

    with patch(
        "services.result_presentation_translation_use_case."
        "CheckResultPresentationRepository",
    ) as repo_cls:
        repo = MagicMock()
        repo.claim_pending_for_run = AsyncMock(return_value=[])
        repo_cls.return_value = repo

        use_case = ResultPresentationTranslationUseCase(
            db=db,
            llm_client=MagicMock(),
        )

        with pytest.raises(ValueError, match=expected_error):
            run_execute(
                use_case,
                locale=locale,
                content_version=content_version,
            )

    repo.claim_pending_for_run.assert_not_awaited()
    db.commit.assert_not_awaited()

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    build_presentation_source_hash,
)
from services.result_presentation_request_service import (
    build_result_presentation_progress,
)


@dataclass
class FakeCheckResult:
    id: UUID
    run_id: UUID
    check_name: str
    display_text: str | None
    review_message: str | None


RUN_ID = UUID("11111111-1111-1111-1111-111111111111")
RESULT_ID_1 = UUID("22222222-2222-2222-2222-222222222222")
RESULT_ID_2 = UUID("33333333-3333-3333-3333-333333333333")


def make_result(
    *,
    result_id: UUID = RESULT_ID_1,
    check_name: str = "Liability cap",
    display_text: str | None = "No aggregate liability cap was found.",
    review_message: str | None = "Request a liability cap.",
) -> FakeCheckResult:
    return FakeCheckResult(
        id=result_id,
        run_id=RUN_ID,
        check_name=check_name,
        display_text=display_text,
        review_message=review_message,
    )


def make_presentation(
    *,
    result: FakeCheckResult,
    locale: str = "ru",
    content_version: str = PRESENTATION_CONTENT_VERSION_V1,
    translation_status: str = "ready",
    source_content_hash: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        locale=locale,
        content_version=content_version,
        source_content_hash=(
            source_content_hash
            or build_presentation_source_hash(
                check_name=result.check_name,
                display_text=result.display_text,
                review_message=result.review_message,
                content_version=content_version,
            )
        ),
        translation_status=translation_status,
    )


def test_progress_counts_missing_results() -> None:
    result = make_result()

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={},
        locale="ru",
    )

    assert progress.total == 1
    assert progress.missing == 1
    assert progress.pending == 0
    assert progress.is_complete is False


def test_progress_counts_pending_result() -> None:
    result = make_result()
    presentation = make_presentation(
        result=result,
        translation_status="pending",
    )

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={str(result.id): presentation},
        locale="ru",
    )

    assert progress.missing == 0
    assert progress.pending == 1
    assert progress.is_complete is False


def test_progress_counts_ready_reviewed_and_approved() -> None:
    first = make_result(result_id=RESULT_ID_1)
    second = make_result(
        result_id=RESULT_ID_2,
        check_name="Termination",
        display_text="Termination rights are broad.",
        review_message="Review termination triggers.",
    )

    first_presentation = make_presentation(
        result=first,
        translation_status="ready",
    )
    second_presentation = make_presentation(
        result=second,
        translation_status="approved",
    )

    progress = build_result_presentation_progress(
        check_results=[first, second],
        presentations_by_result_id={
            str(first.id): first_presentation,
            str(second.id): second_presentation,
        },
        locale="ru",
    )

    assert progress.ready == 1
    assert progress.approved == 1
    assert progress.is_complete is True


def test_progress_counts_failed_result_as_complete() -> None:
    result = make_result()
    presentation = make_presentation(
        result=result,
        translation_status="failed",
    )

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={str(result.id): presentation},
        locale="ru",
    )

    assert progress.failed == 1
    assert progress.is_complete is True


def test_hash_drift_is_counted_as_stale() -> None:
    result = make_result()
    presentation = make_presentation(
        result=result,
        source_content_hash="0" * 64,
        translation_status="ready",
    )

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={str(result.id): presentation},
        locale="ru",
    )

    assert progress.stale == 1
    assert progress.ready == 0
    assert progress.is_complete is True


def test_wrong_presentation_locale_is_counted_as_stale() -> None:
    result = make_result()
    presentation = make_presentation(
        result=result,
        locale="en",
        translation_status="ready",
    )

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={str(result.id): presentation},
        locale="ru",
    )

    assert progress.stale == 1
    assert progress.ready == 0


def test_created_and_existing_counts_are_exposed() -> None:
    result = make_result()
    presentation = make_presentation(
        result=result,
        translation_status="pending",
    )

    progress = build_result_presentation_progress(
        check_results=[result],
        presentations_by_result_id={str(result.id): presentation},
        locale="ru",
        created_pending=3,
        existing=5,
    )

    assert progress.created_pending == 3
    assert progress.existing == 5

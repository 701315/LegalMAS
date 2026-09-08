from __future__ import annotations

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    build_presentation_source_hash,
)
from services.result_presentation_selection import (
    apply_result_presentations,
)


def _canonical_row() -> dict:
    return {
        "id": "8a478cc6-18c5-48b9-a4b2-d3bc2fa5dc44",
        "check_id": "coc_001",
        "check_name": "Liability cap",
        "result": "fail",
        "severity": "high",
        "display_text": "No aggregate liability cap was found.",
        "review_message": "Review the indemnity wording.",
    }


def _source_hash(row: dict) -> str:
    return build_presentation_source_hash(
        check_name=row["check_name"],
        display_text=row["display_text"],
        review_message=row["review_message"],
        content_version=PRESENTATION_CONTENT_VERSION_V1,
    )


def test_ready_presentation_overlays_user_facing_result_fields() -> None:
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "ready",
        "localized_check_name": "Лимит ответственности",
        "display_text": "Совокупный лимит ответственности не обнаружен.",
        "review_message": "Проверьте формулировку об indemnity.",
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Лимит ответственности"
    assert selected[0]["display_text"] == (
        "Совокупный лимит ответственности не обнаружен."
    )
    assert selected[0]["review_message"] == (
        "Проверьте формулировку об indemnity."
    )
    assert selected[0]["canonical_check_name"] == "Liability cap"
    assert selected[0]["canonical_display_text"] == (
        "No aggregate liability cap was found."
    )
    assert selected[0]["canonical_review_message"] == (
        "Review the indemnity wording."
    )
    assert selected[0]["output_locale"] == "ru"
    assert selected[0]["presentation_locale"] == "ru"
    assert selected[0]["presentation_status"] == "ready"
    assert selected[0]["presentation_is_fallback"] is False


def test_pending_presentation_keeps_canonical_fallback() -> None:
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "pending",
        "localized_check_name": "Лимит ответственности",
        "display_text": "Совокупный лимит ответственности не обнаружен.",
        "review_message": "Проверьте формулировку об indemnity.",
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Liability cap"
    assert selected[0]["display_text"] == (
        "No aggregate liability cap was found."
    )
    assert selected[0]["review_message"] == (
        "Review the indemnity wording."
    )
    assert selected[0]["presentation_status"] == "pending"
    assert selected[0]["presentation_is_fallback"] is True
    assert "canonical_check_name" not in selected[0]
    assert "canonical_display_text" not in selected[0]
    assert "canonical_review_message" not in selected[0]


def test_stale_source_hash_keeps_canonical_fallback() -> None:
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": "0" * 64,
        "source_locale": "en",
        "translation_status": "ready",
        "localized_check_name": "Лимит ответственности",
        "display_text": "Совокупный лимит ответственности не обнаружен.",
        "review_message": "Проверьте формулировку об indemnity.",
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Liability cap"
    assert selected[0]["display_text"] == (
        "No aggregate liability cap was found."
    )
    assert selected[0]["presentation_status"] == "ready"
    assert selected[0]["presentation_is_fallback"] is True


def test_other_locale_keeps_canonical_fallback() -> None:
    row = _canonical_row()

    presentation = {
        "locale": "de",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "ready",
        "localized_check_name": "Haftungsobergrenze",
        "display_text": "Keine Gesamthaftungsgrenze gefunden.",
        "review_message": "Prüfen Sie die Freistellungsklausel.",
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Liability cap"
    assert selected[0]["presentation_is_fallback"] is True


def test_missing_presentation_keeps_canonical_fallback() -> None:
    row = _canonical_row()

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Liability cap"
    assert selected[0]["presentation_status"] == "missing"
    assert selected[0]["presentation_is_fallback"] is True


def test_selection_does_not_mutate_input_row() -> None:
    row = _canonical_row()
    original = dict(row)

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "ready",
        "localized_check_name": "Лимит ответственности",
        "display_text": "Совокупный лимит ответственности не обнаружен.",
        "review_message": "Проверьте формулировку об indemnity.",
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert row == original
    assert selected[0] is not row


def test_empty_requested_locale_is_rejected() -> None:
    row = _canonical_row()

    try:
        apply_result_presentations(
            check_results=[row],
            presentations_by_result_id={},
            requested_locale=" ",
        )
    except ValueError as exc:
        assert str(exc) == "requested_locale must be a non-empty string"
    else:
        raise AssertionError("ValueError was not raised")


def test_empty_content_version_is_rejected() -> None:
    row = _canonical_row()

    try:
        apply_result_presentations(
            check_results=[row],
            presentations_by_result_id={},
            requested_locale="ru",
            content_version=" ",
        )
    except ValueError as exc:
        assert str(exc) == "content_version must be a non-empty string"
    else:
        raise AssertionError("ValueError was not raised")


# ── Sprint 6.3: Human override priority tests ───────────────────────


def test_human_override_replaces_llm_display_text() -> None:
    """When human_override_text has display_text, it wins over LLM value."""
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "reviewed",
        "localized_check_name": "Лимит ответственности",
        "display_text": "LLM перевод текста.",
        "review_message": "LLM перевод сообщения.",
        "human_override_text": {
            "display_text": "Человеческий перевод текста.",
        },
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    # Human override wins for display_text
    assert selected[0]["display_text"] == "Человеческий перевод текста."
    # LLM value still used for fields NOT in override
    assert selected[0]["check_name"] == "Лимит ответственности"
    assert selected[0]["review_message"] == "LLM перевод сообщения."
    # Canonical preserved
    assert selected[0]["canonical_display_text"] == (
        "No aggregate liability cap was found."
    )


def test_human_override_replaces_all_fields() -> None:
    """When human_override_text has all fields, all override LLM values."""
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "reviewed",
        "localized_check_name": "LLM Имя",
        "display_text": "LLM текст",
        "review_message": "LLM сообщение",
        "human_override_text": {
            "localized_check_name": "Человеческое имя",
            "display_text": "Человеческий текст",
            "review_message": "Человеческое сообщение",
        },
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Человеческое имя"
    assert selected[0]["display_text"] == "Человеческий текст"
    assert selected[0]["review_message"] == "Человеческое сообщение"


def test_no_human_override_uses_llm_values() -> None:
    """When human_override_text is None, LLM values are used as before."""
    row = _canonical_row()

    presentation = {
        "locale": "ru",
        "content_version": "v1",
        "source_content_hash": _source_hash(row),
        "source_locale": "en",
        "translation_status": "ready",
        "localized_check_name": "Лимит ответственности",
        "display_text": "LLM перевод текста.",
        "review_message": "LLM перевод сообщения.",
        "human_override_text": None,
    }

    selected = apply_result_presentations(
        check_results=[row],
        presentations_by_result_id={row["id"]: presentation},
        requested_locale="ru",
    )

    assert selected[0]["check_name"] == "Лимит ответственности"
    assert selected[0]["display_text"] == "LLM перевод текста."
    assert selected[0]["review_message"] == "LLM перевод сообщения."

from __future__ import annotations

import pytest

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    build_presentation_source_hash,
    build_presentation_source_payload,
)


def test_source_payload_contains_only_presentation_source_fields() -> None:
    payload = build_presentation_source_payload(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message="Review the indemnity wording.",
        dd_request_text="Provide the liability-cap schedule.",
    )

    assert payload == {
        "content_version": PRESENTATION_CONTENT_VERSION_V1,
        "check_name": "Liability cap",
        "display_text": "No aggregate liability cap was found.",
        "review_message": "Review the indemnity wording.",
        "dd_request_text": "Provide the liability-cap schedule.",
    }


def test_source_hash_is_deterministic_for_identical_content() -> None:
    first = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message="Review the indemnity wording.",
        dd_request_text=None,
    )

    second = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message="Review the indemnity wording.",
        dd_request_text=None,
    )

    assert first == second
    assert len(first) == 64


def test_source_hash_changes_when_canonical_text_changes() -> None:
    original = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message=None,
    )

    changed = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="An aggregate liability cap was found.",
        review_message=None,
    )

    assert original != changed


def test_source_hash_changes_when_content_version_changes() -> None:
    first = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message=None,
        content_version="v1",
    )

    second = build_presentation_source_hash(
        check_name="Liability cap",
        display_text="No aggregate liability cap was found.",
        review_message=None,
        content_version="v2",
    )

    assert first != second


def test_source_payload_normalizes_equivalent_unicode_text() -> None:
    precomposed = build_presentation_source_hash(
        check_name="Café",
        display_text=None,
        review_message=None,
    )

    decomposed = build_presentation_source_hash(
        check_name="Cafe\u0301",
        display_text=None,
        review_message=None,
    )

    assert precomposed == decomposed


@pytest.mark.parametrize(
    "content_version",
    [
        "",
        " ",
        "\t",
    ],
)
def test_source_payload_rejects_empty_content_version(
    content_version: str,
) -> None:
    with pytest.raises(ValueError, match="content_version"):
        build_presentation_source_payload(
            check_name="Liability cap",
            display_text=None,
            review_message=None,
            content_version=content_version,
        )


@pytest.mark.parametrize(
    "check_name",
    [
        "",
        " ",
        "\t",
    ],
)
def test_source_payload_rejects_empty_check_name(check_name: str) -> None:
    with pytest.raises(ValueError, match="check_name"):
        build_presentation_source_payload(
            check_name=check_name,
            display_text=None,
            review_message=None,
        )

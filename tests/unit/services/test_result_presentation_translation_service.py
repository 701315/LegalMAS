from __future__ import annotations

import pytest

from services.result_presentation_translation_service import (
    build_result_presentation_translation_prompt,
    parse_result_presentation_translation,
)


def test_prompt_contains_only_presentation_fields() -> None:
    prompt = build_result_presentation_translation_prompt(
        source_locale="ru",
        target_locale="en",
        check_name="Ограничение ответственности",
        display_text="Совокупный лимит не установлен.",
        review_message="Рекомендуется согласовать лимит.",
    )

    assert "Ограничение ответственности" in prompt
    assert "target_locale" in prompt
    assert "localized_check_name" in prompt
    assert "structured_data" not in prompt
    assert "evidence" not in prompt.lower()


def test_prompt_preserves_null_optional_fields() -> None:
    prompt = build_result_presentation_translation_prompt(
        source_locale="ru",
        target_locale="en",
        check_name="Ограничение ответственности",
        display_text=None,
        review_message=None,
    )

    assert '"display_text": null' in prompt
    assert '"review_message": null' in prompt


def test_prompt_rejects_empty_target_locale() -> None:
    with pytest.raises(ValueError, match="target_locale"):
        build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale=" ",
            check_name="Ограничение ответственности",
            display_text="Текст",
            review_message="Сообщение",
        )


def test_prompt_rejects_empty_check_name() -> None:
    with pytest.raises(ValueError, match="check_name"):
        build_result_presentation_translation_prompt(
            source_locale="ru",
            target_locale="en",
            check_name=" ",
            display_text="Текст",
            review_message="Сообщение",
        )


def test_parser_accepts_valid_translation_payload() -> None:
    parsed = parse_result_presentation_translation(
        """
        {
          "localized_check_name": "Limitation of Liability",
          "display_text": "No aggregate liability cap is specified.",
          "review_message": "It is recommended to agree a liability cap."
        }
        """
    )

    assert parsed == {
        "localized_check_name": "Limitation of Liability",
        "display_text": "No aggregate liability cap is specified.",
        "review_message": "It is recommended to agree a liability cap.",
    }


def test_parser_accepts_null_optional_fields() -> None:
    parsed = parse_result_presentation_translation(
        """
        {
          "localized_check_name": "Limitation of Liability",
          "display_text": null,
          "review_message": null
        }
        """
    )

    assert parsed["localized_check_name"] == "Limitation of Liability"
    assert parsed["display_text"] is None
    assert parsed["review_message"] is None


def test_parser_rejects_non_json_response() -> None:
    with pytest.raises(ValueError, match="valid JSON"):
        parse_result_presentation_translation(
            "```json\n"
            '{"localized_check_name":"Name"}'
            "\n```"
        )


def test_parser_rejects_extra_or_missing_keys() -> None:
    with pytest.raises(ValueError, match="exactly"):
        parse_result_presentation_translation(
            """
            {
              "localized_check_name": "Name",
              "display_text": "Text",
              "review_message": null,
              "extra": "must not exist"
            }
            """
        )


def test_parser_rejects_empty_localized_check_name() -> None:
    with pytest.raises(ValueError, match="localized_check_name"):
        parse_result_presentation_translation(
            """
            {
              "localized_check_name": "   ",
              "display_text": "Text",
              "review_message": null
            }
            """
        )


def test_parser_rejects_invalid_optional_field_type() -> None:
    with pytest.raises(ValueError, match="display_text"):
        parse_result_presentation_translation(
            """
            {
              "localized_check_name": "Name",
              "display_text": 123,
              "review_message": null
            }
            """
        )

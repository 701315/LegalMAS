"""
Read-side locale-specific presentation selection for canonical CheckResult rows.

This module does not call the database and does not translate content.
It overlays a ready locale-specific presentation onto copied result dictionaries
only when its source-content hash matches the current canonical source.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from core.result_presentation_content import (
    PRESENTATION_CONTENT_VERSION_V1,
    PRESENTATION_CONTENT_VERSION_V2,
    build_presentation_source_hash,
)


_READY_PRESENTATION_STATUSES = frozenset(
    {
        "ready",
        "reviewed",
        "approved",
    }
)


def _presentation_value(
    presentation: Any,
    field_name: str,
) -> Any:
    """Read a presentation field from either an ORM object or a mapping."""
    if isinstance(presentation, Mapping):
        return presentation.get(field_name)

    return getattr(presentation, field_name, None)


def _canonical_source_hash(
    row: Mapping[str, Any],
    *,
    content_version: str,
) -> str:
    """Build the canonical fingerprint for one check-result row."""
    return build_presentation_source_hash(
        check_name=str(row.get("check_name") or ""),
        display_text=row.get("display_text"),
        review_message=row.get("review_message"),
        structured_data=(
            row.get("structured_data")
            if content_version == PRESENTATION_CONTENT_VERSION_V2
            else None
        ),
        content_version=content_version,
    )


def apply_result_presentations(
    *,
    check_results: Sequence[Mapping[str, Any]],
    presentations_by_result_id: Mapping[str, Any],
    requested_locale: str,
    content_version: str = PRESENTATION_CONTENT_VERSION_V2,
) -> list[dict[str, Any]]:
    """
    Return copied check-result rows enriched with presentation selection metadata.

    A ready/reviewed/approved presentation is used only if:
    - it belongs to the canonical result ID;
    - its source_content_hash matches current canonical content;
    - its locale matches requested_locale;
    - its content_version matches content_version.

    Otherwise the returned row uses canonical fields and exposes explicit
    fallback metadata for the future API and frontend layers.
    """
    normalized_locale = requested_locale.strip()

    if not normalized_locale:
        raise ValueError("requested_locale must be a non-empty string")

    normalized_version = content_version.strip()

    if not normalized_version:
        raise ValueError("content_version must be a non-empty string")

    selected_rows: list[dict[str, Any]] = []

    for source_row in check_results:
        row = dict(source_row)

        result_id = str(row.get("id") or "")
        canonical_hash = _canonical_source_hash(
            row,
            content_version=normalized_version,
        )

        presentation = presentations_by_result_id.get(result_id)

        presentation_locale = _presentation_value(
            presentation,
            "locale",
        )
        presentation_version = _presentation_value(
            presentation,
            "content_version",
        )
        presentation_hash = _presentation_value(
            presentation,
            "source_content_hash",
        )
        presentation_status = _presentation_value(
            presentation,
            "translation_status",
        )

        is_matching_ready_presentation = (
            presentation is not None
            and presentation_locale == normalized_locale
            and presentation_version == normalized_version
            and presentation_hash == canonical_hash
            and presentation_status in _READY_PRESENTATION_STATUSES
        )

        row["output_locale"] = normalized_locale
        row["presentation_locale"] = normalized_locale  # Deprecated alias for backward compatibility
        row["presentation_content_version"] = normalized_version
        row["presentation_source_hash"] = canonical_hash
        row["presentation_source_locale"] = _presentation_value(
            presentation,
            "source_locale",
        )
        row["presentation_status"] = (
            presentation_status if presentation is not None else "missing"
        )
        row["presentation_is_fallback"] = not is_matching_ready_presentation

        if is_matching_ready_presentation:
            localized_check_name = _presentation_value(
                presentation,
                "localized_check_name",
            )
            localized_display_text = _presentation_value(
                presentation,
                "display_text",
            )
            localized_review_message = _presentation_value(
                presentation,
                "review_message",
            )
            localized_structured_data = _presentation_value(
                presentation,
                "localized_structured_data",
            )
            localized_dd_request_text = _presentation_value(
                presentation,
                "dd_request_text",
            )
            localized_dd_request_addressee = _presentation_value(
                presentation,
                "dd_request_addressee",
            )

            # Sprint 6.3: Human override takes priority over LLM translation.
            # If a QC reviewer edited the presentation, human_override_text
            # contains the corrected fields. We merge selectively: only
            # non-None override fields replace the LLM values.
            human_override = _presentation_value(
                presentation,
                "human_override_text",
            )
            if isinstance(human_override, dict):
                if human_override.get("localized_check_name") is not None:
                    localized_check_name = human_override["localized_check_name"]
                if human_override.get("display_text") is not None:
                    localized_display_text = human_override["display_text"]
                if human_override.get("review_message") is not None:
                    localized_review_message = human_override["review_message"]
                if human_override.get("localized_structured_data") is not None:
                    localized_structured_data = human_override[
                        "localized_structured_data"
                    ]

            row["canonical_check_name"] = row.get("check_name")
            row["canonical_display_text"] = row.get("display_text")
            row["canonical_review_message"] = row.get("review_message")
            row["canonical_structured_data"] = row.get("structured_data")

            if localized_check_name:
                row["check_name"] = localized_check_name

            if localized_display_text:
                row["display_text"] = localized_display_text

            if localized_review_message:
                row["review_message"] = localized_review_message

            if localized_dd_request_text:
                row["dd_request_text"] = localized_dd_request_text

            if localized_dd_request_addressee:
                row["dd_request_addressee"] = localized_dd_request_addressee

            # Matrix cells: free-text values translated for requested locale.
            if isinstance(localized_structured_data, dict) and localized_structured_data:
                row["localized_structured_data"] = localized_structured_data

        selected_rows.append(row)

    return selected_rows

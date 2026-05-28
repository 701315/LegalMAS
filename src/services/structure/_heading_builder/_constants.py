# src/services/structure/_heading_builder/_constants.py

"""Константы и наборы типов для сборки заголовков."""

from __future__ import annotations

_MAX_HEADING_RAW_TEXT_LEN = 2000

_REQUIRED_ELEMENT_FIELDS = (
    "scope",
    "segment_id",
    "segment_type",
    "segment_order",
    "element_type",
)

_EXCLUDED_ELEMENT_TYPES = {
    "body_text",
    "table_content",
    "requisites_block",
    "signature_block",
    "page_artifact",
    "unknown_layout",
    "toc_header",
    "toc_line",
    "possible_toc",
}

_ALLOWED_ELEMENT_TYPES = {
    "heading_candidate",
    "section_heading",
    "subsection_heading",
    "appendix_heading",
    "enumerated_clause",
    "definition_item",
    "list_item",
    "toc_false_positive",
}


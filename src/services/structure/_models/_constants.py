# src/services/structure/models/_constants.py

"""
Константы и валидационные наборы для structure models.

Разделены на два блока:
  - Structural constants  — используются в MutableHierarchyNode / FrozenHierarchyNode
  - Semantic constants    — используются в SemanticNodeMetadata
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Scope
# ---------------------------------------------------------------------------

DEFAULT_SCOPE = "main_contract"
SCOPE_NAME_RE = re.compile(r"^[a-z0-9_]+$")

# ---------------------------------------------------------------------------
# Structure confidence
# ---------------------------------------------------------------------------

STRUCTURE_CONFIDENCE_HIGH = "HIGH"
STRUCTURE_CONFIDENCE_MEDIUM = "MEDIUM"
STRUCTURE_CONFIDENCE_LOW = "LOW"
STRUCTURE_CONFIDENCE_FAILED = "FAILED"

VALID_STRUCTURE_CONFIDENCE: frozenset[str] = frozenset(
    {
        STRUCTURE_CONFIDENCE_HIGH,
        STRUCTURE_CONFIDENCE_MEDIUM,
        STRUCTURE_CONFIDENCE_LOW,
        STRUCTURE_CONFIDENCE_FAILED,
    }
)

# ---------------------------------------------------------------------------
# Segment confidence
# ---------------------------------------------------------------------------

SEGMENT_CONFIDENCE_HIGH = "HIGH"
SEGMENT_CONFIDENCE_MEDIUM = "MEDIUM"
SEGMENT_CONFIDENCE_LOW = "LOW"

VALID_SEGMENT_CONFIDENCE: frozenset[str] = frozenset(
    {
        SEGMENT_CONFIDENCE_HIGH,
        SEGMENT_CONFIDENCE_MEDIUM,
        SEGMENT_CONFIDENCE_LOW,
    }
)

# ---------------------------------------------------------------------------
# Segment types
# ---------------------------------------------------------------------------

SEGMENT_TYPE_CONTRACT = "contract"
SEGMENT_TYPE_APPENDIX = "appendix"
SEGMENT_TYPE_AMENDMENT = "amendment"
SEGMENT_TYPE_ACT = "act"
SEGMENT_TYPE_INVOICE = "invoice"
SEGMENT_TYPE_SCHEDULE = "schedule"
SEGMENT_TYPE_PROTOCOL = "protocol"
SEGMENT_TYPE_OTHER = "other"
SEGMENT_TYPE_UNKNOWN = "unknown"

VALID_SEGMENT_TYPES: frozenset[str] = frozenset(
    {
        SEGMENT_TYPE_CONTRACT,
        SEGMENT_TYPE_APPENDIX,
        SEGMENT_TYPE_AMENDMENT,
        SEGMENT_TYPE_ACT,
        SEGMENT_TYPE_INVOICE,
        SEGMENT_TYPE_SCHEDULE,
        SEGMENT_TYPE_PROTOCOL,
        SEGMENT_TYPE_OTHER,
        SEGMENT_TYPE_UNKNOWN,
    }
)

# ---------------------------------------------------------------------------
# Node kinds  (structural)
# ---------------------------------------------------------------------------

NODE_KIND_LEAF = "leaf"
NODE_KIND_SECTION = "section"

VALID_NODE_KINDS: frozenset[str] = frozenset({NODE_KIND_LEAF, NODE_KIND_SECTION})

# ---------------------------------------------------------------------------
# Range end reasons  (structural)
# ---------------------------------------------------------------------------

VALID_RANGE_END_REASONS: frozenset[str] = frozenset(
    {
        "first_child",
        "next_same_or_higher",
        "segment_end",
        "fallback_boundary",
        "unbounded_error",
        "segment_end_recovered",
        "fallback_boundary_recovered",
    }
)

# ---------------------------------------------------------------------------
# TOC confidence bands
# ---------------------------------------------------------------------------

TOC_CONFIDENCE_NONE = "none"
TOC_CONFIDENCE_LOW = "low"
TOC_CONFIDENCE_PARTIAL = "partial"
TOC_CONFIDENCE_HIGH = "high"

VALID_TOC_CONFIDENCE_BANDS: frozenset[str] = frozenset(
    {
        TOC_CONFIDENCE_NONE,
        TOC_CONFIDENCE_LOW,
        TOC_CONFIDENCE_PARTIAL,
        TOC_CONFIDENCE_HIGH,
    }
)

# ---------------------------------------------------------------------------
# Parse quality status
# ---------------------------------------------------------------------------

PARSE_QUALITY_OK = "ok"
PARSE_QUALITY_WEAK = "weak"
PARSE_QUALITY_FAILED = "failed"

VALID_PARSE_QUALITY_STATUS: frozenset[str] = frozenset(
    {
        PARSE_QUALITY_OK,
        PARSE_QUALITY_WEAK,
        PARSE_QUALITY_FAILED,
    }
)

# ---------------------------------------------------------------------------
# Semantic element types
# Используются ТОЛЬКО в SemanticNodeMetadata и downstream (Phase 5+, Phase 12).
# НЕ используются в FSM, Resolution, Recovery.
# ---------------------------------------------------------------------------

SEMANTIC_ELEMENT_TYPE_SECTION_HEADING = "section_heading"
SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING = "subsection_heading"
SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM = "definition_item"
SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE = "enumerated_clause"
SEMANTIC_ELEMENT_TYPE_LIST_ITEM = "list_item"
SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING = "appendix_heading"
SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK = "signature_block"
SEMANTIC_ELEMENT_TYPE_BODY_TEXT = "body_text"

VALID_SEMANTIC_ELEMENT_TYPES: frozenset[str] = frozenset(
    {
        SEMANTIC_ELEMENT_TYPE_SECTION_HEADING,
        SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING,
        SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM,
        SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE,
        SEMANTIC_ELEMENT_TYPE_LIST_ITEM,
        SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING,
        SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK,
        SEMANTIC_ELEMENT_TYPE_BODY_TEXT,
    }
)

HEADING_SEMANTIC_TYPES: frozenset[str] = frozenset(
    {
        SEMANTIC_ELEMENT_TYPE_SECTION_HEADING,
        SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING,
        SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING,
    }
)

BODY_SEMANTIC_TYPES: frozenset[str] = frozenset(
    {
        SEMANTIC_ELEMENT_TYPE_BODY_TEXT,
        SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM,
        SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE,
        SEMANTIC_ELEMENT_TYPE_LIST_ITEM,
    }
)

# Используется Recovery Engine (Phase 4) при вычислении attachment score.
# НЕ используется в FSM напрямую.
NEGATIVE_HEADING_SEMANTIC_TYPES: frozenset[str] = frozenset(
    {
        SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM,
        SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK,
        SEMANTIC_ELEMENT_TYPE_BODY_TEXT,
    }
)

# ---------------------------------------------------------------------------
# Structural hash contract
# Изменение STRUCTURAL_HASH_VERSION или STRUCTURAL_HASH_FIELDS делает
# все существующие хэши невалидными — требует миграции canonical artifacts.
# ---------------------------------------------------------------------------

STRUCTURAL_HASH_FIELDS = ("normalized_path", "stable_level", "sibling_index", "scope_id")
STRUCTURAL_HASH_VERSION = 1



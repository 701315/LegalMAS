# src/services/structure/models.py

"""
Data models for document structure tree and file-level graph.
Публичный фасад, перенаправляющий запросы во внутренний пакет _models.
"""

from __future__ import annotations

# Константы
from services.structure._models._constants import (
    BODY_SEMANTIC_TYPES,
    DEFAULT_SCOPE,
    HEADING_SEMANTIC_TYPES,
    NEGATIVE_HEADING_SEMANTIC_TYPES,
    NODE_KIND_LEAF,
    NODE_KIND_SECTION,
    PARSE_QUALITY_FAILED,
    PARSE_QUALITY_OK,
    PARSE_QUALITY_WEAK,
    SCOPE_NAME_RE,
    SEGMENT_CONFIDENCE_HIGH,
    SEGMENT_CONFIDENCE_LOW,
    SEGMENT_CONFIDENCE_MEDIUM,
    SEGMENT_TYPE_ACT,
    SEGMENT_TYPE_AMENDMENT,
    SEGMENT_TYPE_APPENDIX,
    SEGMENT_TYPE_CONTRACT,
    SEGMENT_TYPE_INVOICE,
    SEGMENT_TYPE_OTHER,
    SEGMENT_TYPE_PROTOCOL,
    SEGMENT_TYPE_SCHEDULE,
    SEGMENT_TYPE_UNKNOWN,
    SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING,
    SEMANTIC_ELEMENT_TYPE_BODY_TEXT,
    SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM,
    SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE,
    SEMANTIC_ELEMENT_TYPE_LIST_ITEM,
    SEMANTIC_ELEMENT_TYPE_SECTION_HEADING,
    SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK,
    SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING,
    STRUCTURE_CONFIDENCE_FAILED,
    STRUCTURE_CONFIDENCE_HIGH,
    STRUCTURE_CONFIDENCE_LOW,
    STRUCTURE_CONFIDENCE_MEDIUM,
    TOC_CONFIDENCE_HIGH,
    TOC_CONFIDENCE_LOW,
    TOC_CONFIDENCE_NONE,
    TOC_CONFIDENCE_PARTIAL,
    VALID_NODE_KINDS,
    VALID_PARSE_QUALITY_STATUS,
    VALID_RANGE_END_REASONS,
    VALID_SEGMENT_CONFIDENCE,
    VALID_SEGMENT_TYPES,
    VALID_SEMANTIC_ELEMENT_TYPES,
    VALID_STRUCTURE_CONFIDENCE,
    VALID_TOC_CONFIDENCE_BANDS,
)

# Diagnostics
from services.structure._models._diagnostics import (
    ParseQualityDiagnostics,
    TOCDiagnostics,
    embed_parse_quality_diagnostics,
    embed_toc_diagnostics,
)

# Graph
from services.structure._models._graph import (
    CrossDocumentLink,
    FileGraph,
    SegmentDocument,
)

# Identity
from services.structure._models._identity import (
    generate_scope_name,
    make_effective_uid,
    make_segment_id,
    split_effective_uid,
)

# Nodes
from services.structure._models._nodes import (
    ClauseNode,
    CrossReference,
    CrossSegmentRef,
)

# Result
from services.structure._models._result import FileStructureResult

# Tree
from services.structure._models._tree import ClauseTree

__all__ = [
    "DEFAULT_SCOPE",
    "SCOPE_NAME_RE",
    "STRUCTURE_CONFIDENCE_HIGH",
    "STRUCTURE_CONFIDENCE_MEDIUM",
    "STRUCTURE_CONFIDENCE_LOW",
    "STRUCTURE_CONFIDENCE_FAILED",
    "VALID_STRUCTURE_CONFIDENCE",
    "SEGMENT_CONFIDENCE_HIGH",
    "SEGMENT_CONFIDENCE_MEDIUM",
    "SEGMENT_CONFIDENCE_LOW",
    "VALID_SEGMENT_CONFIDENCE",
    "SEGMENT_TYPE_CONTRACT",
    "SEGMENT_TYPE_APPENDIX",
    "SEGMENT_TYPE_AMENDMENT",
    "SEGMENT_TYPE_ACT",
    "SEGMENT_TYPE_INVOICE",
    "SEGMENT_TYPE_SCHEDULE",
    "SEGMENT_TYPE_PROTOCOL",
    "SEGMENT_TYPE_OTHER",
    "SEGMENT_TYPE_UNKNOWN",
    "VALID_SEGMENT_TYPES",
    "NODE_KIND_LEAF",
    "NODE_KIND_SECTION",
    "VALID_NODE_KINDS",
    "VALID_RANGE_END_REASONS",
    "TOC_CONFIDENCE_NONE",
    "TOC_CONFIDENCE_LOW",
    "TOC_CONFIDENCE_PARTIAL",
    "TOC_CONFIDENCE_HIGH",
    "VALID_TOC_CONFIDENCE_BANDS",
    "PARSE_QUALITY_OK",
    "PARSE_QUALITY_WEAK",
    "PARSE_QUALITY_FAILED",
    "VALID_PARSE_QUALITY_STATUS",
    "SEMANTIC_ELEMENT_TYPE_SECTION_HEADING",
    "SEMANTIC_ELEMENT_TYPE_SUBSECTION_HEADING",
    "SEMANTIC_ELEMENT_TYPE_DEFINITION_ITEM",
    "SEMANTIC_ELEMENT_TYPE_ENUMERATED_CLAUSE",
    "SEMANTIC_ELEMENT_TYPE_LIST_ITEM",
    "SEMANTIC_ELEMENT_TYPE_APPENDIX_HEADING",
    "SEMANTIC_ELEMENT_TYPE_SIGNATURE_BLOCK",
    "SEMANTIC_ELEMENT_TYPE_BODY_TEXT",
    "VALID_SEMANTIC_ELEMENT_TYPES",
    "HEADING_SEMANTIC_TYPES",
    "BODY_SEMANTIC_TYPES",
    "NEGATIVE_HEADING_SEMANTIC_TYPES",
    "make_effective_uid",
    "split_effective_uid",
    "generate_scope_name",
    "make_segment_id",
    "TOCDiagnostics",
    "ParseQualityDiagnostics",
    "embed_toc_diagnostics",
    "embed_parse_quality_diagnostics",
    "ClauseNode",
    "CrossReference",
    "CrossSegmentRef",
    "ClauseTree",
    "SegmentDocument",
    "CrossDocumentLink",
    "FileGraph",
    "FileStructureResult",
]

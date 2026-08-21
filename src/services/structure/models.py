# src/services/structure/models.py

"""
Public data-model facade for the document structure subsystem.

Назначение:
- предоставить стабильную публичную точку импорта для consumers;
- скрыть внутреннюю организацию services.structure._models.*;
- удерживать совместимость во время phase-by-phase refactoring.

Важно:
- этот модуль является только facade/re-export layer;
- бизнес-логика, validation и orchestration здесь не размещаются;
- новые модели добавляются сюда только если они являются частью публичного API;
- внутренние/экспериментальные модели не должны реэкспортироваться автоматически.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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
    SEGMENT_TYPE_HEADING,
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
    STRUCTURAL_HASH_FIELDS,
    STRUCTURAL_HASH_VERSION,
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

# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------

from services.structure._models._diagnostics import (
    ParseQualityDiagnostics,
    TOCDiagnostics,
    embed_parse_quality_diagnostics,
    embed_toc_diagnostics,
)

# ---------------------------------------------------------------------------
# File / cross-document graph
# ---------------------------------------------------------------------------

from services.structure._models._graph import (
    CrossDocumentLink,
    FileGraph,
    SegmentDocument,
)

from services.structure._models._crossref_graph import (
    CrossReferenceGraph,
    CrossReferenceStats,
)

# ---------------------------------------------------------------------------
# Identity / deterministic IDs
# ---------------------------------------------------------------------------

from services.structure._models._identity import (
    generate_scope_name,
    make_effective_uid,
    make_segment_id,
    split_effective_uid,
)

from services.structure._models._structural_hash import (
    compute_structural_hash,
    structural_hash_version,
)

# ---------------------------------------------------------------------------
# Tree nodes / metadata
# ---------------------------------------------------------------------------

from services.structure._models._nodes import (
    CrossReference,
    CrossSegmentRef,
    FrozenHierarchyNode,
    MutableHierarchyNode,
    freeze,
)

from services.structure._models._semantic_metadata import (
    RecoveryInfo,
    SemanticNodeMetadata,
)

from services.structure._models._tree import ClauseTree

# ---------------------------------------------------------------------------
# Syntax / heading candidates
# ---------------------------------------------------------------------------

from services.structure._models._syntax import (
    HEADING_CONFIDENCE_THRESHOLD,
    HierarchyTokenType,
    SyntaxHeadingCandidate,
)

from services.structure._models._syntax_adapter import (
    scored_to_syntax_candidate,
)

# ---------------------------------------------------------------------------
# FSM
# ---------------------------------------------------------------------------

from services.structure._models._fsm import (
    FSMAttachResult,
    FSMEvent,
    FSMEventType,
)

from services.structure._models._fsm_summary import FSMBuildSummary

# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------

from services.structure._models._resolution import (
    ResolutionAuditLog,
    ResolutionResult,
    RewriteType,
    StructuralRewrite,
)

# ---------------------------------------------------------------------------
# Recovery
# ---------------------------------------------------------------------------

from services.structure._models._recovery import (
    CandidateWindow,
    DEFAULT_CANDIDATE_WINDOW,
    RecoveryCandidate,
    RecoveryDecision,
    RecoveryReport,
    RecoveryStrategyType,
    TieBreakPolicy,
)

# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------

from services.structure._models._confidence import (
    ConfidenceInput,
    DegradedModeConfig,
    RETRIEVAL_SAFE_THRESHOLD,
    StructuralConfidence,
)

# ---------------------------------------------------------------------------
# Canonical artifacts
# ---------------------------------------------------------------------------

from services.structure._models._artifacts import (
    CanonicalArtifactRefs,
    CanonicalArtifactRegistry,
    SegmentArtifactRefs,
)

# ---------------------------------------------------------------------------
# Analysis / postbuild quality (Phase 9)
# ---------------------------------------------------------------------------

from services.structure._models._analysis import (
    CohesionMetrics,
    FileStructureAnalysisResult,
    QualityThresholds,
    QualityWarning,
    QualityWarningCode,
    RecommendedChunkingMode,
    SegmentAnalysisArtifacts,
    StructureMetrics,
    StructureQualityReport,
    WarningSeverity,
)


# ---------------------------------------------------------------------------
# Chunk Planner (Phase 10)
# ---------------------------------------------------------------------------

from services.structure.chunk_planner._types import (
    ChunkingModeDecision,
    ChunkingTokenParams,
    FileChunkPlan,
    SegmentChunkPlan,
    TOKENS_MODE_A,
    TOKENS_MODE_B,
    TOKENS_MODE_C,
)


# ---------------------------------------------------------------------------
# Pipeline result
# ---------------------------------------------------------------------------

from services.structure._models._result import FileStructureResult

from services.structure.chunk_planner._retrieval_readiness import (
    RetrievalReadinessReport,
)

# Public facade contract.
# Keep explicit ordering by domain to reduce accidental API drift.
__all__ = [
    # Constants
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
    "SEGMENT_TYPE_HEADING",
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
    "STRUCTURAL_HASH_VERSION",
    "STRUCTURAL_HASH_FIELDS",
    # Identity / hashing
    "compute_structural_hash",
    "structural_hash_version",
    "make_effective_uid",
    "split_effective_uid",
    "generate_scope_name",
    "make_segment_id",
    # Diagnostics
    "TOCDiagnostics",
    "ParseQualityDiagnostics",
    "embed_toc_diagnostics",
    "embed_parse_quality_diagnostics",
    # Tree / nodes
    "MutableHierarchyNode",
    "FrozenHierarchyNode",
    "freeze",
    "SemanticNodeMetadata",
    "RecoveryInfo",
    "CrossReference",
    "CrossSegmentRef",
    "ClauseTree",
    # File / graph
    "SegmentDocument",
    "CrossDocumentLink",
    "FileGraph",
    "CrossReferenceGraph",
    "CrossReferenceStats",
    # Syntax
    "HierarchyTokenType",
    "SyntaxHeadingCandidate",
    "HEADING_CONFIDENCE_THRESHOLD",
    "scored_to_syntax_candidate",
    # FSM
    "FSMEventType",
    "FSMEvent",
    "FSMAttachResult",
    "FSMBuildSummary",
    # Resolution
    "RewriteType",
    "StructuralRewrite",
    "ResolutionAuditLog",
    "ResolutionResult",
    # Recovery
    "RecoveryStrategyType",
    "TieBreakPolicy",
    "CandidateWindow",
    "DEFAULT_CANDIDATE_WINDOW",
    "RecoveryCandidate",
    "RecoveryDecision",
    "RecoveryReport",
    # Confidence
    "RETRIEVAL_SAFE_THRESHOLD",
    "ConfidenceInput",
    "DegradedModeConfig",
    "StructuralConfidence",
    # Canonical artifacts
    "SegmentArtifactRefs",
    "CanonicalArtifactRefs",
    "CanonicalArtifactRegistry",
    # Pipeline result
    "FileStructureResult",
    # Analysis / postbuild quality (Phase 9)
    "RecommendedChunkingMode",
    "WarningSeverity",
    "QualityWarningCode",
    "QualityWarning",
    "QualityThresholds",
    "StructureMetrics",
    "CohesionMetrics",
    "StructureQualityReport",
    "SegmentAnalysisArtifacts",
    "FileStructureAnalysisResult",
    # Chunk Planner (Phase 10)
    "ChunkingModeDecision",
    "ChunkingTokenParams",
    "FileChunkPlan",
    "SegmentChunkPlan",
    "TOKENS_MODE_A",
    "TOKENS_MODE_B",
    "TOKENS_MODE_C",
    "RetrievalReadinessReport",
]


# src/core/pipeline_errors.py

from __future__ import annotations


class PipelineErrorType:
    STRUCTURE_V2_CONTRACT_VIOLATION = "structure_v2_contract_violation"
    CHUNKING_V2_CONTRACT_VIOLATION = "chunking_v2_contract_violation"


class StructureV2ErrorReason:
    VERSION_NOT_FOUND = "version_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    MISSING_SANITIZED_LAYOUT = "missing_sanitized_layout"
    LAYOUT_READ_ERROR = "layout_read_error"
    EMPTY_LAYOUT = "empty_layout"
    INVALID_FILE_GRAPH_SEGMENT = "invalid_file_graph_segment"
    STRUCTURE_BUILD_ERROR = "structure_build_error"
    CLAUSE_TREE_STORE_ERROR = "clause_tree_store_error"
    DOCUMENT_SEGMENTS_PERSIST_ERROR = "document_segments_persist_error"
    VERSION_UPDATE_FAILED = "version_update_failed"
    DOCUMENT_STATUS_UPDATE_FAILED = "document_status_update_failed"
    POST_FLUSH_INVISIBLE_VERSION = "post_flush_invisible_version"
    POST_FLUSH_CLAUSE_TREE_REF_MISSING = "post_flush_clause_tree_ref_missing"
    POST_FLUSH_CLAUSE_TREE_REF_MISMATCH = "post_flush_clause_tree_ref_mismatch"
    POST_FLUSH_FILE_GRAPH_REF_MISSING = "post_flush_file_graph_ref_missing"
    POST_FLUSH_FILE_GRAPH_REF_MISMATCH = "post_flush_file_graph_ref_mismatch"
    SEGMENTS_COUNT_MISMATCH = "segments_count_mismatch"
    PRIMARY_SEGMENT_INVARIANT_VIOLATED = "primary_segment_invariant_violated"


class ChunkingV2ErrorReason:
    VERSION_NOT_FOUND = "version_not_found"
    DOCUMENT_NOT_FOUND = "document_not_found"
    SEGMENTS_MISSING = "segments_missing"
    MANIFEST_EMPTY = "manifest_empty"
    MANIFEST_INCONSISTENT_WITH_SEGMENTS = "manifest_inconsistent_with_segments"
    SEGMENT_BUILDER_ERROR = "segment_builder_error"
    SEGMENT_NOT_FOUND_FOR_SNAPSHOT = "segment_not_found_for_snapshot"
    SEGMENT_CHUNKS_STORE_ERROR = "segment_chunks_store_error"
    MANIFEST_STORE_ERROR = "manifest_store_error"
    VERSION_UPDATE_FAILED = "version_update_failed"
    DOCUMENT_STATUS_UPDATE_FAILED = "document_status_update_failed"
    POST_FLUSH_INVISIBLE_VERSION = "post_flush_invisible_version"
    POST_FLUSH_MANIFEST_REF_MISSING = "post_flush_manifest_ref_missing"
    POST_FLUSH_MANIFEST_REF_MISMATCH = "post_flush_manifest_ref_mismatch"


class ChunkingQuarantineReason:
    EMPTY_CHUNKS_CONTENT = "emptychunks_content"
    EMPTY_SEGMENTS_CONTENT = "emptysegments_content"

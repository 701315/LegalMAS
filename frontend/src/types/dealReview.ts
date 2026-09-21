// =============================================================
// src/types/dealReview.ts
// DTO types for UI deal review API.
// Mirrors the backend contract from src/api/schemas/deal_review.py,
// but extended with optional fields for canonical display semantics
// and segment-aware UX.
// =============================================================

export type ReviewResult = "fail" | "pass" | "unclear";

/**
 * In the current backend, severity is sometimes semantically mixed with result:
 * in addition to "critical" / "high" / "medium", values like "pass" / "unclear"
 * may appear. We keep this behavior as part of the contract to avoid breaking the existing UI.
 */
export type ReviewSeverity =
  | "critical"
  | "high"
  | "medium"
  | "pass"
  | "unclear";

export type ReviewQcStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_review";

/**
 * Canonical review workflow status from backend result semantics.
 * Frontend does not reinterpret business logic — it only renders.
 */
export type ReviewWorkflowStatus =
  | "needs_review"
  | "ok"
  | "not_applicable"
  | "unclear";

export type ReviewCheckOrigin =
  | "GLOBAL_PLAYBOOK"
  | "DOCUMENT_TYPE"
  | "CONDITIONAL";

export type ReviewFieldFormat = "money" | "date" | "entity_name" | "text";

/**
 * Denormalized semantic type of check from backend playbook/result semantics.
 * Needed for correct renderer / details UX.
 */
export type ReviewUiMode =
  | "clause_presence"
  | "extraction"
  | "field_extraction"
  | "risk_flag"
  | "comparison"
  | "summary";

/**
 * General provenance block for segment/chunk-aware navigation.
 * All fields are optional to keep the contract compatible with current backend.
 */
export interface SegmentProvenanceDTO {
  segment_id?: string | null;
  segment_title?: string | null;
  segment_type?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  chunk_id?: string | null;
  chunk_index?: number | null;
}

/**
 * Document summary for review screens.
 * Optional composition fields are pre-added for future badges/filters.
 */
export interface DocumentSummaryDTO {
  document_id: string;
  name: string;
  doc_type: string;
  status: string;

  critical_count: number;
  high_count: number;
  medium_count: number;
  pass_count: number;
  unclear_count: number;

  has_degraded_structure: boolean;
  in_quarantine: boolean;

  classification_level: string;
  classification_confidence: number;

  // Optional composition fields for multi-document UX
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;
}

/**
 * Details of a specific check on the document detail review page.
 */
export interface CheckItemDTO extends SegmentProvenanceDTO {
  check_id: string;
  check_name: string;

  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  evidence_snippet: string | null;
  page: number | null;
  clause_uid: string | null;

  confidence: number | null;
  detector_used: string | null;
  quality_flags: Record<string, unknown> | null;

  conditional_check_triggered: boolean;
  trigger_name: string | null;

  structured_data: Record<string, unknown>;
  origin?: ReviewCheckOrigin | string | null;

  // Canonical display semantics (NEW)
  display_text?: string | null;
  review_status?: ReviewWorkflowStatus | string | null;
  review_message?: string | null;
  needs_manual_review?: boolean;
  ui_mode?: ReviewUiMode | string | null;
}

/**
 * Metadata of a check column in DD Matrix.
 */
export interface CheckMetaDTO {
  check_id: string;
  check_name: string;
  origin: ReviewCheckOrigin | string;
  severity: "critical" | "high" | "medium" | string;
  order_index: number;
  applicable_doc_types?: string[] | null;
}

/**
 * Extracted field inside a matrix cell / document structured data.
 * Enhanced with provenance fields and document location.
 */
export interface ExtractedFieldDTO extends SegmentProvenanceDTO {
  field_name: string;
  field_value: string;
  field_format: ReviewFieldFormat | string;

  page?: number | null;
  clause_uid?: string | null;
  snippet?: string | null;

  check_id?: string | null;
  check_name?: string | null;
}

/**
 * Cell of a new DD Matrix.
 * Fully prepared for segment-aware drill-down and viewer navigation.
 */
export interface MatrixCellDTO extends SegmentProvenanceDTO {
  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  snippet: string;
  page: number | null;
  clause_uid: string | null;

  extracted: ExtractedFieldDTO[];

  confidence: number | null;
  qc_status: ReviewQcStatus | null;

  // QC audit trail
  qc_by: string | null;
  qc_comment: string | null;
  qc_at: string | null;

  conditional_check_triggered: boolean;
  trigger_name: string | null;

  // Canonical display semantics (NEW)
  display_text?: string | null;
  review_status?: ReviewWorkflowStatus | string | null;
  review_message?: string | null;
  needs_manual_review?: boolean;
  ui_mode?: ReviewUiMode | string | null;
}

/**
 * Matrix row = one document + dictionary of results mapped by check_id.
 */
export interface DocumentMatrixRowDTO {
  document_id: string;
  document_name: string;
  doc_type: string;
  folder_path: string;
  status: string;

  classification_level: string;
  classification_confidence: number;
  requires_manual_review?: boolean;

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  results: Record<string, MatrixCellDTO>;
}

/**
 * NEW:
 * Matrix row = one logical document / segment row.
 * This is the target primary row model for review-only DD Grid.
 */
export interface SegmentMatrixRowDTO {
  document_id: string;
  document_name: string;
  doc_type: string;
  folder_path?: string | null;

  segment_id?: string | null;
  segment_type?: string | null;
  segment_title?: string | null;
  segment_order?: number | null;
  is_primary_segment?: boolean | null;

  status: string;

  classification_level: string;
  classification_confidence: number;
  requires_manual_review?: boolean;

  results: Record<string, MatrixCellDTO>;
}

/**
 * Main response of backend dd-matrix endpoint.
 */
export interface DDMatrixResponseDTO {
  deal_id: string;
  run_id: string;
  deal_name: string;

  checks: CheckMetaDTO[];
  global_check_ids: string[];
  doc_type_check_ids: Record<string, string[]>;

  documents: DocumentMatrixRowDTO[];

  /**
   * NEW:
   * Segment-oriented rows returned by backend.
   * This is the primary source for the review matrix.
   * Optional until full alignment of frontend/backend contracts is completed.
   */
  segment_documents?: SegmentMatrixRowDTO[];

  total_documents: number;
  total_checks: number;
  severity_counts: Record<string, number>;
  quarantine_count: number;
  degraded_count: number;
  evidence_validity_rate: number;
}

/**
 * Review details for a specific document within a run.
 */
export interface DocumentDetailDTO {
  document_id: string;
  name: string;
  doc_type: string;
  status: string;

  classification_level: string;
  classification_confidence: number;
  applicable_triggers: string[];

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  checks: CheckItemDTO[];
}

/**
 * DD Request / follow-up request within a review workflow.
 *
 * This represents a lawyer's request or an automatically generated follow-up
 * question based on document check results. Contains the request text, priority,
 * document lists, and segment/chunk provenance for viewer navigation.
 *
 * CRITICAL for MR4:
 * - document_ids contains document UUIDs for direct navigation in the viewer.
 * - document_names contains human-readable filenames for display.
 * - These two arrays are index-synchronized: document_ids[0] refers to document_names[0], etc.
 * - Segment provenance (segment_id, chunk_id, etc.) is inherited from SegmentProvenanceDTO
 *   and points to a specific spot inside the document.
 */
export interface DDRequestDTO extends SegmentProvenanceDTO {
  request_id: string;
  priority: string;

  check_id: string | null;
  check_name: string | null;

  addressee: string;
  text: string;

  document_names: string[];

  /**
   * Document UUIDs corresponding directly to document_names by index.
   * If backend is not updated yet, this might be an empty array.
   * If at least one ID is present, viewer navigation can be built.
   */
  document_ids: string[];

  doc_types: string[];

  structured_values: Array<
    | { field_name: string; field_value: unknown; field_format?: string | null }
    | Record<string, unknown>
  >;
}

/**
 * Conditional checks in run-scoped review API.
 */
export interface ConditionalCheckDTO extends SegmentProvenanceDTO {
  document_name: string;
  doc_type: string;

  trigger_name: string;
  check_id: string;
  check_name: string;

  result: ReviewResult | string;
  severity: ReviewSeverity | string;

  evidence_snippet: string | null;
  page: number | null;
  clause_uid?: string | null;

  confidence: number | null;
  quality_flags: Record<string, unknown> | null;
}

/**
 * Flat extracted-value representation for run-level / document-level structured data.
 * Extended with provenance fields for segment-aware grouping.
 */
export interface ExtractedValueDTO extends SegmentProvenanceDTO {
  document_name: string;
  doc_type: string;

  check_name: string;
  field_name: string;
  field_value: string;
  field_format: ReviewFieldFormat | string;

  page: number | null;
  clause_uid: string | null;
}

/**
 * Structured data for a specific document inside a review run.
 * values are kept in the current backend contract form,
 * but each entry can now carry segment/chunk provenance metadata.
 */
export interface DocumentStructuredDataDTO {
  deal_id: string;
  run_id: string;

  document_id: string;
  document_name: string;
  doc_type: string;

  playbook_version_id?: string | null;
  playbook_name?: string | null;
  profile?: string | null;

  // Optional composition fields
  is_multi_document?: boolean;
  segment_count?: number | null;
  primary_segment_label?: string | null;

  total_values: number;
  values: ExtractedValueDTO[];
}

// =============================================================
// DD GRID V1 CONTRACT
// -------------------------------------------------------------
// Exact mapping of backend contract GET
// /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
// Strict adherence to DDGridV1ResponseDTO (Pydantic).
//
// Rules:
// - no hardcoded check_id / column_id / doc_type values;
// - all semantic states are closed unions;
// - execution_status is left as string because the closed list
//   of its values is not fixed in the frontend contract yet; when a
//   closed enum appears — replace with a union without UI migrations;
// - dictionaries are strictly typed via Record<string, X>;
// - fallback_display is guaranteed to be a string (always set by contract).
// =============================================================

/**
 * Five possible cell states in DD Grid V1.
 *
 * defined         — value found successfully
 * not_defined     — check executed, value not found
 * not_executed    — check was not executed for this document
 * error           — technical execution error occurred
 */
export type DDGridV1CellState =
  | "defined"
  | "not_defined"
  | "not_executed"
  | "error";

/**
 * Runtime column format in DD Grid V1.
 *
 * text           — plain string (with unit suffix if applicable)
 * enum           — display is built via enum_labels[raw_value]
 * yes_no         — boolean value mapped as "Yes" / "No"
 * presence_only  — presence indicator ("Present" / fallback)
 */
export type DDGridV1ColumnFormat =
  | "text"
  | "enum"
  | "yes_no"
  | "presence_only";

/**
 * Location confidence level for a single field / cell.
 *
 * high  — exact pinpoint (clause_ref / page precisely defined)
 * low   — approximate (fallback), navigation allowed with a caveat
 * null  — location unavailable for this cell
 */
export type DDGridV1LocationConfidence = "high" | "low" | null;

/**
 * Runtime column inside a check definition.
 *
 * IMPORTANT: column_id is NOT guaranteed to be unique across the entire response,
 * because the same column_id may appear multiple times within a single check
 * (different field_name mapping to the same column_id). For stable UI keys,
 * always build the runtime key on the (scope, path, index) level.
 */
export interface DDGridV1ColumnDTO {
  column_id: string;
  check_id: string;
  label: string;
  format: DDGridV1ColumnFormat;
  fallback_display: string;
  display_order: number;
  enum_labels: Record<string, string>;
  unit: string | null;
}

/**
 * Metadata of a single check inside a group (global) or document type.
 */
export interface DDGridV1CheckDTO {
  check_id: string;
  check_name: string;
  display_order: number;
  columns: DDGridV1ColumnDTO[];
  display_summary_field: string | null;
  metadata_fields: string[];
}

/**
 * Global check group (not bound to a specific document type).
 */
export interface DDGridV1GlobalGroupDTO {
  group_id: string;
  label: string;
  display_order: number;
  checks: DDGridV1CheckDTO[];
}

/**
 * Specific document type inside a doc-type class.
 */
export interface DDGridV1DocTypeDTO {
  type_code: string;
  name: string;
  checks: DDGridV1CheckDTO[];
}

/**
 * Class of document types (e.g. "Transfer of Ownership"),
 * grouping one or multiple document types.
 */
export interface DDGridV1DocTypeClassDTO {
  group_id: string;
  label: string;
  display_order: number;
  types: DDGridV1DocTypeDTO[];
}

/**
 * Single cell value for a specific (document_id, column_id) pair.
 *
 * Location rules:
 * - has_location_fallback = false + clause_ref/page set → exact
 * - has_location_fallback = true  + clause_ref/page set → approximate
 * - has_location_fallback = true  + clause_ref/page null → navigation unavailable
 */
export interface DDGridV1CellValueDTO {
  cell_state: DDGridV1CellState;
  display_value: string;
  raw_value: string | null;
  location_clause_ref: string | null;
  location_clause_uid: string | null;
  location_page: number | null;
  location_confidence: DDGridV1LocationConfidence;
  has_location_fallback: boolean;
  location_fallback_reason: string | null;
}

/**
 * Single extracted field inside a drawer-content check.
 *
 * IMPORTANT: multiple fields within a single check can reference the same
 * column_id. For stable UI keys, use the index inside the fields array.
 */
export interface DDGridV1DrawerFieldDTO {
  column_id: string;
  field_name: string;
  label: string;
  cell_state: DDGridV1CellState;
  display_value: string;
  raw_value: string | null;
  location_clause_ref: string | null;
  location_clause_uid: string | null;
  location_page: number | null;
  location_confidence: DDGridV1LocationConfidence;
  has_location_fallback: boolean;
  location_fallback_reason: string | null;
}

/**
 * Detection level.
 * L1 — Pattern/rules, L2 — LLM, L3 — RAG+LLM, L4 — Manual QC.
 */
export type DDGridV1DetectionLevel = "L1" | "L2" | "L3" | "L4";

/**
 * API QC status for drawer.
 * pending — not yet reviewed.
 * approved — approved.
 * rejected — rejected.
 * needs_review — requires review.
 */
export type DDGridV1DrawerQcStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "needs_review";

/**
 * Complete drawer content contract from DDGridV1ResponseDTO (backend B3).
 *
 * execution_status: closed enum — SUCCESS | FAILED | TIMEOUT | SKIPPED | PARTIAL.
 * Left as a string: backend adds new values without breaking changes.
 *
 * detection_level / confidence / quality_flags — result transparency.
 * qc_* — audit trail without a separate round-trip.
 * agent_name / model_version / execution_time_ms / retry_attempts / input_tokens / output_tokens
 * — observability tools.
 */
export interface DDGridV1DrawerContentDTO {
  check_id: string;
  check_name: string;
  document_id: string;
  cell_state: DDGridV1CellState;
  reason: string | null;
  review_status: string | null;
  review_message: string | null;
  display_text: string | null;

  // Locale-specific presentation metadata. The backend remains the
  // source of truth for selecting localized versus canonical content.
  output_locale?: string | null;
  presentation_locale?: string | null; // Deprecated: use output_locale
  presentation_content_version?: string | null;
  presentation_source_locale?: string | null;
  presentation_status?: string | null;
  presentation_is_fallback?: boolean;

  // Canonical source content is supplied only when a safe localized
  // presentation has been selected. It is retained for audit/debug
  // context and must not be rendered alongside the selected content.
  canonical_check_name?: string | null;
  canonical_display_text?: string | null;
  canonical_review_message?: string | null;

  execution_status: string;

  // B3 P0 — Transparency
  detection_level: DDGridV1DetectionLevel | null;
  confidence: number | null;
  quality_flags: Record<string, true> | null;

  // B3 P0 — QC Audit Trail
  qc_status: DDGridV1DrawerQcStatus | null;
  qc_by: string | null;
  qc_at: string | null;
  qc_comment: string | null;

  // B3 P1 — Observability
  agent_name: string | null;
  model_version: string | null;
  execution_time_ms: number | null;
  retry_attempts: number | null;
  input_tokens: number | null;
  output_tokens: number | null;

  fields: DDGridV1DrawerFieldDTO[];
  evidence_items: string[];
}

/**
 * Metadata for a document included in the DD Grid V1 response.
 */
export interface DDGridV1CheckSummaryDTO {
  id: string;
  name: string;
  description: string;
}

export interface DDGridV1InstructionSnapshotDTO {
  doc_type: string;
  version_id: string | null;
  is_persisted_snapshot: boolean;
  global_checks: DDGridV1CheckSummaryDTO[];
  doc_type_checks: DDGridV1CheckSummaryDTO[];
}

export interface DDGridV1DocumentMetaDTO {
  document_id: string;
  filename: string;
  doc_type: string | null;
  status: string;
  folder_path: string | null;
  
  // Segment-aware fields
  segment_id: string | null;
  segment_type: string | null;
  segment_title: string | null;
  
  instruction_snapshot: DDGridV1InstructionSnapshotDTO | null;
}

/**
 * Complete response of the backend endpoint GET
 * /api/v1/deals/{deal_id}/runs/{run_id}/dd-grid-v1
 *
 * Source of truth for the UI:
 * - build runtime columns from global_groups + doc_type_classes,
 *   NOT from column_registry (registry does not guarantee uniqueness).
 * - treat column_registry as an index for fast lookups,
 *   but not as the primary source of truth.
 */
export interface DDGridV1ResponseDTO {
  deal_id: string;
  run_id: string;

  global_groups: DDGridV1GlobalGroupDTO[];
  doc_type_classes: DDGridV1DocTypeClassDTO[];

  column_registry: Record<string, DDGridV1ColumnDTO>;
  
  // 3-level structure: doc → segment → column/check
  cell_values: Record<string, Record<string, Record<string, DDGridV1CellValueDTO>>>;
  drawer_contents: Record<string, Record<string, Record<string, DDGridV1DrawerContentDTO>>>;

  documents_meta: DDGridV1DocumentMetaDTO[];
}

// =============================================================
// Локализованные presentation-версии результатов проверки.
// =============================================================

export interface ResultPresentationRequestDTO {
  locale: string;
}

export interface ResultPresentationProgressDTO {
  run_id: string;
  locale: string;
  content_version: string;

  total: number;
  missing: number;
  pending: number;
  processing: number;
  ready: number;
  reviewed: number;
  approved: number;
  failed: number;
  stale: number;

  created_pending: number;
  existing: number;

  is_complete: boolean;
  dispatch_status: string;
}


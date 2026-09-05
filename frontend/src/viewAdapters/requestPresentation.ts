// =============================================================
// src/viewAdapters/requestPresentation.ts
// Adapters for converting legacy DDRequest and review DDRequestDTO
// into a unified UI read-model for reusable presentation components.
//
// Goals:
// - Isolate differences between legacy and review API contracts
// - Provide stable interface for UI components
// - Support i18n via t-function with canonical English fallback
// =============================================================

import type { TFunction } from "i18next";
import type { DDRequest, StructuredValue } from "../types/ddRequests";
import type { DDRequestDTO } from "../types/dealReview";
import { normalizeStructuredValue } from "../types/ddRequests";
import type { RequestPriority } from "../types/requestPriority";
import { normalizeRequestPriority } from "../types/requestPriority";

// =============================================================
// UI Read-Model types (view layer)
// =============================================================

/**
 * Provenance information about segment and chunk for viewer navigation.
 * All fields are optional because legacy requests lack this data.
 */
export interface SegmentProvenanceView {
  segmentId: string | null;
  segmentTitle: string | null;
  segmentType: string | null;
  segmentOrder: number | null;
  isPrimarySegment: boolean | null;
  chunkId: string | null;
  chunkIndex: number | null;
}

/**
 * Document in UI representation.
 * id is optional because in legacy it's UUID, in review it may be absent.
 * name is always present (UUID in legacy, human-readable in review).
 */
export interface DocumentView {
  id: string | null;
  name: string;
  rawId?: string | null; // for tooltip with UUID in review mode
}

/**
 * Extracted value (structured value) in UI representation.
 */
export interface StructuredValueView {
  key: string;
  value: string;
  format: string | null;
}

/**
 * Request source (source badge).
 */
export interface SourceView {
  code: string;
  label: string;
  colorClass: string;
  helperText?: string | null;
}

/**
 * Request status (for legacy CRUD mode).
 */
export interface StatusView {
  code: string;
  label: string;
}

/**
 * UI read-model for DD requests table row.
 * Used in RequestsTable and ReviewRequestsTable.
 */
export interface RequestTableRowView {
  id: string;
  priority: RequestPriority;
  text: string;
  checkLabel: string | null;
  addressee: string | null;

  // Documents
  documentsLabel: string | null; // "3 docs" or "Contract.pdf +2"
  documentCount: number;

  // Segment context (review only)
  segmentTitle: string | null;
  chunkIndex: number | null;
  hasSegmentContext: boolean;

  // Legacy-only fields
  statusLabel: string | null;
  sourceLabel: string | null;
  sourceColorClass: string | null;

  mode: "legacy" | "review";
}

/**
 * UI read-model for DD request side panel details.
 * Used in RequestSidePanel and ReviewRequestSidePanel.
 */
export interface RequestPanelView {
  id: string;
  title: string;
  priority: RequestPriority;
  text: string;
  addressee: string | null;

  checkId: string | null;
  checkLabel: string | null;

  documents: DocumentView[];
  docTypes: string[];

  structuredValues: StructuredValueView[];

  source: SourceView | null;
  status: StatusView | null;

  evidenceRefs: string[];

  segment: SegmentProvenanceView | null;

  canEdit: boolean;
  canDelete: boolean;
  isReadOnly: boolean;
  mode: "legacy" | "review";
}

/**
 * Viewer navigation target for review request.
 */
export interface RequestViewerTargetView {
  documentId: string;
  segmentId: string | null;
  chunkId: string | null;
  chunkIndex: number | null;
}

// =============================================================
// Localization constants and helpers (Canonical English Fallback)
// =============================================================

export type TranslationFn = TFunction | ((key: string, options?: any) => string);

const CANONICAL_STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_progress: "In progress",
  resolved: "Closed",
};

const CANONICAL_SOURCE_CONFIG: Record<
  string,
  { label: string; color: string; helper?: string }
> = {
  yaml_template: {
    label: "YAML template",
    color: "bg-purple-100 text-purple-700",
    helper:
      "Text and addressee were generated automatically from document type YAML instruction.",
  },
  manual: {
    label: "Manual",
    color: "bg-blue-100 text-blue-700",
  },
  aggregator: {
    label: "Aggregator",
    color: "bg-green-100 text-green-700",
  },
};

/**
 * Get localized request status label.
 */
export function getRequestStatusLabel(status: string, t?: TranslationFn): string {
  if (t) {
    const localized = t(`statuses.${status}`, { defaultValue: "" });
    if (localized) return localized;
  }
  return CANONICAL_STATUS_LABELS[status] ?? status;
}

/**
 * Get request source configuration with localization support.
 */
export function getRequestSourceConfig(
  source: string,
  t?: TranslationFn,
): { label: string; color: string; helper?: string } | null {
  const base = CANONICAL_SOURCE_CONFIG[source];
  if (!base) return null;

  if (t) {
    const localizedLabel = t(`source.${source}`, { defaultValue: base.label });
    const localizedHelper = t(`source.helpers.${source}`, { defaultValue: base.helper });
    return {
      label: localizedLabel,
      color: base.color,
      helper: localizedHelper || undefined,
    };
  }

  return base;
}

// =============================================================
// Helper functions
// =============================================================

/**
 * Generates short label for document list in table.
 * Examples: "Contract.pdf", "Contract.pdf +2"
 */
function getDocumentsLabel(
  documents: DocumentView[],
  maxVisible: number = 1,
): string | null {
  if (documents.length === 0) return null;
  if (documents.length === 1) return documents[0].name;

  const first = documents[0].name;
  const rest = documents.length - maxVisible;
  return rest > 0 ? `${first} +${rest}` : first;
}

/**
 * Generates segment label for table.
 * Priority: segment_title > segment_type > null
 */
function getSegmentLabel(segment: SegmentProvenanceView | null): string | null {
  if (!segment) return null;
  if (segment.segmentTitle) return segment.segmentTitle;
  if (segment.segmentType) return segment.segmentType;
  return null;
}

/**
 * Checks if there is actual segment data (at least one field not null).
 */
function hasSegmentContext(segment: SegmentProvenanceView | null): boolean {
  if (!segment) return false;
  return !!(
    segment.segmentId ||
    segment.segmentTitle ||
    segment.chunkId ||
    segment.chunkIndex != null
  );
}

// =============================================================
// Adapters for Table Row View
// =============================================================

/**
 * Converts legacy DDRequest to UI read-model for table row.
 */
export function toRequestTableRowFromLegacy(
  req: DDRequest,
  t?: TranslationFn,
): RequestTableRowView {
  const documents: DocumentView[] = (req.document_refs || []).map((docId) => ({
    id: docId,
    name: docId, // in legacy no names, only UUID
    rawId: docId,
  }));

  const sourceConfig = req.source ? getRequestSourceConfig(req.source, t) : null;

  return {
    id: req.id,
    priority: normalizeRequestPriority(req.priority),
    text: req.text,
    checkLabel: req.check_id || null,
    addressee: req.addressee || null,

    documentsLabel: getDocumentsLabel(documents),
    documentCount: documents.length,

    // Legacy does NOT have segment context
    segmentTitle: null,
    chunkIndex: null,
    hasSegmentContext: false,

    statusLabel: req.status ? getRequestStatusLabel(req.status, t) : null,
    sourceLabel: sourceConfig?.label || null,
    sourceColorClass: sourceConfig?.color || null,

    mode: "legacy",
  };
}

/**
 * Converts review DDRequestDTO to UI read-model for table row.
 */
export function toRequestTableRowFromReview(
  req: DDRequestDTO,
): RequestTableRowView {
  const documentIds = req.document_ids || [];

  const documents: DocumentView[] = (req.document_names || []).map(
    (name, index) => ({
      id: documentIds[index] ?? null,
      name,
      rawId: documentIds[index] ?? null,
    }),
  );

  const segment: SegmentProvenanceView = {
    segmentId: req.segment_id ?? null,
    segmentTitle: req.segment_title ?? null,
    segmentType: req.segment_type ?? null,
    segmentOrder: req.segment_order ?? null,
    isPrimarySegment: req.is_primary_segment ?? null,
    chunkId: req.chunk_id ?? null,
    chunkIndex: req.chunk_index ?? null,
  };

  return {
    id: req.request_id,
    priority: normalizeRequestPriority(req.priority),
    text: req.text,
    checkLabel: req.check_name || null,
    addressee: req.addressee || null,

    documentsLabel: getDocumentsLabel(documents),
    documentCount: documents.length,

    segmentTitle: getSegmentLabel(segment),
    chunkIndex: segment.chunkIndex,
    hasSegmentContext: hasSegmentContext(segment),

    // Review does NOT have status/source
    statusLabel: null,
    sourceLabel: null,
    sourceColorClass: null,

    mode: "review",
  };
}

// =============================================================
// Adapters for Panel View
// =============================================================

/**
 * Converts legacy DDRequest to UI read-model for side panel.
 */
export function toRequestPanelViewFromLegacy(
  req: DDRequest,
  canManageRequests: boolean = false,
  t?: TranslationFn,
): RequestPanelView {
  const documents: DocumentView[] = (req.document_refs || []).map((docId) => ({
    id: docId,
    name: docId,
    rawId: docId,
  }));

  const structuredValues: StructuredValueView[] = (
    req.structured_values || []
  ).map((sv: StructuredValue) => normalizeStructuredValue(sv));

  const sourceConfig = req.source ? getRequestSourceConfig(req.source, t) : null;
  const source: SourceView | null = sourceConfig
    ? {
        code: req.source!,
        label: sourceConfig.label,
        colorClass: sourceConfig.color,
        helperText: sourceConfig.helper || null,
      }
    : null;

  const status: StatusView | null = req.status
    ? {
        code: req.status,
        label: getRequestStatusLabel(req.status, t),
      }
    : null;

  const defaultTitle = t
    ? t("panel.defaultTitle", { id: req.id.slice(-6), defaultValue: `Request #${req.id.slice(-6)}` })
    : `Request #${req.id.slice(-6)}`;

  return {
    id: req.id,
    title: req.check_id || defaultTitle,
    priority: normalizeRequestPriority(req.priority),
    text: req.text,
    addressee: req.addressee || null,

    checkId: req.check_id || null,
    checkLabel: req.check_id || null,

    documents,
    docTypes: [],

    structuredValues,

    source,
    status,

    evidenceRefs: req.evidence_refs || [],

    // Legacy does NOT have segment provenance
    segment: null,

    canEdit: canManageRequests,
    canDelete: canManageRequests,
    isReadOnly: false,
    mode: "legacy",
  };
}

/**
 * Converts review DDRequestDTO to UI read-model for side panel.
 */
export function toRequestPanelViewFromReview(
  req: DDRequestDTO,
  t?: TranslationFn,
): RequestPanelView {
  const documentIds = req.document_ids || [];

  const documents: DocumentView[] = (req.document_names || []).map(
    (name, index) => ({
      id: documentIds[index] ?? null,
      name,
      rawId: documentIds[index] ?? null,
    }),
  );

  const structuredValues: StructuredValueView[] = (
    req.structured_values || []
  ).map((sv) => normalizeStructuredValue(sv as StructuredValue));

  const segment: SegmentProvenanceView = {
    segmentId: req.segment_id ?? null,
    segmentTitle: req.segment_title ?? null,
    segmentType: req.segment_type ?? null,
    segmentOrder: req.segment_order ?? null,
    isPrimarySegment: req.is_primary_segment ?? null,
    chunkId: req.chunk_id ?? null,
    chunkIndex: req.chunk_index ?? null,
  };

  const defaultReviewTitle = t
    ? t("panel.defaultReviewTitle", { defaultValue: "Request" })
    : "Request";

  return {
    id: req.request_id,
    title: req.check_name || defaultReviewTitle,
    priority: normalizeRequestPriority(req.priority),
    text: req.text,
    addressee: req.addressee || null,

    checkId: req.check_id || null,
    checkLabel: req.check_name || null,

    documents,
    docTypes: req.doc_types || [],

    structuredValues,

    // Review does NOT have source/status (read-only mode)
    source: null,
    status: null,

    evidenceRefs: [],

    segment: hasSegmentContext(segment) ? segment : null,

    // Review mode — read-only
    canEdit: false,
    canDelete: false,
    isReadOnly: true,
    mode: "review",
  };
}

// =============================================================
// Helper for viewer navigation
// =============================================================

/**
 * Determines viewer navigation target from review request panel view.
 */
export function getRequestViewerTarget(
  view: RequestPanelView,
): RequestViewerTargetView | null {
  const firstDocumentWithId = view.documents.find((doc) => !!doc.id);

  if (!firstDocumentWithId?.id) {
    return null;
  }

  return {
    documentId: firstDocumentWithId.id,
    segmentId: view.segment?.segmentId ?? null,
    chunkId: view.segment?.chunkId ?? null,
    chunkIndex: view.segment?.chunkIndex ?? null,
  };
}


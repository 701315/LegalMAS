// =============================================================
// src/utils/compositionHelpers.ts
// Unified helper layer for working with DocumentCompositionMeta.
//
// RULE: All composition/segment display logic lives here only.
// DocumentTree, DocumentsTab, DDGrid, and DDMatrixGrid must NOT
// compute this independently.
// =============================================================

import type {
  DocumentCompositionMeta,
  DocumentColumnId,
  DocumentListItem,
} from "../types";

// -------------------------------------------------------------
// Universal adapter input shapes
// -------------------------------------------------------------

/**
 * Minimal shape for row/view models where composition data
 * is already flattened into separate fields instead of nested
// under composition: {...}.
 *
 * Used for legacy/review grid row adapters.
 */
export interface CompositionMetaLike {
  compositionType?: "single" | "multi" | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

/**
 * Minimal shape for review matrix row.
 * We avoid importing DTO types from here — helper stays loosely coupled
 * to the feature layer and works via structural typing.
 */
export interface ReviewCompositionMetaLike {
  isMultiDocument?: boolean | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

// -------------------------------------------------------------
// Base predicates / adapters
// -------------------------------------------------------------

/**
 * Returns document composition metadata or null if unavailable.
 * Use this function everywhere instead of direct doc.composition access.
 */
export function getCompositionMeta(
  doc: DocumentListItem,
): DocumentCompositionMeta | null {
  return doc.composition ?? null;
}

/**
 * Checks if document is a multi-document file.
 * Returns false if data is unavailable.
 */
export function isMultiDocument(doc: DocumentListItem): boolean {
  return getCompositionMeta(doc)?.composition_type === "multi";
}

/**
 * Returns segment count or 0 if data is unavailable.
 */
export function getSegmentCount(doc: DocumentListItem): number {
  const count = getCompositionMeta(doc)?.segment_count;
  return typeof count === "number" ? count : 0;
}

/**
 * Returns primary segment label or null.
 * Example: "Share Purchase Agreement", "Charter", etc.
 */
export function getPrimarySegmentLabel(doc: DocumentListItem): string | null {
  return getCompositionMeta(doc)?.primary_segment_label ?? null;
}

/**
 * Checks if document is a composite file (flag from backend).
 * Returns false if data is unavailable.
 */
export function isCompositeFile(doc: DocumentListItem): boolean {
  return getCompositionMeta(doc)?.is_composite_file === true;
}

/**
 * Explicit adapter: DocumentListItem -> DocumentCompositionMeta | null
 * Needed for API consistency alongside row-based adapters.
 */
export function toCompositionMetaFromDocument(
  doc: DocumentListItem,
): DocumentCompositionMeta | null {
  return getCompositionMeta(doc);
}

/**
 * Adapter for legacy matrix row / other row models
 * where composition is already flattened.
 */
export function toCompositionMetaFromLegacyMatrixRow(
  row: CompositionMetaLike | null | undefined,
): DocumentCompositionMeta | null {
  if (!row) return null;

  const hasAnyData =
    row.compositionType != null ||
    row.segmentCount != null ||
    row.primarySegmentLabel != null ||
    row.isCompositeFile != null;

  if (!hasAnyData) return null;

  return {
    composition_type: row.compositionType ?? "single",
    segment_count:
      typeof row.segmentCount === "number" ? row.segmentCount : 0,
    primary_segment_label: row.primarySegmentLabel ?? null,
    primary_segment_id: null,
    is_composite_file: row.isCompositeFile === true,
  };
}

/**
 * Adapter for review matrix row where multi-document comes as boolean.
 * Helper does not depend on specific DTO type and works by shape.
 */
export function toCompositionMetaFromReviewMatrixRow(
  row: ReviewCompositionMetaLike | null | undefined,
): DocumentCompositionMeta | null {
  if (!row) return null;

  const hasAnyData =
    row.isMultiDocument != null ||
    row.segmentCount != null ||
    row.primarySegmentLabel != null ||
    row.isCompositeFile != null;

  if (!hasAnyData) return null;

  return {
    composition_type: row.isMultiDocument ? "multi" : "single",
    segment_count:
      typeof row.segmentCount === "number" ? row.segmentCount : 0,
    primary_segment_label: row.primarySegmentLabel ?? null,
    primary_segment_id: null,
    is_composite_file: row.isCompositeFile === true,
  };
}

// -------------------------------------------------------------
// Render helpers for table (return string or number)
// Used in DocumentsTab, Grid and potentially in exports.
// -------------------------------------------------------------

/**
 * Returns text value for composition column cell
 * directly from DocumentCompositionMeta.
 *
 * Returns string or number — primitives only,
 * so function can be used in Excel/Word/PDF exports as well.
 */
export function getCompositionCellValueFromMeta(
  colId: DocumentColumnId,
  meta: DocumentCompositionMeta | null | undefined,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): string | number {
  if (!meta) return "";

  switch (colId) {
    case "composition_type":
      if (meta.composition_type === "multi") {
        return tFn
          ? tFn("documents:compositionType.multi", { defaultValue: "Multi-document" })
          : "Multi-document";
      }
      return tFn
        ? tFn("documents:compositionType.single", { defaultValue: "Single" })
        : "Single";
    case "segment_count":
      return meta.segment_count;
    case "primary_segment_label":
      return meta.primary_segment_label ?? "";
    case "is_composite_file":
      if (meta.is_composite_file) {
        return tFn ? tFn("common:actions.yes", { defaultValue: "Yes" }) : "Yes";
      }
      return tFn ? tFn("common:actions.no", { defaultValue: "No" }) : "No";
    default:
      return "";
  }
}

/**
 * Backward-compatible helper for DocumentListItem.
 */
export function getCompositionCellValue(
  colId: DocumentColumnId,
  doc: DocumentListItem,
  tFn?: (key: string, options?: Record<string, unknown>) => string,
): string | number {
  return getCompositionCellValueFromMeta(colId, getCompositionMeta(doc), tFn);
}

// -------------------------------------------------------------
// Badge data for UI (Tree, Grid etc.)
// Return objects describing what to show visually,
// not ready JSX — to avoid pulling React into utility layer.
// -------------------------------------------------------------

/**
 * Data for rendering composition badges in document row.
 * Component decides how to render, helper only provides data.
 */
export interface CompositionBadgeData {
  /** Whether to show "multi" badge */
  showMultiBadge: boolean;
  /** Whether to show segment count (only if > 1) */
  showSegmentCount: boolean;
  /** Segment count for display */
  segmentCount: number;
  /** Whether to show primary segment label */
  showPrimaryLabel: boolean;
  /** Primary segment label text */
  primaryLabel: string;
  /** Whether to show "composite file" badge */
  showCompositeBadge: boolean;
}

/**
 * Computes all badge data for composition badges of a single document.
 * Use in DocumentTree, DocumentsTab and any other places
 * where full DocumentListItem is available.
 */
export function getCompositionBadgeData(
  doc: DocumentListItem,
): CompositionBadgeData {
  return getCompositionBadgeDataFromMeta(getCompositionMeta(doc));
}

/**
 * Computes badge data directly from DocumentCompositionMeta.
 * Use when full DocumentListItem is not available (e.g. in DDGrid/DDMatrixGrid).
 */
export function getCompositionBadgeDataFromMeta(
  meta: DocumentCompositionMeta | null | undefined,
): CompositionBadgeData {
  if (!meta) {
    return {
      showMultiBadge: false,
      showSegmentCount: false,
      segmentCount: 0,
      showPrimaryLabel: false,
      primaryLabel: "",
      showCompositeBadge: false,
    };
  }

  const segmentCount = meta.segment_count;

  const primaryLabel =
    typeof meta.primary_segment_label === "string"
      ? meta.primary_segment_label.trim()
      : "";

  return {
    showMultiBadge: meta.composition_type === "multi",
    showSegmentCount: segmentCount > 1,
    segmentCount,
    showPrimaryLabel:
      meta.composition_type === "multi" && primaryLabel.length > 0,
    primaryLabel,
    showCompositeBadge: meta.is_composite_file === true,
  };
}

import type { OpenViewerAtPayload } from "../types";

export type RawViewerLocation =
  | {
      page?: number | null;
      start_page?: number | null;
      clause_uid?: string | null;
      element_id?: string | null;
      segment_id?: string | null;
      chunk_id?: string | null;
      chunk_index?: number | null;
    }
  | null
  | undefined;

export function buildViewerLocationPayload(
  documentId: string,
  loc?: RawViewerLocation,
): OpenViewerAtPayload {
  const payload: OpenViewerAtPayload = { documentId };

  const page = loc?.page ?? loc?.start_page ?? undefined;
  if (typeof page === "number") {
    payload.page = page;
  }

  if (loc?.clause_uid) {
    payload.clauseUid = loc.clause_uid;
  }

  if (loc?.element_id) {
    payload.elementId = loc.element_id;
  }

  if (loc?.segment_id) {
    payload.segmentId = loc.segment_id;
  }

  if (loc?.chunk_id) {
    payload.chunkId = loc.chunk_id;
  }

  if (typeof loc?.chunk_index === "number") {
    payload.chunkIndex = loc.chunk_index;
  }

  return payload;
}



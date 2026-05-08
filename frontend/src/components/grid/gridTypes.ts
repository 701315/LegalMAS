// =============================================================
// src/components/grid/gridTypes.ts
// Локальные типы legacy DD Grid
// =============================================================

import type { ICellRendererParams } from "ag-grid-community";

import type {
  CheckResult,
  ClassificationLevel,
  OpenViewerAtFn,
} from "../../types";

// -------------------------------------------------------------
// Matrix types
// -------------------------------------------------------------

export interface MatrixRowBase {
  documentId: string;
  documentName: string;
  docType?: string | null;
  classificationLevel?: ClassificationLevel | null;
  classificationConfidence?: number | null;
  requiresManualReview?: boolean;

  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;

  // Composition — опциональные, заполняются только из compositionByDocId
  compositionType?: "single" | "multi" | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

export type MatrixRow = MatrixRowBase & {
  [key: `risk_${string}`]: CheckResult | undefined;
};

export interface MatrixColumnMeta {
  checkId: string;
  checkName: string;
  origin?: string | null;
}

// -------------------------------------------------------------
// Narrow legacy helper types
// -------------------------------------------------------------

export interface LegacyResultWithManualReview extends CheckResult {
  doc_requires_manual_review?: boolean;
  classification_requires_review?: boolean;
}

export interface LegacyResultWithPageInfo extends CheckResult {
  page?: number | null;
  clause_uid?: string | null;
}

// -------------------------------------------------------------
// Grid context / shared renderer params
// -------------------------------------------------------------

export interface GridContext {
  onEyeClick?: (result: CheckResult) => void;
  onDocumentClick?: (result: CheckResult) => void;
  onCheckClick?: (result: CheckResult) => void;
  onQcChange?: (
    result: CheckResult,
    newStatus: "approved" | "rejected",
  ) => void;
  onOpenAtLocation?: OpenViewerAtFn;
}

/**
 * Намеренно не фиксируем TValue слишком узко.
 * Эти renderers используются в разных колонках, и AG Grid не даёт здесь
 * достаточно строгой гарантии для одного конкретного value type.
 */
export interface BaseCellParams
  extends ICellRendererParams<CheckResult, unknown> {
  context: GridContext;
  data: CheckResult;
}



// =============================================================
// src/components/grid/gridTypes.ts
// Shared matrix row types for review grid helpers
// =============================================================

import type { CheckResult, ClassificationLevel } from "../../types";

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

  // Composition metadata — optional, filled only from compositionByDocId
  compositionType?: "single" | "multi" | null;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;
  isCompositeFile?: boolean | null;
}

export type MatrixRow = MatrixRowBase & {
  [K in `risk_${string}`]?: CheckResult;
};


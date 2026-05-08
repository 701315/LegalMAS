// =============================================================
// src/components/grid/gridLegacyHelpers.ts
// Legacy-specific pure helpers for DDGrid
// =============================================================

import type { CheckResult, DocumentCompositionMeta } from "../../types";
import { toCompositionMetaFromLegacyMatrixRow } from "../../utils/compositionHelpers";

import type {
  LegacyResultWithManualReview,
  LegacyResultWithPageInfo,
  MatrixRowBase,
} from "./gridTypes";

export function getRowCompositionMeta(
  row: MatrixRowBase | null | undefined,
): DocumentCompositionMeta | null {
  return toCompositionMetaFromLegacyMatrixRow(
    row
      ? {
          compositionType: row.compositionType ?? null,
          segmentCount: row.segmentCount ?? null,
          primarySegmentLabel: row.primarySegmentLabel ?? null,
          isCompositeFile: row.isCompositeFile ?? null,
        }
      : null,
  );
}

export function getLegacyManualReviewFlag(result: CheckResult): boolean {
  const typed = result as LegacyResultWithManualReview;

  return Boolean(
    typed.doc_requires_manual_review ??
      typed.classification_requires_review ??
      false,
  );
}

export function getLegacyPageInfo(result: CheckResult): {
  page?: number;
  clauseUid?: string;
} {
  const typed = result as LegacyResultWithPageInfo;

  return {
    page: typeof typed.page === "number" ? typed.page : undefined,
    clauseUid:
      typeof typed.clause_uid === "string" && typed.clause_uid.trim()
        ? typed.clause_uid
        : undefined,
  };
}



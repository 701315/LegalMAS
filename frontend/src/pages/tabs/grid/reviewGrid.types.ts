// =============================================================
// src/pages/tabs/grid/reviewGrid.types.ts
// Типы review-only слоя для DD Grid / Review Matrix.
// Нужны как единый контракт между selectors, filters, export,
// QC и UI-слоем GridTabPage / DDMatrixGrid.
// =============================================================

import type { MatrixCellDTO } from "../../../types/dealReview";

export type ReviewQuickFilter =
  | "all"
  | "critical"
  | "high"
  | "unclear"
  | "no_qc"
  | "important"
  | "conditional"
  | "low_confidence";

export interface ReviewCheckColumn {
  checkId: string;
  checkName: string;
  origin?: string | null;
  severity?: string | null;
}

export interface ReviewGridCheckMeta extends ReviewCheckColumn {}

export interface ReviewGridRow {
  rowId: string;

  documentId: string;
  documentName: string;
  docType?: string | null;
  folderPath?: string | null;

  segmentId?: string | null;
  segmentTitle?: string | null;
  segmentType?: string | null;
  segmentOrder?: number | null;
  isPrimarySegment?: boolean | null;

  classificationLevel?: string | null;
  classificationConfidence?: number | null;
  requiresManualReview?: boolean;

  isMultiDocument?: boolean;
  segmentCount?: number | null;
  primarySegmentLabel?: string | null;

  totalCritical: number;
  totalHigh: number;
  totalMedium: number;
  totalUnclear: number;

  cellsByCheckId: Record<string, MatrixCellDTO | undefined>;
}

export interface ReviewFinding {
  findingId: string;
  rowId: string;

  documentId: string;
  documentName: string;
  docType?: string | null;
  folderPath?: string | null;

  segmentId?: string | null;
  segmentTitle?: string | null;
  segmentType?: string | null;
  segmentOrder?: number | null;
  isPrimarySegment?: boolean | null;

  checkId: string;
  checkName: string;
  origin?: string | null;
  checkSeverityBaseline?: string | null;

  result: string;
  severity?: string | null;
  qcStatus?: string | null;
  confidence?: number | null;

  snippet?: string | null;
  page?: number | null;
  clauseUid?: string | null;

  conditionalTriggered?: boolean;
  triggerName?: string | null;

  chunkId?: string | null;
  chunkIndex?: number | null;

  cell: MatrixCellDTO;
}

export interface ReviewFilterState {
  searchText: string;
  quickFilter: ReviewQuickFilter;

  multiDocumentOnly: boolean;
  criticalOnly: boolean;

  selectedDocTypes: string[];
  selectedOrigins: string[];
}

export interface ReviewSelectionItem {
  rowId: string;
}

export interface ReviewGridStats {
  documentsCount: number;
  rowsCount: number;
  findingsCount: number;
  checksCount: number;

  criticalCount: number;
  highCount: number;
  mediumCount: number;
  unclearCount: number;
  noQcCount: number;
}

export interface ReviewGridDerivedData {
  columns: ReviewCheckColumn[];
  rows: ReviewGridRow[];
  findings: ReviewFinding[];
  stats: ReviewGridStats;
  availableDocTypes: string[];
  availableOrigins: string[];
}

export const DEFAULT_REVIEW_FILTER_STATE: ReviewFilterState = {
  searchText: "",
  quickFilter: "all",
  multiDocumentOnly: false,
  criticalOnly: false,
  selectedDocTypes: [],
  selectedOrigins: [],
};

export interface ReviewExportRow {
  findingId: string;

  documentId: string;
  documentName: string;
  docType?: string | null;
  folderPath?: string | null;

  segmentId?: string | null;
  segmentTitle?: string | null;
  segmentType?: string | null;
  segmentOrder?: number | null;
  isPrimarySegment?: boolean | null;

  checkId: string;
  checkName: string;
  origin?: string | null;

  result: string;
  severity?: string | null;
  qcStatus?: string | null;
  confidence?: number | null;

  snippet?: string | null;
  page?: number | null;
  clauseUid?: string | null;

  conditionalTriggered?: boolean;
  triggerName?: string | null;

  chunkId?: string | null;
  chunkIndex?: number | null;
}



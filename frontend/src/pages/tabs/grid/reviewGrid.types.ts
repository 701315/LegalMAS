// =============================================================
// src/pages/tabs/grid/reviewGrid.types.ts
// Типы review-only слоя для DD Grid / Review Matrix.
//
// Для непрофессионального программиста:
// Этот файл задаёт единый "словарь" review grid:
// - какие бывают строки матрицы;
// - как выглядит один finding;
// - какие фильтры есть у review mode;
// - как выглядит selection;
// - какие данные selectors возвращают в UI.
// =============================================================

import type { MatrixCellDTO } from "../../../types/dealReview";

/**
 * Быстрые фильтры review matrix.
 */
export type ReviewQuickFilter =
  | "all"
  | "critical"
  | "high"
  | "unclear"
  | "no_qc"
  | "important"
  | "conditional"
  | "low_confidence";

/**
 * Метаданные одной check-колонки в review matrix.
 */
export interface ReviewCheckColumn {
  checkId: string;
  checkName: string;
  origin?: string | null;
  severity?: string | null;
}

/**
 * Одна строка review grid.
 *
 * Для непрофессионального программиста:
 * Это строка матрицы на уровне logical document / segment.
 * Пользователь выбирает именно такие строки чекбоксами в grid.
 */
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

/**
 * Один finding внутри review mode.
 *
 * Для непрофессионального программиста:
 * Если ReviewGridRow — это строка матрицы,
 * то ReviewFinding — это одна конкретная проверка внутри этой строки.
 * Именно findings удобно фильтровать, экспортировать и использовать в QC helpers.
 */
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

/**
 * Текущее состояние фильтров review mode.
 */
export interface ReviewFilterState {
  searchText: string;
  quickFilter: ReviewQuickFilter;

  multiDocumentOnly: boolean;
  criticalOnly: boolean;

  selectedDocTypes: string[];
  selectedOrigins: string[];
}

/**
 * Один элемент selection в review grid.
 *
 * Для непрофессионального программиста:
 * Selection в review mode хранится на уровне строк матрицы,
 * поэтому здесь используется rowId, а не findingId.
 */
export interface ReviewSelectionItem {
  rowId: string;
}

/**
 * Сводная статистика для review mode.
 */
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

/**
 * Полный набор derived-данных, который selectors отдают в UI.
 */
export interface ReviewGridDerivedData {
  columns: ReviewCheckColumn[];
  rows: ReviewGridRow[];
  findings: ReviewFinding[];
  stats: ReviewGridStats;
  availableDocTypes: string[];
  availableOrigins: string[];
}

/**
 * Строка для review export.
 *
 * Для непрофессионального программиста:
 * Это отдельная export-oriented форма finding,
 * чтобы экспортный слой не зависел напрямую от всей внутренней модели grid.
 */
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

/**
 * Значения фильтров review mode по умолчанию.
 */
export const DEFAULT_REVIEW_FILTER_STATE: ReviewFilterState = {
  searchText: "",
  quickFilter: "all",
  multiDocumentOnly: false,
  criticalOnly: false,
  selectedDocTypes: [],
  selectedOrigins: [],
};





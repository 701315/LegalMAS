// =============================================================
// src/pages/tabs/grid/reviewGrid.filters.ts
// Чистая логика фильтрации review findings / rows.
// Без JSX, без React, без side effects.
// =============================================================

import type {
  ReviewFilterState,
  ReviewFinding,
  ReviewGridRow,
  ReviewQuickFilter,
} from "./reviewGrid.types";

function normalizeText(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function includesText(haystack: string | null | undefined, needle: string): boolean {
  if (!needle) return true;
  return normalizeText(haystack).includes(needle);
}

function isCritical(finding: ReviewFinding): boolean {
  return finding.severity === "critical";
}

function isHigh(finding: ReviewFinding): boolean {
  return finding.severity === "high";
}

function isUnclear(finding: ReviewFinding): boolean {
  return finding.result === "unclear";
}

function isNoQc(finding: ReviewFinding): boolean {
  return !finding.qcStatus || finding.qcStatus === "pending";
}

function isImportant(finding: ReviewFinding): boolean {
  return (finding.severity === "critical" || finding.severity === "high") && isNoQc(finding);
}

function isConditional(finding: ReviewFinding): boolean {
  return finding.conditionalTriggered === true || finding.origin === "CONDITIONAL";
}

function isLowConfidence(finding: ReviewFinding): boolean {
  return typeof finding.confidence === "number" && finding.confidence < 0.7;
}

function matchQuickFilter(
  finding: ReviewFinding,
  quickFilter: ReviewQuickFilter,
): boolean {
  switch (quickFilter) {
    case "all":
      return true;
    case "critical":
      return isCritical(finding);
    case "high":
      return isHigh(finding);
    case "unclear":
      return isUnclear(finding);
    case "no_qc":
      return isNoQc(finding);
    case "important":
      return isImportant(finding);
    case "conditional":
      return isConditional(finding);
    case "low_confidence":
      return isLowConfidence(finding);
    default:
      return true;
  }
}

function matchSearchText(finding: ReviewFinding, searchNeedle: string): boolean {
  if (!searchNeedle) return true;

  return (
    includesText(finding.documentName, searchNeedle) ||
    includesText(finding.docType, searchNeedle) ||
    includesText(finding.segmentTitle, searchNeedle) ||
    includesText(finding.checkName, searchNeedle) ||
    includesText(finding.origin, searchNeedle) ||
    includesText(finding.result, searchNeedle) ||
    includesText(finding.severity, searchNeedle) ||
    includesText(finding.qcStatus, searchNeedle) ||
    includesText(finding.snippet, searchNeedle) ||
    includesText(finding.clauseUid, searchNeedle) ||
    includesText(finding.triggerName, searchNeedle)
  );
}

function matchDocTypes(
  finding: ReviewFinding,
  selectedDocTypes: string[],
): boolean {
  if (!selectedDocTypes.length) return true;
  if (!finding.docType) return false;

  return selectedDocTypes.includes(finding.docType);
}

function matchOrigins(
  finding: ReviewFinding,
  selectedOrigins: string[],
): boolean {
  if (!selectedOrigins.length) return true;
  if (!finding.origin) return false;

  return selectedOrigins.includes(finding.origin);
}

function matchBooleanFlags(
  finding: ReviewFinding,
  row: ReviewGridRow | undefined,
  filterState: ReviewFilterState,
): boolean {
  if (filterState.multiDocumentOnly && row?.isMultiDocument !== true) {
    return false;
  }

  if (filterState.criticalOnly && finding.severity !== "critical") {
    return false;
  }

  return true;
}

/**
 * Фильтрует плоский список findings.
 *
 * Для непрофессионального программиста:
 * Эта функция применяет все фильтры сразу:
 * - строку поиска;
 * - quick filter;
 * - фильтр по типам документов;
 * - фильтр по origin;
 * - флаги multi-document / critical-only.
 */
export function filterReviewFindings(
  findings: ReviewFinding[],
  rows: ReviewGridRow[],
  filterState: ReviewFilterState,
): ReviewFinding[] {
  const searchNeedle = normalizeText(filterState.searchText);

  const rowsById = new Map<string, ReviewGridRow>();
  for (const row of rows) {
    rowsById.set(row.rowId, row);
  }

  return findings.filter((finding) => {
    const row = rowsById.get(finding.rowId);

    return (
      matchQuickFilter(finding, filterState.quickFilter) &&
      matchSearchText(finding, searchNeedle) &&
      matchDocTypes(finding, filterState.selectedDocTypes) &&
      matchOrigins(finding, filterState.selectedOrigins) &&
      matchBooleanFlags(finding, row, filterState)
    );
  });
}

/**
 * Возвращает только те строки матрицы, у которых осталась хотя бы одна finding
 * после применения фильтров.
 *
 * Для непрофессионального программиста:
 * После фильтрации findings некоторые документы могут остаться "пустыми".
 * Эта функция оставляет в таблице только те строки, где есть хотя бы одна
 * подходящая проверка.
 */
export function filterReviewRows(
  rows: ReviewGridRow[],
  filteredFindings: ReviewFinding[],
): ReviewGridRow[] {
  const allowedRowIds = new Set(filteredFindings.map((finding) => finding.rowId));
  return rows.filter((row) => allowedRowIds.has(row.rowId));
}


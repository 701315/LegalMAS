// =============================================================
// src/pages/tabs/grid/reviewGrid.export.ts
// Чистая логика экспорта review findings в review-native табличный формат.
// Без React, без XLSX/jsPDF/docx импортов — только data transformation.
// Единственный canonical shaping layer для review export.
// =============================================================

import type { ReviewFinding, ReviewExportRow } from "./reviewGrid.types";

/**
 * Плоская строка таблицы для Excel / PDF / Word генераторов.
 *
 * Для непрофессионального программиста:
 * Это уже не внутренняя модель приложения, а почти готовая строка таблицы,
 * где все значения приведены к строкам для удобного вывода в файлы.
 */
export interface ReviewExportTableRow {
  "Document": string;
  "Doc Type": string;
  "Folder": string;

  "Segment Title": string;
  "Segment Type": string;
  "Segment Order": string;
  "Primary Segment": string;

  "Check": string;
  "Origin": string;

  "Result": string;
  "Severity": string;
  "QC": string;
  "Confidence": string;

  "Snippet": string;
  "Page": string;
  "Clause UID": string;

  "Conditional": string;
  "Trigger": string;

  "Finding ID": string;
  "Document ID": string;
  "Segment ID": string;
  "Check ID": string;
  "Chunk ID": string;
  "Chunk Index": string;
}

/**
 * Форматирует булево значение для экспортной таблицы.
 */
function formatYesNo(value: boolean): string {
  return value ? "Yes" : "No";
}

/**
 * Форматирует confidence в проценты для экспортной таблицы.
 */
function formatConfidence(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "";
  }

  return `${Math.round(value * 100)}%`;
}

/**
 * Преобразует один ReviewFinding в canonical export row.
 *
 * ВАЖНО:
 * - это review-native контракт;
 * - он не пытается имитировать legacy CheckResult;
 * - file generators (Excel / PDF / Word) должны работать уже от него.
 */
export function mapReviewFindingToExportRow(
  finding: ReviewFinding,
): ReviewExportRow {
  return {
    findingId: finding.findingId,

    documentId: finding.documentId,
    documentName: finding.documentName,
    docType: finding.docType ?? null,
    folderPath: finding.folderPath ?? null,

    segmentId: finding.segmentId ?? null,
    segmentTitle: finding.segmentTitle ?? null,
    segmentType: finding.segmentType ?? null,
    segmentOrder: finding.segmentOrder ?? null,
    isPrimarySegment: finding.isPrimarySegment ?? null,

    checkId: finding.checkId,
    checkName: finding.checkName,
    origin: finding.origin ?? null,

    result: finding.result,
    severity: finding.severity ?? null,
    qcStatus: finding.qcStatus ?? null,
    confidence: finding.confidence ?? null,

    snippet: finding.snippet ?? null,
    page: finding.page ?? null,
    clauseUid: finding.clauseUid ?? null,

    conditionalTriggered: finding.conditionalTriggered ?? false,
    triggerName: finding.triggerName ?? null,

    chunkId: finding.chunkId ?? null,
    chunkIndex: finding.chunkIndex ?? null,
  };
}

/**
 * Преобразует список review findings в canonical export rows.
 *
 * Для непрофессионального программиста:
 * Это главный вход для review export buttons и export utils.
 * Сначала findings приводятся к стабильной review export форме,
 * и только потом генераторы строят из неё файлы.
 */
export function buildReviewExportRows(
  findings: ReviewFinding[],
): ReviewExportRow[] {
  return findings.map(mapReviewFindingToExportRow);
}

/**
 * Преобразует canonical review export rows в плоский табличный формат
 * для Excel / PDF / Word генераторов.
 *
 * ВАЖНО:
 * - это НЕ legacy CheckResult-формат;
 * - это presentation-ready table model для файлового экспорта.
 */
export function buildReviewExportTableRows(
  rows: ReviewExportRow[],
): ReviewExportTableRow[] {
  return rows.map((row) => ({
    "Document": row.documentName,
    "Doc Type": row.docType ?? "",
    "Folder": row.folderPath ?? "",

    "Segment Title": row.segmentTitle ?? "",
    "Segment Type": row.segmentType ?? "",
    "Segment Order": row.segmentOrder != null ? String(row.segmentOrder) : "",
    "Primary Segment": formatYesNo(Boolean(row.isPrimarySegment)),

    "Check": row.checkName,
    "Origin": row.origin ?? "",

    "Result": row.result,
    "Severity": row.severity ?? "",
    "QC": row.qcStatus ?? "",
    "Confidence": formatConfidence(row.confidence),

    "Snippet": row.snippet ?? "",
    "Page": row.page != null ? String(row.page) : "",
    "Clause UID": row.clauseUid ?? "",

    "Conditional": formatYesNo(Boolean(row.conditionalTriggered)),
    "Trigger": row.triggerName ?? "",

    "Finding ID": row.findingId,
    "Document ID": row.documentId,
    "Segment ID": row.segmentId ?? "",
    "Check ID": row.checkId,
    "Chunk ID": row.chunkId ?? "",
    "Chunk Index": row.chunkIndex != null ? String(row.chunkIndex) : "",
  }));
}

/**
 * Вычисляет краткую агрегированную статистику для export summary / headers.
 */
export function getReviewExportStats(findings: ReviewFinding[]): {
  totalFindings: number;
  uniqueDocuments: number;
  uniqueChecks: number;
  criticalCount: number;
  highCount: number;
  unclearCount: number;
} {
  const uniqueDocIds = new Set(findings.map((f) => f.documentId));
  const uniqueCheckIds = new Set(findings.map((f) => f.checkId));

  return {
    totalFindings: findings.length,
    uniqueDocuments: uniqueDocIds.size,
    uniqueChecks: uniqueCheckIds.size,
    criticalCount: findings.filter((f) => f.severity === "critical").length,
    highCount: findings.filter((f) => f.severity === "high").length,
    unclearCount: findings.filter((f) => f.result === "unclear").length,
  };
}



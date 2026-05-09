// =============================================================
// src/pages/tabs/grid/reviewGrid.export.ts
// Чистая логика экспорта review findings в review-native табличный формат.
// Без React, без XLSX/jsPDF/docx импортов — только data transformation.
// Единственный canonical shaping layer для review export.
// =============================================================

import type { ReviewFinding, ReviewExportRow } from "./reviewGrid.types";

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
 * Это основной вход для review export buttons / export utils.
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
 * - это простой presentation-ready table model для файлового экспорта.
 */
export function buildReviewExportTableRows(
  rows: ReviewExportRow[],
): Array<Record<string, string>> {
  return rows.map((row) => ({
    "Document": row.documentName,
    "Doc Type": row.docType ?? "",
    "Folder": row.folderPath ?? "",

    "Segment Title": row.segmentTitle ?? "",
    "Segment Type": row.segmentType ?? "",
    "Segment Order": row.segmentOrder != null ? String(row.segmentOrder) : "",
    "Primary Segment": row.isPrimarySegment ? "Yes" : "No",

    "Check": row.checkName,
    "Origin": row.origin ?? "",

    "Result": row.result,
    "Severity": row.severity ?? "",
    "QC": row.qcStatus ?? "",
    "Confidence":
      typeof row.confidence === "number"
        ? `${Math.round(row.confidence * 100)}%`
        : "",

    "Snippet": row.snippet ?? "",
    "Page": row.page != null ? String(row.page) : "",
    "Clause UID": row.clauseUid ?? "",

    "Conditional": row.conditionalTriggered ? "Yes" : "No",
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


